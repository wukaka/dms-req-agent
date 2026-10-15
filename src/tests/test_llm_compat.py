from __future__ import annotations

import pytest
from agentscope.credential import OpenAICredential
from agentscope.message import DataBlock, Msg, TextBlock, ToolCallBlock, ToolResultBlock, URLSource
from agentscope.tool import ToolChoice

from src._llm_compat import (
    ToolChoiceRelaxingModel,
    ToolReplyAdjacencyFormatter,
    regroup_tool_replies,
)

_IMAGE = DataBlock(
    type="data",
    source=URLSource(type="url", url="https://example.invalid/shot.png", media_type="image/png"),
)


def _call(call_id: str, name: str) -> ToolCallBlock:
    return ToolCallBlock(type="tool_call", id=call_id, name=name, input="{}")


def _result(call_id: str, name: str, *, image: bool = False) -> ToolResultBlock:
    output: list = [TextBlock(type="text", text="ok")]
    if image:
        output.append(_IMAGE)
    return ToolResultBlock(type="tool_result", id=call_id, name=name, output=output)


def _shape(messages: list[dict]) -> list[str]:
    return [m.get("tool_call_id") or m["role"] for m in messages]


def _tool_calls_are_answered(messages: list[dict]) -> bool:
    """The provider's rule: every assistant `tool_calls` message must be
    followed by one `tool` message per id, with nothing in between."""
    for i, message in enumerate(messages):
        ids = [call["id"] for call in message.get("tool_calls") or ()]
        replies = messages[i + 1 : i + 1 + len(ids)]
        if [r.get("tool_call_id") for r in replies] != ids:
            return False
    return True


@pytest.mark.asyncio
async def test_screenshot_beside_a_parallel_call_keeps_tool_replies_adjacent():
    """The exact shape that 400'd twice in the 亿滋食品 run: the model batched
    two tool calls and the *first* returned a screenshot, so the formatter's
    promoted image message landed between the two `tool` replies."""
    msg = Msg(
        name="dms_bill_details_info",
        role="assistant",
        content=[
            _call("a", "take_screenshot"),
            _call("b", "query_dom"),
            _result("a", "take_screenshot", image=True),
            _result("b", "query_dom"),
        ],
    )

    formatted = await ToolReplyAdjacencyFormatter().format([msg])

    assert _shape(formatted) == ["assistant", "a", "b", "user"]
    assert _tool_calls_are_answered(formatted)


@pytest.mark.asyncio
async def test_lone_screenshot_is_left_alone():
    """The control case: a screenshot that is the round's only tool call
    already formats legally and must not be reshuffled."""
    msg = Msg(
        name="dms_bill_details_info",
        role="assistant",
        content=[_call("a", "take_screenshot"), _result("a", "take_screenshot", image=True)],
    )

    formatted = await ToolReplyAdjacencyFormatter().format([msg])

    assert _shape(formatted) == ["assistant", "a", "user"]
    assert _tool_calls_are_answered(formatted)


def test_regroup_preserves_order_of_displaced_messages():
    messages = [
        {"role": "assistant", "tool_calls": [{"id": "a"}, {"id": "b"}]},
        {"role": "tool", "tool_call_id": "a"},
        {"role": "user", "content": "first"},
        {"role": "user", "content": "second"},
        {"role": "tool", "tool_call_id": "b"},
        {"role": "user", "content": "after"},
    ]

    regrouped = regroup_tool_replies(messages)

    assert _shape(regrouped) == ["assistant", "a", "b", "user", "user", "user"]
    assert [m.get("content") for m in regrouped[3:]] == ["first", "second", "after"]


def test_regroup_leaves_a_well_formed_conversation_untouched():
    messages = [
        {"role": "user", "content": "go"},
        {"role": "assistant", "tool_calls": [{"id": "a"}, {"id": "b"}]},
        {"role": "tool", "tool_call_id": "a"},
        {"role": "tool", "tool_call_id": "b"},
        {"role": "user", "content": "hint"},
        {"role": "assistant", "tool_calls": [{"id": "c"}]},
        {"role": "tool", "tool_call_id": "c"},
    ]

    assert regroup_tool_replies(messages) == messages


def test_regroup_does_not_drag_a_new_turn_into_a_missing_reply():
    """A tool call that never got a reply is already broken; don't make it
    worse by hoisting the following turn above the replies that do exist."""
    messages = [
        {"role": "assistant", "tool_calls": [{"id": "a"}, {"id": "b"}]},
        {"role": "tool", "tool_call_id": "a"},
        {"role": "assistant", "content": "next turn"},
        {"role": "user", "content": "later"},
    ]

    assert regroup_tool_replies(messages) == messages


def _model() -> ToolChoiceRelaxingModel:
    return ToolChoiceRelaxingModel(
        credential=OpenAICredential(api_key="test-key"),
        model="deepseek-flash",
    )


def _tools() -> list[dict]:
    return [
        {"type": "function", "function": {"name": "generate_structured_output", "parameters": {}}},
        {"type": "function", "function": {"name": "query_dom", "parameters": {}}},
    ]


@pytest.mark.parametrize("mode", ["auto", "none", "required"])
def test_literal_tool_choice_modes_pass_through(mode: str):
    _, formatted = _model()._format_tools(_tools(), ToolChoice(mode=mode))
    assert formatted == mode


def test_forced_single_tool_choice_is_downgraded_to_auto():
    """DeepSeek's thinking mode 400s on a forced tool name, which is what
    AgentScope sends once an agent hits `max_iters` owing a structured
    output. Downgrading keeps the call legal; the agent still gets the hint."""
    _, formatted = _model()._format_tools(
        _tools(), ToolChoice(mode="generate_structured_output")
    )
    assert formatted == "auto"
