"""Stopping and talking to a running table agent.

The registry is duck-typed (`.cancel(table)`, `.running()`) rather than
imported: `TableTaskRegistry` lives in `orchestrator.py`, which imports this
package, and a real import here would close the cycle.

Delivery uses `state.append_context(name, [HintBlock(...)])` on the
`on_reasoning` middleware hook - the same mechanism AgentScope's own runtime
state injection uses (`agentscope/agent/_agent.py:1164`). It is the only
deterministic way in: the framework cannot push into a running agent
(`UserInterruptEvent` merely clears a paused state), and `is_external_tool`
ends the reply stream rather than pausing inside it.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, AsyncGenerator, Callable

from agentscope.message import HintBlock
from agentscope.middleware import MiddlewareBase
from agentscope.tool import FunctionTool


class AgentMailbox:
    """Messages queued for agents, drained at each agent's next reasoning step."""

    def __init__(self) -> None:
        self._boxes: dict[str, list[str]] = defaultdict(list)

    def send(self, agent: str, message: str) -> None:
        self._boxes[agent].append(message)

    def drain(self, agent: str) -> list[str]:
        messages = self._boxes.get(agent, [])
        self._boxes[agent] = []
        return messages

    def pending(self, agent: str) -> int:
        return len(self._boxes.get(agent, []))


class MailboxMiddleware(MiddlewareBase):
    """Hands an agent its queued messages before every reasoning step."""

    def __init__(self, mailbox: AgentMailbox) -> None:
        self._mailbox = mailbox

    async def on_reasoning(
        self,
        agent: Any,
        input_kwargs: dict,
        next_handler: Callable[..., AsyncGenerator],
    ) -> AsyncGenerator:
        messages = self._mailbox.drain(agent.name)
        if messages:
            agent.state.append_context(
                agent.name,
                [
                    HintBlock(
                        hint="<系统转达>以下是编排方/人工发给你的指令，优先于你当前的计划："
                        + "\n".join(f"\n- {m}" for m in messages)
                        + "\n</系统转达>"
                    )
                ],
            )
        async for event in next_handler():
            yield event


def make_terminate_agent_tool(registry: Any, name: str = "terminate_agent") -> FunctionTool:
    async def terminate_agent(table: str, reason: str) -> str:
        """中止一个正在运行的表 agent。

        被中止的表本轮不产出结论，下次重跑会从头开始（进度以 manifest.json 为准）。
        其它表不受影响，继续运行。

        Args:
            table: 要中止的表名，必须是当前正在运行的表之一。
            reason: 中止原因，会记录下来给人工看。
        """
        if registry.cancel(table):
            return f"已中止 {table}（原因：{reason}）。该表本轮无结论，下次重跑从头开始。"
        return (
            f"没有中止 {table}：它当前没有在运行（可能已结束或表名写错）。"
            f"正在运行的表：{registry.running() or '无'}。"
        )

    return FunctionTool(terminate_agent, name=name)


def make_send_message_tool(
    mailbox: AgentMailbox,
    registry: Any,
    name: str = "send_message_to_agent",
) -> FunctionTool:
    async def send_message_to_agent(table: str, message: str) -> str:
        """给一个正在运行的表 agent 发一条指令，它会在下一步推理前读到。

        Args:
            table: 目标表名，必须是当前正在运行的表之一。
            message: 要转达的内容，讲清你要它改做什么。
        """
        if table not in registry.running():
            return (
                f"没有发出：{table} 当前没有在运行（可能已结束或表名写错）。"
                f"正在运行的表：{registry.running() or '无'}。"
            )
        mailbox.send(table, message)
        return f"已发给 {table}，它会在下一步推理前读到。"

    return FunctionTool(send_message_to_agent, name=name)
