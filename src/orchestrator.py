"""AgentScope orchestration: Discovery -> fan-out business agents -> Judge.

Design doc §3 and §9; see docs/superpowers/specs/2026-09-17-dms-survey-*.md.

Split in two halves, per the handoff note in
docs/superpowers/specs/2026-09-17-dms-survey-progress.md §3:

- Pure functions (top of file): decide what to do from `manifest.json` /
  `evidence_index.json` state alone. Unit-tested with plain dicts, no
  MCP/LLM involved.
- `run_platform()` and its helpers (bottom of file): construct real MCP
  clients and agents and drive the pure functions' decisions. Not unit
  tested - only structural/type correctness, per the same handoff note.

Resume model: after Discovery runs, its `DiscoveryResult` is immediately
persisted into `manifest.json` via `persist_discovery()` and never held in
memory across a process boundary. Every decision after that point (which
tables to launch, which are pending_human, ...) reads `manifest["tables"]`
- plain JSON dicts - rather than the `TableTriage` pydantic objects Discovery
returned. This sidesteps a real conflict: `TableTriage` structurally forbids
`existence: "absent"` (design §5.3 纪律②, enforced by a validator in
models.py), but a human resolving a `pending_human` entry between runs does
exactly that by hand-editing the manifest. Plain dicts have no such
constraint, so resuming after a human edit just works.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator, Coroutine, Iterable, Optional, Sequence

from agentscope.agent import Agent
from agentscope.model import ChatModelBase

from .agents._control import (
    AgentMailbox,
    MailboxMiddleware,
    make_send_message_tool,
    make_terminate_agent_tool,
)
from .agents._events import ConsoleSink, EventSink, JsonlEventLog, tee
from .agents._human import HumanChannel, make_ask_human_tool
from .agents.discovery import DISCOVERY_TOOLS, build_discovery_agent, run_discovery
from .agents.judge import build_judge_agent, check_consistency, compile_documents, make_ask_judge_tool
from .agents.table_agent import (
    SCREENSHOT_AGENT_TOOLS,
    TABLE_AGENT_TOOLS,
    build_screenshot_agent,
    build_table_agent,
    make_read_file_tool,
    make_write_file_tool,
    resume_digest,
    run_screenshot_phase,
    run_table_agent,
)
from .browser_queue import BrowserQueue, BrowserQueueMiddleware
from .mcp_client import JSREVERSER_NAME, annotator_client, jsreverser_client, qualify, require_available
from .model_config import build_chat_model
from .models import (
    PRODUCING,
    DiscoveryResult,
    EvidenceTable,
    Existence,
    ScreenshotResult,
    TableVerdict,
)
from .operator_console import OperatorConsole
from .store import BLACKBOARD, Store

_PRODUCING_VALUES = frozenset(e.value for e in PRODUCING)

# ---------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------


def discovery_already_done(manifest: dict[str, Any]) -> bool:
    """True once a previous run's Discovery block has been persisted."""
    return bool(manifest.get("discovery", {}).get("verified_at"))


def table_has_field_evidence(table: str, evidence_index: dict[str, Any]) -> bool:
    return bool(evidence_index.get(table, {}).get("fields"))


def table_is_settled(entry: dict[str, Any], evidence_index: dict[str, Any]) -> bool:
    """Has this table's manifest entry already reached a final state?

    Non-producing verdicts (absent/granularity_mismatch) are final the
    moment they are written - no business agent ever runs for them.
    Producing verdicts (exists/partial) are only settled once field mapping
    actually happened, i.e. evidence_index carries their fields; a producing
    verdict with no evidence yet still needs its business agent launched
    (or re-launched, after a crash mid-run).
    """
    existence = entry.get("existence")
    if not existence:
        return False
    if existence not in _PRODUCING_VALUES:
        return True
    return table_has_field_evidence(entry.get("table", ""), evidence_index)


