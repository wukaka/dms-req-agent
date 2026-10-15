"""Unit test for agents/__init__.py's `bypass_permission_state()` - see the
2026-09-18 investigation into `discovery: no structured_output
(finished_reason=None)`: `Agent()`'s default `AgentState` uses
`PermissionMode.DEFAULT`, under which every non-read-only tool call (MCP or
a plain `FunctionTool` with no `permission=` override, e.g. this package's
own `write_file`/`ask_judge_tool`) asks for human approval that never comes
in this headless pipeline - the reply silently exits early with
`finished_reason=None` instead of raising. `bypass_permission_state()` gives
`build_discovery_agent`/`build_table_agent` a state that skips that gate."""

from __future__ import annotations

from agentscope.permission import PermissionMode

from dms_survey.agents import bypass_permission_state


def test_bypass_permission_state_uses_bypass_mode():
    state = bypass_permission_state()

    assert state.permission_context.mode == PermissionMode.BYPASS
