#!/usr/bin/env python3
"""Mutation benchmark for public digital-government-like contracts.

The benchmark uses downloaded public artifacts:
- OpenAPI specs from APIs.guru.
- Open-government CKAN metadata records.
- FHIR US Core examples.

It injects controlled contract drift into those real artifacts and evaluates
baseline detectors against a multi-layer contract oracle.
"""

from __future__ import annotations

import argparse
import copy
import gzip
import json
import math
import random
import re
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from benchlib import DATA_DIR, ROOT, load_json, write_csv, write_json

RESULTS_DIR = ROOT / "results" / "benchmark"


Mutation = Dict[str, Any]
DetectorResult = Dict[str, bool]


REQUIRED_METADATA_FIELDS = ("title", "notes", "organization", "metadata_modified", "license_id", "resources")
SEVERITY_WEIGHTS = {
    "non_breaking": 0,
    "breaking_schema": 2,
    "breaking_semantic": 4,
    "breaking_security": 6,
    "breaking_provenance": 4,
}


def deep_items(value: Any, key: str) -> Iterable[Any]:
    if isinstance(value, dict):
        for current_key, current_value in value.items():
            if current_key == key:
                yield current_value
            yield from deep_items(current_value, key)
    elif isinstance(value, list):
        for item in value:
            yield from deep_items(item, key)


def iter_openapi_specs(limit: int) -> Iterable[Tuple[str, Dict[str, Any]]]:
    manifest_path = DATA_DIR / "apis_guru" / "manifest.json"
    if not manifest_path.exists():
        return
    manifest = load_json(manifest_path)
    count = 0
    for row in manifest:
        if row.get("status") != "ok":
            continue
        path = ROOT / row["local_path"]
        try:
            spec = load_json(path)
        except Exception:
            continue
        count += 1
        yield row.get("api_name", path.stem), spec
        if count >= limit:
            break


def iter_ckan_records(limit: int) -> Iterable[Tuple[str, Dict[str, Any]]]:
    path = DATA_DIR / "data_gov" / "packages.jsonl.gz"
    if not path.exists():
        return
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for index, line in enumerate(handle):
            if index >= limit:
                break
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except Exception:
                continue
            artifact_id = record.get("id") or record.get("name") or f"ckan_{index}"
            yield str(artifact_id), record


def iter_fhir_examples(limit: int) -> Iterable[Tuple[str, Dict[str, Any]]]:
    count = 0
    examples_dir = DATA_DIR / "fhir_us_core" / "examples"
    if examples_dir.exists():
        for path in sorted(examples_dir.glob("*.json")):
            try:
                resource = load_json(path)
            except Exception:
                continue
            artifact_id = f"us_core:{resource.get('resourceType', path.stem)}/{resource.get('id', path.stem)}"
            yield artifact_id, resource
            count += 1
            if count >= limit:
                return

    smart_dir = DATA_DIR / "smart_bulk_fhir" / "small"
    if smart_dir.exists():
        for path in sorted(smart_dir.glob("*.ndjson")):
            with path.open("r", encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, start=1):
                    if not line.strip():
                        continue
                    try:
                        resource = json.loads(line)
                    except Exception:
                        continue
                    artifact_id = f"smart_bulk:{resource.get('resourceType', path.stem)}/{resource.get('id', line_number)}"
                    yield artifact_id, resource
                    count += 1
                    if count >= limit:
                        return


def openapi_schemas(spec: Dict[str, Any]) -> Dict[str, Any]:
    components = spec.get("components") or {}
    schemas = components.get("schemas")
    if isinstance(schemas, dict):
        return schemas
    definitions = spec.get("definitions")
    if isinstance(definitions, dict):
        return definitions
    return {}


def schema_properties(schema: Dict[str, Any]) -> Dict[str, Any]:
    properties = schema.get("properties")
    return properties if isinstance(properties, dict) else {}


