"""Judge-side control over the six table agents: stop one, talk to one.

Termination rides on `TableTaskRegistry` (test_table_registry.py), which is
what already makes one table's death cost one table.

Delivering a *message* is the harder half. AgentScope has no way to push into
a running agent - `UserInterruptEvent` only clears a paused state, and
`is_external_tool` ends the stream. What it does have is the same trick it
uses on itself: `state.append_context(name, [HintBlock(...)])`, the runtime
state injection at `agentscope/agent/_agent.py:1164`. Draining a mailbox into
that on the `on_reasoning` middleware hook gives a real delivery point - every
ReAct iteration, whether or not the agent ever chooses to ask anything.
"""

from __future__ import annotations

import asyncio

from agentscope.state import AgentState

from dms_survey.agents._control import (
    AgentMailbox,
    MailboxMiddleware,
    make_send_message_tool,
    make_terminate_agent_tool,
)
from dms_survey.orchestrator import TableRunResult, TableTaskRegistry


async def _blocks_forever(table: str) -> TableRunResult:
    await asyncio.Event().wait()
    raise AssertionError("unreachable")


def _text(chunk) -> str:
    return chunk.content[0].text


# ---------------------------------------------------------------------------
# terminate_agent
# ---------------------------------------------------------------------------


async def test_terminate_stops_the_named_table_and_leaves_the_others_running():
    registry = TableTaskRegistry()
    registry.launch("dms_order_details_info", _blocks_forever("dms_order_details_info"))
    registry.launch("dms_bill_details_info", _blocks_forever("dms_bill_details_info"))
    await asyncio.sleep(0)

    tool = make_terminate_agent_tool(registry)
    chunk = await tool.call(table="dms_order_details_info", reason="入口判错了，重来")

    assert "dms_order_details_info" in _text(chunk)
    await asyncio.sleep(0)  # cancellation lands on the next loop tick
    assert registry.running() == ["dms_bill_details_info"]

    registry.cancel("dms_bill_details_info")
    await registry.gather()


async def test_terminate_reports_what_is_running_when_the_name_is_wrong():
    """The judge is an LLM; it will get a name wrong. Telling it which tables
    are actually in flight is what lets it correct itself in one step."""
    registry = TableTaskRegistry()
    registry.launch("dms_bill_details_info", _blocks_forever("dms_bill_details_info"))
    await asyncio.sleep(0)

    tool = make_terminate_agent_tool(registry)
    chunk = await tool.call(table="dms_no_such_table", reason="随便")

    text = _text(chunk)
    assert "dms_no_such_table" in text
    assert "dms_bill_details_info" in text

    registry.cancel("dms_bill_details_info")
    await registry.gather()


# ---------------------------------------------------------------------------
# The mailbox
# ---------------------------------------------------------------------------


def test_mailbox_drain_returns_what_was_sent_and_empties_the_box():
    mailbox = AgentMailbox()
    mailbox.send("dms_order_details_info", "别再翻页了，先确认核载体")

    assert mailbox.drain("dms_order_details_info") == ["别再翻页了，先确认核载体"]
    assert mailbox.drain("dms_order_details_info") == []


def test_mailbox_keeps_each_agents_messages_to_itself():
    mailbox = AgentMailbox()
    mailbox.send("dms_order_details_info", "订单的话")
    mailbox.send("dms_bill_details_info", "对账单的话")

    assert mailbox.drain("dms_bill_details_info") == ["对账单的话"]
    assert mailbox.drain("dms_order_details_info") == ["订单的话"]


def test_mailbox_preserves_the_order_messages_were_sent_in():
    mailbox = AgentMailbox()
    mailbox.send("dms_order_details_info", "第一条")
    mailbox.send("dms_order_details_info", "第二条")

    assert mailbox.drain("dms_order_details_info") == ["第一条", "第二条"]


def test_mailbox_pending_lists_undelivered_messages_per_agent():
    mailbox = AgentMailbox()
    mailbox.send("dms_order_details_info", "第一条")

    assert mailbox.pending("dms_order_details_info") == 1
    mailbox.drain("dms_order_details_info")
    assert mailbox.pending("dms_order_details_info") == 0


# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------


class FakeAgent:
    def __init__(self, name: str) -> None:
        self.name = name
        self.state = AgentState()


async def _collect(agen):
    return [x async for x in agen]


async def test_middleware_injects_queued_messages_into_the_agents_context():
    mailbox = AgentMailbox()
    mailbox.send("dms_order_details_info", "别再翻页了，先确认核载体")
    agent = FakeAgent("dms_order_details_info")

    async def next_handler():
        yield "reasoned"

    events = await _collect(
        MailboxMiddleware(mailbox).on_reasoning(agent, {}, next_handler)
    )

    assert events == ["reasoned"]
    injected = "".join(
        getattr(block, "hint", "")
        for msg in agent.state.context
        for block in msg.content
    )
    assert "别再翻页了，先确认核载体" in injected


async def test_middleware_delivers_a_message_only_once():
    mailbox = AgentMailbox()
    mailbox.send("dms_order_details_info", "只说一遍")
    agent = FakeAgent("dms_order_details_info")

    async def next_handler():
        yield "reasoned"

    mw = MailboxMiddleware(mailbox)
    await _collect(mw.on_reasoning(agent, {}, next_handler))
    await _collect(mw.on_reasoning(agent, {}, next_handler))

    injected = "".join(
        getattr(block, "hint", "")
        for msg in agent.state.context
        for block in msg.content
    )
    assert injected.count("只说一遍") == 1


async def test_middleware_leaves_the_context_alone_when_there_is_no_mail():
    agent = FakeAgent("dms_order_details_info")

    async def next_handler():
        yield "reasoned"

    await _collect(MailboxMiddleware(AgentMailbox()).on_reasoning(agent, {}, next_handler))

    assert agent.state.context == []


# ---------------------------------------------------------------------------
# send_message_to_agent
# ---------------------------------------------------------------------------


async def test_send_message_queues_for_a_running_table():
    registry = TableTaskRegistry()
    registry.launch("dms_order_details_info", _blocks_forever("dms_order_details_info"))
    await asyncio.sleep(0)
    mailbox = AgentMailbox()

    tool = make_send_message_tool(mailbox, registry)
    await tool.call(table="dms_order_details_info", message="先确认核载体")

    assert mailbox.drain("dms_order_details_info") == ["先确认核载体"]

    registry.cancel("dms_order_details_info")
    await registry.gather()


async def test_send_message_refuses_a_table_that_is_not_running():
    """A message to a finished table would sit in the box forever and the
    judge would go on believing it was delivered."""
    registry = TableTaskRegistry()
    registry.launch("dms_bill_details_info", _blocks_forever("dms_bill_details_info"))
    await asyncio.sleep(0)
    mailbox = AgentMailbox()

    tool = make_send_message_tool(mailbox, registry)
    chunk = await tool.call(table="dms_order_details_info", message="喂？")

    assert mailbox.drain("dms_order_details_info") == []
    text = _text(chunk)
    assert "dms_order_details_info" in text
    assert "dms_bill_details_info" in text

    registry.cancel("dms_bill_details_info")
    await registry.gather()