def tables_to_launch(
    manifest_tables: list[dict[str, Any]],
    evidence_index: dict[str, Any],
) -> list[dict[str, Any]]:
    """Manifest entries whose business agent still needs to run."""
    return [
        entry
        for entry in manifest_tables
        if entry.get("existence") in _PRODUCING_VALUES
        and not table_is_settled(entry, evidence_index)
    ]


def pending_human_entries(manifest_tables: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [t for t in manifest_tables if t.get("existence") == Existence.PENDING_HUMAN.value]


def needs_screenshot_round(entry: dict[str, Any], evidence_index: dict[str, Any]) -> bool:
    """Has this table reached phase 3's doorstep but not walked through it?

    True for a producing table whose field mapping exists, whose screenshot
    round has not run, and which has no unresolved `deferred_questions` -
    i.e. everything settled except the human's go-ahead. Says nothing about
    whether that go-ahead has been given; `fields_confirmed` is what splits
    the two callers below.

    Tables finished under the old single-pass flow carry
    `screenshots_done: true` (backfilled by hand) and drop out here, which is
    what "不追溯" means in practice.
    """
    if entry.get("existence") not in _PRODUCING_VALUES:
        return False
    if entry.get("screenshots_done") is True:
        return False
    if entry.get("deferred_questions"):
        return False
    return table_has_field_evidence(entry.get("table", ""), evidence_index)


def tables_awaiting_field_confirmation(
    manifest_tables: list[dict[str, Any]],
    evidence_index: dict[str, Any],
) -> list[dict[str, Any]]:
    """Field mapping done, nothing disputed, human has not signed off yet."""
    return [
        entry
        for entry in manifest_tables
        if needs_screenshot_round(entry, evidence_index)
        and entry.get("fields_confirmed") is not True
    ]


def tables_ready_for_screenshot(
    manifest_tables: list[dict[str, Any]],
    evidence_index: dict[str, Any],
) -> list[dict[str, Any]]:
    """Same set, but the human has set `fields_confirmed: true` by hand."""
    return [
        entry
        for entry in manifest_tables
        if needs_screenshot_round(entry, evidence_index)
        and entry.get("fields_confirmed") is True
    ]


def field_confirmation_questions(entries: list[dict[str, Any]]) -> list[str]:
    """The human-facing ask for the field-mapping review checkpoint.

    Screenshots are the expensive, throwaway-on-change part of a table's
    work: re-deciding one field's source after the fact invalidates the
    annotation that pointed at it. So the browser is not touched again until
    someone has read the field table and said so explicitly.
    """
    return [
        f"{entry.get('table')}：字段映射已产出，请审核 tables/{entry.get('table')}.md 的字段采集表"
        f"与「待截图字段清单」；确认无误后在 manifest.json 里把该表的 "
        f'"fields_confirmed" 设为 true，重跑即进入截图标注阶段。'
        for entry in entries
    ]


def collect_deferred_questions(manifest_tables: list[dict[str, Any]]) -> list[str]:
    """§8.3 `deferred` blockers, attued from every table's verdict/evidence.

    Business agents write these into `TableVerdict.deferred_questions` /
    `EvidenceTable.deferred_questions` (see models.py); `persist_table_result`
    copies them onto the manifest entry as `deferred_questions`. Reading from
    the manifest rather than from a live batch of `TableRunResult` is what
    lets this survive a process restart: a table that is already
    `table_is_settled()` never runs its business agent again, so its
    unresolved questions would otherwise vanish the moment `to_launch` is
    empty on a later run.

    A human resolves one by editing it away (or emptying the list) in
    `manifest.json`, the same hand-edit protocol as `pending_human` - there is
    no "answered" flag to flip.
    """
    lines: list[str] = []
    for entry in manifest_tables:
        for question in entry.get("deferred_questions") or []:
            lines.append(f"{entry.get('table')}：{question}")
    return lines


def pending_human_questions(manifest_tables: list[dict[str, Any]]) -> list[str]:
    """§9.3 人工中断点①: one question per still-undecided table."""
    lines = []
    for entry in pending_human_entries(manifest_tables):
        menu_path = entry.get("entry", {}).get("menu_path", "")
        lines.append(
            f"{entry.get('table')}：Discovery 判定 pending_human"
            f"（{menu_path or '零命中'}），请对照 menu_map.md 拍板 existence。"
        )
    return lines


def persist_discovery(store: Store, manifest: dict[str, Any], result: DiscoveryResult) -> dict[str, Any]:
    """Write a freshly-run Discovery's output into manifest.json + menu_map.md.

    This is the only place a `DiscoveryResult` (and its `TableTriage`
    objects) touches disk - after this call every downstream decision reads
    the plain-dict manifest, per the module docstring's resume model.
    """
    manifest = store.ensure_tables(manifest)
    manifest = store.set_discovery(manifest, result.discovery)
    for triage in result.tables:
        manifest = store.set_verdict(
            manifest,
            triage.table,
            triage.existence,
            entry=triage.entry,
            notes=triage.rationale,
        )
    store.save_manifest(manifest)
    (store.dir / "menu_map.md").write_text(result.menu_tree_markdown, encoding="utf-8")
    return manifest


def read_blackboard(store: Store) -> str:
    path = store.dir / BLACKBOARD
    return path.read_text(encoding="utf-8") if path.exists() else ""


def read_tables_markdown(platform_dir: Path) -> dict[str, str]:
    """tables/<table>.md files a finished business agent left behind, keyed
    by table name - the raw material `agents.judge.compile_documents` needs
    for §8.4 合稿."""
    tables_dir = platform_dir / "tables"
    if not tables_dir.is_dir():
        return {}
    return {p.stem: p.read_text(encoding="utf-8") for p in sorted(tables_dir.glob("*.md"))}


def browser_queue_tool_names(tool_names: Iterable[str]) -> frozenset[str]:
    """Names `BrowserQueueMiddleware` must match at runtime.

    `DISCOVERY_TOOLS`/`TABLE_AGENT_TOOLS` are bare server-side tool names
    (correct for `MCPClient(enable_tools=...)`, which filters against the
    MCP server's raw tool list - see mcp_client.py). But the middleware
    compares against `tool_call.name`, which AgentScope has already renamed
    to `mcp__{client}__{tool}` by the time the LLM issues a call
    (agentscope/tool/_adapters.py `MCPTool.__init__`). Without this
    qualification the middleware's `in` check never matches a real browser
    tool call, and the single-browser-at-a-time guarantee (design §3.2)
    silently never engages.
    """
    return frozenset(qualify(JSREVERSER_NAME, t) for t in tool_names)


# ---------------------------------------------------------------------------
# Real MCP/LLM wiring
# ---------------------------------------------------------------------------


@dataclass
class TableRunResult:
    """One business agent's outcome. `error` set means design §8.3's
    `blocking` class (exception during the run, e.g. lost login/MCP
    disconnect) - the orchestrator aborts on the first one rather than
    accumulating, per the progress doc's `asyncio.gather` note."""

    table: str
    verdict: Optional[TableVerdict] = None
    evidence: Optional[EvidenceTable] = None
    error: Optional[BaseException] = None


class TableTaskRegistry:
    """Named, individually-cancellable handles on the in-flight table agents.

    Handing bare coroutines to `asyncio.gather()` left nothing to cancel by
    name, and its default `return_exceptions=False` re-raises the first
    failure into the caller while the siblings keep running - orphaned agents
    still driving the one shared browser after the coordinator has unwound.
    Every outcome is collected here instead, including a cancellation, so one
    table's death costs exactly one table.
    """

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task[TableRunResult]] = {}

    def launch(
        self, table: str, coro: Coroutine[Any, Any, TableRunResult]
    ) -> asyncio.Task[TableRunResult]:
        task = asyncio.create_task(coro, name=table)
        self._tasks[table] = task
        return task

    def cancel(self, table: str) -> bool:
        """True if a still-running table was asked to stop."""
        task = self._tasks.get(table)
        if task is None or task.done():
            return False
        task.cancel()
        return True

    def running(self) -> list[str]:
        return [table for table, task in self._tasks.items() if not task.done()]

    async def gather(self, tables: Optional[Iterable[str]] = None) -> list[TableRunResult]:
        """Await the launched tasks - all of them, or just the named ones.

        The filter exists because one run can hold two rounds (field mapping,
        then screenshots) against the same registry, keyed by the same table
        names. Without it the second round would re-gather the first round's
        finished tasks and hand their results to a caller expecting its own.
        """
        selected = (
            self._tasks
            if tables is None
            else {t: self._tasks[t] for t in tables if t in self._tasks}
        )
        outcomes = await asyncio.gather(*selected.values(), return_exceptions=True)
        return [
            TableRunResult(table=table, error=outcome)
            if isinstance(outcome, BaseException)
            else outcome
            for table, outcome in zip(selected, outcomes)
        ]


