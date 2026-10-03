"""Field-level lineage graph for a BW style data flow, with impact analysis."""
from __future__ import annotations

from collections import deque
from typing import Any

import yaml


class LineageError(ValueError):
    """Raised when the lineage definition is invalid."""


class Lineage:
    def __init__(self, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]):
        self.nodes = {n["id"]: n for n in nodes}
        if len(self.nodes) != len(nodes):
            raise LineageError("duplicate node ids")
        self.edges = edges
        self.out: dict[str, list[dict[str, Any]]] = {n: [] for n in self.nodes}
        for e in edges:
            for end in ("from", "to"):
                if e[end] not in self.nodes:
                    raise LineageError(f"edge refers to unknown node '{e[end]}'")
            self.out[e["from"]].append(e)
        self._check_acyclic()

    @classmethod
    def load(cls, path: str) -> "Lineage":
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        return cls(data["nodes"], data["edges"])

    def _check_acyclic(self) -> None:
        state: dict[str, int] = {}

        def visit(n: str) -> None:
            state[n] = 1
            for e in self.out[n]:
                s = state.get(e["to"], 0)
                if s == 1:
                    raise LineageError(f"cycle through '{e['to']}'")
                if s == 0:
                    visit(e["to"])
            state[n] = 2

        for n in self.nodes:
            if state.get(n, 0) == 0:
                visit(n)

    def downstream(self, node: str, field: str | None = None) -> dict[str, str | None]:
        """Objects reached from `node`. Maps node id to the field name it carries there.

        With a field, an edge with a 'map' only passes the field if it is listed,
        and the field takes the mapped name. Edges without a map pass it unchanged.
        Without a field, everything downstream is reported.
        """
        if node not in self.nodes:
            raise LineageError(f"unknown node '{node}'")
        seen: dict[str, str | None] = {}
        queue = deque([(node, field)])
        while queue:
            cur, fld = queue.popleft()
            for e in self.out[cur]:
                nxt = fld
                if fld is not None and "map" in e:
                    if fld not in e["map"]:
                        continue
                    nxt = e["map"][fld]
                if e["to"] not in seen:
                    seen[e["to"]] = nxt
                    queue.append((e["to"], nxt))
        return seen

    def upstream(self, node: str) -> list[str]:
        rev: dict[str, list[str]] = {n: [] for n in self.nodes}
        for e in self.edges:
            rev[e["to"]].append(e["from"])
        seen, queue = [], deque([node])
        while queue:
            for p in rev[queue.popleft()]:
                if p not in seen:
                    seen.append(p)
                    queue.append(p)
        return seen

    def to_mermaid(self, highlight: set[str] | None = None) -> str:
        highlight = highlight or set()
        lines = ["flowchart LR"]
        for n in self.nodes.values():
            label = f"{n['label']}<br/>{n.get('type', '')}".rstrip("<br/>")
            lines.append(f'  {n["id"]}["{label}"]')
        for e in self.edges:
            lines.append(f"  {e['from']} --> {e['to']}")
        if highlight:
            lines.append("  classDef hit fill:#ffe4e1,stroke:#c0392b,color:#7b241c")
            lines.append("  class " + ",".join(sorted(highlight)) + " hit")
        return "\n".join(lines)


def impact_for_failures(lineage: Lineage, results, datasets: dict[str, Any]) -> list[dict[str, Any]]:
    """For each failed rule, list the downstream objects that consume the bad data."""
    out = []
    for r in results:
        if r.passed:
            continue
        node = datasets[r.dataset].get("node")
        if not node:
            continue
        field = r.field if r.field and "," not in r.field else None
        reached = lineage.downstream(node, field)
        out.append({
            "rule": r.id,
            "dataset": r.dataset,
            "field": r.field,
            "node": node,
            "affected": [
                {"id": n, "label": lineage.nodes[n]["label"], "type": lineage.nodes[n].get("type"), "field": f}
                for n, f in reached.items()
            ],
        })
    return out
