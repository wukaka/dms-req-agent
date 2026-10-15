"""run_discovery() just needs to drive the agent once with the
DiscoveryResult schema and unwrap structured_output - these tests pin that
contract with a fake agent, same pattern as test_table_agent.py."""

from __future__ import annotations

import pytest
from agentscope.message import Msg, TextBlock

from src.agents.discovery import run_discovery
from src.models import Existence


class FakeAgent:
    def __init__(self, structured_output):
        self.name = "discovery"
        self._output = structured_output
        self.calls = 0

    async def reply_stream(self, msg, structured_schema=None, yield_final_msg=False):
        self.calls += 1
        final = Msg(name=self.name, role="assistant", content=[TextBlock(type="text", text="done")])
        final.structured_output = self._output
        yield final


async def test_run_discovery_returns_parsed_result():
    agent = FakeAgent({
        "discovery": {"menu_tree_ref": "menu_map.md", "verified_at": "2026-09-17"},
        "tables": [
            {"table": "dms_order_details_info", "existence": "exists", "rationale": "唯一载体"},
        ],
        "menu_tree_markdown": "# 菜单树",
    })

    result = await run_discovery(agent)

    assert agent.calls == 1
    assert result.discovery.verified_at == "2026-09-17"
    assert result.tables[0].existence is Existence.EXISTS


async def test_run_discovery_raises_without_structured_output():
    agent = FakeAgent(None)
    with pytest.raises(RuntimeError):
        await run_discovery(agent)
