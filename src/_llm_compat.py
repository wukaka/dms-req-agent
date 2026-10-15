"""Two workarounds for how AgentScope talks to DeepSeek, both observed as
hard 400s that killed a table agent mid-run (see logs/agent_events.jsonl).

Neither is a race, despite looking like one: each reproduces exactly when
its precondition holds, and the preconditions are rare enough that a table
can survive several passes before hitting one.

1. `ToolReplyAdjacencyFormatter` - the upstream formatter promotes image
   data inside a tool result into an extra `role: "user"` message emitted
   *right after* that tool message
   (agentscope/formatter/_openai_formatter.py, the `ToolResultBlock`
   branch). Harmless when the screenshot was the round's only tool call;
   when the model batched two calls and the screenshot was not the last,
   the promoted message lands between the two `tool` replies and breaks the
   provider's "an assistant message with tool_calls must be followed by
   tool messages responding to each tool_call_id" rule.

2. `ToolChoiceRelaxingModel` - on reaching `max_iters` with a structured
   output still outstanding, `Agent._next_action` forces
   `tool_choice=<tool name>` to make the agent submit
   (agentscope/agent/_agent.py, the `required and not satisfied` branch).
   DeepSeek's thinking mode rejects a forced single-tool choice outright.
"""

from __future__ import annotations

from typing import Any

from agentscope.formatter import OpenAIChatFormatter
from agentscope.model import OpenAIChatModel
from agentscope.tool import ToolChoice

#: `ToolChoice.mode` values that are plain strings rather than a tool name.
_LITERAL_MODES = frozenset({"auto", "none", "required"})


def regroup_tool_replies(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Move anything wedged between an assistant `tool_calls` message and
    its `tool` replies to just after the last of them.

    Order within each group is preserved, nothing is dropped, and a
    well-formed sequence comes back unchanged - so this stays correct for
    interleavings other than the promoted-image one that prompted it.
    """
    out: list[dict[str, Any]] = []
    i = 0
    while i < len(messages):
        message = messages[i]
        out.append(message)
        i += 1

        pending = {call["id"] for call in message.get("tool_calls") or ()}
        displaced: list[dict[str, Any]] = []
        while pending and i < len(messages):
            candidate = messages[i]
            if candidate.get("role") == "assistant":
                # A new turn started with replies still missing; leave the
                # malformed remainder alone rather than dragging it along.
                break
            if (
                candidate.get("role") == "tool"
                and candidate.get("tool_call_id") in pending
            ):
                pending.discard(candidate["tool_call_id"])
                out.append(candidate)
            else:
                displaced.append(candidate)
            i += 1
        out.extend(displaced)
    return out


class ToolReplyAdjacencyFormatter(OpenAIChatFormatter):
    """`OpenAIChatFormatter` with `regroup_tool_replies` applied on the way out."""

    async def format(self, msgs: list) -> list[dict[str, Any]]:
        return regroup_tool_replies(await super().format(msgs))


class ToolChoiceRelaxingModel(OpenAIChatModel):
    """`OpenAIChatModel` that downgrades a forced single-tool choice to `auto`.

    The agent keeps the accompanying "call this tool at once" hint and its
    `structured_output_grace_iters` rounds to act on it, so the deadline is
    still communicated - just as a strong request rather than a request
    parameter the provider refuses.
    """

    def _format_tools(
        self,
        tools: list[dict] | None,
        tool_choice: ToolChoice | None,
    ) -> tuple[list[dict] | None, str | dict | None]:
        if tool_choice is not None and tool_choice.mode not in _LITERAL_MODES:
            tool_choice = tool_choice.model_copy(update={"mode": "auto"})
        return super()._format_tools(tools, tool_choice)