async def close_quietly(
    client: Any,
    client_name: str,
    table: str,
    on_event: Optional[EventSink] = None,
) -> None:
    """Close one MCP client without letting teardown rewrite the outcome.

    `await client.close()` raises on its own while a task unwinds - anyio's
    "Attempted to exit a cancel scope that isn't the current task's" is how a
    real model failure got replaced by a `CancelledError` in production - and
    a raise here also skips the sibling client's close. Swallow it, but record
    it: swallowed is not the same as hidden.
    """
    try:
        await client.close()
    except BaseException as exc:  # noqa: BLE001 - teardown must not mask the run's outcome
        if on_event is not None:
            on_event(table, {
                "type": "mcp_close_failed",
                "client": client_name,
                "error": f"{type(exc).__name__}: {exc}",
            })


def table_run_questions(
    results: "Sequence[TableRunResult | ScreenshotRunResult]",
) -> list[str]:
    """One human-facing line per table that did not finish.

    Takes either round's result type - a field-mapping run and a screenshot
    run fail the same two ways (operator cancelled it / it broke), and the
    human-facing wording is the same.

    A cancellation is an operator's decision, not a fault - filing it under
    "登录态/MCP 断连" would send someone chasing a bug that never happened.
    Note the classes stay apart on their own: `registry.gather()` only turns a
    *child's* cancellation into a result, while a shutdown that cancels the
    gather itself still propagates.
    """
    lines: list[str] = []
    for result in results:
        if result.error is None:
            continue
        if isinstance(result.error, asyncio.CancelledError):
            lines.append(f"{result.table}：已被人工中止，本轮未完成；下次重跑将从头开始。")
        else:
            lines.append(
                f"{result.table}：运行异常需要人工排查（登录态/MCP 断连等）：{result.error!r}"
            )
    return lines


