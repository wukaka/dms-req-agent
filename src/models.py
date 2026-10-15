"""Data contracts shared by Discovery, table agents and the Judge.

`TableVerdict` doubles as the ``structured_schema`` passed to ``Agent.reply``,
so its field descriptions are read by the model and are part of the prompt.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

TABLES: tuple[str, ...] = (
    "dms_basic_info",
    "dms_order_details_info",
    "dms_bill_monthly_info",
    "dms_bill_details_info",
    "dms_contract_sign_info",
    "dms_certified_info",
)

MAX_SAMPLES = 2


class Existence(str, Enum):
    EXISTS = "exists"
    PARTIAL = "partial"
    ABSENT = "absent"
    GRANULARITY_MISMATCH = "granularity_mismatch"
    PENDING_HUMAN = "pending_human"


#: Only these two verdicts allow a table agent past the gate into field mapping.
PRODUCING = (Existence.EXISTS, Existence.PARTIAL)


class EntryInfo(BaseModel):
    """Where Discovery found a table's business carrier."""

    menu_path: str = ""
    route: str = ""
    probe_apis: list[str] = Field(default_factory=list)
    columns: list[str] = Field(default_factory=list)
    row_count: Optional[int] = None
    needs_query_params: bool = Field(
        default=False,
        description="Page yields no rows until a filter is chosen. Empty is NOT absence.",
    )
    may_have_drilldown: bool = Field(
        default=False,
        description="List view looks field-poor; a detail view may carry the rest.",
    )


class Anchor(BaseModel):
    source: str
    path: str
    sample: str = ""


class DiscoveryBlock(BaseModel):
    menu_tree_ref: str = "menu_map.md"
    anchors: dict[str, Anchor] = Field(default_factory=dict)
    same_source_hints: list[list[str]] = Field(default_factory=list)
    verified_at: str = ""


class TableTriage(BaseModel):
    """One table's Discovery-stage triage (design §5.3). Not a final verdict -
    a business agent's own verdict overrides this when one gets launched."""

    table: str
    existence: Existence
    entry: EntryInfo = Field(default_factory=EntryInfo)
    rationale: str = ""

    @field_validator("existence")
    @classmethod
    def _discovery_never_finalises_absent(cls, v: Existence) -> Existence:
        if v is Existence.ABSENT:
            raise ValueError(
                "Discovery must not emit 'absent' (design §5.3 纪律②: it only "
                "nominates, absent is decided by a human at checkpoint①); use "
                "'pending_human' instead"
            )
        return v


class DiscoveryResult(BaseModel):
    """Discovery agent's full structured output (design §5, §4.1)."""

    discovery: DiscoveryBlock
    tables: list[TableTriage]
    menu_tree_markdown: str = Field(
        default="",
        description="Full menu tree, written to menu_map.md verbatim - the absent-verdict evidence chain.",
    )


class TableVerdict(BaseModel):
    """A table agent's ruling. Emitting `absent` is a success, not a failure."""

    table: str
    existence: Existence = Field(
        description=(
            "exists: unique carrier, granularity matches. "
            "partial: carrier exists, some fields missing. "
            "absent: the site has no such business object. "
            "granularity_mismatch: object exists but granularity differs from the contract. "
            "pending_human: zero hits or genuinely undecidable."
        )
    )
    rationale: str = Field(
        description="Why this verdict. Cite concrete menus, APIs or response fields."
    )
    evidence_refs: list[str] = Field(
        default_factory=list,
        description="Paths under files/ or API names backing the rationale.",
    )
    actual_granularity: str = Field(
        default="",
        description="Required when existence is granularity_mismatch, e.g. 'half-month period'.",
    )
    dissent_from_discovery: str = Field(
        default="",
        description="Fill in when this verdict overrides Discovery's initial triage.",
    )
    deferred_questions: list[str] = Field(
        default_factory=list,
        description=(
            "Judgment calls only a human can make about whether/how this table's "
            "business object exists (e.g. 'is this really absent, or just outside "
            "this account's permissions?'). One self-contained question per item - "
            "it is copied verbatim into questions.md, so do not write 'see above'. "
            "Leave empty when nothing needs a human. Do not use this for things you "
            "can resolve yourself with more digging."
        ),
    )

    @field_validator("actual_granularity")
    @classmethod
    def _granularity_required(cls, v: str, info: Any) -> str:
        if info.data.get("existence") is Existence.GRANULARITY_MISMATCH and not v.strip():
            raise ValueError("actual_granularity is required for granularity_mismatch")
        return v


