"""compile_documents() just needs to hand manifest + tables/*.md to the
agent and unwrap ComposedDocs - pinned with a fake agent, same pattern as
test_table_agent.py / test_discovery.py."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from agentscope.message import Msg, TextBlock

from dms_survey.agents.judge import compile_documents, make_ask_judge_tool


class FakeAgent:
    def __init__(self, structured_output):
        self.name = "judge"
        self._output = structured_output
        self.calls = 0
        self.last_msg = None

    async def reply_stream(self, msg, structured_schema=None, yield_final_msg=False):
        self.calls += 1
        self.last_msg = msg
        final = Msg(name=self.name, role="assistant", content=[TextBlock(type="text", text="done")])
        final.structured_output = self._output
        yield final


async def test_compile_documents_returns_parsed_result():
    agent = FakeAgent({"main_doc": "# 主文档", "tech_notes": "# 技术笔记"})
    manifest = {"system": "emdlz", "tables": []}

    docs = await compile_documents(
        agent,
        platform="emdlz",
        manifest=manifest,
        tables_markdown={"dms_order_details_info": "字段表..."},
    )

    assert agent.calls == 1
    assert docs.main_doc == "# 主文档"
    assert docs.tech_notes == "# 技术笔记"
    sent_text = agent.last_msg.content[0].text
    assert "emdlz" in sent_text
    assert "dms_order_details_info" in sent_text


async def test_compile_documents_raises_without_structured_output():
    agent = FakeAgent(None)
    with pytest.raises(RuntimeError):
        await compile_documents(agent, platform="x", manifest={}, tables_markdown={})


class FakeJudgeAgent:
    """Only `.reply()` is used by `ask_judge()`'s model-fallback path."""

    def __init__(self):
        self.calls = 0

    async def reply(self, msg, structured_schema=None):
        self.calls += 1
        from agentscope.message import TextBlock

        return SimpleNamespace(content=[TextBlock(type="text", text="model 推断：无关联证据")])


async def test_ask_judge_tool_answers_from_evidence_index_without_model_call():
    judge_agent = FakeJudgeAgent()
    evidence_index = {
        "dms_order_details_info": {
            "fields": [{"path": "main.orderNo", "type": "string", "samples": ["A1"], "mapped_to": "order_no"}],
        },
    }
    tool = make_ask_judge_tool(judge_agent, evidence_index, from_table="dms_bill_details_info")

    chunk = await tool.call(about="order_no", need="编码格式与样例", scope=["dms_order_details_info"])

    assert "main.orderNo" in chunk.content[0].text
    assert judge_agent.calls == 0


async def test_ask_judge_tool_enforces_budget():
    judge_agent = FakeJudgeAgent()
    tool = make_ask_judge_tool(judge_agent, {}, from_table="dms_bill_details_info", budget=2)

    first = await tool.call(about="order_no", need="x")
    second = await tool.call(about="order_no", need="x")
    third = await tool.call(about="order_no", need="x")

    assert judge_agent.calls == 2
    assert "预算已用尽" in third.content[0].text
