"""Unit tests for orchestrator.py's pure decision functions - the part the
progress doc's handoff note says should be tested without any real MCP/LLM,
following test_table_agent.py's plain-object style."""

from __future__ import annotations

import asyncio
from pathlib import Path

from src import orchestrator as orch
from src.models import (
    DiscoveryBlock,
    DiscoveryResult,
    EntryInfo,
    EvidenceField,
    EvidenceTable,
    ScreenshotResult,
    TableTriage,
    TableVerdict,
)
from src.store import Store


def test_discovery_already_done_false_when_missing():
    assert orch.discovery_already_done({}) is False


def test_discovery_already_done_true_when_verified_at_set():
    manifest = {"discovery": {"verified_at": "2026-09-17"}}
    assert orch.discovery_already_done(manifest) is True


def test_table_is_settled_unset_existence_is_not_settled():
    assert orch.table_is_settled({"table": "dms_basic_info"}, {}) is False


def test_table_is_settled_non_producing_is_settled_immediately():
    entry = {"table": "dms_basic_info", "existence": "absent"}
    assert orch.table_is_settled(entry, {}) is True


def test_table_is_settled_producing_without_evidence_is_not_settled():
    entry = {"table": "dms_order_details_info", "existence": "exists"}
    assert orch.table_is_settled(entry, {}) is False


def test_table_is_settled_producing_with_evidence_is_settled():
    entry = {"table": "dms_order_details_info", "existence": "exists"}
    evidence_index = {"dms_order_details_info": {"fields": [{"path": "a", "mapped_to": "order_no"}]}}
    assert orch.table_is_settled(entry, evidence_index) is True


def test_tables_to_launch_filters_settled_and_non_producing():
    manifest_tables = [
        {"table": "dms_basic_info", "existence": "absent"},
        {"table": "dms_order_details_info", "existence": "exists"},
        {"table": "dms_bill_details_info", "existence": "partial"},
        {"table": "dms_certified_info", "existence": "pending_human"},
    ]
    evidence_index = {"dms_bill_details_info": {"fields": [{"path": "a", "mapped_to": "x"}]}}

    launch = orch.tables_to_launch(manifest_tables, evidence_index)

    assert [t["table"] for t in launch] == ["dms_order_details_info"]


def test_pending_human_entries_and_questions():
    manifest_tables = [
        {"table": "dms_contract_sign_info", "existence": "pending_human", "entry": {"menu_path": ""}},
        {"table": "dms_order_details_info", "existence": "exists"},
    ]

    pending = orch.pending_human_entries(manifest_tables)
    assert [t["table"] for t in pending] == ["dms_contract_sign_info"]

    questions = orch.pending_human_questions(manifest_tables)
    assert len(questions) == 1
    assert "dms_contract_sign_info" in questions[0]


_MAPPED = {"dms_order_details_info": {"fields": [{"path": "a", "mapped_to": "order_no"}]}}


def test_awaiting_field_confirmation_waits_for_the_human_flag():
    """Field mapping done and nothing disputed is not enough - screenshots
    wait for someone to actually read the field table and say so."""
    manifest_tables = [{"table": "dms_order_details_info", "existence": "exists"}]

    awaiting = orch.tables_awaiting_field_confirmation(manifest_tables, _MAPPED)
    ready = orch.tables_ready_for_screenshot(manifest_tables, _MAPPED)

    assert [t["table"] for t in awaiting] == ["dms_order_details_info"]
    assert ready == []


def test_confirmed_table_moves_to_the_screenshot_round():
    manifest_tables = [
        {"table": "dms_order_details_info", "existence": "exists", "fields_confirmed": True}
    ]

    assert orch.tables_awaiting_field_confirmation(manifest_tables, _MAPPED) == []
    assert [t["table"] for t in orch.tables_ready_for_screenshot(manifest_tables, _MAPPED)] == [
        "dms_order_details_info"
    ]