def persist_table_result(
    store: Store,
    manifest: dict[str, Any],
    evidence_index: dict[str, Any],
    result: TableRunResult,
) -> dict[str, Any]:
    """Write one finished table's verdict + evidence straight to disk.

    Called per result rather than once over the whole batch: a later table
    failing (or being cancelled) must not cost an earlier one its work, which
    is exactly what the old collect-then-write-unless-any-failed path did.
    """
    if result.verdict is None:
        return manifest
    deferred = list(result.verdict.deferred_questions)
    if result.evidence is not None:
        deferred += result.evidence.deferred_questions
    manifest = store.set_verdict(
        manifest,
        result.table,
        result.verdict.existence,
        notes=result.verdict.rationale,
        deferred_questions=deferred,
    )
    if result.evidence is not None:
        payload = result.evidence.model_dump(mode="json")
        evidence_index[result.table] = payload
        store.merge_evidence(result.table, payload)
    store.save_manifest(manifest)
    return manifest


@dataclass
class ScreenshotRunResult:
    """One screenshot round's outcome. Mirrors `TableRunResult`'s shape so
    `table_run_questions()` can classify its failures the same way."""

    table: str
    result: Optional[ScreenshotResult] = None
    error: Optional[BaseException] = None


def persist_screenshot_result(
    store: Store,
    manifest: dict[str, Any],
    run: ScreenshotRunResult,
) -> dict[str, Any]:
    """Close one table's screenshot round on disk, per result (same reason as
    `persist_table_result`: a sibling's failure must not cost this one its
    browser work)."""
    if run.result is None:
        return manifest
    manifest = store.mark_screenshots_done(
        manifest,
        run.table,
        images=run.result.annotated_images,
        notes=run.result.notes,
    )
    store.save_manifest(manifest)
    return manifest


