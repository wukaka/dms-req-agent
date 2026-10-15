"""Single global semaphore serializing all browser MCP calls (design §3.2).

Browser operations stay fully serial by design (see
docs/superpowers/specs/2026-09-17-dms-survey-agentscope-design.md §3.1):
JSReverser-Strong-MCP models "current page" as global state with a race
between select_page and the following action, and real headed Chrome
throttles background tabs regardless of tooling. Parallelism happens only
in the offline analysis layer, which never touches this queue.

This is a semaphore, not a broker: no tab registry, no lease timeouts, no
atomicity guarantees beyond "one agent talks to the browser at a time".
Callers acquire one ticket per evidence block (enter a route, page through
results, drill into a detail, capture responses, screenshot - all in one
hold) per design §3.2, because re-navigating the SPA back to the caller's
route on every re-acquire is pure waste.
"""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, AsyncIterator, Callable

from agentscope.middleware import MiddlewareBase

logger = logging.getLogger(__name__)


class BrowserQueue:
    """Process-wide FIFO lock of capacity 1."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._holder: str | None = None

    @property
    def holder(self) -> str | None:
        return self._holder

    @asynccontextmanager
    async def acquire_block(self, agent_name: str) -> AsyncIterator[None]:
        waited_from = time.monotonic()
        await self._lock.acquire()
        waited = time.monotonic() - waited_from
        self._holder = agent_name
        logger.info("browser_queue: %s acquired (waited %.1fs)", agent_name, waited)
        try:
            yield
        finally:
            logger.info("browser_queue: %s released", agent_name)
            self._holder = None
            self._lock.release()


class BrowserQueueMiddleware(MiddlewareBase):
    """Gates an agent's browser-touching tool calls through a `BrowserQueue`.

    Acquire granularity is one MCP tool call: `on_acting` wraps exactly one
    `toolkit.call_tool`, the narrowest hook this queue can attach to. As a
    side effect this satisfies design §7.3 ("提问前必须先释放浏览器叫号")
    for free - a non-browser tool call like `ask_judge` never enters this
    middleware's guarded branch, so there is nothing to release before
    asking a question; do not add an explicit release anywhere else.
    """

    def __init__(self, queue: BrowserQueue, browser_tool_names: frozenset[str]) -> None:
        self._queue = queue
        self._browser_tool_names = browser_tool_names

    async def on_acting(
        self,
        agent: Any,
        input_kwargs: dict,
        next_handler: Callable[..., AsyncGenerator],
    ) -> AsyncGenerator:
        tool_call = input_kwargs["tool_call"]
        if tool_call.name not in self._browser_tool_names:
            async for event in next_handler():
                yield event
            return
        async with self._queue.acquire_block(agent.name):
            async for event in next_handler():
                yield event
