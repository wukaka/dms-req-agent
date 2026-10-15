"""Business ("table") agent: two-phase verdict-then-mapping (design §6).

Phase 1 (判定) always runs. Phase 2 (字段映射) only runs if phase 1's verdict
is `exists`/`partial` (`models.PRODUCING`) - the hard gate from design §6.1:
"agent 必须能『一张表都没交』地成功完成任务". `run_table_agent()` is the one
entry point that enforces this; nothing else in this module calls phase 2.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any, Optional

from agentscope.agent import Agent, ReActConfig
from agentscope.mcp import MCPClient
from agentscope.message import Msg, TextBlock
from agentscope.middleware import MiddlewareBase
from agentscope.model import ChatModelBase
from agentscope.tool import FunctionTool, Toolkit

from ..models import PRODUCING, TABLES, EvidenceTable, ScreenshotResult, TableVerdict
from ._events import EventSink, structured
from ._permission import bypass_permission_state

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

#: JSReverser tools a *business* (verdict + field-mapping) agent may use.
#: `take_screenshot` is deliberately absent: screenshots and annotation are
#: phase 3's job (`screenshot_rules.md`), and `common_rules.md` tells the
#: business agent not to call it. Keeping it out of `enable_tools` means the
#: LLM is never shown the schema, so it cannot call it by accident.
TABLE_AGENT_TOOLS: tuple[str, ...] = (
    "list_pages",
    "select_page",
    "list_frames",
    "select_frame",
    "list_network_requests",
    "get_network_request",
    "evaluate_script",
    "get_dom_structure",
    "query_dom",
    "find_clickable_elements",
    "wait_for_element",
    "click_element",
    "type_text",
    "get_storage",
    "list_console_messages",
    "get_console_message",
)

#: JSReverser tools for phase 3's screenshot agent: the business surface plus
#: `take_screenshot`. The annotator MCP (red-box drawing) is a separate
#: client and only ever attached to this agent.
SCREENSHOT_AGENT_TOOLS: tuple[str, ...] = TABLE_AGENT_TOOLS + ("take_screenshot",)


def system_prompt(table: str) -> str:
    """common_rules.md + this table's own field prompt only (design §6.2:
    the other 5 tables' definitions are explicitly withheld)."""
    if table not in TABLES:
        raise ValueError(f"unknown table '{table}', must be one of {TABLES}")
    common = (_PROMPTS_DIR / "common_rules.md").read_text(encoding="utf-8")
    field = (_PROMPTS_DIR / "fields" / f"{table}.md").read_text(encoding="utf-8")
    return common + "\n\n---\n\n" + field


def screenshot_system_prompt(table: str) -> str:
    """screenshot_rules.md + this table's own field prompt.

    The field prompt comes along because annotation numbers *are* the
    standard field numbers defined there - without it the agent would have to
    guess which number goes on which column. `common_rules.md` deliberately
    does not: by phase 3 the field mapping is frozen and human-confirmed, and
    re-reading the mapping rules is exactly the invitation to re-litigate it.
    """
    if table not in TABLES:
        raise ValueError(f"unknown table '{table}', must be one of {TABLES}")
    rules = (_PROMPTS_DIR / "screenshot_rules.md").read_text(encoding="utf-8")
    field = (_PROMPTS_DIR / "fields" / f"{table}.md").read_text(encoding="utf-8")
    return rules + "\n\n---\n\n" + field


def build_table_agent(
    table: str,
    model: ChatModelBase,
    jsreverser: MCPClient,
    middlewares: Optional[list[MiddlewareBase]] = None,
) -> Agent:
    """Construct one table agent, named after its table.

    `jsreverser` must already be connected (see
    `discovery.build_discovery_agent`'s docstring for why) and should be built
    with `enable_tools=TABLE_AGENT_TOOLS`. No annotator client here: the
    business agent does not screenshot or annotate (phase 3 does), so it has
    no red-box capability at all. `middlewares` is where the orchestrator
    wires in `browser_queue.BrowserQueueMiddleware`; the `ask_judge` tool
    (design §7.2) is added afterwards via `agent.toolkit.add_tool()`, not
    through this constructor, since it needs a live Judge agent and a
    per-table budget counter built by the caller.
    """
    return Agent(
        name=table,
        system_prompt=system_prompt(table),
        model=model,
        toolkit=Toolkit(mcps=[jsreverser]),
        react_config=ReActConfig(max_iters=120),
        middlewares=middlewares,
        state=bypass_permission_state(),
    )


