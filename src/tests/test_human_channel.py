"""`ask_human`: an agent suspending itself until a human answers.

AgentScope's own mechanism for this is `is_external_tool=True`, but in 2.0.8
that makes `_reasoning` `return` right after `RequireExternalExecutionEvent`
(`agentscope/agent/_agent.py:2606-2617`) - the reply stream *ends*, and our
`structured()` would raise "stream ended without a final message". Resuming
means replaying an `ExternalExecutionResultEvent` into a fresh `reply_stream`
call, which breaks the one-call contract every caller here is built on.

An ordinary async tool that awaits a future does the same job: the agent's
coroutine simply suspends inside the tool call, the stream stays open, and
the answer comes back as a normal tool result. It also keeps the waiting in
*our* code, which is what lets the same channel deliver a message the judge
sends (design §7.2) rather than only a human's.
"""

from __future__ import annotations

import asyncio

import pytest

from dms_survey.agents._human import HumanChannel, make_ask_human_tool


async def test_ask_returns_the_answer_a_human_hands_back():
    channel = HumanChannel()
    asking = asyncio.create_task(channel.ask("dms_order_details_info", "这张表在哪个菜单？"))

    await asyncio.sleep(0)
    pending = channel.pending()
    assert channel.answer(pending[0].id, "订单管理 > 我的订单") is True

    assert await asking == "订单管理 > 我的订单"


async def test_ask_stays_suspended_until_someone_answers():
    channel = HumanChannel()
    asking = asyncio.create_task(channel.ask("dms_order_details_info", "在哪？"))

    await asyncio.sleep(0.01)

    assert not asking.done()
    asking.cancel()


async def test_pending_shows_the_question_while_it_waits_and_drops_it_after():
    channel = HumanChannel()
    asking = asyncio.create_task(channel.ask("dms_order_details_info", "在哪？"))
    await asyncio.sleep(0)

    pending = channel.pending()
    assert len(pending) == 1
    assert pending[0].agent == "dms_order_details_info"
    assert pending[0].question == "在哪？"

    channel.answer(pending[0].id, "订单管理")
    await asking

    assert channel.pending() == []


async def test_answering_an_unknown_question_reports_false():
    channel = HumanChannel()

    assert channel.answer("no-such-question", "随便") is False


async def test_answering_the_same_question_twice_reports_false():
    """The CLI can be typed into twice; the second must not blow up the loop
    with `InvalidStateError` on an already-resolved future."""
    channel = HumanChannel()
    asking = asyncio.create_task(channel.ask("dms_order_details_info", "在哪？"))
    await asyncio.sleep(0)
    qid = channel.pending()[0].id

    assert channel.answer(qid, "订单管理") is True
    assert channel.answer(qid, "又说一遍") is False
    assert await asking == "订单管理"


async def test_two_agents_waiting_at_once_do_not_get_each_others_answers():
    """Six tables run concurrently; the whole point is per-agent delivery."""
    channel = HumanChannel()
    order = asyncio.create_task(channel.ask("dms_order_details_info", "订单在哪？"))
    bill = asyncio.create_task(channel.ask("dms_bill_details_info", "对账单在哪？"))
    await asyncio.sleep(0)

    by_agent = {q.agent: q.id for q in channel.pending()}
    channel.answer(by_agent["dms_bill_details_info"], "财务 > 对账单")
    channel.answer(by_agent["dms_order_details_info"], "订单管理 > 我的订单")

    assert await order == "订单管理 > 我的订单"
    assert await bill == "财务 > 对账单"


async def test_a_cancelled_agent_leaves_no_question_behind():
    """Table cancelled while it waits on a human (task #2's per-table cancel).
    A leaked entry would have the operator answering a dead agent forever."""
    channel = HumanChannel()
    asking = asyncio.create_task(channel.ask("dms_order_details_info", "在哪？"))
    await asyncio.sleep(0)
    assert channel.pending() != []

    asking.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asking

    assert channel.pending() == []


async def test_ask_human_tool_routes_the_question_under_its_own_agent_name():
    channel = HumanChannel()
    tool = make_ask_human_tool(channel, "dms_order_details_info")
    assert tool.name == "ask_human"

    calling = asyncio.create_task(tool.call(question="这张表在哪个菜单？"))
    await asyncio.sleep(0)

    pending = channel.pending()
    assert pending[0].agent == "dms_order_details_info"
    assert pending[0].question == "这张表在哪个菜单？"

    channel.answer(pending[0].id, "订单管理 > 我的订单")
    chunk = await calling

    assert "订单管理 > 我的订单" in chunk.content[0].text