def test_open_deferred_questions_block_the_confirmation_checkpoint():
    """An unresolved question means the mapping itself is still in play, so
    the table is not even offered up for confirmation yet."""
    manifest_tables = [
        {
            "table": "dms_order_details_info",
            "existence": "exists",
            "fields_confirmed": True,
            "deferred_questions": ["这个字段该取哪个来源？"],
        }
    ]

    assert orch.tables_awaiting_field_confirmation(manifest_tables, _MAPPED) == []
    assert orch.tables_ready_for_screenshot(manifest_tables, _MAPPED) == []


def test_tables_finished_before_this_gate_existed_are_left_alone():
    """不追溯: a table carrying screenshots_done never re-enters phase 3, with
    or without the new confirmation flag."""
    manifest_tables = [
        {"table": "dms_order_details_info", "existence": "exists", "screenshots_done": True}
    ]

    assert orch.tables_awaiting_field_confirmation(manifest_tables, _MAPPED) == []
    assert orch.tables_ready_for_screenshot(manifest_tables, _MAPPED) == []


def test_non_producing_and_unmapped_tables_never_reach_the_screenshot_gate():
    manifest_tables = [
        {"table": "dms_contract_sign_info", "existence": "absent", "fields_confirmed": True},
        {"table": "dms_bill_monthly_info", "existence": "granularity_mismatch"},
        # producing, confirmed, but field mapping has not run yet
        {"table": "dms_basic_info", "existence": "partial", "fields_confirmed": True},
    ]

    assert orch.tables_awaiting_field_confirmation(manifest_tables, _MAPPED) == []
    assert orch.tables_ready_for_screenshot(manifest_tables, _MAPPED) == []


def test_field_confirmation_questions_name_the_flag_to_set():
    entries = [{"table": "dms_order_details_info"}]

    questions = orch.field_confirmation_questions(entries)

    assert len(questions) == 1
    assert "dms_order_details_info" in questions[0]
    assert "fields_confirmed" in questions[0]


def test_persist_screenshot_result_closes_the_round(tmp_path: Path):
    store = Store(tmp_path)
    manifest = store.ensure_tables(store.load_manifest())
    run = orch.ScreenshotRunResult(
        table="dms_order_details_info",
        result=ScreenshotResult(
            annotated_images=["images/dms_order_details_info_列表页_0-annotated.jpg"],
            notes="第 7 列已改名",
        ),
    )

    orch.persist_screenshot_result(store, manifest, run)

    entry = next(t for t in store.load_manifest()["tables"] if t["table"] == "dms_order_details_info")
    assert entry["screenshots_done"] is True
    assert entry["annotated_images"] == ["images/dms_order_details_info_列表页_0-annotated.jpg"]
    assert entry["screenshot_notes"] == "第 7 列已改名"


def test_persist_screenshot_result_ignores_a_failed_round(tmp_path: Path):
    """A crashed screenshot round must not mark the table as done - the next
    run has to be able to pick it back up."""
    store = Store(tmp_path)
    manifest = store.ensure_tables(store.load_manifest())
    run = orch.ScreenshotRunResult(table="dms_order_details_info", error=RuntimeError("timeout"))

    orch.persist_screenshot_result(store, manifest, run)

    entry = next(t for t in manifest["tables"] if t["table"] == "dms_order_details_info")
    assert "screenshots_done" not in entry


def test_collect_deferred_questions_reads_from_manifest_entries():
    """§8.3 deferred blockers: read from the manifest, not a live batch of
    results, so a table that is not relaunched on a resumed run does not
    silently lose its unresolved question."""
    manifest_tables = [
        {
            "table": "dms_basic_info",
            "existence": "partial",
            "deferred_questions": ["本平台是否存在「经销商基础资料」专属页面？"],
        },
        {"table": "dms_order_details_info", "existence": "exists", "deferred_questions": []},
        {"table": "dms_bill_details_info", "existence": "partial"},
    ]

    questions = orch.collect_deferred_questions(manifest_tables)

    assert len(questions) == 1
    assert questions[0] == "dms_basic_info：本平台是否存在「经销商基础资料」专属页面？"