def openapi_mutations(artifact_id: str, spec: Dict[str, Any], max_per_artifact: int) -> List[Mutation]:
    mutations: List[Mutation] = []
    security_mutations: List[Mutation] = []
    schemas = openapi_schemas(spec)

    for schema_name, schema in schemas.items():
        if not isinstance(schema, dict):
            continue
        props = schema_properties(schema)
        required = schema.get("required") if isinstance(schema.get("required"), list) else []

        if required:
            field = required[0]
            mutated = copy.deepcopy(spec)
            m_schema = openapi_schemas(mutated).get(schema_name, {})
            m_schema["required"] = [x for x in m_schema.get("required", []) if x != field]
            mutations.append(make_mutation(artifact_id, "openapi", "remove_required_field", "breaking_schema", "medium", spec, mutated, f"{schema_name}.{field}"))

        optional = [field for field in props.keys() if field not in required]
        if optional:
            field = optional[0]
            mutated = copy.deepcopy(spec)
            m_schema = openapi_schemas(mutated).get(schema_name, {})
            m_schema.setdefault("required", [])
            if field not in m_schema["required"]:
                m_schema["required"].append(field)
            mutations.append(make_mutation(artifact_id, "openapi", "optional_becomes_required", "breaking_schema", "medium", spec, mutated, f"{schema_name}.{field}"))

        for field, prop in props.items():
            if not isinstance(prop, dict):
                continue
            if prop.get("type") in {"string", "number", "integer", "boolean"}:
                mutated = copy.deepcopy(spec)
                m_prop = openapi_schemas(mutated).get(schema_name, {}).get("properties", {}).get(field, {})
                original_type = m_prop.get("type")
                m_prop["type"] = "integer" if original_type != "integer" else "string"
                mutations.append(make_mutation(artifact_id, "openapi", "type_changed", "breaking_schema", "medium", spec, mutated, f"{schema_name}.{field}"))
                break

        enum_path = find_first_enum_field(props)
        if enum_path:
            field, enum_values = enum_path
            mutated = copy.deepcopy(spec)
            m_prop = openapi_schemas(mutated).get(schema_name, {}).get("properties", {}).get(field, {})
            m_prop["enum"] = [f"CODE_{index}" for index, _ in enumerate(enum_values, start=1)]
            mutations.append(make_mutation(artifact_id, "openapi", "enum_code_list_remapped", "breaking_semantic", "high", spec, mutated, f"{schema_name}.{field}"))

        if props:
            field = next(iter(props.keys()))
            mutated = copy.deepcopy(spec)
            m_props = openapi_schemas(mutated).get(schema_name, {}).get("properties", {})
            if field in m_props:
                m_props[f"{field}_v2"] = m_props.pop(field)
                mutations.append(make_mutation(artifact_id, "openapi", "field_renamed_without_alias", "breaking_semantic", "high", spec, mutated, f"{schema_name}.{field}"))

        if len(mutations) >= max_per_artifact:
            break

    for schema_name, schema in schemas.items():
        if isinstance(schema, dict) and isinstance(schema_properties(schema), dict):
            mutated = copy.deepcopy(spec)
            m_schema = openapi_schemas(mutated).get(schema_name, {})
            m_schema.setdefault("properties", {})
            if "x_bench_optional_note" not in m_schema["properties"]:
                m_schema["properties"]["x_bench_optional_note"] = {
                    "type": "string",
                    "description": "Optional compatibility-preserving field added by the benchmark.",
                }
                mutations.append(make_mutation(artifact_id, "openapi", "optional_field_added", "non_breaking", "none", spec, mutated, f"{schema_name}.x_bench_optional_note"))
            break

    if has_security(spec):
        mutated = copy.deepcopy(spec)
        remove_security(mutated)
        security_mutations.append(make_mutation(artifact_id, "openapi", "security_requirement_removed", "breaking_security", "critical", spec, mutated, "security"))

    # Keep security drift outside the regular per-artifact mutation quota.
    # Otherwise rich schemas can fill the quota before security mutations are
    # appended, under-representing security drift despite many secured specs.
    return mutations[:max_per_artifact] + security_mutations


