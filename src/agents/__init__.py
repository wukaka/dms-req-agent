"""AgentScope agent factories for DMS phase-1 (design §6-8).

Three roles, all built on `agentscope.agent.Agent` - AgentScope 2.0.8 has no
`ReActAgent` subclass; every agent is the base `Agent` class configured with
a system prompt, a toolkit and a `ReActConfig`. What differs per role is the
prompt, the tool surface, and (for the table agent) the two-phase call
protocol in `table_agent.run_table_agent()`.
"""

from __future__ import annotations

from ._permission import bypass_permission_state
from .discovery import DISCOVERY_TOOLS, build_discovery_agent
from .judge import ask_judge, build_judge_agent, check_consistency
from .table_agent import (
    SCREENSHOT_AGENT_TOOLS,
    TABLE_AGENT_TOOLS,
    build_table_agent,
    run_table_agent,
)

__all__ = [
    "DISCOVERY_TOOLS",
    "build_discovery_agent",
    "TABLE_AGENT_TOOLS",
    "SCREENSHOT_AGENT_TOOLS",
    "build_table_agent",
    "run_table_agent",
    "build_judge_agent",
    "ask_judge",
    "check_consistency",
    "bypass_permission_state",
]
