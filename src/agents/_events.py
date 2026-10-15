"""One `structured()` for all three agent roles, streaming instead of blocking.

`agent.reply()` is `reply_stream(yield_final_msg=True)` with every event
discarded (`agentscope/agent/_agent.py:370-379`); consuming the stream
ourselves is therefore lossless for `structured_output` and gives us the
`AgentEvent` record of what each agent did. That record is what the
interleaved fan-out log (`orchestrator.py:250` runs the table agents under
`asyncio.gather`) cannot otherwise provide - MCP writes its own lines with
no agent attribution.
"""

from __future__ import annotations

import json
import traceback
from pathlib import Path
from typing import Any, Callable, Optional

from agentscope.message import Msg

EventSink = Callable[[str, Any], None]


async def structured(
    agent: Any,
    msg: Any,
    schema: type,
    on_event: Optional[EventSink] = None,
) -> Any:
    """Run `agent` to completion, feeding every event to `on_event`.

    Raises `RuntimeError` naming the agent when no structured output comes
    back, so a failure reads as "which agent" rather than as an anonymous
    `None`.
    """
    final: Optional[Msg] = None
    try:
        async for item in agent.reply_stream(
            msg,
            structured_schema=schema,
            yield_final_msg=True,
        ):
            if isinstance(item, Msg):
                final = item
            elif on_event is not None:
                on_event(agent.name, item)
    except BaseException as exc:
        # A failing model call raises instead of emitting an end event, and
        # the caller's own teardown can replace this exception with its own
        # (orchestrator.py's `finally: await ann.close()` raising
        # `CancelledError` is how the original cause got lost). Record first,
        # then let it propagate untouched.
        if on_event is not None:
            on_event(agent.name, {
                "type": "agent_exception",
                "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(),
            })
        raise

    if final is None:
        raise RuntimeError(f"{agent.name}: reply stream ended without a final message")
    if final.structured_output is None:
        raise RuntimeError(
            f"{agent.name}: no structured_output "
            f"(finished_reason={final.finished_reason}); check the event log"
        )
    return schema.model_validate(final.structured_output)


class JsonlEventLog:
    """Append-only `agent`-tagged event sink.

    One shared file keeps the true interleaving of concurrent agents, and
    the `agent` key makes it filterable per agent after the fact.
    """

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def __call__(self, agent_name: str, event: Any) -> None:
        record = {"agent": agent_name, "event": _dump(event)}
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


class ConsoleSink:
    """Live terminal view, delegating to AgentScope's own `ConsoleRenderer`.

    Adds the two things the renderer cannot supply here: an agent label (six
    tables interleave on one terminal and `render(event)` takes only the
    event), and a path for the plain-dict records `structured()` emits, which
    are not `AgentEvent`s and would raise inside the agent's stream loop.
    """

    def __init__(
        self,
        renderer: Any = None,
        console: Any = None,
        verbosity: str = "default",
    ) -> None:
        if console is None:
            from rich.console import Console

            console = Console()
        if renderer is None:
            from agentscope.console import ConsoleRenderer

            renderer = ConsoleRenderer(verbosity=verbosity, console=console)
        self._console = console
        self._renderer = renderer
        self._speaking: Optional[str] = None

    def __call__(self, agent_name: str, event: Any) -> None:
        if agent_name != self._speaking:
            self._console.rule(f"[bold]{agent_name}")
            self._speaking = agent_name
        if isinstance(event, dict):
            self._console.print(f"{event.get('type', 'event')}: {event.get('error', event)}")
        else:
            self._renderer.render(event)


def tee(*sinks: EventSink) -> EventSink:
    """Fan one event out to every sink, letting each fail on its own.

    The sink runs inside `structured()`'s stream loop, so an exception here
    aborts the table. A terminal-rendering failure is not worth a table, and
    it must not cost the durable log its copy either.
    """

    def fanout(agent_name: str, event: Any) -> None:
        for sink in sinks:
            try:
                sink(agent_name, event)
            except Exception:  # noqa: BLE001 - one sink's failure is not the run's
                continue

    return fanout


def _dump(event: Any) -> Any:
    if isinstance(event, dict):
        return event
    dump = getattr(event, "model_dump", None)
    return dump(mode="json") if dump else repr(event)