#: Cap on what `read_file` returns in one call. Archived responses run to a
#: few hundred KB and an agent only needs enough to recognise the shape of
#: what it already captured.
READ_FILE_CHAR_LIMIT = 100_000


def _resolve_in_scope(platform_dir: Path, table: str, relative_path: str) -> "Path | str":
    """Map a relative path to an absolute one, or return the refusal text.

    Two layers: the path must land inside `tables/`/`files/` (via
    `.resolve()`, so `../..` segments cannot escape the platform
    directory), *and* it must be a name this table owns. Ownership is
    encoded in the name itself - `tables/<table>.md` and `files/<table>_*` -
    which is what makes `existing_artifacts()` able to attribute leftovers
    from an interrupted pass to the right table without a side ledger, and
    keeps one table from reading another's archive (design §6.2).
    """
    tables_root = (platform_dir / "tables").resolve()
    files_root = (platform_dir / "files").resolve()
    target = (platform_dir / relative_path).resolve()

    if target.parent == tables_root:
        if target.name != f"{table}.md":
            return (
                f"'{relative_path}' 不是本表的文档：tables/ 下你只能读写 "
                f"tables/{table}.md。"
            )
        return target
    if target.parent == files_root:
        if not target.name.startswith(f"{table}_"):
            return (
                f"'{relative_path}' 不是本表的存档：files/ 下的文件名必须以 "
                f"'{table}_' 开头，例如 files/{table}_列表页_0.json。"
            )
        return target
    return f"'{relative_path}' 不在允许范围内，路径必须是 tables/{table}.md 或 files/{table}_*。"


def make_write_file_tool(platform_dir: Path, table: str) -> FunctionTool:
    """Give a table agent a way to persist prose/archival content to disk.

    `prompts/common_rules.md` was already written (and reviewed) assuming
    agents have a generic "Write 工具" for exactly two purposes: `tables/`
    (its own `<表名>.md`, the prose `checks/consistency.py` scans) and
    `files/` (raw XHR/HTML/Excel archival, rule 11). Neither MCP client
    (jsreverser/annotator) can write arbitrary text - only images have a
    dedicated tool - so this closes that gap locally instead of through MCP.
    """

    async def write_file(relative_path: str, content: str, encoding: str = "utf-8") -> str:
        """把内容写入平台目录下的 files/ 或 tables/ 子目录。

        Args:
            relative_path: 相对平台目录的路径，只能是 "tables/<本表名>.md"，
                或以 "files/<本表名>_" 开头的存档文件。
            content: 要写入的文本内容；写二进制文件（如 .xlsx）时先转成 base64 字符串，
                并把 encoding 设为 "base64"。
            encoding: "utf-8"（默认，纯文本原样写入）或 "base64"（写入前对 content 做 base64 解码）。
        """
        if encoding not in ("utf-8", "base64"):
            return f"写入失败：不支持的 encoding '{encoding}'，只接受 utf-8 或 base64。"

        target = _resolve_in_scope(platform_dir, table, relative_path)
        if isinstance(target, str):
            return f"写入失败：{target}"

        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            if encoding == "base64":
                target.write_bytes(base64.b64decode(content))
            else:
                target.write_text(content, encoding="utf-8")
        except Exception as exc:  # noqa: BLE001 - report to the agent, don't crash its run
            return f"写入失败：{exc!r}"
        return f"已写入 {relative_path}"

    return FunctionTool(write_file, name="write_file")