def test_collect_deferred_questions_empty_when_none_pending():
    manifest_tables = [
        {"table": "dms_basic_info", "existence": "partial", "deferred_questions": []},
        {"table": "dms_order_details_info", "existence": "exists"},
    ]

    assert orch.collect_deferred_questions(manifest_tables) == []


def test_collect_deferred_questions_reports_every_table_with_one():
    manifest_tables = [
        {"table": "dms_basic_info", "deferred_questions": ["Q1"]},
        {"table": "dms_bill_details_info", "deferred_questions": ["Q2", "Q3"]},
    ]

    questions = orch.collect_deferred_questions(manifest_tables)

    assert questions == [
        "dms_basic_info：Q1",
        "dms_bill_details_info：Q2",
        "dms_bill_details_info：Q3",
    ]


def test_persist_discovery_writes_manifest_and_menu_map(tmp_path: Path):
    store = Store(tmp_path)
    manifest = store.ensure_tables(store.load_manifest())
    result = DiscoveryResult(
        discovery=DiscoveryBlock(verified_at="2026-09-17"),
        tables=[
            TableTriage(
                table="dms_order_details_info",
                existence="exists",
                entry=EntryInfo(menu_path="订单管理 > 我的订单", route="/order"),
                rationale="唯一载体",
            ),
        ],
        menu_tree_markdown="# 菜单树\n- 订单管理",
    )

    manifest = orch.persist_discovery(store, manifest, result)

    assert manifest["discovery"]["verified_at"] == "2026-09-17"
    reloaded = store.load_manifest()
    assert reloaded["discovery"]["verified_at"] == "2026-09-17"
    entry = next(t for t in reloaded["tables"] if t["table"] == "dms_order_details_info")
    assert entry["existence"] == "exists"
    assert entry["entry"]["route"] == "/order"
    assert (tmp_path / "menu_map.md").read_text(encoding="utf-8") == "# 菜单树\n- 订单管理"


def test_read_blackboard_missing_file_returns_empty(tmp_path: Path):
    store = Store(tmp_path)
    assert orch.read_blackboard(store) == ""


def test_read_blackboard_reads_existing_file(tmp_path: Path):
    store = Store(tmp_path)
    store.append_blackboard("学到一条站点经验")
    assert "学到一条站点经验" in orch.read_blackboard(store)


def test_read_tables_markdown_missing_dir_returns_empty(tmp_path: Path):
    assert orch.read_tables_markdown(tmp_path) == {}


def test_read_tables_markdown_reads_all_files(tmp_path: Path):
    tables_dir = tmp_path / "tables"
    tables_dir.mkdir()
    (tables_dir / "dms_order_details_info.md").write_text("# 订单明细", encoding="utf-8")

    result = orch.read_tables_markdown(tmp_path)

    assert result == {"dms_order_details_info": "# 订单明细"}


def test_browser_queue_tool_names_qualifies_with_mcp_prefix():
    result = orch.browser_queue_tool_names(["click_element", "list_pages"])

    assert result == {"mcp__jsreverser__click_element", "mcp__jsreverser__list_pages"}


# ---------------------------------------------------------------------------
# Per-table persistence
#
# run_platform persists each TableRunResult the moment it arrives, so a failure
# or a cancellation costs exactly the table it happened to. Collecting every
# result first and writing afterwards would discard the successful siblings of a
# failure: six tables, one failure, and four tables' work thrown away.
# ---------------------------------------------------------------------------


def _verdict(table: str, existence: str = "exists") -> TableVerdict:
    return TableVerdict(table=table, existence=existence, rationale="唯一载体")


def _evidence() -> EvidenceTable:
    return EvidenceTable(
        columns=["订单编号"],
        fields=[EvidenceField(path="main.orderNo", mapped_to="order_no")],
    )


