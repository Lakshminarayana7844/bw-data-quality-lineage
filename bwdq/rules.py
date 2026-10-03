"""Rule engine: loads extracts and evaluates quality rules against them."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import pandas as pd
import yaml

SEVERITY_WEIGHT = {"error": 3, "warning": 1}
RULE_TYPES = (
    "not_null",
    "unique",
    "allowed_values",
    "regex",
    "range",
    "date_not_future",
    "reference",
    "row_count",
)


class RuleError(ValueError):
    """Raised when the rule configuration is invalid."""


@dataclass
class RuleResult:
    id: str
    dataset: str
    type: str
    severity: str
    description: str
    field: str | None
    checked: int
    failed: int
    examples: list[dict[str, Any]] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.failed == 0

    @property
    def pass_rate(self) -> float:
        if self.checked == 0:
            return 1.0
        return max(0.0, 1.0 - self.failed / self.checked)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "dataset": self.dataset,
            "type": self.type,
            "severity": self.severity,
            "description": self.description,
            "field": self.field,
            "checked": self.checked,
            "failed": self.failed,
            "pass_rate": round(self.pass_rate, 4),
            "examples": self.examples,
        }


def load_config(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    if not isinstance(cfg, dict) or "datasets" not in cfg or "rules" not in cfg:
        raise RuleError("rules file needs 'datasets' and 'rules'")
    base = os.path.dirname(os.path.abspath(path))
    for name, ds in cfg["datasets"].items():
        if "path" not in ds:
            raise RuleError(f"dataset {name} has no path")
        if not os.path.isabs(ds["path"]):
            ds["path"] = os.path.normpath(os.path.join(base, ds["path"]))
    ids = [r.get("id") for r in cfg["rules"]]
    if len(ids) != len(set(ids)):
        raise RuleError("rule ids must be unique")
    for r in cfg["rules"]:
        validate_rule(r, cfg["datasets"])
    return cfg


def validate_rule(rule: dict[str, Any], datasets: dict[str, Any]) -> None:
    for key in ("id", "dataset", "type"):
        if key not in rule:
            raise RuleError(f"rule is missing '{key}': {rule}")
    if rule["type"] not in RULE_TYPES:
        raise RuleError(f"rule {rule['id']}: unknown type '{rule['type']}'")
    if rule["dataset"] not in datasets:
        raise RuleError(f"rule {rule['id']}: unknown dataset '{rule['dataset']}'")
    if rule.get("severity", "error") not in SEVERITY_WEIGHT:
        raise RuleError(f"rule {rule['id']}: severity must be error or warning")
    needs_field = rule["type"] != "row_count"
    if needs_field and not (rule.get("field") or rule.get("fields")):
        raise RuleError(f"rule {rule['id']}: needs 'field'")
    if rule["type"] == "reference" and not all(k in rule for k in ("ref_dataset", "ref_field")):
        raise RuleError(f"rule {rule['id']}: reference needs ref_dataset and ref_field")


def load_tables(datasets: dict[str, Any]) -> dict[str, pd.DataFrame]:
    """Read every extract as text. Empty strings count as missing."""
    tables = {}
    for name, ds in datasets.items():
        df = pd.read_csv(ds["path"], dtype=str, keep_default_na=False, sep=ds.get("sep", ","))
        tables[name] = df
    return tables


def _blank(series: pd.Series) -> pd.Series:
    return series.str.strip() == ""


def _bad_mask(rule: dict[str, Any], df: pd.DataFrame, tables: dict[str, pd.DataFrame], as_of: date):
    """Return (mask of failing rows, number of rows checked)."""
    rtype = rule["type"]
    if rtype == "unique":
        cols = rule.get("fields") or [rule["field"]]
        return df.duplicated(subset=cols, keep=False), len(df)

    col = df[rule["field"]]
    blank = _blank(col)
    filled = ~blank

    if rtype == "not_null":
        return blank, len(df)
    if rtype == "allowed_values":
        return filled & ~col.isin([str(v) for v in rule["values"]]), int(filled.sum())
    if rtype == "regex":
        return filled & ~col.str.fullmatch(rule["pattern"]), int(filled.sum())
    if rtype == "range":
        num = pd.to_numeric(col, errors="coerce")
        bad = num.isna()
        if "min" in rule:
            bad |= num < rule["min"]
        if "max" in rule:
            bad |= num > rule["max"]
        return filled & bad, int(filled.sum())
    if rtype == "date_not_future":
        parsed = pd.to_datetime(col, format=rule.get("format", "%Y%m%d"), errors="coerce")
        return filled & (parsed.isna() | (parsed > pd.Timestamp(as_of))), int(filled.sum())
    if rtype == "reference":
        ref = tables[rule["ref_dataset"]][rule["ref_field"]]
        return filled & ~col.isin(set(ref)), int(filled.sum())
    raise RuleError(f"unsupported rule type {rtype}")


def evaluate_rule(rule, tables, datasets, as_of: date, max_examples: int = 5) -> RuleResult:
    df = tables[rule["dataset"]]
    desc = rule.get("description", rule["type"])
    fld = rule.get("field") or ",".join(rule.get("fields", [])) or None
    severity = rule.get("severity", "error")

    if rule["type"] == "row_count":
        failed = 1 if len(df) < rule.get("min", 1) else 0
        return RuleResult(rule["id"], rule["dataset"], "row_count", severity, desc, None, 1, failed,
                          [{"rows": len(df)}] if failed else [])

    mask, checked = _bad_mask(rule, df, tables, as_of)
    failed = int(mask.sum())
    keys = datasets[rule["dataset"]].get("key", [])
    show = [c for c in keys + [c for c in (rule.get("fields") or [rule["field"]]) if c not in keys] if c in df.columns]
    examples = df.loc[mask, show].head(max_examples).to_dict("records")
    return RuleResult(rule["id"], rule["dataset"], rule["type"], severity, desc, fld, checked, failed, examples)


def run_rules(cfg: dict[str, Any], tables: dict[str, pd.DataFrame] | None = None) -> list[RuleResult]:
    tables = tables if tables is not None else load_tables(cfg["datasets"])
    as_of = cfg.get("as_of")
    if isinstance(as_of, str):
        as_of = datetime.strptime(as_of, "%Y-%m-%d").date()
    as_of = as_of or date.today()
    return [evaluate_rule(r, tables, cfg["datasets"], as_of) for r in cfg["rules"]]


def blocking(results: list[RuleResult], rules: list[dict[str, Any]]) -> list[str]:
    """Ids of error rules whose failure share is above their tolerance (default 0 percent)."""
    tol = {r["id"]: float(r.get("tolerance_pct", 0)) for r in rules}
    out = []
    for r in results:
        if r.severity == "error" and r.checked and 100.0 * r.failed / r.checked > tol[r.id]:
            out.append(r.id)
    return out


def score(results: list[RuleResult]) -> float:
    """Weighted mean of rule pass rates, 0 to 100. Errors count 3x, warnings 1x."""
    if not results:
        return 100.0
    total = sum(SEVERITY_WEIGHT[r.severity] for r in results)
    got = sum(SEVERITY_WEIGHT[r.severity] * r.pass_rate for r in results)
    return round(100.0 * got / total, 2)
