"""Regression tests for the consistency checks.

The old architecture emitted `status: "done"` for tables whose own notes said
the business object did not exist. The `existence` field is the fix, so the
checks now key on it and fall back to `status` only for legacy manifests.

`fixtures/emdlz_manifest.json` is a real snapshot straddling both eras -
`status` from the old run, `existence` from the new - so the two tables that
used to be false positives now carry a correct `existence` and are rightly
not flagged. The tests that asserted the old flagging behaviour were retired
rather than re-pinned; `test_absent_table_is_never_flagged` states the
contract that replaced them.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dms_survey.checks import consistency
from dms_survey.models import Existence

FIXTURES = Path(__file__).resolve().parent / "fixtures"
EMDLZ = FIXTURES  # consistency checks that accept platform_dir use this


@pytest.fixture(scope="module")
def emdlz_manifest() -> dict:
    return json.loads((FIXTURES / "emdlz_manifest.json").read_text(encoding="utf-8"))


def flagged(findings) -> set[str]:
    return {f.table for f in findings}


def test_does_not_flag_the_genuinely_present_table(emdlz_manifest):
    findings = consistency.run_all(emdlz_manifest, platform_dir=EMDLZ)
    assert "dms_order_details_info" not in flagged(findings)


def _one_to_one_manifest(acknowledged=None) -> tuple[dict, dict]:
    manifest = {"tables": []}
    if acknowledged is not None:
        manifest["acknowledged"] = acknowledged
    evidence = {"t": {"fields": [
        {"path": "a.b", "mapped_to": "order_no"},
        {"path": "a.c", "mapped_to": "order_no"},
    ]}}
    return manifest, evidence


def test_acknowledged_finding_is_retired():
    manifest, evidence = _one_to_one_manifest()
    blocking = consistency.run_all(manifest, evidence=evidence)
    assert len(blocking) == 1

    manifest["acknowledged"] = [str(blocking[0])]
    assert consistency.run_all(manifest, evidence=evidence) == []


def test_acknowledgement_lapses_when_the_evidence_changes():
    """Matching on full text is what makes this safe: a human retires one
    specific situation, not the check itself."""
    manifest, evidence = _one_to_one_manifest()
    manifest["acknowledged"] = [str(consistency.run_all(manifest, evidence=evidence)[0])]

    evidence["t"]["fields"][1]["path"] = "a.d"
    evidence["t"]["fields"].append({"path": "a.e", "mapped_to": "order_no"})

    assert consistency.run_all(manifest, evidence=evidence)


def test_granularity_catches_a_wrong_exists_verdict():
    """This check only runs on tables claiming exists/partial - it exists to
    catch an agent that saw finer-grained evidence and judged `exists`
    anyway. The real run judged correctly, so this path has never fired in
    production and has no evidence behind it other than this test."""
    manifest = {
        "tables": [{
            "table": "dms_bill_monthly_info",
            "existence": "exists",
            "route": "/b",
            "notes": "对账日期下拉为 fileNameMonth 列表，共 72 期半月期号。",
        }]
    }

    findings = consistency.check_granularity(manifest)

    assert [f.table for f in findings] == ["dms_bill_monthly_info"]
    assert "半月" in findings[0].detail


def test_granularity_stays_quiet_when_the_verdict_already_says_mismatch():
    manifest = {
        "tables": [{
            "table": "dms_bill_monthly_info",
            "existence": "granularity_mismatch",
            "route": "/b",
            "notes": "对账日期下拉为 fileNameMonth 列表，共 72 期半月期号。",
        }]
    }

    assert consistency.check_granularity(manifest) == []


def test_field_level_negation_is_allowed():
    """'no weight field' is legitimate - that is what `unsupported` is for."""
    manifest = {
        "tables": [
            {
                "table": "dms_order_details_info",
                "status": "done",
                "route": "/order/reserved",
                "apis": ["POST /a/list"],
                "notes": "两接口逐字段核对及页面列名核对均无重量相关字段，全站无中文字典映射。",
            }
        ]
    }
    assert consistency.check_negation_conflict(manifest) == []


def test_table_level_negation_is_caught():
    manifest = {
        "tables": [
            {
                "table": "dms_bill_monthly_info",
                "status": "done",
                "route": "/x",
                "apis": ["POST /a/list"],
                "notes": "人工已确认该后台无月度账单。",
            }
        ]
    }
    assert len(consistency.check_negation_conflict(manifest)) == 1


def test_absent_table_is_never_flagged():
    """A correct `absent` verdict must pass cleanly, however negative its prose."""
    manifest = {
        "tables": [
            {
                "table": "dms_contract_sign_info",
                "existence": Existence.ABSENT.value,
                "route": "",
                "notes": "全站未发现合同相关菜单/Tab。",
            }
        ]
    }
    assert consistency.run_all(manifest) == []


def test_same_source_must_be_declared():
    manifest = {
        "tables": [
            {"table": "dms_bill_monthly_info", "existence": "exists", "route": "/b",
             "apis": ["POST /acct/queryList"]},
            {"table": "dms_bill_details_info", "existence": "exists", "route": "/b",
             "apis": ["POST /acct/queryList"]},
        ]
    }
    assert consistency.check_carrier_uniqueness(manifest)

    manifest["discovery"] = {
        "same_source_hints": [["dms_bill_monthly_info", "dms_bill_details_info"]]
    }
    assert consistency.check_carrier_uniqueness(manifest) == []


def test_api_only_carrier_is_a_carrier():
    """A table the platform only exposes through an interface has no route to
    give - emdlz's `dms_basic_info` is carried by `GET /mdlz-user/user/info`
    and judged `partial`. Its own recorded APIs are the carrier, so demanding
    a page entry would flag a correct verdict on every run.
    """
    manifest = {
        "tables": [
            {
                "table": "dms_basic_info",
                "existence": "partial",
                "entry": {"menu_path": "", "route": ""},
            }
        ]
    }
    evidence = {"dms_basic_info": {"apis": [{"url": "GET /mdlz-user/user/info"}]}}
    assert consistency.check_carrier_uniqueness(manifest, evidence=evidence) == []


def test_nested_entry_route_counts_as_an_entry():
    """`entry.route` is where table agents record the page they actually used;
    the old lookup only read the legacy top-level `route` or `entry.menu_path`,
    so a table with a route but no menu name was flagged while being correct.
    """
    manifest = {
        "tables": [
            {
                "table": "dms_order_details_info",
                "existence": "exists",
                "entry": {"menu_path": "", "route": "/order/reserved"},
            }
        ]
    }
    evidence = {
        "dms_order_details_info": {
            "apis": [{"url": "POST /mdlz-order/otc-order-main/my/list"}]
        }
    }
    assert consistency.check_carrier_uniqueness(manifest, evidence=evidence) == []


def test_carrier_with_neither_entry_nor_api_is_flagged():
    manifest = {
        "tables": [
            {
                "table": "dms_basic_info",
                "existence": "partial",
                "entry": {"menu_path": "", "route": ""},
            }
        ]
    }
    details = [f.detail for f in consistency.check_carrier_uniqueness(manifest)]
    assert len(details) == 1
    assert "无法指认业务载体" in details[0]


def test_discovery_nominated_probe_apis_count_as_the_carrier_apis():
    """A producing table that has not been field-mapped yet has no evidence
    entry, so its only API record is the nested `entry.probe_apis` Discovery
    wrote. Ignoring it flagged such a table for having no APIs at all."""
    manifest = {
        "tables": [
            {
                "table": "dms_bill_monthly_info",
                "existence": "exists",
                "entry": {
                    "menu_path": "订单管理 > 应收账款对账单",
                    "route": "/order/accountsReceivableStatement",
                    "probe_apis": ["POST /mdlz-order/accountsReceivableStatement/queryList"],
                },
            }
        ]
    }

    assert consistency.check_carrier_uniqueness(manifest) == []


def test_one_to_one_violations():
    evidence = {
        "t": {
            "fields": [
                {"path": "a.b", "mapped_to": "order_no"},
                {"path": "a.c", "mapped_to": "order_no"},
                {"path": "a.d", "mapped_to": "amount"},
                {"path": "a.d", "mapped_to": "total"},
            ]
        }
    }
    details = [f.detail for f in consistency.check_one_to_one(evidence=evidence)]
    assert any("order_no" in d and "多个路径" in d for d in details)
    assert any("a.d" in d and "多个标准字段" in d for d in details)


def test_any_declared_path_of_a_multi_path_anchor_is_accepted():
    """The real emdlz anchor lists three interchangeable paths. Plain string
    equality could never match one of them, so every table mapping
    `distributor_code` was reported as inconsistent while being correct."""
    manifest = {
        "tables": [],
        "discovery": {"anchors": {"distributor_code": {
            "path": "records[].soldToCode | result[0][0].payerToCode | localStorage['x'].payerCode",
        }}},
    }
    evidence = {"dms_bill_details_info": {"fields": [
        {"path": "result[0][0].payerToCode", "mapped_to": "distributor_code"},
    ]}}

    assert consistency.check_anchor_consistency(manifest, evidence=evidence) == []


def test_provenance_annotation_does_not_break_anchor_matching():
    """A table's evidence explains where the value came from
    (`my/list: result.records[].payerToCode（人工裁定：…）`) while the anchor
    lists bare paths, so both sides are reduced to the bare path before they
    are compared."""
    manifest = {
        "tables": [],
        "discovery": {"anchors": {"distributor_code": {
            "path": (
                "result.user.account | result.records[].payerToCode "
                "| result[0][0].payerToCode"
            ),
        }}},
    }
    evidence = {"dms_order_details_info": {"fields": [
        {
            "path": "my/list: result.records[].payerToCode（登录账号/付款方口径；人工裁定：全表统一）",
            "mapped_to": "distributor_code",
        },
    ]}}

    assert consistency.check_anchor_consistency(manifest, evidence=evidence) == []


def test_annotated_path_outside_the_anchor_is_still_caught():
    manifest = {
        "tables": [],
        "discovery": {"anchors": {"distributor_code": {
            "path": "result.user.account | result.records[].payerToCode",
        }}},
    }
    evidence = {"t": {"fields": [
        {
            "path": "my/list: result.records[].soldToCode（送达方角色码，已弃用）",
            "mapped_to": "distributor_code",
        },
    ]}}

    findings = consistency.check_anchor_consistency(manifest, evidence=evidence)

    assert len(findings) == 1
    assert "soldToCode" in findings[0].detail


def test_url_shaped_path_is_not_mangled_by_canonicalisation():
    """A URL keeps its `://`; only an `api: path` / `api → path` label is cut."""
    manifest = {
        "tables": [],
        "discovery": {"anchors": {"distributor_code": {
            "path": "https://x.test/api/user/info",
        }}},
    }
    evidence = {"t": {"fields": [
        {"path": "https://x.test/api/user/info", "mapped_to": "distributor_code"},
    ]}}

    assert consistency.check_anchor_consistency(manifest, evidence=evidence) == []


def test_path_outside_a_multi_path_anchor_is_still_caught():
    manifest = {
        "tables": [],
        "discovery": {"anchors": {"distributor_code": {
            "path": "records[].soldToCode | result[0][0].payerToCode",
        }}},
    }
    evidence = {"t": {"fields": [{"path": "main.customerCode", "mapped_to": "distributor_code"}]}}

    findings = consistency.check_anchor_consistency(manifest, evidence=evidence)

    assert len(findings) == 1
    assert "customerCode" in findings[0].detail


def test_anchor_mismatch_is_caught():
    manifest = {
        "tables": [],
        "discovery": {"anchors": {"distributor_code": {"source": "api", "path": "main.customerCode"}}},
    }
    evidence = {"t": {"fields": [{"path": "main.soldToCode", "mapped_to": "distributor_code"}]}}
    findings = consistency.check_anchor_consistency(manifest, evidence=evidence)
    assert len(findings) == 1
    assert "soldToCode" in findings[0].detail


def test_swapped_path_and_mapped_to_are_caught():
    """dms_basic_info's first emdlz pass wrote `path` = standard field name and
    `mapped_to` = provenance prose. Check 4 looks anchors up by `mapped_to`, so
    that table was skipped in complete silence rather than flagged."""
    contracts = {"dms_basic_info": frozenset({"distributor_code", "tenant_name"})}
    evidence = {
        "dms_basic_info": {
            "fields": [
                {"path": "distributor_code", "mapped_to": "GET /x → result.user.account"},
                {"path": "tenant_name", "mapped_to": ""},
            ]
        }
    }

    details = [
        f.detail
        for f in consistency.check_one_to_one(evidence=evidence, contract_fields=contracts)
    ]

    assert any("mapped_to" in d and "疑似与 path 写反" in d for d in details)
    assert any("疑似与 mapped_to 写反" in d for d in details)


def test_contract_guard_skips_tables_it_has_no_contract_for():
    evidence = {"unknown_table": {"fields": [{"path": "order_no", "mapped_to": "main.orderNo"}]}}

    assert consistency.check_one_to_one(evidence=evidence, contract_fields={}) == []


def test_contract_fields_are_loaded_from_the_field_prompts():
    assert "distributor_code" in consistency.CONTRACT_FIELDS["dms_basic_info"]
    assert "order_weight" in consistency.CONTRACT_FIELDS["dms_order_details_info"]
    assert "systemCredentialNo" not in consistency.CONTRACT_FIELDS["dms_bill_details_info"]


def test_anchor_is_looked_up_by_the_contract_field_name():
    """The emdlz anchor was keyed `distributor_name`, while the contract field
    is `distributor_name_original` - so check 4 matched nothing and never
    validated that anchor at all."""
    manifest = {
        "tables": [],
        "discovery": {"anchors": {
            "distributor_name_original": {
                "path": "result[0][0].payerToName | result.user.zhName",
            },
        }},
    }
    evidence = {
        "dms_basic_info": {
            "fields": [
                {
                    "path": "GET /mdlz-user/user/info → result.user.otherName",
                    "mapped_to": "distributor_name_original",
                },
            ]
        }
    }

    findings = consistency.check_anchor_consistency(manifest, evidence=evidence)

    assert len(findings) == 1
    assert "otherName" in findings[0].detail

