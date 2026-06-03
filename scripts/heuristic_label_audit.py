#!/usr/bin/env python3
"""Create heuristic pre-labels for the natural-drift audit packet.

The output is intentionally named as heuristic-labeled data. It is not a
replacement for manual audit; it reduces review effort by assigning transparent
starting labels from alert type and layer.
"""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIT_DIR = ROOT / "results" / "natural_drift"
INPUT = AUDIT_DIR / "manual_audit_packet.csv"
OUTPUT = AUDIT_DIR / "manual_audit_packet_heuristic_labeled.csv"
SUMMARY = AUDIT_DIR / "manual_audit_heuristic_summary.md"


def heuristic_label(row: dict[str, str]) -> tuple[str, str]:
    layer = row.get("layer", "")
    alert_type = row.get("alert_type", "")
    severity = row.get("severity", "")

    if layer == "non_breaking":
        return "non_breaking", "Heuristic: additive non-breaking alert layer."
    if layer == "security":
        return "true_breaking", "Heuristic: removed security metadata is treated as breaking."
    if layer == "semantic":
        return "semantic_risk", "Heuristic: semantic alert layer requires domain review."
    if alert_type == "operation_removed":
        return "true_breaking", "Heuristic: removed operation is breaking for existing callers."
    if alert_type in {"schema_field_removed", "field_requiredness_changed", "field_type_or_format_changed"}:
        return "potentially_breaking", "Heuristic: compatibility-risk schema change."
    return "ambiguous", "Heuristic: no stronger rule matched; needs human review."


def main() -> None:
    with INPUT.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    labeled = []
    counts = Counter()
    for row in rows:
        label, note = heuristic_label(row)
        row = dict(row)
        row["manual_label"] = label
        row["manual_notes"] = note
        labeled.append(row)
        counts[label] += 1

    with OUTPUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(labeled[0].keys()))
        writer.writeheader()
        writer.writerows(labeled)

    lines = [
        "# Natural Drift Heuristic Audit Summary",
        "",
        f"- Input rows: {len(rows)}",
        f"- Output: `{OUTPUT.relative_to(ROOT)}`",
        "- Status: heuristic pre-labels only; human confirmation is still required.",
        "",
        "| Heuristic label | Rows |",
        "|---|---:|",
    ]
    for label, count in sorted(counts.items()):
        lines.append(f"| `{label}` | {count} |")
    SUMMARY.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
