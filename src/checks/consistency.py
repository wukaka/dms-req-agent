"""The five consistency checks from the design doc, section 8.2.

These exist because the previous architecture shipped two tables whose prose
said the business object did not exist while the structured status said
"done". Prose and verdict must agree, and that agreement has to be verifiable
by code rather than by the model's own diligence.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

import frontmatter

from ..models import Existence, Finding

#: Site-wide scope qualifiers. A negation carrying one of these is talking
#: about the whole platform, not about one field on one page.
_SITE_SCOPE = r"(?:站内|全站|全网|该后台|本后台|本系统|系统本身|系统内)"

#: Nouns that make a negation field-level, which is legitimate: that is
#: precisely what the `unsupported` list is for.
_FIELD_NOUN = r"(?:字段|列名?|单位|摘要|标识|取值|字典|映射|样本|证据)"

#: "无法" ("unable to") is not a negation of existence and must not match -
#: it is what phrases like "判定无法采集" use, and it sits close enough to
#: nearby field nouns to slip past the field-level lookahead below.
_NEGATION = r"(?:无(?!法)|没有|不存在|不提供|未发现|未见|缺少)"

_TABLE_LEVEL_NEGATION = re.compile(
    _SITE_SCOPE + r"[^。；;\n]{0,12}?" + _NEGATION + r"(?![^。；;\n]{0,8}" + _FIELD_NOUN + r")"
)

#: Where the per-table field-definition prompts live (design §8.2③: the
#: granularity contract is declared once, in the field prompt's frontmatter,
#: not duplicated as a hardcoded dict here). The same files' field tables are
#: the standard-field-name contract check 5 enforces.
_PROMPTS_FIELDS_DIR = Path(__file__).resolve().parent.parent / "prompts" / "fields"

#: One row of such a field table: `| 1 | order_group_id | 分组号 | String | 系统生成 |`.
_FIELD_ROW = re.compile(r"^\|\s*\d+\s*\|\s*([A-Za-z0-9_]+)\s*\|")


def _load_granularity_contracts(
    directory: Path = _PROMPTS_FIELDS_DIR,
) -> "tuple[dict[str, str], dict[str, tuple[str, ...]]]":
    """Read granularity_required/finer_than out of prompts/fields/*.md frontmatter.

    Returns empty dicts if the directory is missing, so importing this module
    outside the repo layout (e.g. from a copied checks/ dir) still works.
    """
    required: dict[str, str] = {}
    finer_than: dict[str, tuple[str, ...]] = {}
    if not directory.is_dir():
        return required, finer_than
    for path in sorted(directory.glob("*.md")):
        post = frontmatter.load(path)
        unit = post.metadata.get("granularity_required")
        if not unit:
            continue
        required[path.stem] = unit
        finer_than[unit] = tuple(post.metadata.get("finer_than") or ())
    return required, finer_than


#: Granularity contract, loaded from prompts/fields/<table>.md frontmatter.
#: Callers can still override per-call via run_all(granularity_required=...).
GRANULARITY_REQUIRED, _FINER_THAN = _load_granularity_contracts()


def claims_existence(entry: dict[str, Any]) -> bool:
    """Does this entry assert the table exists?

    Falls back to the legacy `status == "done"` for manifests written by the
    previous architecture, which had no `existence` field at all.
    """
    raw = entry.get("existence")
    if raw:
        return raw in (Existence.EXISTS.value, Existence.PARTIAL.value)
    return entry.get("status") == "done"


def _prose(entry: dict[str, Any], platform_dir: Optional[Path]) -> str:
    """Narrative text for a table: manifest notes plus tables/*.md prose.

    Markdown table rows (one row = one field's mapping/notes) are dropped:
    they are field-level by construction, the same way `unsupported` is, so
    scanning them would drown check 1 in false positives like "全站无对应
    概念" written against a single field's "功能版本" row.
    """
    text = str(entry.get("notes") or "")
    if platform_dir is not None:
        doc = platform_dir / "tables" / f"{entry.get('table')}.md"
        if doc.exists():
            lines = doc.read_text(encoding="utf-8").splitlines()
            text += "\n" + "\n".join(ln for ln in lines if not ln.lstrip().startswith("|"))
    return text


def check_negation_conflict(
    manifest: dict[str, Any], platform_dir: Optional[Path] = None, **_: Any
) -> list[Finding]:
    """1. Table-level negation coexisting with an existence claim."""
    findings: list[Finding] = []
    for entry in manifest.get("tables", []):
        if not claims_existence(entry):
            continue
        text = _prose(entry, platform_dir)
        for match in _TABLE_LEVEL_NEGATION.finditer(text):
            snippet = text[match.start() : match.start() + 40].replace("\n", " ")
            findings.append(
                Finding(
                    check="negation_conflict",
                    table=str(entry.get("table")),
                    detail=f"表级否定与存在性判定冲突：…{snippet}…",
                )
            )
            break
    return findings


def check_carrier_uniqueness(
    manifest: dict[str, Any], evidence: Optional[dict[str, Any]] = None, **_: Any
) -> list[Finding]:
    """2. An existing table needs an identifiable, non-borrowed carrier.

    A carrier is a page entry - nested `entry.route` / `entry.menu_path`, or
    the legacy top-level `route` - or, for a table the platform only exposes
    through an interface, that table's own recorded APIs: emdlz's
    `dms_basic_info` is judged `partial` and is carried by
    `GET /mdlz-user/user/info` with no page at all, so demanding a route would
    flag a correct verdict on every run. Only a table with neither an entry
    nor a single API of its own is genuinely unpinpointable.
    """
    findings: list[Finding] = []
    evidence = evidence or {}
    hints = {
        frozenset(pair) for pair in manifest.get("discovery", {}).get("same_source_hints", [])
    }

    apis_by_table: dict[str, set[str]] = {}
    for entry in manifest.get("tables", []):
        name = str(entry.get("table"))
        listed = [a.get("url", "") for a in evidence.get(name, {}).get("apis", [])]
        listed += list(entry.get("apis", []))
        # Discovery nominates a table's carrier APIs into the nested entry, so
        # a table that is producing but not yet field-mapped (no evidence yet)
        # still has its APIs on record - the same reason `entry.route` had to
        # be read alongside the legacy top-level `route`.
        listed += list((entry.get("entry") or {}).get("probe_apis", []))
        apis_by_table[name] = {_normalise_api(a) for a in listed if a}

    for entry in manifest.get("tables", []):
        name = str(entry.get("table"))
        if not claims_existence(entry):
            continue

        entry_info = entry.get("entry") or {}
        route = (
            entry.get("route")
            or entry_info.get("route")
            or entry_info.get("menu_path")
            or ""
        )
        mine = apis_by_table.get(name, set())
        if not route and not mine:
            findings.append(
                Finding(
                    check="carrier_uniqueness",
                    table=name,
                    detail=(
                        "判定为存在，但既没有入口（route/menu_path 为空）"
                        "也没有记录任何接口，无法指认业务载体"
                    ),
                )
            )
            continue
        if not mine:
            findings.append(
                Finding(
                    check="carrier_uniqueness",
                    table=name,
                    detail="判定为存在，但没有记录任何接口",
                )
            )
            continue

        borrowed_from = [
            other
            for other, theirs in apis_by_table.items()
            if other != name and mine and mine <= theirs
        ]
        undeclared = [o for o in borrowed_from if frozenset((name, o)) not in hints]
        if undeclared:
            findings.append(
                Finding(
                    check="carrier_uniqueness",
                    table=name,
                    detail=(
                        "接口全部来自其他表（"
                        + "、".join(undeclared)
                        + "），且未在 discovery.same_source_hints 中声明同源"
                    ),
                )
            )
    return findings


def _normalise_api(raw: str) -> str:
    """Strip verbs, query strings and trailing Chinese annotations."""
    text = re.split(r"[（(]", raw)[0].strip()
    text = re.sub(r"^(GET|POST|PUT|DELETE|PATCH)\s+", "", text, flags=re.I)
    return text.split("?")[0].strip().rstrip("/")


def check_granularity(
    manifest: dict[str, Any],
    platform_dir: Optional[Path] = None,
    granularity_required: Optional[dict[str, str]] = None,
    **_: Any,
) -> list[Finding]:
    """3. Contracted granularity vs the granularity the site actually offers."""
    required = granularity_required or GRANULARITY_REQUIRED
    findings: list[Finding] = []
    for entry in manifest.get("tables", []):
        name = str(entry.get("table"))
        unit = required.get(name)
        if not unit or not claims_existence(entry):
            continue
        text = _prose(entry, platform_dir)
        hits = [w for w in _FINER_THAN.get(unit, ()) if w in text]
        if hits:
            findings.append(
                Finding(
                    check="granularity",
                    table=name,
                    detail=(
                        f"契约要求「{unit}」粒度，证据中出现更细粒度："
                        + "、".join(hits)
                        + "，应判 granularity_mismatch"
                    ),
                )
            )
    return findings


def _canonical_path(raw: Any) -> str:
    """The bare source path inside a provenance string.

    Table agents record the API and the human ruling beside the path
    (`my/list: result.records[].payerToCode（人工裁定：…）`) while
    discovery.anchors lists bare paths, so comparing the raw strings reported
    every correctly-mapped anchor as inconsistent.
    """
    text = re.split(r"[（(]", str(raw or ""))[0].strip()
    # ": " rather than ":" on purpose: it separates an API label from its path
    # ("my/list: result.x") without eating the scheme of a URL-shaped path.
    for separator in ("→", ": "):
        if separator in text:
            text = text.rsplit(separator, 1)[-1]
    return text.strip()


def check_anchor_consistency(
    manifest: dict[str, Any], evidence: Optional[dict[str, Any]] = None, **_: Any
) -> list[Finding]:
    """4. Every table's anchor mapping agrees with discovery.anchors.

    Discovery may declare several interchangeable paths for one anchor,
    pipe-separated, when it cross-checked the same value across APIs. Taking
    any one of them is compliant, so compare against the set rather than the
    whole string - plain equality flagged every table that mapped a
    multi-path anchor, however correctly it chose.

    Both sides are reduced to the bare path first (`_canonical_path`), because
    the two sides are written for different readers: anchors list paths, while
    a table's evidence explains where the value came from and why.
    """
    findings: list[Finding] = []
    anchors = manifest.get("discovery", {}).get("anchors", {})
    if not anchors or not evidence:
        return findings
    for table, payload in evidence.items():
        for field in payload.get("fields", []):
            target = field.get("mapped_to")
            declared = anchors.get(target)
            if not declared:
                continue
            accepted = {
                _canonical_path(p) for p in str(declared.get("path", "")).split("|")
            }
            if _canonical_path(field.get("path")) not in accepted:
                findings.append(
                    Finding(
                        check="anchor_consistency",
                        table=table,
                        detail=(
                            f"{target} 取自 {field.get('path')}，"
                            f"与 discovery.anchors 声明的 {declared.get('path')} 不一致"
                        ),
                    )
                )
    return findings


def _load_contract_fields(directory: Path = _PROMPTS_FIELDS_DIR) -> dict[str, frozenset[str]]:
    """Standard field names per table, read from `prompts/fields/<table>.md`.

    That field table is the contract: `mapped_to` has to name one of its rows
    and `path` must never be a row name. Nothing else in the repo can tell an
    inverted `path`/`mapped_to` pair from a correct one, which is how the first
    emdlz run's `dms_basic_info` passed every check while check 4 compared
    nothing at all.

    Returns an empty mapping if the directory is missing, so a copied
    `checks/` directory still imports.
    """
    fields: dict[str, frozenset[str]] = {}
    if not directory.is_dir():
        return fields
    for path in sorted(directory.glob("*.md")):
        names = [
            match.group(1)
            for match in (
                _FIELD_ROW.match(line)
                for line in path.read_text(encoding="utf-8").splitlines()
            )
            if match
        ]
        if names:
            fields[path.stem] = frozenset(names)
    return fields


#: Contract field names per table, loaded from prompts/fields/<table>.md.
#: Callers can still override per-call via run_all/check_one_to_one.
CONTRACT_FIELDS = _load_contract_fields()


def _short(value: Any, limit: int = 60) -> str:
    text = str(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _convention_findings(
    table: str, target: Any, path: Any, names: frozenset[str]
) -> list[Finding]:
    """Flag a row whose mapping column is not the kind of value it should hold.

    `mapped_to` names a standard field, `path` says where the value was read.
    dms_basic_info's first emdlz pass wrote all 16 rows the other way round;
    check 4 looks anchors up by `mapped_to`, so the whole table was skipped
    without a word, and check 5 never saw two rows collide either.
    """
    findings: list[Finding] = []
    if target and target not in names:
        findings.append(
            Finding(
                check="one_to_one",
                table=table,
                detail=(
                    f"mapped_to 应为本表契约字段名，实际是「{_short(target)}」"
                    "（疑似与 path 写反；无法采集请把 mapped_to 留为标准字段名、path 留空）"
                ),
            )
        )
    if path and path in names:
        findings.append(
            Finding(
                check="one_to_one",
                table=table,
                detail=(
                    f"path 应填取值路径，实际填了本表契约字段名「{path}」"
                    "（疑似与 mapped_to 写反）"
                ),
            )
        )
    return findings


def check_one_to_one(
    evidence: Optional[dict[str, Any]] = None,
    contract_fields: Optional[dict[str, frozenset[str]]] = None,
    **_: Any,
) -> list[Finding]:
    """5. One standard field maps to exactly one path, and vice versa.

    Also guards the column convention itself: a table whose `mapped_to` holds
    prose and whose `path` holds standard field names would otherwise satisfy
    both directions vacuously.
    """
    contracts = CONTRACT_FIELDS if contract_fields is None else contract_fields
    findings: list[Finding] = []
    for table, payload in (evidence or {}).items():
        names = contracts.get(table)
        by_target: dict[str, set[str]] = {}
        by_path: dict[str, set[str]] = {}
        for field in payload.get("fields", []):
            target, path = field.get("mapped_to"), field.get("path")
            if names:
                findings.extend(_convention_findings(table, target, path, names))
            if not target or not path:
                continue
            by_target.setdefault(target, set()).add(path)
            by_path.setdefault(path, set()).add(target)

        for target, paths in by_target.items():
            if len(paths) > 1:
                findings.append(
                    Finding(
                        check="one_to_one",
                        table=table,
                        detail=f"标准字段 {target} 映射到多个路径：" + "、".join(sorted(paths)),
                    )
                )
        for path, targets in by_path.items():
            if len(targets) > 1:
                findings.append(
                    Finding(
                        check="one_to_one",
                        table=table,
                        detail=f"路径 {path} 同时映射到多个标准字段：" + "、".join(sorted(targets)),
                    )
                )
    return findings


CHECKS = (
    check_negation_conflict,
    check_carrier_uniqueness,
    check_granularity,
    check_anchor_consistency,
    check_one_to_one,
)


def run_all(
    manifest: dict[str, Any],
    evidence: Optional[dict[str, Any]] = None,
    platform_dir: Optional[Path] = None,
    granularity_required: Optional[dict[str, str]] = None,
) -> list[Finding]:
    """Run every check. A non-empty result blocks the final write-up.

    `manifest["acknowledged"]` lets a human retire a finding they have judged
    to be acceptable, which is the only way past a check that would otherwise
    block every future pass. Entries are matched against the finding's full
    text on purpose: if the underlying evidence changes, the text changes and
    the finding resurfaces rather than staying silently suppressed.
    """
    acknowledged = {str(a) for a in manifest.get("acknowledged", [])}
    findings: list[Finding] = []
    for check in CHECKS:
        findings.extend(
            check(
                manifest=manifest,
                evidence=evidence,
                platform_dir=platform_dir,
                granularity_required=granularity_required,
            )
        )
    return [f for f in findings if str(f) not in acknowledged]
