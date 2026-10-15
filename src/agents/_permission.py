"""Shared `AgentState` factory for `discovery`/table agents.

Split out from `__init__.py` to avoid a circular import: `__init__.py`
imports from `discovery.py`/`table_agent.py`, and those two need this
factory at `Agent()` construction time.
"""

from __future__ import annotations

from agentscope.permission import PermissionContext, PermissionMode
from agentscope.state import AgentState


def bypass_permission_state() -> AgentState:
    """`AgentState` for `discovery`/table agents: this pipeline is fully
    headless (design §9.2/CLAUDE.md 人工前置: no step-by-step confirmation),
    but `Agent()`'s default state uses `PermissionMode.DEFAULT`, which asks
    for human approval before any non-read-only tool call - MCP tools like
    `click_element`/`evaluate_script`/`select_frame`/`type_text` (JSReverser
    marks them `readOnlyHint: false`) and this package's own `write_file`/
    `ask_judge_tool` (plain `FunctionTool`s with no `permission=` override,
    same default). With nothing ever answering that ASK, `agent.reply()`
    exits early with `finished_reason=None` instead of raising, which reads
    as an unrelated "no structured_output" crash three layers up.

    `PermissionMode.BYPASS` is safe here specifically because the tool
    surface it can reach is already whitelisted upstream, before permission
    checking ever runs: `mcp_client.jsreverser_client()` passes
    `enable_tools=DISCOVERY_TOOLS`/`TABLE_AGENT_TOOLS` and hard-disables
    `NAVIGATION_TOOLS`. BYPASS only ever has to decide on tools this
    codebase already chose to expose - not "does the agent do anything at
    all"."""
    return AgentState(permission_context=PermissionContext(mode=PermissionMode.BYPASS))