def find_first_enum_field(props: Dict[str, Any]) -> Optional[Tuple[str, List[Any]]]:
    for field, prop in props.items():
        if isinstance(prop, dict) and isinstance(prop.get("enum"), list) and len(prop["enum"]) >= 2:
            return field, prop["enum"]
    return None


def has_security(spec: Dict[str, Any]) -> bool:
    components = spec.get("components") or {}
    return bool(spec.get("security") or components.get("securitySchemes") or spec.get("securityDefinitions"))


def remove_security(spec: Dict[str, Any]) -> None:
    spec.pop("security", None)
    if isinstance(spec.get("components"), dict):
        spec["components"].pop("securitySchemes", None)
    spec.pop("securityDefinitions", None)
    for path_item in (spec.get("paths") or {}).values():
        if isinstance(path_item, dict):
            for operation in path_item.values():
                if isinstance(operation, dict):
                    operation.pop("security", None)


def ckan_mutations(artifact_id: str, record: Dict[str, Any], max_per_artifact: int) -> List[Mutation]:
    mutations: List[Mutation] = []
    mutated = copy.deepcopy(record)
    tags = mutated.setdefault("tags", [])
    if isinstance(tags, list):
        tags.append({"name": "contract-benchmark-compatible-addition", "display_name": "contract-benchmark-compatible-addition"})
        mutations.append(make_mutation(artifact_id, "ckan", "metadata_tag_added", "non_breaking", "none", record, mutated, "tags"))

    for field in ("title", "license_id", "metadata_modified"):
        if record.get(field):
            mutated = copy.deepcopy(record)
            mutated.pop(field, None)
            label = "breaking_provenance" if field in {"license_id", "metadata_modified"} else "breaking_schema"
            mutations.append(make_mutation(artifact_id, "ckan", f"metadata_field_removed_{field}", label, "medium", record, mutated, field))
            if len(mutations) >= max_per_artifact:
                return mutations

    resources = record.get("resources") if isinstance(record.get("resources"), list) else []
    resource_with_url = next((resource for resource in resources if isinstance(resource, dict) and resource.get("url")), None)
    if resource_with_url:
        mutated = copy.deepcopy(record)
        m_resource = next(resource for resource in mutated.get("resources", []) if isinstance(resource, dict) and resource.get("url"))
        m_resource.pop("url", None)
        mutations.append(make_mutation(artifact_id, "ckan", "distribution_url_removed", "breaking_schema", "medium", record, mutated, "resources.url"))

        mutated = copy.deepcopy(record)
        m_resource = next(resource for resource in mutated.get("resources", []) if isinstance(resource, dict) and resource.get("url"))
        url = str(m_resource.get("url", ""))
        if url.lower().endswith(".csv"):
            m_resource["format"] = "PDF"
        else:
            m_resource["url"] = url.rstrip("/") + "/download.csv"
            m_resource["format"] = "PDF"
        mutations.append(make_mutation(artifact_id, "ckan", "resource_format_url_mismatch", "breaking_semantic", "high", record, mutated, "resources.format"))

    if record.get("metadata_modified"):
        mutated = copy.deepcopy(record)
        mutated["metadata_modified"] = "1900-01-01T00:00:00"
        mutations.append(make_mutation(artifact_id, "ckan", "stale_metadata_timestamp", "breaking_semantic", "medium", record, mutated, "metadata_modified"))

    return mutations[:max_per_artifact]