async def _run_discovery_phase(
    store: Store,
    manifest: dict[str, Any],
    model: ChatModelBase,
    queue: BrowserQueue,
    human: HumanChannel,
    on_event: Optional[EventSink] = None,
) -> dict[str, Any]:
    jsr = jsreverser_client(enable_tools=list(DISCOVERY_TOOLS))
    await jsr.connect()
    try:
        agent = build_discovery_agent(
            model,
            jsr,
            middlewares=[BrowserQueueMiddleware(queue, browser_queue_tool_names(DISCOVERY_TOOLS))],
        )
        await agent.toolkit.add_tool(make_ask_human_tool(human, agent.name), group_name="basic")
        result = await run_discovery(agent, blackboard=read_blackboard(store), on_event=on_event)
    finally:
        await jsr.close()
    return persist_discovery(store, manifest, result)


async def _run_one_table(
    model: ChatModelBase,
    queue: BrowserQueue,
    judge_agent: Agent,
    entry: dict[str, Any],
    anchors: dict[str, Any],
    blackboard: str,
    evidence_index: dict[str, Any],
    platform_dir: Path,
    human: HumanChannel,
    mailbox: AgentMailbox,
    on_event: Optional[EventSink] = None,
) -> TableRunResult:
    table = entry["table"]
    jsr = jsreverser_client(enable_tools=list(TABLE_AGENT_TOOLS))
    await jsr.connect()
    try:
        agent = build_table_agent(
            table,
            model,
            jsr,
            middlewares=[
                BrowserQueueMiddleware(queue, browser_queue_tool_names(TABLE_AGENT_TOOLS)),
                MailboxMiddleware(mailbox),
            ],
        )
        await agent.toolkit.add_tool(
            make_ask_judge_tool(judge_agent, evidence_index, from_table=table),
            group_name="basic",
        )
        await agent.toolkit.add_tool(make_write_file_tool(platform_dir, table), group_name="basic")
        await agent.toolkit.add_tool(make_read_file_tool(platform_dir, table), group_name="basic")
        await agent.toolkit.add_tool(make_ask_human_tool(human, table), group_name="basic")
        verdict, evidence = await run_table_agent(
            agent, entry.get("entry", {}), anchors, blackboard, on_event,
            resume=resume_digest(platform_dir, table),
        )
        return TableRunResult(table=table, verdict=verdict, evidence=evidence)
    except Exception as exc:  # noqa: BLE001 - classified by the caller, not raised further
        return TableRunResult(table=table, error=exc)
    finally:
        await close_quietly(jsr, JSREVERSER_NAME, table, on_event)


async def _run_table_agents(
    model: ChatModelBase,
    queue: BrowserQueue,
    judge_agent: Agent,
    to_launch: list[dict[str, Any]],
    anchors: dict[str, Any],
    blackboard: str,
    evidence_index: dict[str, Any],
    platform_dir: Path,
    human: HumanChannel,
    registry: TableTaskRegistry,
    mailbox: AgentMailbox,
    on_event: Optional[EventSink] = None,
) -> list[TableRunResult]:
    """Browser access is still fully serial (design §3.1/§3.2 - `queue`
    enforces this); what actually runs concurrently here is each agent's
    offline reasoning between browser calls."""
    for entry in to_launch:
        registry.launch(
            entry["table"],
            _run_one_table(
                model, queue, judge_agent, entry, anchors, blackboard,
                evidence_index, platform_dir, human, mailbox, on_event,
            ),
        )
    return await registry.gather()


