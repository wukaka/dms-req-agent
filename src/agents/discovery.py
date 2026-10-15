"""Discovery agent: candidate-entry triage for all 6 tables (design §5).

Discovery only does 轻点确认 (design §5.2): capture the XHR a click triggers,
read DOM headers, note the response shape. No field mapping, no screenshots,
no form-filling - `DISCOVERY_TOOLS` makes that a structural property of the
MCP tool surface it is given, not just a prompt instruction (same pattern as
`mcp_client.NAVIGATION_TOOLS`).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from agentscope.agent import Agent, ReActConfig
from agentscope.mcp import MCPClient
from agentscope.message import Msg, TextBlock
from agentscope.middleware import MiddlewareBase
from agentscope.model import ChatModelBase
from agentscope.tool import Toolkit

from ..models import TABLES, DiscoveryResult
from ._events import EventSink, structured
from ._permission import bypass_permission_state

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

DISCOVERY_TOOLS: tuple[str, ...] = (
    "list_pages",
    "select_page",
    "list_frames",
    "select_frame",
    "list_network_requests",
    "get_network_request",
    "evaluate_script",
    "get_dom_structure",
    "query_dom",
    "find_clickable_elements",
    "wait_for_element",
    "click_element",
    "get_storage",
    "list_console_messages",
    "get_console_message",
)


def system_prompt() -> str:
    """Discovery's system prompt: prompts/discovery.md verbatim."""
    return (_PROMPTS_DIR / "discovery.md").read_text(encoding="utf-8")


def build_discovery_agent(
    model: ChatModelBase,
    jsreverser: MCPClient,
    middlewares: Optional[list[MiddlewareBase]] = None,
) -> Agent:
    """Construct the Discovery agent.

    `jsreverser` must already be connected and built with
    `mcp_client.jsreverser_client(enable_tools=DISCOVERY_TOOLS)` - connection
    lifecycle and tool filtering are the orchestrator's job (design §9.2),
    not this factory's; `Toolkit(mcps=...)` requires a stateful client to
    already be connected or it raises. `middlewares` is where the
    orchestrator wires in `browser_queue.BrowserQueueMiddleware`.
    """
    return Agent(
        name="discovery",
        system_prompt=system_prompt(),
        model=model,
        toolkit=Toolkit(mcps=[jsreverser]),
        react_config=ReActConfig(max_iters=80),
        middlewares=middlewares,
        state=bypass_permission_state(),
    )


def _task_msg(blackboard: str = "") -> Msg:
    """Discovery's kickoff message. Unlike a table agent it has no `entry` to
    receive - finding entries for all 6 tables is its whole job - so this is
    just the run trigger plus any carried-over site experience."""
    parts = [
        "开始阶段 1 Discovery：抓全量菜单树，按白名单逐个候选入口轻点确认，"
        "为下列 6 张表各自给出五态判定与 entry，定锚点口径，记同源提示。",
        f"6 张表契约顺序：{', '.join(TABLES)}。",
    ]
    if blackboard:
        parts += ["", "## blackboard.md（既有站点经验）", blackboard]
    return Msg(
        name="orchestrator",
        role="user",
        content=[TextBlock(type="text", text="\n".join(parts))],
    )


async def run_discovery(
    agent: Agent,
    blackboard: str = "",
    on_event: Optional[EventSink] = None,
) -> DiscoveryResult:
    """Run Discovery to completion and return its structured verdict set."""
    return await structured(agent, _task_msg(blackboard), DiscoveryResult, on_event)