def fhir_mutations(artifact_id: str, resource: Dict[str, Any], max_per_artifact: int) -> List[Mutation]:
    mutations: List[Mutation] = []
    mutated = copy.deepcopy(resource)
    meta = mutated.setdefault("meta", {})
    if isinstance(meta, dict):
        meta.setdefault("tag", [])
        if isinstance(meta["tag"], list):
            meta["tag"].append({"system": "https://example.org/contract-bench", "code": "compatible-addition"})
            mutations.append(make_mutation(artifact_id, "fhir", "meta_tag_added", "non_breaking", "none", resource, mutated, "meta.tag"))

    if resource.get("id"):
        mutated = copy.deepcopy(resource)
        mutated.pop("id", None)
        mutations.append(make_mutation(artifact_id, "fhir", "resource_id_removed", "breaking_provenance", "medium", resource, mutated, "id"))

    ref_path = find_first_reference_path(resource)
    if ref_path:
        mutated = copy.deepcopy(resource)
        set_path(mutated, ref_path, "Patient/nonexistent-contract-bench-id")
        mutations.append(make_mutation(artifact_id, "fhir", "reference_broken", "breaking_semantic", "high", resource, mutated, ".".join(map(str, ref_path))))

    period_path = find_period_path(resource)
    if period_path:
        mutated = copy.deepcopy(resource)
        period = get_path(mutated, period_path)
        if isinstance(period, dict):
            period["start"] = "2025-01-02T00:00:00Z"
            period["end"] = "2025-01-01T00:00:00Z"
            mutations.append(make_mutation(artifact_id, "fhir", "period_end_before_start", "breaking_semantic", "high", resource, mutated, ".".join(map(str, period_path))))

    if resource.get("resourceType"):
        mutated = copy.deepcopy(resource)
        mutated["resourceType"] = "UnknownResource"
        mutations.append(make_mutation(artifact_id, "fhir", "resource_type_changed", "breaking_schema", "medium", resource, mutated, "resourceType"))

    return mutations[:max_per_artifact]


def find_first_reference_path(value: Any, prefix: Optional[List[Any]] = None) -> Optional[List[Any]]:
    prefix = prefix or []
    if isinstance(value, dict):
        if isinstance(value.get("reference"), str):
            return prefix + ["reference"]
        for key, child in value.items():
            found = find_first_reference_path(child, prefix + [key])
            if found:
                return found
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found = find_first_reference_path(child, prefix + [index])
            if found:
                return found
    return None


def find_period_path(value: Any, prefix: Optional[List[Any]] = None) -> Optional[List[Any]]:
    prefix = prefix or []
    if isinstance(value, dict):
        if isinstance(value.get("period"), dict):
            period = value["period"]
            if period.get("start") and period.get("end"):
                return prefix + ["period"]
        for key, child in value.items():
            found = find_period_path(child, prefix + [key])
            if found:
                return found
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found = find_period_path(child, prefix + [index])
            if found:
                return found
    return None


def get_path(value: Any, path: Sequence[Any]) -> Any:
    current = value
    for part in path:
        current = current[part]
    return current


def set_path(value: Any, path: Sequence[Any], replacement: Any) -> None:
    current = value
    for part in path[:-1]:
        current = current[part]
    current[path[-1]] = replacement


def make_mutation(
    artifact_id: str,
    artifact_type: str,
    mutation_type: str,
    label: str,
    severity: str,
    original: Dict[str, Any],
    mutated: Dict[str, Any],
    location: str,
) -> Mutation:
    return {
        "artifact_id": artifact_id,
        "artifact_type": artifact_type,
        "mutation_type": mutation_type,
        "label": label,
        "severity": severity,
        "location": location,
        "original": original,
        "mutated": mutated,
    }


def parser_only_detects(mutation: Mutation, context: Dict[str, Any]) -> bool:
    try:
        json.dumps(mutation["mutated"])
        if mutation["artifact_type"] == "openapi":
            return not isinstance(mutation["mutated"].get("paths"), dict)
        if mutation["artifact_type"] == "fhir":
            return not isinstance(mutation["mutated"].get("resourceType"), str)
        return not isinstance(mutation["mutated"], dict)
    except Exception:
        return True


