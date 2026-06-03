#!/usr/bin/env python3
"""Analyze natural OpenAPI drift from extracted Git history pairs."""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Set, Tuple

from benchlib import ROOT, load_json, write_csv

DATA_DIR = ROOT / "data" / "openapi_histories"
RESULTS_DIR = ROOT / "results" / "natural_drift"


def openapi_schemas(spec: Dict[str, Any]) -> Dict[str, Any]:
    components = spec.get("components") or {}
    schemas = components.get("schemas")
    if isinstance(schemas, dict):
        return schemas
    definitions = spec.get("definitions")
    if isinstance(definitions, dict):
        return definitions
    return {}


def properties(schema: Dict[str, Any]) -> Dict[str, Any]:
    props = schema.get("properties")
    return props if isinstance(props, dict) else {}


def path_methods(spec: Dict[str, Any]) -> Set[str]:
    result: Set[str] = set()
    for path, path_item in (spec.get("paths") or {}).items():
        if not isinstance(path_item, dict):
            continue
        for method in path_item:
            if str(method).lower() in {"get", "post", "put", "patch", "delete", "options", "head"}:
                result.add(f"{method.upper()} {path}")
    return result


def has_security(spec: Dict[str, Any]) -> bool:
    components = spec.get("components") or {}
    return bool(spec.get("security") or components.get("securitySchemes") or spec.get("securityDefinitions"))


def enum_values(spec: Dict[str, Any]) -> Set[str]:
    values: Set[str] = set()
    def walk(value: Any, prefix: str = "") -> None:
        if isinstance(value, dict):
            if isinstance(value.get("enum"), list):
                values.add(prefix + ":" + "|".join(map(str, value["enum"])))
            for key, child in value.items():
                walk(child, f"{prefix}.{key}" if prefix else str(key))
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{prefix}[{index}]")
    walk(spec)
    return values


