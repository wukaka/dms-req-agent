"""A live view of the run, built on AgentScope's own `ConsoleRenderer`.

Two things stand between the renderer and our fan-out. `render(event)` takes
only the event, so with six table agents interleaved on one terminal there is
nothing saying *which* agent a line belongs to. And `structured()` feeds the
sink plain dicts of its own (`agent_exception`, `mcp_close_failed`) that are
not `AgentEvent`s at all - handing those to `render()` is a crash inside the
agent's stream loop, which would cost the table.
"""

from __future__ import annotations

from io import StringIO

from pydantic import BaseModel
from rich.console import Console

from src.agents._events import ConsoleSink, tee


class FakeEvent(BaseModel):
    type: str


class FakeRenderer:
    def __init__(self) -> None:
        self.rendered: list = []

    def render(self, event) -> None:
        self.rendered.append(event)


def _console() -> tuple[Console, StringIO]:
    buffer = StringIO()
    return Console(file=buffer, width=200, no_color=True), buffer


def test_console_sink_renders_agent_events_through_the_renderer():
    renderer = FakeRenderer()
    console, _ = _console()
    sink = ConsoleSink(renderer=renderer, console=console)
    event = FakeEvent(type="tool_call_end")

    sink("dms_order_details_info", event)

    assert renderer.rendered == [event]


def test_console_sink_labels_which_agent_the_output_belongs_to():
    """Six agents interleaved on one terminal is unreadable without this."""
    renderer = FakeRenderer()
    console, buffer = _console()
    sink = ConsoleSink(renderer=renderer, console=console)

    sink("dms_order_details_info", FakeEvent(type="reply_start"))
    sink("dms_bill_details_info", FakeEvent(type="reply_start"))

    output = buffer.getvalue()
    assert "dms_order_details_info" in output
    assert "dms_bill_details_info" in output


def test_console_sink_does_not_repeat_the_label_while_one_agent_keeps_talking():
    renderer = FakeRenderer()
    console, buffer = _console()
    sink = ConsoleSink(renderer=renderer, console=console)

    sink("dms_order_details_info", FakeEvent(type="reply_start"))
    sink("dms_order_details_info", FakeEvent(type="model_call_start"))
    sink("dms_order_details_info", FakeEvent(type="model_call_end"))

    assert buffer.getvalue().count("dms_order_details_info") == 1


def test_console_sink_relabels_when_an_agent_speaks_again_after_another():
    renderer = FakeRenderer()
    console, buffer = _console()
    sink = ConsoleSink(renderer=renderer, console=console)

    sink("dms_order_details_info", FakeEvent(type="reply_start"))
    sink("dms_bill_details_info", FakeEvent(type="reply_start"))
    sink("dms_order_details_info", FakeEvent(type="reply_end"))

    assert buffer.getvalue().count("dms_order_details_info") == 2


def test_console_sink_prints_dict_events_instead_of_rendering_them():
    """`structured()`'s exception record is a plain dict. `render()` would
    raise on it, inside the agent's stream loop, and cost us the table."""
    renderer = FakeRenderer()
    console, buffer = _console()
    sink = ConsoleSink(renderer=renderer, console=console)

    sink("dms_order_details_info", {"type": "agent_exception", "error": "RuntimeError: boom"})

    assert renderer.rendered == []
    output = buffer.getvalue()
    assert "agent_exception" in output
    assert "RuntimeError: boom" in output


def test_tee_delivers_every_event_to_every_sink():
    first: list = []
    second: list = []

    sink = tee(lambda n, e: first.append((n, e)), lambda n, e: second.append((n, e)))
    sink("discovery", {"type": "reply_start"})

    assert first == second == [("discovery", {"type": "reply_start"})]


def test_tee_keeps_one_sink_alive_when_another_raises():
    """A terminal-rendering failure must not cost us the durable log - nor the
    table, since the sink runs inside the agent's own stream loop."""
    seen: list = []

    def explodes(name, event):
        raise RuntimeError("rich blew up on an event it did not expect")

    sink = tee(explodes, lambda n, e: seen.append((n, e)))
    sink("discovery", {"type": "reply_start"})

    assert seen == [("discovery", {"type": "reply_start"})]