def structural_required_detects(mutation: Mutation, context: Dict[str, Any]) -> bool:
    original = mutation["original"]
    mutated = mutation["mutated"]
    artifact_type = mutation["artifact_type"]
    if artifact_type == "openapi":
        return (
            compare_required_sets(original, mutated)
            or compare_property_presence(original, mutated)
            or compare_property_types(original, mutated)
        )
    if artifact_type == "ckan":
        return ckan_required_fields_ok(original) and not ckan_required_fields_ok(mutated)
    if artifact_type == "fhir":
        return fhir_basic_ok(original) and not fhir_basic_ok(mutated)
    return False


def compatibility_detects(mutation: Mutation, context: Dict[str, Any]) -> bool:
    original = mutation["original"]
    mutated = mutation["mutated"]
    artifact_type = mutation["artifact_type"]
    if structural_required_detects(mutation, context):
        return True
    if artifact_type == "openapi":
        return compare_security_presence(original, mutated)
    if artifact_type == "ckan":
        return ckan_new_violation(original, mutated, ckan_distribution_missing)
    if artifact_type == "fhir":
        return fhir_basic_ok(original) and not fhir_basic_ok(mutated)
    return False


def proposed_multilayer_detects(mutation: Mutation, context: Dict[str, Any]) -> bool:
    original = mutation["original"]
    mutated = mutation["mutated"]
    artifact_type = mutation["artifact_type"]
    if compatibility_detects(mutation, context):
        return True
    if artifact_type == "openapi":
        return (
            compare_enums(original, mutated)
            or compare_security_presence(original, mutated)
            or compare_property_renames(original, mutated)
        )
    if artifact_type == "ckan":
        return (
            (ckan_required_fields_ok(original) and not ckan_required_fields_ok(mutated))
            or ckan_new_violation(original, mutated, ckan_distribution_missing)
            or ckan_new_violation(original, mutated, ckan_format_url_mismatch)
            or ckan_new_violation(original, mutated, ckan_stale_metadata)
        )
    if artifact_type == "fhir":
        return (
            (fhir_basic_ok(original) and not fhir_basic_ok(mutated))
            or fhir_new_broken_references(original, mutated, context.get("fhir_ids", set()))
            or fhir_new_period_violation(original, mutated)
        )
    return False


def semantic_layer_detects(mutation: Mutation, context: Dict[str, Any]) -> bool:
    original = mutation["original"]
    mutated = mutation["mutated"]
    artifact_type = mutation["artifact_type"]
    if artifact_type == "openapi":
        return compare_enums(original, mutated) or compare_property_renames(original, mutated)
    if artifact_type == "ckan":
        return ckan_new_violation(original, mutated, ckan_format_url_mismatch) or ckan_new_violation(original, mutated, ckan_stale_metadata)
    if artifact_type == "fhir":
        return fhir_new_broken_references(original, mutated, context.get("fhir_ids", set())) or fhir_new_period_violation(original, mutated)
    return False


def structural_plus_semantic_detects(mutation: Mutation, context: Dict[str, Any]) -> bool:
    return structural_required_detects(mutation, context) or semantic_layer_detects(mutation, context)


def compare_required_sets(original: Dict[str, Any], mutated: Dict[str, Any]) -> bool:
    for name, schema in openapi_schemas(original).items():
        if not isinstance(schema, dict):
            continue
        m_schema = openapi_schemas(mutated).get(name)
        if not isinstance(m_schema, dict):
            continue
        if set(schema.get("required") or []) != set(m_schema.get("required") or []):
            return True
    return False


def compare_property_presence(original: Dict[str, Any], mutated: Dict[str, Any]) -> bool:
    for name, schema in openapi_schemas(original).items():
        m_schema = openapi_schemas(mutated).get(name)
        if not isinstance(schema, dict) or not isinstance(m_schema, dict):
            continue
        if set(schema_properties(schema)) - set(schema_properties(m_schema)):
            return True
    return False


