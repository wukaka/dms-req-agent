"""The two-phase gate is the structural claim design §6.1 rests on: a table
agent must be able to finish with zero fields submitted. These tests exercise
`run_table_agent()`'s call count against a fake agent, so the gate is proven
by code rather than by trusting the prompt.
"""

from __future__ import annotations

import base64
from pathlib import Path

from agentscope.message import Msg, TextBlock

from dms_survey.agents.table_agent import (
    READ_FILE_CHAR_LIMIT,
    existing_artifacts,
    make_read_file_tool,
    make_write_file_tool,
    resume_digest,
    run_table_agent,
)
from dms_survey.models import Existence

TABLE = "dms_order_details_info"


class FakeAgent:
    """Stands in for `agentscope.agent.Agent`: only `.reply_stream()` is used
    by `run_table_agent()`, so only that needs faking."""

    def __init__(self, structured_outputs):
        self.name = "dms_contract_sign_info"
        self._queue = list(structured_outputs)
        self.calls = 0
        self.seen = []

    async def reply_stream(self, msg, structured_schema=None, yield_final_msg=False):
        self.calls += 1
        self.seen.append(msg)
        final = Msg(name=self.name, role="assistant", content=[TextBlock(type="text", text="done")])
        final.structured_output = self._queue.pop(0)
        yield final


async def test_non_producing_verdict_never_calls_field_mapping():
    agent = FakeAgent([
        {"table": "dms_contract_sign_info", "existence": "absent", "rationale": "全站未发现合同相关菜单"},
    ])

    verdict, evidence = await run_table_agent(agent, entry={}, anchors={})

    assert verdict.existence is Existence.ABSENT
    assert evidence is None
    assert agent.calls == 1


async def test_producing_verdict_proceeds_to_field_mapping():
    agent = FakeAgent([
        {"table": "dms_order_details_info", "existence": "exists", "rationale": "唯一载体，粒度吻合"},
        {"apis": [], "columns": ["订单编号"], "fields": []},
    ])

    verdict, evidence = await run_table_agent(agent, entry={}, anchors={})

    assert verdict.existence is Existence.EXISTS
    assert evidence is not None
    assert evidence.columns == ["订单编号"]
    assert agent.calls == 2


async def test_task_message_never_mentions_screenshots():
    """The business agent does not screenshot or annotate - that is phase 3.

    An earlier version injected the absolute images directory (and
    `take_screenshot`/`annotate_screenshot` usage) into this very message
    while `common_rules.md` told the agent not to screenshot. One of the two
    had to go; the prompt won, so the task message must stay clean.
    """
    agent = FakeAgent([
        {"table": "dms_contract_sign_info", "existence": "absent", "rationale": "无入口"},
    ])

    await run_table_agent(agent, entry={}, anchors={})

    text = agent.seen[0].content[0].text
    assert "截图目录" not in text
    assert "take_screenshot" not in text
    assert "annotate_screenshot" not in text


async def test_field_mapping_prompt_sends_screenshots_to_phase_three():
    agent = FakeAgent([
        {"table": "dms_order_details_info", "existence": "exists", "rationale": "唯一载体"},
        {"apis": [], "columns": [], "fields": []},
    ])

    await run_table_agent(agent, entry={}, anchors={})

    phase_two = agent.seen[1].content[0].text
    assert "截图标注" not in phase_two
    assert "阶段三" in phase_two
    assert "take_screenshot" not in phase_two


def test_business_tools_exclude_screenshot_and_phase_three_keeps_it():
    from dms_survey.agents.table_agent import SCREENSHOT_AGENT_TOOLS, TABLE_AGENT_TOOLS

    assert "take_screenshot" not in TABLE_AGENT_TOOLS
    assert "take_screenshot" in SCREENSHOT_AGENT_TOOLS
    # Phase 3 is a strict superset of the business surface, not a replacement.
    assert set(TABLE_AGENT_TOOLS) <= set(SCREENSHOT_AGENT_TOOLS)


async def test_write_file_tool_writes_under_tables(tmp_path: Path):
    tool = make_write_file_tool(tmp_path, TABLE)

    chunk = await tool.call(relative_path=f"tables/{TABLE}.md", content="# 订单明细")

    written = tmp_path / "tables" / f"{TABLE}.md"
    assert written.read_text(encoding="utf-8") == "# 订单明细"
    assert "已写入" in chunk.content[0].text


async def test_write_file_tool_writes_under_files(tmp_path: Path):
    tool = make_write_file_tool(tmp_path, TABLE)

    await tool.call(relative_path=f"files/{TABLE}_列表页_0.html", content="<html></html>")

    written = tmp_path / "files" / f"{TABLE}_列表页_0.html"
    assert written.read_text(encoding="utf-8") == "<html></html>"


async def test_write_file_tool_base64_roundtrip(tmp_path: Path):
    tool = make_write_file_tool(tmp_path, TABLE)
    raw = b"PK\x03\x04fake-xlsx-bytes"
    encoded = base64.b64encode(raw).decode("ascii")

    await tool.call(
        relative_path=f"files/{TABLE}_导出.xlsx", content=encoded, encoding="base64"
    )

    written = tmp_path / "files" / f"{TABLE}_导出.xlsx"
    assert written.read_bytes() == raw


async def test_write_file_tool_rejects_path_outside_allowed_roots(tmp_path: Path):
    tool = make_write_file_tool(tmp_path, TABLE)

    chunk = await tool.call(relative_path="menu_map.md", content="不该写这")

    assert "不在允许范围内" in chunk.content[0].text
    assert not (tmp_path / "menu_map.md").exists()