#: Placeholders agents reach for to mean "this field was not collected". `path`
#: is the source path a value was read from, so a placeholder is not a path at
#: all: check 5 (`one_to_one`) would report every placeholder as one path
#: serving many standard fields, and check 4 would compare it against the
#: declared anchors. The contractually meaningful spelling of "not collected"
#: is an empty path.
_PLACEHOLDER_PATHS = {"/", "-", "--", "n/a", "na", "none", "null", "无", "无对应"}


class EvidenceField(BaseModel):
    path: str = Field(
        default="",
        description=(
            "该标准字段在原始响应中的取值路径（如 result.records[].orderNo）。"
            "无法采集或系统生成时留空字符串，不要写 '/'、'-'、'N/A' 之类的占位符"
            "（会被校验直接拒绝）；排查过程写进分片文档的字段表。"
        ),
    )
    type: str = ""
    samples: list[str] = Field(default_factory=list)
    mapped_to: str = ""

    @field_validator("samples")
    @classmethod
    def _cap_samples(cls, v: list[str]) -> list[str]:
        return v[:MAX_SAMPLES]

    @field_validator("path")
    @classmethod
    def _reject_placeholder_path(cls, v: str) -> str:
        """Refuse a placeholder in `path`, so the mistake fails loudly at
        generation time instead of surfacing later as a bogus
        one-to-one / anchor violation."""
        if v.strip().lower() in _PLACEHOLDER_PATHS:
            raise ValueError(
                "path 是取值路径：无法采集/系统生成请留空字符串，"
                "不要写 '/'、'-'、'N/A' 之类的占位符"
            )
        return v


class EvidenceApi(BaseModel):
    method: str = ""
    url: str = ""
    file: str = ""


class EvidenceTable(BaseModel):
    apis: list[EvidenceApi] = Field(default_factory=list)
    columns: list[str] = Field(default_factory=list)
    fields: list[EvidenceField] = Field(default_factory=list)
    deferred_questions: list[str] = Field(
        default_factory=list,
        description=(
            "Field-mapping-time judgment calls only a human can make (e.g. two "
            "candidate sources conflict, or a cross-table field ownership is "
            "unclear even after ask_judge). One self-contained question per item - "
            "it is copied verbatim into questions.md, so do not write 'see above'. "
            "Leave empty when nothing needs a human."
        ),
    )


class ScreenshotResult(BaseModel):
    """The screenshot agent's report for one table (design: phase 3).

    Deliberately thin: by the time this runs the field mapping is frozen and
    human-confirmed, so there is no verdict left to make. `annotated_images`
    is what the Judge's compile step needs; `notes` is where a mismatch
    between the confirmed field table and the live page gets reported rather
    than silently "fixed".
    """

    annotated_images: list[str] = Field(
        default_factory=list,
        description="images/ paths of the annotated screenshots written, e.g. 'images/dms_order_details_info_列表页_0-annotated.jpg'.",
    )
    skipped: bool = Field(
        default=False,
        description="True when the table has no page-visible fields and needs no screenshot at all.",
    )
    notes: str = Field(
        default="",
        description=(
            "Anything a human should know: a confirmed field whose column is "
            "no longer on the page, a screenshot that could not be captured, "
            "etc. Do not edit the field table to make a mismatch go away - "
            "report it here."
        ),
    )


class CrossAgentQuery(BaseModel):
    """A narrow, structured question from one table agent to the Judge."""

    from_table: str
    about: str
    need: str
    scope: list[str] = Field(default_factory=list)


class ComposedDocs(BaseModel):
    """Judge's §8.4 合稿 output: the two contract documents phases 2-5 read.

    Structure and split rules are prompts/judge.md's 「模式 D：合稿」 section
    verbatim (design §8.4) - this model only names the two halves.
    """

    main_doc: str = Field(description="<平台名>采集需求.md 全文")
    tech_notes: str = Field(description="<平台名>技术笔记.md 全文")


class Finding(BaseModel):
    """One consistency-check violation. Any finding blocks the final write-up."""

    check: str
    table: str
    detail: str

    def __str__(self) -> str:
        return f"[{self.check}] {self.table}: {self.detail}"