def compare_property_renames(original: Dict[str, Any], mutated: Dict[str, Any]) -> bool:
    for name, schema in openapi_schemas(original).items():
        m_schema = openapi_schemas(mutated).get(name)
        if not isinstance(schema, dict) or not isinstance(m_schema, dict):
            continue
        before = set(schema_properties(schema))
        after = set(schema_properties(m_schema))
        removed = before - after
        added = after - before
        if removed and added:
            return True
    return False


def compare_property_types(original: Dict[str, Any], mutated: Dict[str, Any]) -> bool:
    for name, schema in openapi_schemas(original).items():
        m_schema = openapi_schemas(mutated).get(name)
        if not isinstance(schema, dict) or not isinstance(m_schema, dict):
            continue
        for field, prop in schema_properties(schema).items():
            m_prop = schema_properties(m_schema).get(field)
            if isinstance(prop, dict) and isinstance(m_prop, dict) and prop.get("type") != m_prop.get("type"):
                return True
    return False


def compare_enums(original: Dict[str, Any], mutated: Dict[str, Any]) -> bool:
    return list(deep_items(original, "enum")) != list(deep_items(mutated, "enum"))


def compare_security_presence(original: Dict[str, Any], mutated: Dict[str, Any]) -> bool:
    return has_security(original) and not has_security(mutated)


def ckan_required_fields_ok(record: Dict[str, Any]) -> bool:
    return all(bool(record.get(field)) for field in REQUIRED_METADATA_FIELDS)


def ckan_distribution_missing(record: Dict[str, Any]) -> bool:
    resources = record.get("resources")
    if not isinstance(resources, list) or not resources:
        return True
    for resource in resources:
        if not isinstance(resource, dict):
            return True
        if not resource.get("url") or not resource.get("format"):
            return True
    return False


def ckan_format_url_mismatch(record: Dict[str, Any]) -> bool:
    resources = record.get("resources")
    if not isinstance(resources, list):
        return False
    extension_to_format = {
        ".csv": "csv",
        ".json": "json",
        ".pdf": "pdf",
        ".zip": "zip",
        ".geojson": "geojson",
        ".xlsx": "xlsx",
    }
    for resource in resources:
        if not isinstance(resource, dict):
            continue
        url = str(resource.get("url", "")).lower()
        fmt = str(resource.get("format", "")).lower()
        for extension, expected in extension_to_format.items():
            if url.endswith(extension) and expected not in fmt:
                return True
    return False


def ckan_stale_metadata(record: Dict[str, Any]) -> bool:
    value = str(record.get("metadata_modified") or record.get("modified") or "")
    match = re.match(r"(\d{4})", value)
    if not match:
        return False
    return int(match.group(1)) < 2000


def ckan_new_violation(original: Dict[str, Any], mutated: Dict[str, Any], check: Callable[[Dict[str, Any]], bool]) -> bool:
    return check(mutated) and not check(original)


def fhir_basic_ok(resource: Dict[str, Any]) -> bool:
    return isinstance(resource.get("resourceType"), str) and resource.get("resourceType") != "UnknownResource" and bool(resource.get("id"))


def collect_fhir_ids() -> Set[str]:
    ids: Set[str] = set()
    for artifact_id, resource in iter_fhir_examples(limit=100000):
        rtype = resource.get("resourceType")
        rid = resource.get("id")
        if rtype and rid:
            ids.add(f"{rtype}/{rid}")
    return ids


def fhir_references(resource: Any) -> Iterable[str]:
    if isinstance(resource, dict):
        ref = resource.get("reference")
        if isinstance(ref, str):
            yield ref
        for value in resource.values():
            yield from fhir_references(value)
    elif isinstance(resource, list):
        for item in resource:
            yield from fhir_references(item)


def fhir_has_broken_reference(resource: Dict[str, Any], known_ids: Set[str]) -> bool:
    return bool(fhir_broken_reference_set(resource, known_ids))


