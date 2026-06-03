#!/usr/bin/env python3
"""Fetch public datasets for Paper 1.

The script intentionally avoids fabricated experimental data. It downloads:
- OpenAPI specifications from APIs.guru.
- Dataset metadata from the Data.gov CKAN API.
- Official FHIR US Core package examples.

All outputs include retrieval metadata and checksums for reproducibility.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import os
import re
import tarfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from benchlib import DATA_DIR, ROOT, USER_AGENT, now_iso, sha256_bytes, write_json

APIS_GURU_LIST = "https://api.apis.guru/v2/list.json"
DATA_GOV_SEARCH = "https://catalog.data.gov/api/3/action/package_search"
DATA_GOV_BULK_JSONL = "https://filestore.data.gov/gsa/catalog/jsonl/dataset.jsonl.gz"
FALLBACK_CKAN_SEARCH_ENDPOINTS = (
    "https://open.canada.ca/data/api/action/package_search",
    "https://data.gov.au/data/api/3/action/package_search",
)
FHIR_US_CORE_PACKAGE = "https://hl7.org/fhir/us/core/STU6.1/package.tgz"
SMART_BULK_FHIR_SMALL = "https://github.com/smart-on-fhir/sample-bulk-fhir-datasets/archive/refs/heads/10-patients.zip"

TARGET_KEYWORDS = (
    "government",
    "gov",
    "open data",
    "opendata",
    "health",
    "healthcare",
    "fhir",
    "geo",
    "geospatial",
    "transport",
    "transit",
    "finance",
    "tax",
    "identity",
    "education",
    "census",
    "environment",
)


def safe_filename(value: str, max_len: int = 140) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_")
    return value[:max_len] or "item"


def fetch_bytes(url: str, timeout: int = 60, retries: int = 3) -> bytes:
    last_error: Optional[Exception] = None
    headers = {"User-Agent": USER_AGENT}
    request = urllib.request.Request(url, headers=headers)
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(1.5 * attempt)
    raise RuntimeError(f"failed to fetch {url}: {last_error}")


def choose_api_entries(raw: Dict[str, Any], limit: int) -> List[Tuple[str, str, Dict[str, Any], bool]]:
    candidates: List[Tuple[str, str, Dict[str, Any], bool]] = []
    for api_name, api_meta in raw.items():
        versions = api_meta.get("versions") or {}
        preferred = api_meta.get("preferred")
        version_key = preferred if preferred in versions else None
        if not version_key and versions:
            version_key = sorted(versions.keys())[-1]
        if not version_key:
            continue
        version_meta = versions[version_key]
        spec_url = version_meta.get("swaggerUrl") or version_meta.get("openapiUrl")
        if not spec_url:
            continue
        info = version_meta.get("info") or {}
        haystack = " ".join(
            str(x or "")
            for x in (
                api_name,
                info.get("title"),
                info.get("description"),
                api_meta.get("providerName"),
                " ".join(api_meta.get("categories") or []),
            )
        ).lower()
        targeted = any(keyword in haystack for keyword in TARGET_KEYWORDS)
        candidates.append((api_name, version_key, version_meta, targeted))

    targeted = [row for row in candidates if row[3]]
    others = [row for row in candidates if not row[3]]
    ordered = targeted + others
    return ordered[:limit]


def fetch_apis_guru(limit: int) -> None:
    out_dir = DATA_DIR / "apis_guru"
    specs_dir = out_dir / "specs"
    out_dir.mkdir(parents=True, exist_ok=True)
    specs_dir.mkdir(parents=True, exist_ok=True)

    raw_bytes = fetch_bytes(APIS_GURU_LIST)
    raw = json.loads(raw_bytes.decode("utf-8"))
    (out_dir / "list.json").write_bytes(raw_bytes)

    manifest: List[Dict[str, Any]] = []
    for index, (api_name, version_key, version_meta, targeted) in enumerate(
        choose_api_entries(raw, limit), start=1
    ):
        spec_url = version_meta.get("swaggerUrl") or version_meta.get("openapiUrl")
        suffix = ".json" if str(spec_url).lower().endswith(".json") else ".yaml"
        filename = f"{index:04d}_{safe_filename(api_name)}_{safe_filename(version_key)}{suffix}"
        path = specs_dir / filename
        status = "ok"
        error = ""
        digest = ""
        size = 0
        try:
            data = fetch_bytes(spec_url)
            path.write_bytes(data)
            digest = sha256_bytes(data)
            size = len(data)
        except Exception as exc:  # keep going so the manifest documents failures
            status = "error"
            error = str(exc)

        info = version_meta.get("info") or {}
        manifest.append(
            {
                "index": index,
                "dataset": "apis_guru",
                "api_name": api_name,
                "version": version_key,
                "title": info.get("title", ""),
                "target_keyword_match": targeted,
                "source_url": spec_url,
                "local_path": str(path.relative_to(ROOT)) if status == "ok" else "",
                "retrieved_at": now_iso(),
                "status": status,
                "error": error,
                "sha256": digest,
                "bytes": size,
            }
        )

    write_json(out_dir / "manifest.json", manifest)
    write_manifest_csv(out_dir / "manifest.csv", manifest)


def write_manifest_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def fetch_data_gov(limit: int, rows_per_page: int = 1000) -> None:
    out_dir = DATA_DIR / "data_gov"
    out_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = out_dir / "packages.jsonl.gz"

    fetched = 0
    start = 0
    manifest: Dict[str, Any] = {
        "dataset": "data_gov_ckan",
        "source_api": DATA_GOV_SEARCH,
        "retrieved_at": now_iso(),
        "requested_limit": limit,
        "rows_per_page": rows_per_page,
        "records": 0,
        "status": "ok",
        "errors": [],
    }
    with gzip.open(jsonl_path, "wt", encoding="utf-8") as handle:
        while fetched < limit:
            rows = min(rows_per_page, limit - fetched)
            query = urllib.parse.urlencode({"rows": rows, "start": start})
            url = f"{DATA_GOV_SEARCH}?{query}"
            try:
                payload = json.loads(fetch_bytes(url).decode("utf-8"))
            except Exception as exc:
                manifest["errors"].append({"start": start, "error": str(exc)})
                break
            if not payload.get("success"):
                manifest["errors"].append({"start": start, "error": "CKAN success=false"})
                break
            results = (payload.get("result") or {}).get("results") or []
            if not results:
                break
            for record in results:
                handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")
            fetched += len(results)
            start += len(results)
            if len(results) < rows:
                break

    if fetched == 0:
        bulk_result = fetch_data_gov_bulk(limit, jsonl_path)
        if bulk_result.get("records", 0):
            manifest.update(bulk_result)
            write_json(out_dir / "manifest.json", manifest)
            return
        fallback_result = fetch_fallback_ckan(limit, jsonl_path)
        manifest.update(fallback_result)
        write_json(out_dir / "manifest.json", manifest)
        return

    data = jsonl_path.read_bytes()
    manifest["records"] = fetched
    manifest["local_path"] = str(jsonl_path.relative_to(ROOT))
    manifest["sha256"] = sha256_bytes(data)
    manifest["bytes"] = len(data)
    if manifest["errors"]:
        manifest["status"] = "partial"
    write_json(out_dir / "manifest.json", manifest)


def fetch_data_gov_bulk(limit: int, jsonl_path: Path) -> Dict[str, Any]:
    """Stream the official bulk JSONL export and keep the first `limit` records."""
    rows = 0
    errors: List[Dict[str, str]] = []
    headers = {"User-Agent": USER_AGENT}
    request = urllib.request.Request(DATA_GOV_BULK_JSONL, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            with gzip.GzipFile(fileobj=response) as gz:
                with gzip.open(jsonl_path, "wt", encoding="utf-8") as output:
                    for raw_line in gz:
                        if not raw_line.strip():
                            continue
                        line = raw_line.decode("utf-8", errors="replace")
                        output.write(line if line.endswith("\n") else line + "\n")
                        rows += 1
                        if rows >= limit:
                            break
    except Exception as exc:
        errors.append({"source": DATA_GOV_BULK_JSONL, "error": str(exc)})

    data = jsonl_path.read_bytes() if jsonl_path.exists() else b""
    return {
        "source_api": DATA_GOV_BULK_JSONL,
        "retrieval_method": "bulk_jsonl_stream_first_n",
        "records": rows,
        "local_path": str(jsonl_path.relative_to(ROOT)),
        "sha256": sha256_bytes(data),
        "bytes": len(data),
        "status": "ok" if rows else "partial",
        "errors": errors,
    }


def fetch_fallback_ckan(limit: int, jsonl_path: Path) -> Dict[str, Any]:
    errors: List[Dict[str, str]] = []
    for endpoint in FALLBACK_CKAN_SEARCH_ENDPOINTS:
        rows = 0
        start = 0
        try:
            with gzip.open(jsonl_path, "wt", encoding="utf-8") as handle:
                while rows < limit:
                    page_size = min(1000, limit - rows)
                    query = urllib.parse.urlencode({"rows": page_size, "start": start})
                    url = f"{endpoint}?{query}"
                    payload = json.loads(fetch_bytes(url).decode("utf-8"))
                    if not payload.get("success"):
                        raise RuntimeError("CKAN success=false")
                    results = (payload.get("result") or {}).get("results") or []
                    if not results:
                        break
                    for record in results:
                        handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")
                    rows += len(results)
                    start += len(results)
                    if len(results) < page_size:
                        break
            if rows:
                data = jsonl_path.read_bytes()
                return {
                    "source_api": endpoint,
                    "retrieval_method": "fallback_ckan_package_search",
                    "records": rows,
                    "local_path": str(jsonl_path.relative_to(ROOT)),
                    "sha256": sha256_bytes(data),
                    "bytes": len(data),
                    "status": "ok",
                    "errors": errors,
                    "note": "Data.gov endpoints were unreachable from this environment; used a public government CKAN fallback.",
                }
        except Exception as exc:
            errors.append({"source": endpoint, "error": str(exc)})
    data = jsonl_path.read_bytes() if jsonl_path.exists() else b""
    return {
        "source_api": "",
        "retrieval_method": "fallback_ckan_package_search",
        "records": 0,
        "local_path": str(jsonl_path.relative_to(ROOT)),
        "sha256": sha256_bytes(data),
        "bytes": len(data),
        "status": "partial",
        "errors": errors,
    }


def fetch_fhir_us_core() -> None:
    out_dir = DATA_DIR / "fhir_us_core"
    package_path = out_dir / "package.tgz"
    examples_dir = out_dir / "examples"
    out_dir.mkdir(parents=True, exist_ok=True)
    examples_dir.mkdir(parents=True, exist_ok=True)

    data = fetch_bytes(FHIR_US_CORE_PACKAGE, timeout=90)
    package_path.write_bytes(data)

    extracted = 0
    resource_types: Dict[str, int] = {}
    with tarfile.open(package_path, "r:gz") as archive:
        for member in archive.getmembers():
            if not member.isfile() or not member.name.endswith(".json"):
                continue
            basename = Path(member.name).name
            if not (
                basename.startswith("Patient-")
                or basename.startswith("Encounter-")
                or basename.startswith("Observation-")
                or basename.startswith("Condition-")
                or basename.startswith("Coverage-")
                or basename.startswith("Provenance-")
                or basename.startswith("DiagnosticReport-")
                or basename.startswith("Medication")
            ):
                continue
            file_obj = archive.extractfile(member)
            if file_obj is None:
                continue
            content = file_obj.read()
            target = examples_dir / basename
            target.write_bytes(content)
            extracted += 1
            try:
                parsed = json.loads(content.decode("utf-8"))
                rtype = parsed.get("resourceType", "unknown")
            except Exception:
                rtype = "unparsed"
            resource_types[rtype] = resource_types.get(rtype, 0) + 1

    manifest = {
        "dataset": "fhir_us_core_examples",
        "source_url": FHIR_US_CORE_PACKAGE,
        "retrieved_at": now_iso(),
        "package_path": str(package_path.relative_to(ROOT)),
        "examples_dir": str(examples_dir.relative_to(ROOT)),
        "sha256": sha256_bytes(data),
        "bytes": len(data),
        "extracted_json_examples": extracted,
        "resource_types": resource_types,
        "status": "ok",
    }
    write_json(out_dir / "manifest.json", manifest)


def fetch_smart_bulk_fhir_small() -> None:
    out_dir = DATA_DIR / "smart_bulk_fhir"
    archive_path = out_dir / "10-patients.zip"
    extract_dir = out_dir / "small"
    out_dir.mkdir(parents=True, exist_ok=True)
    extract_dir.mkdir(parents=True, exist_ok=True)

    data = fetch_bytes(SMART_BULK_FHIR_SMALL, timeout=120)
    archive_path.write_bytes(data)

    ndjson_files = 0
    records = 0
    resource_types: Dict[str, int] = {}
    with zipfile.ZipFile(archive_path) as archive:
        for member in archive.namelist():
            if not member.endswith(".ndjson"):
                continue
            target = extract_dir / Path(member).name
            target.write_bytes(archive.read(member))
            ndjson_files += 1
            with target.open("r", encoding="utf-8") as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    try:
                        parsed = json.loads(line)
                    except Exception:
                        continue
                    records += 1
                    rtype = parsed.get("resourceType", "unknown")
                    resource_types[rtype] = resource_types.get(rtype, 0) + 1

    manifest = {
        "dataset": "smart_bulk_fhir_synthea_small",
        "source_url": SMART_BULK_FHIR_SMALL,
        "source_repository": "https://github.com/smart-on-fhir/sample-bulk-fhir-datasets",
        "retrieved_at": now_iso(),
        "archive_path": str(archive_path.relative_to(ROOT)),
        "extract_dir": str(extract_dir.relative_to(ROOT)),
        "sha256": sha256_bytes(data),
        "bytes": len(data),
        "ndjson_files": ndjson_files,
        "records": records,
        "resource_types": resource_types,
        "status": "ok",
        "note": "Synthea-generated sample FHIR bulk export dataset from SMART-on-FHIR; small package contains 10 patients.",
    }
    write_json(out_dir / "manifest.json", manifest)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apis-guru-limit", type=int, default=150)
    parser.add_argument("--data-gov-limit", type=int, default=10000)
    parser.add_argument("--skip-apis-guru", action="store_true")
    parser.add_argument("--skip-data-gov", action="store_true")
    parser.add_argument("--skip-fhir", action="store_true")
    parser.add_argument("--skip-smart-bulk-fhir", action="store_true")
    args = parser.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not args.skip_apis_guru:
        fetch_apis_guru(args.apis_guru_limit)
    if not args.skip_data_gov:
        fetch_data_gov(args.data_gov_limit)
    if not args.skip_fhir:
        fetch_fhir_us_core()
    if not args.skip_smart_bulk_fhir:
        fetch_smart_bulk_fhir_small()


if __name__ == "__main__":
    main()