async def _run_one_screenshot(
    model: ChatModelBase,
    queue: BrowserQueue,
    entry: dict[str, Any],
    evidence_index: dict[str, Any],
    platform_dir: Path,
    human: HumanChannel,
    mailbox: AgentMailbox,
    on_event: Optional[EventSink] = None,
) -> ScreenshotRunResult:
    """Phase 3 for one table.

    No `ask_judge` here: cross-table field questions belong to the mapping
    round, and by now that mapping is frozen and human-confirmed - a Judge
    query could only reopen it. `ask_human` stays as the stuck-on-the-page
    escape hatch.
    """
    table = entry["table"]
    jsr = jsreverser_client(enable_tools=list(SCREENSHOT_AGENT_TOOLS))
    ann = annotator_client()
    await jsr.connect()
    await ann.connect()
    try:
        agent = build_screenshot_agent(
            table,
            model,
            jsr,
            ann,
            middlewares=[
                BrowserQueueMiddleware(queue, browser_queue_tool_names(SCREENSHOT_AGENT_TOOLS)),
                MailboxMiddleware(mailbox),
            ],
        )
        await agent.toolkit.add_tool(make_write_file_tool(platform_dir, table), group_name="basic")
        await agent.toolkit.add_tool(make_read_file_tool(platform_dir, table), group_name="basic")
        await agent.toolkit.add_tool(make_ask_human_tool(human, table), group_name="basic")
        result = await run_screenshot_phase(
            agent,
            entry.get("entry", {}),
            evidence_index.get(table, {}),
            images_dir=str((platform_dir / "images").resolve()),
            on_event=on_event,
        )
        return ScreenshotRunResult(table=table, result=result)
    except Exception as exc:  # noqa: BLE001 - classified by the caller, not raised further
        return ScreenshotRunResult(table=table, error=exc)
    finally:
        await close_quietly(jsr, JSREVERSER_NAME, table, on_event)
        await close_quietly(ann, "annotator", table, on_event)


async def _run_screenshot_agents(
    model: ChatModelBase,
    queue: BrowserQueue,
    ready: list[dict[str, Any]],
    evidence_index: dict[str, Any],
    platform_dir: Path,
    human: HumanChannel,
    registry: TableTaskRegistry,
    mailbox: AgentMailbox,
    on_event: Optional[EventSink] = None,
) -> list[ScreenshotRunResult]:
    for entry in ready:
        registry.launch(
            entry["table"],
            _run_one_screenshot(
                model, queue, entry, evidence_index, platform_dir, human, mailbox, on_event,
            ),
        )
    # `registry.gather()` only wraps what it had to - a cancellation it caught
    # itself comes back as a `TableRunResult`, everything else passes through
    # as the `ScreenshotRunResult` `_run_one_screenshot` already returned.
    return [
        outcome
        if isinstance(outcome, ScreenshotRunResult)
        else ScreenshotRunResult(table=outcome.table, error=outcome.error)
        for outcome in await registry.gather([entry["table"] for entry in ready])
    ]


@asynccontextmanager
async def operator_console(
    human: HumanChannel,
    registry: TableTaskRegistry,
    mailbox: AgentMailbox,
) -> AsyncIterator[None]:
    """Run the typed half of the live view alongside the pipeline.

    Cancelled rather than awaited on the way out: the operator is not
    expected to type anything, so waiting for stdin to close would mean the
    run never ends.
    """
    task = asyncio.create_task(
        OperatorConsole(human, registry, mailbox).run(), name="operator-console"
    )
    try:
        yield
    finally:
        task.cancel()


