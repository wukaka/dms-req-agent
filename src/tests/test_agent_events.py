"""`agents/_events.py` replaces the three identical `_structured()` copies
(discovery/judge/table_agent) with one that consumes `agent.reply_stream()`
instead of `agent.reply()`.

`reply()` is literally `reply_stream(yield_final_msg=True)` with every event
thrown away (`agentscope/agent/_agent.py:370-379`), so switching is lossless
for `structured_output` - but it hands us the `AgentEvent` stream, which is
the only per-agent record of what each agent actually did. Without it a
concurrent fan-out (`orchestrator.py:250`) produces one interleaved log with
no agent attribution, and a model failure surfaces only as whatever
exception escapes last."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from agentscope.message import Msg, TextBlock
from pydantic import BaseModel

from src.agents._events import JsonlEventLog, structured


class Result(BaseModel):
    value: str


class FakeEvent(BaseModel):
    """Every `AgentEvent` is a pydantic model (`agentscope/event/_event.py`
    `EventBase(BaseModel)`), which is what makes `model_dump()` sinks work."""

    type: str


def final_msg(structured_output) -> Msg:
    msg = Msg(name="discovery", role="assistant", content=[TextBlock(type="text", text="done")])
    msg.structured_output = structured_output
    return msg


class FakeAgent:
    def __init__(self, stream):
        self.name = "discovery"
        self._stream = stream
        self.schemas: list = []

    async def reply_stream(self, msg, structured_schema=None, yield_final_msg=False):
        self.schemas.append(structured_schema)
        assert yield_final_msg, "final Msg must be requested or structured_output is lost"
        for item in self._stream:
            yield item


async def test_structured_returns_parsed_final_message():
    agent = FakeAgent([FakeEvent(type="reply_start"), final_msg({"value": "ok"})])

    result = await structured(agent, "msg", Result)

    assert result.value == "ok"
    assert agent.schemas == [Result]


async def test_structured_forwards_events_to_sink_but_not_the_final_message():
    events = [FakeEvent(type="tool_call_end"), FakeEvent(type="model_call_end")]
    agent = FakeAgent([events[0], events[1], final_msg({"value": "ok"})])
    seen: list[tuple] = []

    await structured(agent, "msg", Result, on_event=lambda n, e: seen.append((n, e)))

    assert seen == [("discovery", events[0]), ("discovery", events[1])]


async def test_structured_records_the_exception_before_re_raising():
    """The run that motivated this: a table agent's model call failed, then
    `_run_one_table`'s `finally: await ann.close()` raised `CancelledError`
    (a `BaseException`, so `except Exception` never saw it) and that is what
    escaped - the original failure never reached any log. Recording it on
    the way out means the sink holds the cause even when the process dies of
    something else."""

    class Boom(FakeAgent):
        async def reply_stream(self, msg, structured_schema=None, yield_final_msg=False):
            yield FakeEvent(type="reply_start")
            raise RuntimeError("model exhausted all 1 attempt(s)")

    agent = Boom([])
    seen: list[tuple] = []

    with pytest.raises(RuntimeError, match="exhausted"):
        await structured(agent, "msg", Result, on_event=lambda n, e: seen.append((n, e)))

    assert seen[0][1].type == "reply_start"
    name, err = seen[-1]
    assert name == "discovery"
    assert err["type"] == "agent_exception"
    assert "exhausted" in err["error"]


async def test_structured_raises_when_no_structured_output():
    agent = FakeAgent([final_msg(None)])

    with pytest.raises(RuntimeError, match="discovery"):
        await structured(agent, "msg", Result)


async def test_structured_raises_when_stream_ends_without_final_message():
    agent = FakeAgent([FakeEvent(type="reply_start")])

    with pytest.raises(RuntimeError, match="discovery"):
        await structured(agent, "msg", Result)


def test_jsonl_event_log_writes_one_line_per_event(tmp_path: Path):
    log = JsonlEventLog(tmp_path / "events.jsonl")

    log("discovery", FakeEvent(type="tool_call_end"))
    log("dms_order_details_info", FakeEvent(type="model_call_end"))

    lines = (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(x)["agent"] for x in lines] == ["discovery", "dms_order_details_info"]
    assert [json.loads(x)["event"]["type"] for x in lines] == ["tool_call_end", "model_call_end"]


def test_jsonl_event_log_keeps_plain_dict_records_queryable(tmp_path: Path):
    """`structured()` emits the exception record as a plain dict, not a
    pydantic event. It has to land as real JSON - the point of writing it is
    being able to read the cause back out."""
    log = JsonlEventLog(tmp_path / "events.jsonl")

    log("dms_order_details_info", {"type": "agent_exception", "error": "RuntimeError: boom"})

    record = json.loads((tmp_path / "events.jsonl").read_text(encoding="utf-8"))
    assert record["event"]["type"] == "agent_exception"
    assert record["event"]["error"] == "RuntimeError: boom"


def test_jsonl_event_log_creates_parent_directory(tmp_path: Path):
    log = JsonlEventLog(tmp_path / "logs" / "events.jsonl")

    log("discovery", FakeEvent(type="reply_start"))

    assert (tmp_path / "logs" / "events.jsonl").exists()