def test_persist_table_result_writes_verdict_and_evidence_to_disk(tmp_path: Path):
    store = Store(tmp_path)
    manifest = store.ensure_tables(store.load_manifest())
    evidence_index: dict = {}
    result = orch.TableRunResult(
        table="dms_order_details_info",
        verdict=_verdict("dms_order_details_info"),
        evidence=_evidence(),
    )

    orch.persist_table_result(store, manifest, evidence_index, result)

    entry = next(t for t in store.load_manifest()["tables"] if t["table"] == "dms_order_details_info")
    assert entry["existence"] == "exists"
    assert store.load_evidence()["dms_order_details_info"]["columns"] == ["订单编号"]
    assert evidence_index["dms_order_details_info"]["columns"] == ["订单编号"]


def test_persist_table_result_merges_deferred_questions_from_verdict_and_evidence(
    tmp_path: Path,
):
    """The two structured outputs - phase 1's verdict and phase 2's evidence -
    can each carry their own deferred_questions; both must land on the
    manifest entry so collect_deferred_questions() sees the union."""
    store = Store(tmp_path)
    manifest = store.ensure_tables(store.load_manifest())
    evidence_index: dict = {}
    verdict = TableVerdict(
        table="dms_basic_info",
        existence="partial",
        rationale="载体存在但字段大面积缺失",
        deferred_questions=["本平台是否存在「经销商基础资料」专属页面？"],
    )
    evidence = EvidenceTable(
        columns=["经销商编码"],
        fields=[EvidenceField(path="user.account", mapped_to="distributor_code")],
        deferred_questions=["CRM 客户主数据能否作为地址字段的来源？"],
    )
    result = orch.TableRunResult(table="dms_basic_info", verdict=verdict, evidence=evidence)

    orch.persist_table_result(store, manifest, evidence_index, result)

    entry = next(t for t in store.load_manifest()["tables"] if t["table"] == "dms_basic_info")
    assert entry["deferred_questions"] == [
        "本平台是否存在「经销商基础资料」专属页面？",
        "CRM 客户主数据能否作为地址字段的来源？",
    ]


def test_persist_table_result_keeps_a_finished_table_when_a_sibling_fails(tmp_path: Path):
    """The regression that motivated this: a sibling's failure must not cost
    an already-finished table its verdict or its evidence."""
    store = Store(tmp_path)
    manifest = store.ensure_tables(store.load_manifest())
    evidence_index: dict = {}

    orch.persist_table_result(
        store,
        manifest,
        evidence_index,
        orch.TableRunResult(
            table="dms_bill_details_info",
            verdict=_verdict("dms_bill_details_info"),
            evidence=_evidence(),
        ),
    )
    orch.persist_table_result(
        store,
        manifest,
        evidence_index,
        orch.TableRunResult(table="dms_order_details_info", error=RuntimeError("model exhausted")),
    )

    reloaded = store.load_manifest()["tables"]
    finished = next(t for t in reloaded if t["table"] == "dms_bill_details_info")
    failed = next(t for t in reloaded if t["table"] == "dms_order_details_info")
    assert finished["existence"] == "exists"
    assert store.load_evidence()["dms_bill_details_info"]["columns"] == ["订单编号"]
    assert "existence" not in failed


# ---------------------------------------------------------------------------
# MCP teardown
#
# `finally: await jsr.close(); await ann.close()` is how the production run
# lost its real cause: the model failure raised, then close() raised anyio's
# "Attempted to exit a cancel scope that isn't the current task's" on the way
# out and *replaced* it. A raise there also skips the sibling client's close.
# ---------------------------------------------------------------------------


class FakeClient:
    def __init__(self, raises: BaseException | None = None) -> None:
        self._raises = raises
        self.closed = False

    async def close(self) -> None:
        self.closed = True
        if self._raises is not None:
            raise self._raises