def make_read_file_tool(platform_dir: Path, table: str) -> FunctionTool:
    """Let a table agent read back what an earlier, interrupted pass archived.

    Without this the resume digest in `_task_msg()` would only be able to
    *name* the leftovers: a crashed table would still have to re-drive the
    browser to recover content that is already sitting on disk.
    """

    async def read_file(relative_path: str, encoding: str = "utf-8") -> str:
        """读回本表之前写到 files/ 或 tables/ 的文件。

        Args:
            relative_path: 相对平台目录的路径，只能是 "tables/<本表名>.md"，
                或以 "files/<本表名>_" 开头的存档文件。
            encoding: "utf-8"（默认，按文本读取）或 "base64"（二进制文件，如 .xlsx，返回 base64 字符串）。
        """
        if encoding not in ("utf-8", "base64"):
            return f"读取失败：不支持的 encoding '{encoding}'，只接受 utf-8 或 base64。"

        target = _resolve_in_scope(platform_dir, table, relative_path)
        if isinstance(target, str):
            return f"读取失败：{target}"
        if not target.is_file():
            return f"读取失败：{relative_path} 不存在。"

        try:
            if encoding == "base64":
                text = base64.b64encode(target.read_bytes()).decode("ascii")
            else:
                text = target.read_text(encoding="utf-8")
        except Exception as exc:  # noqa: BLE001 - report to the agent, don't crash its run
            return f"读取失败：{exc!r}"

        if len(text) > READ_FILE_CHAR_LIMIT:
            return (
                text[:READ_FILE_CHAR_LIMIT]
                + f"\n\n…（已截断，全文 {len(text)} 字符，只返回前 {READ_FILE_CHAR_LIMIT} 字符）"
            )
        return text

    return FunctionTool(read_file, name="read_file")


def existing_artifacts(platform_dir: Path, table: str) -> list[Path]:
    """This table's own leftovers from an earlier pass, newest name order.

    Only names this table could have written are considered, so a shared
    `files/` directory does not leak one table's archive into another's
    context.
    """
    found = []
    doc = platform_dir / "tables" / f"{table}.md"
    if doc.is_file():
        found.append(doc)
    files_dir = platform_dir / "files"
    if files_dir.is_dir():
        found += sorted(p for p in files_dir.glob(f"{table}_*") if p.is_file())
    return found


def resume_digest(platform_dir: Path, table: str) -> str:
    """The 「已有产物」 section of a re-launched table agent's task message.

    Empty string when there is nothing on disk, so a first run's prompt is
    byte-identical to what it was before resume existed.
    """
    artifacts = existing_artifacts(platform_dir, table)
    if not artifacts:
        return ""
    lines = [
        "## 已有产物（上一轮中断前留下的，本轮可直接复用）",
        "",
        "| 路径 | 大小 |",
        "|------|------|",
    ]
    for path in artifacts:
        lines.append(f"| {path.parent.name}/{path.name} | {path.stat().st_size} 字节 |")
    lines += [
        "",
        "这些是你自己上一轮写下的。先用 `read_file` 读回来看看已经拿到了什么，",
        "只补采缺的部分，不要把已经存档过的请求重新跑一遍。",
        "若读回的内容与当前页面明显对不上（比如站点改版、账号换了），以当前页面为准，重采并覆盖同名文件。",
    ]
    return "\n".join(lines)


def _task_msg(
    entry: dict[str, Any],
    anchors: dict[str, Any],
    blackboard: str,
    resume: str = "",
) -> Msg:
    """The per-run context a table agent gets (design §6.2 left column: its
    own table's Discovery entry, the anchors, blackboard.md - plus, on a
    re-launch, `resume_digest()` for its own leftovers and nothing else).

    Deliberately no screenshot directory here: this agent does not screenshot
    or annotate (see `common_rules.md`'s 「字段的页面形态」 section), so the
    phase-3 path would only invite it to try.
    """
    parts = [
        "## Discovery 提名的入口 (entry)",
        "```json",
        json.dumps(entry, ensure_ascii=False, indent=2),
        "```",
        "## discovery.anchors（无条件遵守）",
        "```json",
        json.dumps(anchors, ensure_ascii=False, indent=2),
        "```",
    ]
    if blackboard:
        parts += ["## blackboard.md", blackboard]
    if resume:
        parts += ["", resume]
    parts += [
        "",
        "先完成第一段判定：核载体唯一性、核粒度、必要时下钻一层确认有无更细数据。",
        "verdict 不是 exists/partial 时，写完结论直接退出，不做任何字段映射。",
    ]
    return Msg(
        name="orchestrator",
        role="user",
        content=[TextBlock(type="text", text="\n".join(parts))],
    )


async def run_verdict(
    agent: Agent,
    entry: dict[str, Any],
    anchors: dict[str, Any],
    blackboard: str = "",
    on_event: Optional[EventSink] = None,
    resume: str = "",
) -> TableVerdict:
    """Phase 1 (判定). Never does field mapping."""
    return await structured(
        agent,
        _task_msg(entry, anchors, blackboard, resume),
        TableVerdict,
        on_event,
    )


