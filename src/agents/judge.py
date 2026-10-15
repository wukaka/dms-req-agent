"""Judge agent: runtime query answering + consistency self-check (design §7-8).

Judge is offline (design §8.1: "运行中答疑...主体是机器查询...能确定性映射的
不挂模型") - it never touches a browser, so it gets no toolkit at all. The
deterministic half of both its jobs (evidence_index lookups, the five
consistency checks) is plain Python that runs *without* the model;
`agent.reply()` is only called for the genuinely semantic calls design §7.2
and §8.2①③ carve out.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from agentscope.agent import Agent, ReActConfig
from agentscope.message import Msg, TextBlock
from agentscope.model import ChatModelBase
from agentscope.tool import FunctionTool

from ..checks.consistency import run_all
from ..models import TABLES, ComposedDocs, CrossAgentQuery, Finding
from ._events import EventSink, structured

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

#: design §7.3: 追问链深度上限 1（不在此模块强制，由 orchestrator 不递归调用
#: ask_judge 的结果去生成新的 CrossAgentQuery 来保证）；每个 agent 提问预算 3 次。
MAX_QUERY_BUDGET_PER_AGENT = 3


def system_prompt() -> str:
    return (_PROMPTS_DIR / "judge.md").read_text(encoding="utf-8")


def build_judge_agent(model: ChatModelBase) -> Agent:
    """No toolkit: Judge reasons over text handed to it, it does not act."""
    return Agent(
        name="judge",
        system_prompt=system_prompt(),
        model=model,
        react_config=ReActConfig(max_iters=20),
    )


def answer_from_evidence(query: CrossAgentQuery, evidence_index: dict[str, Any]) -> Optional[str]:
    """§7.2 step 1: deterministic evidence_index lookup, no model call.

    Returns None on a miss rather than raising, so the caller can fall
    through to `ask_judge()` (which reads `files/` context via the model).
    """
    tables = query.scope or list(evidence_index.keys())
    for table in tables:
        payload = evidence_index.get(table, {})
        for field in payload.get("fields", []):
            if field.get("mapped_to") == query.about:
                return (
                    f"{table}.{field.get('path')}"
                    f"（type={field.get('type', '')}, samples={field.get('samples', [])}）"
                )
    return None


async def ask_judge(
    agent: Agent,
    query: CrossAgentQuery,
    evidence_index: dict[str, Any],
) -> str:
    """§7.2 full resolution order: evidence_index first, model second.

    Does not itself decide "still unresolved -> blocker" (§7.3 budget /
    §8.3 classification are the orchestrator's job); it always returns
    *some* answer, the caller judges whether that answer is good enough.
    """
    found = answer_from_evidence(query, evidence_index)
    if found is not None:
        return found

    msg = Msg(
        name="orchestrator",
        role="user",
        content=[TextBlock(
            type="text",
            text=(
                f"来自 {query.from_table} 的追问：{query.need}\n"
                f"（关于 {query.about}，范围限定：{query.scope or '未限定'}）\n"
                "evidence_index 里没有查到，凭你已有的上下文给出最佳判断，"
                "并说明这是推断还是确证。"
            ),
        )],
    )
    reply = await agent.reply(msg)
    return "".join(getattr(b, "text", "") for b in reply.content if getattr(b, "type", None) == "text")


def make_ask_judge_tool(
    judge_agent: Agent,
    evidence_index: dict[str, Any],
    from_table: str,
    budget: int = MAX_QUERY_BUDGET_PER_AGENT,
) -> FunctionTool:
    """Wrap `ask_judge()` into a tool one table agent's ReAct loop can call.

    `from_table` is baked in via closure so the schema the LLM sees only
    exposes `about`/`need`/`scope` (design §7.2's query shape minus the one
    field the caller can't get wrong). The budget (design §7.3: 3 per agent)
    is enforced here by a closure counter, not by raising - exceeding it
    returns guidance to decide from existing evidence instead; turning that
    into a `deferred` blocker (design §8.3) is the orchestrator's call, not
    this tool's.

    Add the result to one table agent's toolkit with
    `Toolkit.add_tool(tool, group_name='basic')` after construction - do not
    share one instance's budget counter across two table agents.
    """
    remaining = {"n": budget}

    async def ask_judge_tool(about: str, need: str, scope: Optional[list[str]] = None) -> str:
        """向 Judge 提出一个关于其他表证据的窄查询，用于确认本表字段与其他表的关联。

        Args:
            about: 想问清楚的标准字段名或概念，例如 "order_no"。
            need: 具体想要什么，例如 "order_no 的编码格式与2条样例"。
            scope: 限定查询范围的表名列表；留空则查全部已知表。
        """
        if remaining["n"] <= 0:
            return (
                "提问预算已用尽（每 agent 上限 3 次），请基于已有证据自行判断，"
                "无法确证时把这一点记为待人工确认，不要再继续追问。"
            )
        remaining["n"] -= 1
        query = CrossAgentQuery(from_table=from_table, about=about, need=need, scope=scope or [])
        return await ask_judge(judge_agent, query, evidence_index)

    return FunctionTool(ask_judge_tool, name="ask_judge")


def check_consistency(
    manifest: dict[str, Any],
    evidence: Optional[dict[str, Any]] = None,
    platform_dir: Optional[Path] = None,
) -> list[Finding]:
    """§8.2 五条一致性自检。②④⑤全代码；①③在 consistency.py 里只做正则粗筛，
    真正的语义判断（否定的作用域、粒度是否当真更细）仍需人或 judge 复核命中项。
    """
    return run_all(manifest, evidence=evidence, platform_dir=platform_dir)


async def compile_documents(
    agent: Agent,
    platform: str,
    manifest: dict[str, Any],
    tables_markdown: dict[str, str],
    on_event: Optional[EventSink] = None,
) -> ComposedDocs:
    """§8.4 合稿. Caller must have already run `check_consistency()` and
    confirmed it returned no findings - this function does not re-check the
    gate itself, it only produces the two documents once the gate is clear.

    The split rules live in prompts/judge.md's 「模式 D：合稿」 section
    (already part of `agent`'s system prompt); this function's only job is
    to hand over the raw material - manifest.json and each table's
    tables/<table>.md - in contract order.
    """
    parts = [
        f"平台名：{platform}",
        "开始模式 D 合稿：按 system prompt 中「模式 D：合稿」一节的规则，"
        "产出两份文档（主文档 + 技术笔记）。",
        "## manifest.json",
        "```json",
        json.dumps(manifest, ensure_ascii=False, indent=2),
        "```",
    ]
    for table in TABLES:
        md = tables_markdown.get(table)
        if not md:
            continue
        parts += ["", f"## tables/{table}.md", md]
    msg = Msg(
        name="orchestrator",
        role="user",
        content=[TextBlock(type="text", text="\n".join(parts))],
    )
    return await structured(agent, msg, ComposedDocs, on_event)
