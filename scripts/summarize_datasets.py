#!/usr/bin/env python3
"""Summarize downloaded public datasets for Paper 1."""

from __future__ import annotations

import csv
import gzip
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List

from benchlib import DATA_DIR, RESULTS_DIR, load_json, flatten_for_csv, write_csv

ROOT = DATA_DIR.parent

def summarize_apis_guru() -> Dict[str, Any]:
    manifest_path = DATA_DIR / "apis_guru" / "manifest.json"
    if not manifest_path.exists():
        return {"dataset": "apis_guru", "status": "missing"}
    manifest = load_json(manifest_path)
    rows = [row for row in manifest if row.get("status") == "ok"]
    parsed_json = 0
    text_only = 0
    path_counts: List[int] = []
    schema_counts: List[int] = []
    required_counts: List[int] = []
    enum_counts: List[int] = []
    security_scheme_count = 0
    targeted_count = 0

    for row in rows:
        targeted_count += int(bool(row.get("target_keyword_match")))
        path = ROOT / row["local_path"]
        text = path.read_text(encoding="utf-8", errors="ignore")
        try:
            spec = json.loads(text)
            parsed_json += 1
            paths = spec.get("paths") or {}
            components = spec.get("components") or {}
            definitions = spec.get("definitions") or {}
            schemas = components.get("schemas") or definitions or {}
            path_counts.append(len(paths))
            schema_counts.append(len(schemas))
            required_counts.append(count_key(spec, "required"))
            enum_counts.append(count_key(spec, "enum"))
            security = (components.get("securitySchemes") or spec.get("securityDefinitions") or {})
            if security:
                security_scheme_count += 1
        except Exception:
            text_only += 1
            path_counts.append(len(re.findall(r"(?m)^\s*/[^:\s]+:", text)))
            schema_counts.append(len(re.findall(r"(?m)^\s{0,8}[A-Za-z0-9_.-]+:\s*$", text)))
            required_counts.append(len(re.findall(r"\brequired\b", text)))
            enum_counts.append(len(re.findall(r"\benum\b", text)))
            if "securitySchemes" in text or "securityDefinitions" in text:
                security_scheme_count += 1

    return {
        "dataset": "apis_guru",
        "status": "ok",
        "downloaded_specs": len(rows),
        "target_keyword_specs": targeted_count,
        "json_parsed_specs": parsed_json,
        "yaml_or_text_specs": text_only,
        "total_paths_heuristic": sum(path_counts),
        "median_paths_heuristic": median(path_counts),
        "total_schemas_heuristic": sum(schema_counts),
        "median_schemas_heuristic": median(schema_counts),
        "specs_with_security_schemes": security_scheme_count,
        "required_occurrences": sum(required_counts),
        "enum_occurrences": sum(enum_counts),
    }


def count_key(value: Any, key: str) -> int:
    if isinstance(value, dict):
        return int(key in value) + sum(count_key(v, key) for v in value.values())
    if isinstance(value, list):
        return sum(count_key(item, key) for item in value)
    return 0


def median(values: List[int]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[mid])
    return (ordered[mid - 1] + ordered[mid]) / 2


def summarize_data_gov() -> Dict[str, Any]:
    path = DATA_DIR / "data_gov" / "packages.jsonl.gz"
    if not path.exists():
        return {"dataset": "open_gov_ckan_metadata", "status": "missing"}
    manifest_path = DATA_DIR / "data_gov" / "manifest.json"
    manifest = load_json(manifest_path) if manifest_path.exists() else {}
    fields = [
        "title",
        "notes",
        "organization",
        "metadata_modified",
        "license_id",
        "resources",
        "tags",
        "groups",
    ]
    present = Counter()
    resource_total = 0
    resource_url_present = 0
    resource_format_present = 0
    records = 0
    organizations = Counter()
    license_ids = Counter()
    formats = Counter()
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            records += 1
            for field in fields:
                if record.get(field):
                    present[field] += 1
            org = record.get("organization") or {}
            org_name = org.get("name") or org.get("title") or ""
            if org_name:
                organizations[org_name] += 1
            if record.get("license_id"):
                license_ids[record["license_id"]] += 1
            for resource in record.get("resources") or []:
                resource_total += 1
                if resource.get("url"):
                    resource_url_present += 1
                if resource.get("format"):
                    resource_format_present += 1
                    formats[str(resource.get("format")).lower()] += 1

    completeness = {field: round(present[field] / records, 4) if records else 0 for field in fields}
    return {
        "dataset": "open_gov_ckan_metadata",
        "source_api": manifest.get("source_api", ""),
        "retrieval_method": manifest.get("retrieval_method", ""),
        "status": "ok",
        "records": records,
        "field_completeness": completeness,
        "resource_total": resource_total,
        "resource_url_completeness": round(resource_url_present / resource_total, 4)
        if resource_total
        else 0,
        "resource_format_completeness": round(resource_format_present / resource_total, 4)
        if resource_total
        else 0,
        "top_organizations": organizations.most_common(10),
        "top_licenses": license_ids.most_common(10),
        "top_resource_formats": formats.most_common(15),
    }


def summarize_fhir() -> Dict[str, Any]:
    examples_dir = DATA_DIR / "fhir_us_core" / "examples"
    if not examples_dir.exists():
        return {"dataset": "fhir_us_core", "status": "missing"}
    resource_types = Counter()
    references = 0
    records = 0
    ids_present = 0
    for path in sorted(examples_dir.glob("*.json")):
        try:
            record = load_json(path)
        except Exception:
            continue
        records += 1
        resource_types[record.get("resourceType", "unknown")] += 1
        if record.get("id"):
            ids_present += 1
        references += count_key(record, "reference")
    return {
        "dataset": "fhir_us_core_examples",
        "status": "ok",
        "records": records,
        "ids_present_rate": round(ids_present / records, 4) if records else 0,
        "resource_types": resource_types.most_common(),
        "reference_occurrences": references,
    }


def summarize_smart_bulk_fhir() -> Dict[str, Any]:
    manifest_path = DATA_DIR / "smart_bulk_fhir" / "manifest.json"
    if not manifest_path.exists():
        return {"dataset": "smart_bulk_fhir_synthea_small", "status": "missing"}
    manifest = load_json(manifest_path)
    return {
        "dataset": "smart_bulk_fhir_synthea_small",
        "status": manifest.get("status", "unknown"),
        "source_url": manifest.get("source_url", ""),
        "records": manifest.get("records", 0),
        "ndjson_files": manifest.get("ndjson_files", 0),
        "resource_types": manifest.get("resource_types", {}),
        "note": manifest.get("note", ""),
    }


def write_markdown(path: Path, summaries: List[Dict[str, Any]]) -> None:
    lines = ["# Dataset Summary", ""]
    for summary in summaries:
        lines.append(f"## {summary.get('dataset')}")
        lines.append("")
        for key, value in summary.items():
            if key == "dataset":
                continue
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False)
            lines.append(f"- `{key}`: {value}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    summaries = [summarize_apis_guru(), summarize_data_gov(), summarize_fhir(), summarize_smart_bulk_fhir()]
    (RESULTS_DIR / "dataset_summary.json").write_text(
        json.dumps(summaries, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    write_csv(RESULTS_DIR / "dataset_summary.csv", [flatten_for_csv(row) for row in summaries])
    write_markdown(RESULTS_DIR / "dataset_summary.md", summaries)
    print(json.dumps(summaries, indent=2, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
