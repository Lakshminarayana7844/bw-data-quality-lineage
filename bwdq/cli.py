"""Command line entry point: python -m bwdq run ..."""
from __future__ import annotations

import argparse
import os
import sys

from . import report
from .lineage import Lineage, impact_for_failures
from .rules import RuleError, blocking, load_config, run_rules, score


def run(rules_path: str, lineage_path: str, out_dir: str, threshold: float | None = None) -> dict:
    cfg = load_config(rules_path)
    results = run_rules(cfg)
    quality = score(results)
    limit = threshold if threshold is not None else cfg.get("threshold", 90)
    lineage = Lineage.load(lineage_path)
    impact = impact_for_failures(lineage, results, cfg["datasets"])
    hit = {a["id"] for item in impact for a in item["affected"]} | {item["node"] for item in impact}
    summ = report.summary(results, quality, limit, blocking(results, cfg["rules"]))

    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "report.json"), "w", encoding="utf-8") as fh:
        fh.write(report.to_json(results, impact, summ))
    with open(os.path.join(out_dir, "report.md"), "w", encoding="utf-8") as fh:
        fh.write(report.to_markdown(results, impact, summ, lineage.to_mermaid(hit)))
    with open(os.path.join(out_dir, "report.html"), "w", encoding="utf-8") as fh:
        fh.write(report.to_html(results, impact, summ))
    return summ


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="bwdq", description="Data quality and lineage checks for BW style extracts")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="evaluate rules and write the reports")
    r.add_argument("--rules", default="config/rules.yaml")
    r.add_argument("--lineage", default="config/lineage.yaml")
    r.add_argument("--out", default="report")
    r.add_argument("--threshold", type=float, help="override the minimum score from the rules file")
    args = p.parse_args(argv)
    try:
        summ = run(args.rules, args.lineage, args.out, args.threshold)
    except (RuleError, OSError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"score {summ['score']} (min {summ['threshold']}): gate {summ['gate']}; "
          f"{summ['rules_failed']}/{summ['rules']} rules failed, blocking: {', '.join(summ['blocking_rules']) or 'none'}; reports in {args.out}/")
    return 0 if summ["gate"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
