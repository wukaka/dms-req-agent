"""The channel an agent suspends on while it waits for a human.

Deliberately not AgentScope's `is_external_tool=True`: that path ends the
reply stream (`agentscope/agent/_agent.py:2606-2617`) and needs an
`ExternalExecutionResultEvent` replayed into a *new* `reply_stream` call to
resume, which is not something `structured()`'s one-call contract can carry.
An ordinary async tool awaiting a future suspends the agent just as well,
keeps the stream open, and leaves the waiting in our own code - which is what
lets the judge deliver a message through the same channel later.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass

from agentscope.tool import FunctionTool


@dataclass(frozen=True)
class PendingQuestion:
    id: str
    agent: str
    question: str


class HumanChannel:
    """Questions waiting for an answer, keyed so concurrent agents stay apart."""

    def __init__(self) -> None:
        self._waiting: dict[str, tuple[PendingQuestion, asyncio.Future[str]]] = {}

    async def ask(self, agent: str, question: str) -> str:
        question_id = uuid.uuid4().hex
        future: asyncio.Future[str] = asyncio.get_running_loop().create_future()
        self._waiting[question_id] = (PendingQuestion(question_id, agent, question), future)
        try:
            return await future
        finally:
            # Also covers the asker being cancelled: a leaked entry would have
            # the operator answering an agent that is already gone.
            self._waiting.pop(question_id, None)

    def pending(self) -> list[PendingQuestion]:
        return [question for question, _ in self._waiting.values()]

    def answer(self, question_id: str, text: str) -> bool:
        """True if a waiting agent was actually handed this answer."""
        entry = self._waiting.get(question_id)
        if entry is None or entry[1].done():
            return False
        entry[1].set_result(text)
        return True


def make_ask_human_tool(
    channel: HumanChannel,
    agent_name: str,
    name: str = "ask_human",
) -> FunctionTool:
    """Bind one agent's identity to the shared channel.

    Not a browser tool, so `BrowserQueueMiddleware` never wraps it - the agent
    waits here without holding the single browser ticket (design §7.3).
    """

    async def ask_human(question: str) -> str:
        """向人工提问并等待答复，会一直阻塞到人工回答为止。

        只在确实卡住、靠自己无法推进时使用（例如入口找不到、页面要求人工操作、
        判定依据不足）。提问要具体到可以一句话回答。

        Args:
            question: 要问人工的问题，讲清你卡在哪、需要什么信息才能继续。
        """
        return await channel.ask(agent_name, question)

    return FunctionTool(ask_human, name=name)