async def test_write_file_tool_rejects_path_traversal(tmp_path: Path):
    tool = make_write_file_tool(tmp_path, TABLE)

    chunk = await tool.call(relative_path="tables/../../escaped.md", content="不该写这")

    assert "不在允许范围内" in chunk.content[0].text
    assert not (tmp_path.parent / "escaped.md").exists()


async def test_write_file_tool_rejects_another_tables_document(tmp_path: Path):
    """Ownership is what lets `existing_artifacts()` attribute leftovers
    without a side ledger, so writing outside your own name has to fail."""
    tool = make_write_file_tool(tmp_path, TABLE)

    chunk = await tool.call(relative_path="tables/dms_bill_details_info.md", content="x")

    assert "不是本表的文档" in chunk.content[0].text
    assert not (tmp_path / "tables" / "dms_bill_details_info.md").exists()


async def test_write_file_tool_rejects_unprefixed_archive(tmp_path: Path):
    tool = make_write_file_tool(tmp_path, TABLE)

    chunk = await tool.call(relative_path="files/订单明细_0.html", content="x")

    assert "不是本表的存档" in chunk.content[0].text
    assert not (tmp_path / "files" / "订单明细_0.html").exists()


async def test_write_file_tool_rejects_unsupported_encoding(tmp_path: Path):
    tool = make_write_file_tool(tmp_path, TABLE)

    chunk = await tool.call(relative_path=f"tables/{TABLE}.md", content="x", encoding="utf-16")

    assert "不支持的 encoding" in chunk.content[0].text
    assert not (tmp_path / "tables" / f"{TABLE}.md").exists()


async def test_read_file_tool_round_trips_what_write_file_wrote(tmp_path: Path):
    write = make_write_file_tool(tmp_path, TABLE)
    read = make_read_file_tool(tmp_path, TABLE)

    await write.call(relative_path=f"files/{TABLE}_列表接口_0.json", content='{"a": 1}')
    chunk = await read.call(relative_path=f"files/{TABLE}_列表接口_0.json")

    assert chunk.content[0].text == '{"a": 1}'


async def test_read_file_tool_base64_returns_encoded_bytes(tmp_path: Path):
    raw = b"PK\x03\x04fake-xlsx-bytes"
    (tmp_path / "files").mkdir()
    (tmp_path / "files" / f"{TABLE}_导出.xlsx").write_bytes(raw)
    read = make_read_file_tool(tmp_path, TABLE)

    chunk = await read.call(relative_path=f"files/{TABLE}_导出.xlsx", encoding="base64")

    assert base64.b64decode(chunk.content[0].text) == raw


async def test_read_file_tool_reports_a_missing_file_instead_of_raising(tmp_path: Path):
    read = make_read_file_tool(tmp_path, TABLE)

    chunk = await read.call(relative_path=f"files/{TABLE}_没写过.json")

    assert "不存在" in chunk.content[0].text


async def test_read_file_tool_refuses_another_tables_archive(tmp_path: Path):
    (tmp_path / "files").mkdir()
    (tmp_path / "files" / "dms_bill_details_info_列表页_0.html").write_text("别人的", encoding="utf-8")
    read = make_read_file_tool(tmp_path, TABLE)

    chunk = await read.call(relative_path="files/dms_bill_details_info_列表页_0.html")

    assert "不是本表的存档" in chunk.content[0].text
    assert "别人的" not in chunk.content[0].text


async def test_read_file_tool_truncates_an_oversized_archive(tmp_path: Path):
    """A full list-page HTML dump can be megabytes; returning it whole would
    blow the context the resume digest exists to protect."""
    (tmp_path / "files").mkdir()
    (tmp_path / "files" / f"{TABLE}_列表页_0.html").write_text(
        "x" * (READ_FILE_CHAR_LIMIT + 500), encoding="utf-8"
    )
    read = make_read_file_tool(tmp_path, TABLE)

    chunk = await read.call(relative_path=f"files/{TABLE}_列表页_0.html")

    assert "已截断" in chunk.content[0].text
    assert chunk.content[0].text.count("x") == READ_FILE_CHAR_LIMIT


def test_existing_artifacts_only_claims_this_tables_names(tmp_path: Path):
    (tmp_path / "tables").mkdir()
    (tmp_path / "files").mkdir()
    (tmp_path / "tables" / f"{TABLE}.md").write_text("mine", encoding="utf-8")
    (tmp_path / "tables" / "dms_bill_details_info.md").write_text("theirs", encoding="utf-8")
    (tmp_path / "files" / f"{TABLE}_列表页_0.html").write_text("mine", encoding="utf-8")
    (tmp_path / "files" / "dms_bill_details_info_列表页_0.html").write_text("theirs", encoding="utf-8")

    found = [p.name for p in existing_artifacts(tmp_path, TABLE)]

    assert found == [f"{TABLE}.md", f"{TABLE}_列表页_0.html"]


def test_resume_digest_is_empty_on_a_first_run(tmp_path: Path):
    assert resume_digest(tmp_path, TABLE) == ""


def test_resume_digest_lists_leftovers_with_sizes(tmp_path: Path):
    (tmp_path / "files").mkdir()
    (tmp_path / "files" / f"{TABLE}_列表页_0.html").write_text("<html></html>", encoding="utf-8")

    digest = resume_digest(tmp_path, TABLE)

    assert "已有产物" in digest
    assert f"files/{TABLE}_列表页_0.html" in digest
    assert "13 字节" in digest
    assert "read_file" in digest
