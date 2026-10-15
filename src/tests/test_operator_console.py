"""The typed half of the live view: `ConsoleSink` shows what the agents are
doing, this is how an operator answers, stops, or redirects one.

Commands key on the table name rather than a question number. An agent's
coroutine can only be suspended inside one `ask_human` at a time, so "the
question from dms_order_details_info" is exact - and it matches `kill` and
`msg`, so there is one addressing scheme to remember rather than three.

Only dispatch is tested here. Reading stdin is glue.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import textwrap
from pathlib import Path

from src.agents._control import AgentMailbox
from src.agents._human import HumanChannel
from src.operator_console import OperatorConsole
from src.orchestrator import TableRunResult, TableTaskRegistry


async def _blocks_forever(table: str) -> TableRunResult:
    await asyncio.Event().wait()
    raise AssertionError("unreachable")


def _console() -> tuple[OperatorConsole, HumanChannel, TableTaskRegistry, AgentMailbox]:
    human = HumanChannel()
    registry = TableTaskRegistry()
    mailbox = AgentMailbox()
    return OperatorConsole(human, registry, mailbox), human, registry, mailbox


def test_blank_input_says_nothing():
    console, *_ = _console()

    assert console.dispatch("   ") == ""


def test_unknown_command_shows_the_usage():
    console, *_ = _console()

    reply = console.dispatch("frobnicate")

    assert "kill" in reply and "msg" in reply


def test_q_reports_an_empty_queue_plainly():
    console, *_ = _console()

    assert "没有" in console.dispatch("q")


async def test_q_lists_a_waiting_question_under_its_table():
    console, human, *_ = _console()
    asking = asyncio.create_task(human.ask("dms_order_details_info", "这张表在哪个菜单？"))
    await asyncio.sleep(0)

    reply = console.dispatch("q")

    assert "dms_order_details_info" in reply
    assert "这张表在哪个菜单？" in reply

    asking.cancel()


async def test_a_delivers_the_answer_to_the_waiting_table():
    console, human, *_ = _console()
    asking = asyncio.create_task(human.ask("dms_order_details_info", "在哪？"))
    await asyncio.sleep(0)

    reply = console.dispatch("a dms_order_details_info 订单管理 > 我的订单")

    assert "dms_order_details_info" in reply
    assert await asking == "订单管理 > 我的订单"


def test_a_reports_when_that_table_is_not_waiting_on_anything():
    console, *_ = _console()

    reply = console.dispatch("a dms_order_details_info 随便")

    assert "dms_order_details_info" in reply
    assert "没有" in reply


async def test_a_without_an_answer_refuses_rather_than_sending_an_empty_one():
    """An empty answer would unblock the agent with nothing to act on, and
    the question would be gone - unrecoverable from the operator's side."""
    console, human, *_ = _console()
    asking = asyncio.create_task(human.ask("dms_order_details_info", "在哪？"))
    await asyncio.sleep(0)

    reply = console.dispatch("a dms_order_details_info")

    assert not asking.done()
    assert "用法" in reply

    asking.cancel()


async def test_ps_lists_the_tables_still_running():
    console, _, registry, _ = _console()
    registry.launch("dms_order_details_info", _blocks_forever("dms_order_details_info"))
    await asyncio.sleep(0)

    assert "dms_order_details_info" in console.dispatch("ps")

    registry.cancel("dms_order_details_info")
    await registry.gather()


def test_ps_reports_an_idle_run_plainly():
    console, *_ = _console()

    assert "没有" in console.dispatch("ps")


async def test_kill_cancels_the_named_table():
    console, _, registry, _ = _console()
    registry.launch("dms_order_details_info", _blocks_forever("dms_order_details_info"))
    registry.launch("dms_bill_details_info", _blocks_forever("dms_bill_details_info"))
    await asyncio.sleep(0)

    reply = console.dispatch("kill dms_order_details_info 入口判错了")

    assert "dms_order_details_info" in reply
    await asyncio.sleep(0)
    assert registry.running() == ["dms_bill_details_info"]

    registry.cancel("dms_bill_details_info")
    await registry.gather()


def test_kill_reports_a_table_that_is_not_running():
    console, *_ = _console()

    reply = console.dispatch("kill dms_order_details_info")

    assert "dms_order_details_info" in reply
    assert "没有" in reply


async def test_msg_queues_a_message_for_a_running_table():
    console, _, registry, mailbox = _console()
    registry.launch("dms_order_details_info", _blocks_forever("dms_order_details_info"))
    await asyncio.sleep(0)

    console.dispatch("msg dms_order_details_info 先确认核载体，别急着翻页")

    assert mailbox.drain("dms_order_details_info") == ["先确认核载体，别急着翻页"]

    registry.cancel("dms_order_details_info")
    await registry.gather()


async def test_msg_refuses_a_table_that_is_not_running():
    console, _, registry, mailbox = _console()

    reply = console.dispatch("msg dms_order_details_info 喂？")

    assert mailbox.drain("dms_order_details_info") == []
    assert "没有" in reply


async def test_msg_without_a_body_refuses():
    console, _, registry, mailbox = _console()
    registry.launch("dms_order_details_info", _blocks_forever("dms_order_details_info"))
    await asyncio.sleep(0)

    reply = console.dispatch("msg dms_order_details_info")

    assert mailbox.drain("dms_order_details_info") == []
    assert "用法" in reply

    registry.cancel("dms_order_details_info")
    await registry.gather()


def test_help_lists_every_command():
    console, *_ = _console()

    reply = console.dispatch("help")

    for command in ("q", "a", "ps", "kill", "msg"):
        assert command in reply


def test_cancelling_the_console_does_not_hang_the_process_at_exit(tmp_path: Path):
    """`asyncio.to_thread(input)` reads correctly and then never lets the
    process die: `asyncio.run()` joins the default executor on its way out,
    and that worker is blocked in `input()` until stdin closes. Cancelling the
    task does not touch the thread. A run that finished all six tables would
    hang at the very end, with nothing on screen saying why.

    Only a subprocess can show this - the deadlock is in interpreter shutdown.
    """
    script = tmp_path / "exit_check.py"
    script.write_text(
        textwrap.dedent(
            """
            import asyncio
            from dms_survey.agents._control import AgentMailbox
            from dms_survey.agents._human import HumanChannel
            from dms_survey.operator_console import OperatorConsole
            from dms_survey.orchestrator import TableTaskRegistry

            async def main():
                console = OperatorConsole(HumanChannel(), TableTaskRegistry(), AgentMailbox())
                task = asyncio.create_task(console.run())
                await asyncio.sleep(0.3)
                task.cancel()

            asyncio.run(main())
            print("exited cleanly")
            """
        ),
        encoding="utf-8",
    )
    repo_root = Path(__file__).resolve().parents[2]

    # stdin stays open and silent - exactly the operator who types nothing.
    proc = subprocess.Popen(
        [sys.executable, str(script)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=repo_root,
        env={**os.environ, "PYTHONPATH": str(repo_root)},
        text=True,
    )
    # Deliberately not `communicate()`: it would close stdin, handing the
    # reader an EOF and hiding the very deadlock under test.
    try:
        returncode = proc.wait(timeout=20)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        raise AssertionError("the console kept the process alive after being cancelled")
    finally:
        if proc.stdin is not None:
            proc.stdin.close()

    stdout = proc.stdout.read() if proc.stdout else ""
    stderr = proc.stderr.read() if proc.stderr else ""
    assert returncode == 0, stderr
    assert "exited cleanly" in stdout