def fhir_broken_reference_set(resource: Dict[str, Any], known_ids: Set[str]) -> Set[str]:
    broken: Set[str] = set()
    for ref in fhir_references(resource):
        if "/" not in ref or ref.startswith("#") or ref.startswith("http"):
            continue
        if ref not in known_ids:
            broken.add(ref)
    return broken


def fhir_new_broken_references(original: Dict[str, Any], mutated: Dict[str, Any], known_ids: Set[str]) -> bool:
    return bool(fhir_broken_reference_set(mutated, known_ids) - fhir_broken_reference_set(original, known_ids))


def fhir_new_violation(
    original: Dict[str, Any],
    mutated: Dict[str, Any],
    known_ids: Set[str],
    check: Callable[[Dict[str, Any], Set[str]], bool],
) -> bool:
    return check(mutated, known_ids) and not check(original, known_ids)


def fhir_new_period_violation(original: Dict[str, Any], mutated: Dict[str, Any]) -> bool:
    return fhir_period_invalid(mutated) and not fhir_period_invalid(original)


def fhir_period_invalid(resource: Any) -> bool:
    if isinstance(resource, dict):
        period = resource.get("period")
        if isinstance(period, dict) and period.get("start") and period.get("end"):
            if str(period["end"]) < str(period["start"]):
                return True
        return any(fhir_period_invalid(value) for value in resource.values())
    if isinstance(resource, list):
        return any(fhir_period_invalid(item) for item in resource)
    return False


DETECTORS: Dict[str, Callable[[Mutation, Dict[str, Any]], bool]] = {
    "parser_only": parser_only_detects,
    "structural_required": structural_required_detects,
    "structural_plus_semantic": structural_plus_semantic_detects,
    "compatibility": compatibility_detects,
    "proposed_multilayer": proposed_multilayer_detects,
}


def build_mutations(args: argparse.Namespace) -> List[Mutation]:
    mutations: List[Mutation] = []
    for artifact_id, spec in iter_openapi_specs(args.openapi_artifacts):
        mutations.extend(openapi_mutations(artifact_id, spec, args.max_mutations_per_artifact))
    for artifact_id, record in iter_ckan_records(args.ckan_artifacts):
        mutations.extend(ckan_mutations(artifact_id, record, args.max_mutations_per_artifact))
    for artifact_id, resource in iter_fhir_examples(args.fhir_artifacts):
        mutations.extend(fhir_mutations(artifact_id, resource, args.max_mutations_per_artifact))
    random.Random(args.seed).shuffle(mutations)
    return mutations


