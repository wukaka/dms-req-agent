"""The operator's side of the live run: answer, stop, redirect.

`ConsoleSink` renders what the agents are doing; this reads what the operator
types back. Everything is keyed by table name - an agent can only be
suspended inside one `ask_human` at a time, so a table names its question
unambiguously, and the same word addresses `kill` and `msg`.

`dispatch()` is synchronous and returns the line to print, so the whole
command surface is testable without a terminal. `run()` is the stdin glue.
"""

from __future__ import annotations

import asyncio
import sys
import threading
from typing import Any, Optional

from .agents._control import AgentMailbox
from .agents._human import HumanChannel

USAGE = """可用命令：
  q                      列出等待人工回答的问题
  a <表名> <答案>        回答某张表的问题
  ps                     列出仍在运行的表
  kill <表名> [原因]     中止某张表（其它表不受影响）
  msg <表名> <内容>      给某张表发一条指令，它下一步推理前会读到
  help                   显示本帮助"""


class OperatorConsole:
    def __init__(
        self,
        human: HumanChannel,
        registry: Any,
        mailbox: AgentMailbox,
    ) -> None:
        self._human = human
        self._registry = registry
        self._mailbox = mailbox

    def dispatch(self, line: str) -> str:
        parts = line.strip().split(maxsplit=1)
        if not parts:
            return ""
        command, rest = parts[0], (parts[1] if len(parts) > 1 else "")
        handler = {
            "q": self._questions,
            "a": self._answer,
            "ps": self._running,
            "kill": self._kill,
            "msg": self._message,
            "help": lambda _: USAGE,
        }.get(command)
        return handler(rest) if handler else USAGE

    def _questions(self, _: str) -> str:
        pending = self._human.pending()
        if not pending:
            return "当前没有等待回答的问题。"
        return "\n".join(f"[{q.agent}] {q.question}" for q in pending)

    def _answer(self, rest: str) -> str:
        table, _, text = rest.partition(" ")
        if not table or not text.strip():
            return f"用法：a <表名> <答案>\n\n{USAGE}"
        question = next((q for q in self._human.pending() if q.agent == table), None)
        if question is None:
            return f"{table} 当前没有在等待回答。"
        if not self._human.answer(question.id, text.strip()):
            return f"{table} 的问题已经不在等待中了（可能刚被回答或该表已结束）。"
        return f"已回答 {table}。"

    def _running(self, _: str) -> str:
        running = self._registry.running()
        return "\n".join(running) if running else "当前没有正在运行的表。"

    def _kill(self, rest: str) -> str:
        table, _, reason = rest.partition(" ")
        if not table:
            return f"用法：kill <表名> [原因]\n\n{USAGE}"
        if not self._registry.cancel(table):
            return f"{table} 没有在运行（可能已结束或表名写错）。"
        suffix = f"（原因：{reason.strip()}）" if reason.strip() else ""
        return f"已中止 {table}{suffix}。该表本轮无结论，下次重跑从头开始。"

    def _message(self, rest: str) -> str:
        table, _, text = rest.partition(" ")
        if not table or not text.strip():
            return f"用法：msg <表名> <内容>\n\n{USAGE}"
        if table not in self._registry.running():
            return f"{table} 没有在运行，消息没有发出。"
        self._mailbox.send(table, text.strip())
        return f"已发给 {table}，它下一步推理前会读到。"

    async def run(self, prompt: str = "dms> ") -> None:
        """Read commands until stdin closes or the task is cancelled.

        Reading runs on a *daemon* thread rather than `asyncio.to_thread`:
        cancelling this task cannot unblock a thread sitting in `readline()`,
        and `asyncio.run()` joins the default executor on its way out - so a
        run that finished every table would hang at exit with nothing on
        screen saying why. A daemon thread is simply abandoned instead.
        """
        loop = asyncio.get_running_loop()
        lines: asyncio.Queue[Optional[str]] = asyncio.Queue()

        def pump() -> None:
            for line in sys.stdin:
                loop.call_soon_threadsafe(lines.put_nowait, line)
            loop.call_soon_threadsafe(lines.put_nowait, None)

        threading.Thread(target=pump, name="dms-operator-stdin", daemon=True).start()

        print(USAGE, flush=True)
        print(prompt, end="", flush=True)
        while True:
            line = await lines.get()
            if line is None:
                return
            reply = self.dispatch(line)
            if reply:
                print(reply, flush=True)
            print(prompt, end="", flush=True)
