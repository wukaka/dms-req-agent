"""`TableTaskRegistry` is what makes one table's death cost one table.

The fan-out used to hand bare coroutines to `asyncio.gather()`, which has two
consequences that showed up in production: there is no handle to cancel a
single table by name, and the default `return_exceptions=False` re-raises the
first failure into `run_platform` while leaving the *siblings running* -
orphaned agents still driving the one shared browser after the coordinator
has already unwound.

Naming the tasks and collecting every outcome fixes both. These tests use
plain coroutines rather than real agents: the property under test is the
registry's supervision semantics, not anything about MCP or an LLM.
"""

from __future__ import annotations

import asyncio

from src.orchestrator import TableRunResult, TableTaskRegistry


async def _finishes(table: str, sibling_ran: list[str]) -> TableRunResult:
    await asyncio.sleep(0.01)
    sibling_ran.append(table)
    return TableRunResult(table=table)


async def _blocks_forever(table: str) -> TableRunResult:
    await asyncio.Event().wait()
    raise AssertionError("unreachable")


async def _raises(table: str) -> TableRunResult:
    await asyncio.sleep(0)
    raise RuntimeError("model exhausted all 1 attempt(s)")


async def test_gather_returns_one_result_per_launched_table():
    registry = TableTaskRegistry()
    ran: list[str] = []
    registry.launch("dms_order_details_info", _finishes("dms_order_details_info", ran))
    registry.launch("dms_bill_details_info", _finishes("dms_bill_details_info", ran))

    results = await registry.gather()

    assert sorted(r.table for r in results) == ["dms_bill_details_info", "dms_order_details_info"]
    assert all(r.error is None for r in results)


async def test_cancelling_one_table_lets_the_others_finish():
    """The whole point: terminating one agent must not take the batch with it."""
    registry = TableTaskRegistry()
    ran: list[str] = []
    registry.launch("dms_order_details_info", _blocks_forever("dms_order_details_info"))
    registry.launch("dms_bill_details_info", _finishes("dms_bill_details_info", ran))
    registry.launch("dms_contract_sign_info", _finishes("dms_contract_sign_info", ran))

    await asyncio.sleep(0)
    assert registry.cancel("dms_order_details_info") is True
    results = await registry.gather()

    assert sorted(ran) == ["dms_bill_details_info", "dms_contract_sign_info"]
    by_table = {r.table: r for r in results}
    assert by_table["dms_bill_details_info"].error is None
    assert isinstance(by_table["dms_order_details_info"].error, asyncio.CancelledError)


async def test_a_raising_table_does_not_abandon_its_siblings():
    registry = TableTaskRegistry()
    ran: list[str] = []
    registry.launch("dms_order_details_info", _raises("dms_order_details_info"))
    registry.launch("dms_bill_details_info", _finishes("dms_bill_details_info", ran))

    results = await registry.gather()

    assert ran == ["dms_bill_details_info"]
    by_table = {r.table: r for r in results}
    assert isinstance(by_table["dms_order_details_info"].error, RuntimeError)
    assert by_table["dms_bill_details_info"].error is None


async def test_cancel_reports_false_for_a_table_it_does_not_run():
    registry = TableTaskRegistry()

    assert registry.cancel("dms_order_details_info") is False


async def test_running_lists_tables_still_in_flight():
    registry = TableTaskRegistry()
    registry.launch("dms_order_details_info", _blocks_forever("dms_order_details_info"))

    await asyncio.sleep(0)
    assert registry.running() == ["dms_order_details_info"]

    registry.cancel("dms_order_details_info")
    await registry.gather()
    assert registry.running() == []