def schema_field_signature(spec: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    sig: Dict[str, Dict[str, Any]] = {}
    for schema_name, schema in openapi_schemas(spec).items():
        if not isinstance(schema, dict):
            continue
        required = set(schema.get("required") or [])
        for field, prop in properties(schema).items():
            if not isinstance(prop, dict):
                prop = {}
            key = f"{schema_name}.{field}"
            sig[key] = {
                "type": prop.get("type", ""),
                "format": prop.get("format", ""),
                "required": field in required,
                "enum": tuple(map(str, prop.get("enum") or [])),
            }
    return sig


def analyze_pair(row: Dict[str, Any]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    old = load_json(ROOT / row["old_path"])
    new = load_json(ROOT / row["new_path"])
    old_ops = path_methods(old)
    new_ops = path_methods(new)
    old_fields = schema_field_signature(old)
    new_fields = schema_field_signature(new)

    alerts: List[Dict[str, Any]] = []

    def add_alert(alert_type: str, layer: str, severity: str, location: str, detail: str) -> None:
        alerts.append({
            "pair_id": row["pair_id"],
            "path": row["path"],
            "old_commit": row["old_commit"],
            "new_commit": row["new_commit"],
            "old_date": row["old_date"],
            "new_date": row["new_date"],
            "alert_type": alert_type,
            "layer": layer,
            "severity": severity,
            "location": location,
            "detail": detail,
        })

    for op in sorted(old_ops - new_ops):
        add_alert("operation_removed", "compatibility", "high", op, "Existing operation disappeared.")
    for op in sorted(new_ops - old_ops):
        add_alert("operation_added", "non_breaking", "low", op, "New operation added.")

    for field in sorted(set(old_fields) - set(new_fields)):
        add_alert("schema_field_removed", "compatibility", "high", field, "Existing schema property disappeared.")
    for field in sorted(set(new_fields) - set(old_fields)):
        add_alert("schema_field_added", "non_breaking", "low", field, "New schema property added.")

    for field in sorted(set(old_fields) & set(new_fields)):
        before = old_fields[field]
        after = new_fields[field]
        if before["type"] != after["type"] or before["format"] != after["format"]:
            add_alert("field_type_or_format_changed", "compatibility", "high", field, f"{before} -> {after}")
        if before["required"] != after["required"]:
            severity = "high" if after["required"] else "medium"
            add_alert("field_requiredness_changed", "compatibility", severity, field, f"required {before['required']} -> {after['required']}")
        if before["enum"] != after["enum"]:
            add_alert("enum_values_changed", "semantic", "high", field, f"{before['enum']} -> {after['enum']}")

    if has_security(old) and not has_security(new):
        add_alert("security_removed", "security", "critical", "security", "Security metadata disappeared.")

    old_enums = enum_values(old)
    new_enums = enum_values(new)
    for enum_sig in sorted(old_enums - new_enums)[:50]:
        add_alert("deep_enum_signature_removed", "semantic", "medium", "enum", enum_sig)

    summary = {
        "pair_id": row["pair_id"],
        "path": row["path"],
        "old_commit": row["old_commit"],
        "new_commit": row["new_commit"],
        "old_date": row["old_date"],
        "new_date": row["new_date"],
        "old_operations": len(old_ops),
        "new_operations": len(new_ops),
        "old_fields": len(old_fields),
        "new_fields": len(new_fields),
        "alerts": len(alerts),
        "compatibility_alerts": sum(1 for alert in alerts if alert["layer"] == "compatibility"),
        "semantic_alerts": sum(1 for alert in alerts if alert["layer"] == "semantic"),
        "security_alerts": sum(1 for alert in alerts if alert["layer"] == "security"),
        "non_breaking_alerts": sum(1 for alert in alerts if alert["layer"] == "non_breaking"),
    }
    return summary, alerts


def write_markdown(path: Path, summaries: List[Dict[str, Any]], alerts: List[Dict[str, Any]]) -> None:
    alert_counts = Counter(alert["alert_type"] for alert in alerts)
    layer_counts = Counter(alert["layer"] for alert in alerts)
    lines = ["# Natural OpenAPI Drift Results", ""]
    lines.append(f"- Version pairs: {len(summaries)}")
    lines.append(f"- Total alerts: {len(alerts)}")
    lines.append(f"- Alert layers: {dict(layer_counts)}")
    lines.append("")
    lines.append("## Top Alert Types")
    lines.append("")
    lines.append("| Alert type | Count |")
    lines.append("|---|---:|")
    for alert_type, count in alert_counts.most_common(20):
        lines.append(f"| {alert_type} | {count} |")
    lines.append("")
    lines.append("## Pair-Level Summary")
    lines.append("")
    lines.append("| Pair | Alerts | Compatibility | Semantic | Security | Non-breaking | Path |")
    lines.append("|---|---:|---:|---:|---:|---:|---|")
    for row in summaries[:50]:
        lines.append(
            f"| {row['pair_id']} | {row['alerts']} | {row['compatibility_alerts']} | "
            f"{row['semantic_alerts']} | {row['security_alerts']} | {row['non_breaking_alerts']} | `{row['path']}` |"
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit-sample", type=int, default=120)
    parser.add_argument("--seed", type=int, default=20260602)
    args = parser.parse_args()

    manifest_path = DATA_DIR / "manifest.json"
    if not manifest_path.exists():
        raise SystemExit("Missing data/openapi_histories/manifest.json. Run fetch_openapi_histories.py first.")
    manifest = load_json(manifest_path)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    summaries: List[Dict[str, Any]] = []
    alerts: List[Dict[str, Any]] = []
    for row in manifest:
        summary, pair_alerts = analyze_pair(row)
        summaries.append(summary)
        alerts.extend(pair_alerts)

    write_csv(RESULTS_DIR / "pair_summary.csv", summaries)
    write_csv(RESULTS_DIR / "alerts.csv", alerts)
    rng = random.Random(args.seed)
    sample = alerts[:]
    rng.shuffle(sample)
    audit_rows = []
    for alert in sample[: args.audit_sample]:
        audit = dict(alert)
        audit.update({
            "manual_label": "",
            "manual_notes": "",
            "label_options": "true_breaking|potentially_breaking|semantic_risk|non_breaking|documentation_only|ambiguous",
        })
        audit_rows.append(audit)
    write_csv(RESULTS_DIR / "manual_audit_packet.csv", audit_rows)
    summary = {
        "pairs": len(summaries),
        "alerts": len(alerts),
        "alert_types": dict(Counter(alert["alert_type"] for alert in alerts)),
        "layers": dict(Counter(alert["layer"] for alert in alerts)),
        "audit_sample": len(audit_rows),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    (RESULTS_DIR / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    write_markdown(RESULTS_DIR / "natural_drift_report.md", summaries, alerts)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