async def run_field_mapping(agent: Agent, on_event: Optional[EventSink] = None) -> EvidenceTable:
    """Phase 2 (字段映射). Only call after run_verdict() cleared the gate."""
    msg = Msg(
        name="orchestrator",
        role="user",
        content=[TextBlock(
            type="text",
            text=(
                "门禁已通过，进入第二段：逐字段对标准字段、查中文字典映射、"
                "归档原始响应、把「待截图字段清单」写进分片文档。"
                "截图与标注不在这里做，由阶段三的截图 agent 在人工确认字段映射后进行。"
            ),
        )],
    )
    return await structured(agent, msg, EvidenceTable, on_event)


async def run_table_agent(
    agent: Agent,
    entry: dict[str, Any],
    anchors: dict[str, Any],
    blackboard: str = "",
    on_event: Optional[EventSink] = None,
    resume: str = "",
) -> "tuple[TableVerdict, Optional[EvidenceTable]]":
    """The full two-phase protocol, gate included. This is the one function
    orchestrator.py should call per table - it is what makes 'zero tables
    submitted' a valid, successful outcome rather than something the caller
    has to special-case."""
    verdict = await run_verdict(
        agent, entry, anchors, blackboard, on_event, resume
    )
    if verdict.existence not in PRODUCING:
        return verdict, None
    evidence = await run_field_mapping(agent, on_event)
    return verdict, evidence


def build_screenshot_agent(
    table: str,
    model: ChatModelBase,
    jsreverser: MCPClient,
    annotator: MCPClient,
    middlewares: Optional[list[MiddlewareBase]] = None,
) -> Agent:
    """Phase 3's agent: same tools as a table agent, different instructions.

    Named `<table>-screenshot` rather than `<table>` so the operator console's
    `ps`/`kill`/`msg` can tell a screenshot round apart from a field-mapping
    round for the same table.
    """
    return Agent(
        name=f"{table}-screenshot",
        system_prompt=screenshot_system_prompt(table),
        model=model,
        toolkit=Toolkit(mcps=[jsreverser, annotator]),
        react_config=ReActConfig(max_iters=60),
        middlewares=middlewares,
        state=bypass_permission_state(),
    )


def _screenshot_task_msg(
    entry: dict[str, Any],
    evidence: dict[str, Any],
    images_dir: str,
) -> Msg:
    """What phase 3 gets: the entry to navigate back to, and the *confirmed*
    field mapping to annotate against - nothing that invites re-deciding it.

    The draft document is not inlined here: the agent reads it back with
    `read_file` itself, which keeps a long document out of the opening
    context and forces it to work from what is actually on disk.
    """
    parts = [
        "## 载体页 entry（用 SPA 点击回到这里，不要 navigate/刷新）",
        "```json",
        json.dumps(entry, ensure_ascii=False, indent=2),
        "```",
        "## 已确认的字段映射（人工已审核，不得改动）",
        "```json",
        json.dumps(evidence, ensure_ascii=False, indent=2),
        "```",
        "## 截图目录（绝对路径，已建好）",
        f"`{images_dir}`",
        "take_screenshot 的 filePath、annotate_screenshot 的 input_path/output_path"
        " 一律拼在这个绝对路径后面。",
        "",
        "先 `read_file(relative_path=\"tables/<本表名>.md\")` 读回草稿，按其中的"
        "「待截图字段清单」逐项截图标注；清单写明无页面可见字段时，直接返回 "
        "skipped=true，不要截图。",
        "最后把补好截图小节的**完整**文档 `write_file` 写回同一路径。",
    ]
    return Msg(
        name="orchestrator",
        role="user",
        content=[TextBlock(type="text", text="\n".join(parts))],
    )


async def run_screenshot_phase(
    agent: Agent,
    entry: dict[str, Any],
    evidence: dict[str, Any],
    images_dir: str,
    on_event: Optional[EventSink] = None,
) -> ScreenshotResult:
    """Phase 3 (截图标注). Only reached after a human set `fields_confirmed`."""
    return await structured(
        agent,
        _screenshot_task_msg(entry, evidence, images_dir),
        ScreenshotResult,
        on_event,
    )