def evaluate(mutations: List[Mutation], context: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    runtime_totals = Counter()
    for index, mutation in enumerate(mutations, start=1):
        row: Dict[str, Any] = {
            "case_id": f"M{index:06d}",
            "artifact_id": mutation["artifact_id"],
            "artifact_type": mutation["artifact_type"],
            "mutation_type": mutation["mutation_type"],
            "label": mutation["label"],
            "severity": mutation["severity"],
            "location": mutation["location"],
            "is_breaking": mutation["label"] != "non_breaking",
        }
        for detector_name, detector in DETECTORS.items():
            start = time.perf_counter()
            detected = detector(mutation, context)
            runtime_totals[detector_name] += time.perf_counter() - start
            row[detector_name] = detected
        rows.append(row)

    metrics = [metric_row(detector_name, rows, runtime_totals[detector_name]) for detector_name in DETECTORS]
    by_label = []
    for detector_name in DETECTORS:
        for label in sorted({row["label"] for row in rows}):
            label_rows = [row for row in rows if row["label"] == label]
            by_label.append(metric_row(detector_name, label_rows, runtime_totals[detector_name], label))

    summary = {
        "cases": len(rows),
        "by_artifact_type": Counter(row["artifact_type"] for row in rows),
        "by_label": Counter(row["label"] for row in rows),
        "by_mutation_type": Counter(row["mutation_type"] for row in rows),
        "detectors": list(DETECTORS.keys()),
        "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }
    return rows, metrics, by_label, summary


def metric_row(detector_name: str, rows: List[Dict[str, Any]], runtime: float, label: str = "all") -> Dict[str, Any]:
    tp = sum(1 for row in rows if row[detector_name] and row["is_breaking"])
    fp = sum(1 for row in rows if row[detector_name] and not row["is_breaking"])
    fn = sum(1 for row in rows if not row[detector_name] and row["is_breaking"])
    tn = sum(1 for row in rows if not row[detector_name] and not row["is_breaking"])
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    weighted_possible = sum(SEVERITY_WEIGHTS.get(row["label"], 1) for row in rows if row["is_breaking"])
    weighted_detected = sum(SEVERITY_WEIGHTS.get(row["label"], 1) for row in rows if row["is_breaking"] and row[detector_name])
    weighted_recall = weighted_detected / weighted_possible if weighted_possible else 0.0
    return {
        "detector": detector_name,
        "label": label,
        "cases": len(rows),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "severity_weighted_recall": round(weighted_recall, 4),
        "mutation_score": round(recall, 4),
        "runtime_seconds_total": round(runtime, 6),
        "runtime_ms_per_case": round((runtime / len(rows) * 1000) if rows else 0, 6),
    }


def write_markdown_report(path: Path, summary: Dict[str, Any], metrics: List[Dict[str, Any]], by_label: List[Dict[str, Any]]) -> None:
    lines = ["# GovDataContractBench Initial Results", ""]
    lines.append(f"- Cases: {summary['cases']}")
    lines.append(f"- By artifact type: {dict(summary['by_artifact_type'])}")
    lines.append(f"- By label: {dict(summary['by_label'])}")
    lines.append("")
    lines.append("## Overall Detector Metrics")
    lines.append("")
    lines.append("| Detector | Precision | Recall | F1 | Severity-weighted recall | Runtime ms/case |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for row in metrics:
        lines.append(
            f"| {row['detector']} | {row['precision']} | {row['recall']} | {row['f1']} | "
            f"{row['severity_weighted_recall']} | {row['runtime_ms_per_case']} |"
        )
    lines.append("")
    lines.append("## Recall By Label")
    lines.append("")
    lines.append("| Detector | Label | Cases | Recall | Severity-weighted recall |")
    lines.append("|---|---|---:|---:|---:|")
    for row in by_label:
        if row["cases"]:
            lines.append(
                f"| {row['detector']} | {row['label']} | {row['cases']} | {row['recall']} | {row['severity_weighted_recall']} |"
            )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--openapi-artifacts", type=int, default=150)
    parser.add_argument("--ckan-artifacts", type=int, default=1000)
    parser.add_argument("--fhir-artifacts", type=int, default=141)
    parser.add_argument("--max-mutations-per-artifact", type=int, default=5)
    parser.add_argument("--seed", type=int, default=20260602)
    args = parser.parse_args()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    context = {"fhir_ids": collect_fhir_ids()}
    mutations = build_mutations(args)
    rows, metrics, by_label, summary = evaluate(mutations, context)

    serializable_summary = {
        **summary,
        "by_artifact_type": dict(summary["by_artifact_type"]),
        "by_label": dict(summary["by_label"]),
        "by_mutation_type": dict(summary["by_mutation_type"]),
        "parameters": vars(args),
    }
    write_csv(RESULTS_DIR / "mutation_cases.csv", rows)
    write_csv(RESULTS_DIR / "metrics_overall.csv", metrics)
    write_csv(RESULTS_DIR / "metrics_by_label.csv", by_label)
    write_json(RESULTS_DIR / "summary.json", serializable_summary)
    write_markdown_report(RESULTS_DIR / "benchmark_report.md", serializable_summary, metrics, by_label)
    print(json.dumps(serializable_summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