async def test_close_quietly_swallows_a_failing_teardown():
    client = FakeClient(RuntimeError("Attempted to exit a cancel scope"))

    await orch.close_quietly(client, "jsreverser", "dms_order_details_info")

    assert client.closed is True


async def test_close_quietly_records_the_teardown_failure():
    """Swallowed is not the same as hidden - the event log has to keep it."""
    client = FakeClient(RuntimeError("Attempted to exit a cancel scope"))
    seen: list[tuple] = []

    await orch.close_quietly(
        client, "jsreverser", "dms_order_details_info", lambda n, e: seen.append((n, e))
    )

    assert len(seen) == 1
    name, event = seen[0]
    assert name == "dms_order_details_info"
    assert event["type"] == "mcp_close_failed"
    assert event["client"] == "jsreverser"
    assert "cancel scope" in event["error"]


async def test_close_quietly_stays_silent_on_a_clean_teardown():
    client = FakeClient()
    seen: list[tuple] = []

    await orch.close_quietly(client, "jsreverser", "t", lambda n, e: seen.append((n, e)))

    assert seen == []


async def test_close_quietly_does_not_mask_a_cancellation_in_flight():
    """The caller is unwinding from a CancelledError; teardown swallowing its
    own failure must not turn that into a different exception."""
    client = FakeClient(asyncio.CancelledError())

    await orch.close_quietly(client, "annotator", "t")

    assert client.closed is True


def test_table_run_questions_reports_a_cancelled_table_as_deliberate(tmp_path: Path):
    """A table the operator stopped on purpose is not a fault to investigate.
    Filing it under "登录态/MCP 断连" would send someone chasing a bug that
    never happened."""
    results = [
        orch.TableRunResult(table="dms_order_details_info", error=asyncio.CancelledError()),
    ]

    questions = orch.table_run_questions(results)

    assert len(questions) == 1
    assert "dms_order_details_info" in questions[0]
    assert "人工中止" in questions[0]
    assert "排查" not in questions[0]


def test_table_run_questions_reports_a_real_failure_for_diagnosis():
    results = [
        orch.TableRunResult(table="dms_order_details_info", error=RuntimeError("model exhausted")),
    ]

    questions = orch.table_run_questions(results)

    assert len(questions) == 1
    assert "排查" in questions[0]
    assert "model exhausted" in questions[0]


def test_table_run_questions_ignores_finished_tables():
    results = [
        orch.TableRunResult(table="dms_bill_details_info", verdict=_verdict("dms_bill_details_info")),
    ]

    assert orch.table_run_questions(results) == []


def test_table_run_questions_keeps_the_two_classes_apart_in_one_batch():
    results = [
        orch.TableRunResult(table="dms_bill_details_info", verdict=_verdict("dms_bill_details_info")),
        orch.TableRunResult(table="dms_order_details_info", error=asyncio.CancelledError()),
        orch.TableRunResult(table="dms_contract_sign_info", error=RuntimeError("MCP 断连")),
    ]

    questions = orch.table_run_questions(results)

    assert len(questions) == 2
    cancelled = next(q for q in questions if "dms_order_details_info" in q)
    failed = next(q for q in questions if "dms_contract_sign_info" in q)
    assert "人工中止" in cancelled
    assert "排查" in failed


def test_persist_table_result_writes_verdict_without_evidence(tmp_path: Path):
    """A non-producing verdict never reaches field mapping, so it arrives with
    `evidence=None` - it still has to land in the manifest."""
    store = Store(tmp_path)
    manifest = store.ensure_tables(store.load_manifest())
    evidence_index: dict = {}

    orch.persist_table_result(
        store,
        manifest,
        evidence_index,
        orch.TableRunResult(table="dms_basic_info", verdict=_verdict("dms_basic_info", "absent")),
    )

    entry = next(t for t in store.load_manifest()["tables"] if t["table"] == "dms_basic_info")
    assert entry["existence"] == "absent"
    assert store.load_evidence() == {}
