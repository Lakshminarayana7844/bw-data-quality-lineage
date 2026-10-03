import json
import os
from datetime import date

import pandas as pd
import pytest

from bwdq.rules import RuleError, blocking, evaluate_rule, load_config, run_rules, score, validate_rule

ROOT = os.path.join(os.path.dirname(__file__), "..")
DS = {"T": {"key": ["ID"]}, "REF": {"key": ["K"]}}


def table(**cols):
    return pd.DataFrame({k: [str(v) for v in vals] for k, vals in cols.items()})


def run(rule, tables, as_of=date(2026, 9, 30)):
    rule = {"id": "X", "dataset": "T", **rule}
    return evaluate_rule(rule, tables, DS, as_of)


def test_not_null_counts_blank_and_spaces():
    t = {"T": table(ID=[1, 2, 3], A=["x", "", "  "])}
    r = run({"type": "not_null", "field": "A"}, t)
    assert (r.checked, r.failed) == (3, 2)


def test_unique_flags_all_copies():
    t = {"T": table(ID=[1, 1, 2, 3], A=["a", "a", "b", "c"])}
    r = run({"type": "unique", "fields": ["ID", "A"]}, t)
    assert r.failed == 2


def test_allowed_values_ignores_blank():
    t = {"T": table(ID=[1, 2, 3], C=["EUR", "EU", ""])}
    r = run({"type": "allowed_values", "field": "C", "values": ["EUR", "USD"]}, t)
    assert (r.checked, r.failed) == (2, 1)
    assert r.examples == [{"ID": "2", "C": "EU"}]


def test_range_rejects_text_and_bounds():
    t = {"T": table(ID=[1, 2, 3, 4], Q=["5", "-1", "abc", "1000"])}
    r = run({"type": "range", "field": "Q", "min": 1, "max": 100}, t)
    assert r.failed == 3


def test_date_not_future():
    t = {"T": table(ID=[1, 2, 3], D=["20260930", "20261001", "20261340"])}
    r = run({"type": "date_not_future", "field": "D"}, t)
    assert r.failed == 2  # the future date and the impossible date


def test_reference_uses_other_dataset():
    t = {"T": table(ID=[1, 2], M=["A", "Z"]), "REF": table(K=["A", "B"])}
    r = run({"type": "reference", "field": "M", "ref_dataset": "REF", "ref_field": "K"}, t)
    assert r.failed == 1


def test_regex_must_match_whole_value():
    t = {"T": table(ID=[1, 2], N=["1234567890", "12345678901"])}
    r = run({"type": "regex", "field": "N", "pattern": r"\d{10}"}, t)
    assert r.failed == 1


def test_row_count():
    t = {"T": table(ID=[1, 2])}
    assert run({"type": "row_count", "min": 3}, t).failed == 1
    assert run({"type": "row_count", "min": 2}, t).failed == 0


def test_score_weights_errors_above_warnings():
    t = {"T": table(ID=[1, 2], A=["", "x"], B=["", "x"])}
    err = run({"id": "E", "type": "not_null", "field": "A"}, t)
    warn = run({"id": "W", "type": "not_null", "field": "B", "severity": "warning"}, t)
    assert score([err, warn]) == pytest.approx(50.0)
    assert score([]) == 100.0


def test_blocking_respects_tolerance():
    t = {"T": table(ID=list(range(10)), A=[""] + ["x"] * 9)}
    res = [run({"id": "E", "type": "not_null", "field": "A"}, t)]
    assert blocking(res, [{"id": "E"}]) == ["E"]
    assert blocking(res, [{"id": "E", "tolerance_pct": 10}]) == []


def test_invalid_rules_are_rejected():
    with pytest.raises(RuleError):
        validate_rule({"id": "A", "dataset": "T", "type": "nope", "field": "x"}, DS)
    with pytest.raises(RuleError):
        validate_rule({"id": "A", "dataset": "MISSING", "type": "not_null", "field": "x"}, DS)
    with pytest.raises(RuleError):
        validate_rule({"id": "A", "dataset": "T", "type": "reference", "field": "x"}, DS)


def test_sample_data_matches_planted_defects():
    """The generator records what it broke; the rules must find exactly that."""
    planted = json.load(open(os.path.join(ROOT, "data", "planted_defects.json")))
    cfg = load_config(os.path.join(ROOT, "config", "rules.yaml"))
    failed = {r.id: r.failed for r in run_rules(cfg)}
    assert failed["R002"] == planted["duplicate_rows_flagged"]
    assert failed["R003"] == planted["null_customer"]
    assert failed["R004"] == planted["orphan_material"]
    assert failed["R006"] == planted["negative_quantity"]
    assert failed["R007"] == planted["future_date"]
    assert failed["R008"] == planted["bad_currency"]
    assert failed["R009"] == planted["bad_unit"]
    assert failed["R010"] == planted["extreme_value"]
    assert failed["R012"] == planted["material_missing_group"]
    assert failed["R014"] == planted["customer_bad_country"]
    for clean in ("R001", "R005", "R011", "R013"):
        assert failed[clean] == 0
