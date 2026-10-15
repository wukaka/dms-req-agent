"""Schema contracts that keep the consistency checks meaningful.

`EvidenceField.path` is the source path a value was read from. The previous
emdlz run wrote `/` there for every uncollected field, and check 5
(`one_to_one`) then read twelve such rows as one path serving twelve standard
fields. The model refuses the placeholder at generation time, and the
contractually meaningful spelling of "not collected" is an empty path with
`mapped_to` still naming the standard field.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.checks import consistency
from src.models import EvidenceField, EvidenceTable


@pytest.mark.parametrize("placeholder", ["/", "-", "--", "N/A", "无", " none "])
def test_placeholder_path_is_rejected(placeholder):
    with pytest.raises(ValidationError):
        EvidenceField(path=placeholder, mapped_to="order_id")


def test_uncollected_field_is_an_empty_path_with_the_standard_name_kept():
    field = EvidenceField(mapped_to="order_weight")

    assert field.path == ""
    assert field.mapped_to == "order_weight"


def test_a_real_path_still_validates():
    field = EvidenceField(path="result.records[].orderNo", mapped_to="order_no")

    assert field.path == "result.records[].orderNo"


def test_unmapped_fields_do_not_trip_one_to_one():
    """The contract the validator protects: many uncollected fields share an
    empty path, and check 5 must not read that as one path -> many fields, nor
    as one standard field -> many paths."""
    evidence = {
        "t": {
            "fields": [
                {"path": "", "mapped_to": "order_id"},
                {"path": "", "mapped_to": "taxpayer_id"},
                {"path": "result.x", "mapped_to": "order_no"},
            ]
        }
    }

    assert consistency.check_one_to_one(evidence=evidence) == []


def test_evidence_table_accepts_the_normalised_shape():
    table = EvidenceTable(
        fields=[
            EvidenceField(path="result.records[].orderNo", mapped_to="order_no"),
            EvidenceField(type="系统生成", mapped_to="order_id"),
        ]
    )

    assert [f.path for f in table.fields] == ["result.records[].orderNo", ""]
    assert [f.mapped_to for f in table.fields] == ["order_no", "order_id"]