async def run_platform(platform_dir: Path, platform: str) -> None:
    """Run one pass of the phase-1 pipeline for `platform_dir`.

    Both human interruption points are exit-style (design §9.3): this
    function writes `questions.md` and returns without raising. Re-running
    it after a human edits `manifest.json` picks up where it left off - it
    never holds progress in memory across calls.
    """
    await require_available()
    # take_screenshot writes the path it is given and will not create parent
    # directories, and table agents have no shell to `mkdir` with - so an
    # absent images/ silently pushes every screenshot to the process cwd.
    (platform_dir / "images").mkdir(parents=True, exist_ok=True)
    store = Store(platform_dir)
    manifest = store.ensure_tables(store.load_manifest())
    model = build_chat_model()
    queue = BrowserQueue()
    human = HumanChannel()
    registry = TableTaskRegistry()
    mailbox = AgentMailbox()
    on_event = tee(
        JsonlEventLog(platform_dir / "logs" / "agent_events.jsonl"),
        ConsoleSink(),
    )

    async with operator_console(human, registry, mailbox):
        if not discovery_already_done(manifest):
            manifest = await _run_discovery_phase(store, manifest, model, queue, human, on_event)

        manifest_tables = manifest.get("tables", [])
        pending = pending_human_entries(manifest_tables)
        if pending:
            store.write_questions(pending_human_questions(manifest_tables))

        evidence_index = store.load_evidence()
        to_launch = tables_to_launch(manifest_tables, evidence_index)

        if to_launch:
            judge_agent = build_judge_agent(model)
            await judge_agent.toolkit.add_tool(
                make_terminate_agent_tool(registry), group_name="basic"
            )
            await judge_agent.toolkit.add_tool(
                make_send_message_tool(mailbox, registry), group_name="basic"
            )
            anchors = manifest.get("discovery", {}).get("anchors", {})
            blackboard = read_blackboard(store)
            results = await _run_table_agents(
                model, queue, judge_agent, to_launch, anchors, blackboard,
                evidence_index, platform_dir, human, registry, mailbox, on_event,
            )

            for r in results:
                manifest = persist_table_result(store, manifest, evidence_index, r)

            unfinished = table_run_questions(results)
            if unfinished:
                store.write_questions(unfinished)
                return

        if pending:
            # §9.3 exit-style: producing tables finished this pass, but the
            # platform as a whole still waits on a human decision.
            return

        findings = check_consistency(manifest, evidence=evidence_index, platform_dir=platform_dir)
        if findings:
            store.write_questions([str(f) for f in findings])
            return

        deferred = collect_deferred_questions(manifest.get("tables", []))
        if deferred:
            # §9.3 exit-style: the questions land in questions.md, and a human
            # resolves them by editing the entries away in manifest.json (§8.3
            # deferred blockers have no other "answered" signal).
            store.write_questions(deferred)
            return

        manifest_tables = manifest.get("tables", [])
        awaiting = tables_awaiting_field_confirmation(manifest_tables, evidence_index)
        if awaiting:
            # 人工中断点③: screenshots are the expensive part and they point at
            # specific field sources, so the browser is not touched again until
            # a human has read the field table and set `fields_confirmed`.
            store.write_questions(field_confirmation_questions(awaiting))
            return

        ready = tables_ready_for_screenshot(manifest_tables, evidence_index)
        if ready:
            results = await _run_screenshot_agents(
                model, queue, ready, evidence_index, platform_dir,
                human, registry, mailbox, on_event,
            )
            for r in results:
                manifest = persist_screenshot_result(store, manifest, r)

            unfinished = table_run_questions(results)
            if unfinished:
                store.write_questions(unfinished)
                return

        judge_agent = build_judge_agent(model)
        docs = await compile_documents(
            judge_agent, platform, manifest, read_tables_markdown(platform_dir), on_event
        )
        (platform_dir / f"{platform}采集需求.md").write_text(docs.main_doc, encoding="utf-8")
        (platform_dir / f"{platform}技术笔记.md").write_text(docs.tech_notes, encoding="utf-8")
        manifest["phase"] = "done"
        store.save_manifest(manifest)
