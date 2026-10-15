from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from dms_survey.agents._human import HumanChannel, make_ask_human_tool
from dms_survey.browser_queue import BrowserQueue, BrowserQueueMiddleware


@pytest.mark.asyncio
async def test_serializes_two_agents():
    queue = BrowserQueue()
    order: list[str] = []

    async def worker(name: str, hold_seconds: float) -> None:
        async with queue.acquire_block(name):
            assert queue.holder == name
            order.append(f"{name}:enter")
            await asyncio.sleep(hold_seconds)
            order.append(f"{name}:exit")

    await asyncio.gather(worker("A", 0.05), worker("B", 0.0))

    # Whichever wins the race, its enter/exit must be contiguous - no
    # interleaving is possible with a capacity-1 lock.
    first = order[0].split(":")[0]
    assert order[:2] == [f"{first}:enter", f"{first}:exit"]
    assert queue.holder is None


@pytest.mark.asyncio
async def test_released_on_exception():
    queue = BrowserQueue()
    with pytest.raises(ValueError):
        async with queue.acquire_block("A"):
            raise ValueError("boom")
    assert queue.holder is None
    async with queue.acquire_block("B"):
        assert queue.holder == "B"


async def _collect(agen):
    return [x async for x in agen]


@pytest.mark.asyncio
async def test_middleware_acquires_queue_for_browser_tool():
    queue = BrowserQueue()
    mw = BrowserQueueMiddleware(queue, frozenset({"click_element"}))
    holder_during: list[str | None] = []

    async def next_handler():
        holder_during.append(queue.holder)
        yield "event"

    agent = SimpleNamespace(name="dms_order_details_info")
    tool_call = SimpleNamespace(name="click_element")
    events = await _collect(mw.on_acting(agent, {"tool_call": tool_call}, next_handler))

    assert events == ["event"]
    assert holder_during == ["dms_order_details_info"]
    assert queue.holder is None


@pytest.mark.asyncio
async def test_middleware_passes_through_for_non_browser_tool():
    queue = BrowserQueue()
    mw = BrowserQueueMiddleware(queue, frozenset({"click_element"}))
    holder_during: list[str | None] = []

    async def next_handler():
        holder_during.append(queue.holder)
        yield "event"

    agent = SimpleNamespace(name="dms_order_details_info")
    tool_call = SimpleNamespace(name="ask_judge")
    events = await _collect(mw.on_acting(agent, {"tool_call": tool_call}, next_handler))

    assert events == ["event"]
    assert holder_during == [None]


@pytest.mark.asyncio
async def test_an_agent_suspended_on_ask_human_does_not_hold_the_browser():
    """Design §7.3 as an executable guard rather than a comment.

    `ask_human` blocks for as long as the human takes to answer. If it were
    ever listed as a browser tool - or the middleware's guarded branch grew to
    cover non-browser calls - that wait would happen *holding* the only
    browser ticket, and the other five tables would block behind a human who
    may not be watching. The failure mode is a silent, total stall.
    """
    queue = BrowserQueue()
    mw = BrowserQueueMiddleware(queue, frozenset({"click_element"}))
    channel = HumanChannel()
    tool = make_ask_human_tool(channel, "dms_order_details_info")

    async def asking_handler():
        yield await tool.call(question="这张表在哪个菜单？")

    asking = asyncio.create_task(_collect(mw.on_acting(
        SimpleNamespace(name="dms_order_details_info"),
        {"tool_call": SimpleNamespace(name="ask_human")},
        asking_handler,
    )))
    await asyncio.sleep(0.01)
    assert not asking.done(), "the asking agent should still be waiting on a human"
    assert queue.holder is None

    holder_during: list[str | None] = []

    async def click_handler():
        holder_during.append(queue.holder)
        yield "clicked"

    await asyncio.wait_for(_collect(mw.on_acting(
        SimpleNamespace(name="dms_bill_details_info"),
        {"tool_call": SimpleNamespace(name="click_element")},
        click_handler,
    )), timeout=1)

    assert holder_during == ["dms_bill_details_info"]

    channel.answer(channel.pending()[0].id, "订单管理 > 我的订单")
    await asking
