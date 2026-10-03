"""Render results as JSON, Markdown and a self-contained HTML dashboard."""
from __future__ import annotations

import html
import json
from typing import Any

from .rules import RuleResult


def summary(results: list[RuleResult], quality_score: float, threshold: float,
            blocking: list[str] | None = None) -> dict[str, Any]:
    failed = [r for r in results if not r.passed]
    blocking = blocking or []
    return {
        "score": quality_score,
        "threshold": threshold,
        "gate": "PASS" if quality_score >= threshold and not blocking else "FAIL",
        "blocking_rules": blocking,
        "rules": len(results),
        "rules_passed": len(results) - len(failed),
        "rules_failed": len(failed),
        "errors_failed": sum(1 for r in failed if r.severity == "error"),
        "warnings_failed": sum(1 for r in failed if r.severity == "warning"),
    }


def to_json(results, impact, summ) -> str:
    return json.dumps({"summary": summ, "rules": [r.to_dict() for r in results], "impact": impact},
                      indent=2, ensure_ascii=False)


def to_markdown(results, impact, summ, mermaid: str) -> str:
    out = ["# Data quality report", ""]
    out.append(f"**Score {summ['score']} / 100** (gate {summ['gate']}, threshold {summ['threshold']}). "
               f"{summ['rules_failed']} of {summ['rules']} rules failed "
               f"({summ['errors_failed']} errors, {summ['warnings_failed']} warnings). "
               f"Blocking rules: {', '.join(summ['blocking_rules']) or 'none'}.")
    out += ["", "## Rules", "", "| Rule | Dataset | Field | Severity | Checked | Failed | Pass rate | Description |",
            "|---|---|---|---|---:|---:|---:|---|"]
    for r in results:
        out.append(f"| {r.id} | {r.dataset} | {r.field or '-'} | {r.severity} | {r.checked} | {r.failed} | "
                   f"{r.pass_rate:.1%} | {r.description} |")
    out += ["", "## Downstream impact", ""]
    if not impact:
        out.append("No failed rules.")
    for item in impact:
        names = ", ".join(f"{a['label']}" for a in item["affected"]) or "nothing downstream"
        out.append(f"- **{item['rule']}** ({item['dataset']}.{item['field'] or 'dataset'}): {names}")
    out += ["", "## Lineage", "", "```mermaid", mermaid, "```", ""]
    return "\n".join(out)


CSS = """
body{font-family:system-ui,Segoe UI,Arial,sans-serif;margin:0;background:#f4f6fb;color:#1b2333}
header{background:#0a2540;color:#fff;padding:22px 32px}
h1{margin:0;font-size:22px} main{max-width:1100px;margin:0 auto;padding:24px}
.cards{display:flex;gap:16px;flex-wrap:wrap;margin-bottom:24px}
.card{background:#fff;border-radius:10px;padding:16px 20px;box-shadow:0 1px 4px rgba(0,0,0,.08);min-width:150px}
.card b{display:block;font-size:28px} .pass{color:#1e8449} .fail{color:#c0392b}
table{border-collapse:collapse;width:100%;background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,.08);margin-bottom:24px}
th,td{padding:8px 10px;text-align:left;border-bottom:1px solid #e6eaf2;font-size:14px}
th{background:#eef2fa} td.n{text-align:right}
.bar{height:8px;background:#e6eaf2;border-radius:4px;min-width:80px} .bar i{display:block;height:8px;border-radius:4px;background:#27ae60}
.bar.bad i{background:#e67e22} code{background:#eef2fa;padding:1px 5px;border-radius:4px}
h2{margin-top:32px} .tag{display:inline-block;background:#fdecea;color:#922b21;border-radius:4px;padding:1px 7px;margin:2px;font-size:13px}
"""


def to_html(results, impact, summ) -> str:
    e = html.escape
    gate_cls = "pass" if summ["gate"] == "PASS" else "fail"
    rows = []
    for r in results:
        bad = " bad" if not r.passed else ""
        rows.append(
            f"<tr><td>{e(r.id)}</td><td>{e(r.dataset)}</td><td>{e(r.field or '-')}</td><td>{e(r.severity)}</td>"
            f"<td class='n'>{r.checked}</td><td class='n'>{r.failed}</td>"
            f"<td><div class='bar{bad}'><i style='width:{r.pass_rate * 100:.0f}%'></i></div></td>"
            f"<td>{e(r.description)}</td></tr>")
    detail = []
    for r in results:
        if r.passed:
            continue
        ex = "".join(f"<li><code>{e(json.dumps(x, ensure_ascii=False))}</code></li>" for x in r.examples)
        detail.append(f"<h3>{e(r.id)} - {e(r.description)} ({r.failed} failed)</h3><ul>{ex}</ul>")
    imp = []
    for item in impact:
        tags = "".join(f"<span class='tag'>{e(a['label'])}</span>" for a in item["affected"]) or "nothing downstream"
        imp.append(f"<tr><td>{e(item['rule'])}</td><td>{e(item['dataset'])}.{e(item['field'] or 'dataset')}</td><td>{tags}</td></tr>")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Data quality report</title>
<style>{CSS}</style></head><body>
<header><h1>Data quality report</h1></header><main>
<div class="cards">
<div class="card">Quality score<b class="{gate_cls}">{summ['score']}</b>gate {summ['gate']} (min {summ['threshold']})</div>
<div class="card">Rules<b>{summ['rules']}</b>{summ['rules_passed']} passed</div>
<div class="card">Blocking rules<b class="fail">{len(summ['blocking_rules'])}</b>{e(', '.join(summ['blocking_rules']))}</div>
<div class="card">Errors failed<b class="fail">{summ['errors_failed']}</b></div>
<div class="card">Warnings failed<b>{summ['warnings_failed']}</b></div></div>
<h2>Rules</h2><table><tr><th>Rule</th><th>Dataset</th><th>Field</th><th>Severity</th><th>Checked</th><th>Failed</th><th>Pass rate</th><th>Description</th></tr>
{''.join(rows)}</table>
<h2>Failed rows (examples)</h2>{''.join(detail) or '<p>No failures.</p>'}
<h2>Downstream impact</h2><table><tr><th>Rule</th><th>Where</th><th>Affected objects</th></tr>{''.join(imp)}</table>
</main></body></html>"""
