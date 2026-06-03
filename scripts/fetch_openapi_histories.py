#!/usr/bin/env python3
"""Fetch natural OpenAPI drift pairs from the APIs.guru Git history.

This script uses the public Git history of APIs-guru/openapi-directory rather
than fabricated changes. It extracts consecutive versions of OpenAPI JSON files
that changed over time and stores them as old/new pairs for natural drift
analysis.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from benchlib import ROOT, USER_AGENT, write_csv, write_json

DATA_DIR = ROOT / "data" / "openapi_histories"
REPO_DIR = DATA_DIR / "openapi-directory"
PAIRS_DIR = DATA_DIR / "pairs"
REPO_URL = "https://github.com/APIs-guru/openapi-directory.git"
GITHUB_API = "https://api.github.com/repos/APIs-guru/openapi-directory"
RAW_BASE = "https://raw.githubusercontent.com/APIs-guru/openapi-directory"
APIS_GURU_LIST = ROOT / "data" / "apis_guru" / "list.json"


def run_git(args: List[str], cwd: Optional[Path] = None, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd) if cwd else None,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def ensure_repo() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if (REPO_DIR / ".git").exists():
        run_git(["fetch", "--all", "--prune"], cwd=REPO_DIR)
        return
    run_git(["clone", "--filter=blob:none", "--sparse", REPO_URL, str(REPO_DIR)])
    run_git(["sparse-checkout", "set", "APIs"], cwd=REPO_DIR)


def fetch_json_url(url: str) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_bytes_url(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def api_path_from_apis_guru_url(url: str) -> Optional[str]:
    marker = "/v2/specs/"
    if marker not in url:
        return None
    return "APIs/" + url.split(marker, 1)[1]


def candidate_paths_from_existing_manifest(max_files: int) -> List[str]:
    manifest_path = ROOT / "data" / "apis_guru" / "manifest.json"
    if not manifest_path.exists():
        return []
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    paths: List[str] = []
    for row in manifest:
        if row.get("status") != "ok":
            continue
        path = api_path_from_apis_guru_url(row.get("source_url", ""))
        if path and path.endswith(".json"):
            paths.append(path)
        if len(paths) >= max_files * 5:
            break
    return paths


def github_commits_for_path(path: str, max_commits: int) -> List[Dict[str, Any]]:
    query = urllib.parse.urlencode({"path": path, "per_page": max_commits})
    url = f"{GITHUB_API}/commits?{query}"
    try:
        commits = fetch_json_url(url)
    except Exception:
        return []
    if not isinstance(commits, list):
        return []
    return commits[:max_commits]


def github_raw_file(commit: str, path: str) -> Optional[bytes]:
    url = f"{RAW_BASE}/{commit}/{path}"
    try:
        return fetch_bytes_url(url)
    except Exception:
        return None


def fetch_with_github_api(args: argparse.Namespace) -> Dict[str, Any]:
    PAIRS_DIR.mkdir(parents=True, exist_ok=True)
    rows: List[Dict[str, Any]] = []
    selected_files = 0
    pair_index = 0
    for path in candidate_paths_from_existing_manifest(args.max_files):
        commits = github_commits_for_path(path, args.max_commits_per_file)
        if len(commits) < 2:
            continue
        valid_pairs_for_file = 0
        for newer_info, older_info in zip(commits, commits[1:]):
            newer = newer_info.get("sha")
            older = older_info.get("sha")
            if not newer or not older:
                continue
            old_data = github_raw_file(older, path)
            new_data = github_raw_file(newer, path)
            if not old_data or not new_data:
                continue
            if parse_json(old_data) is None or parse_json(new_data) is None:
                continue
            pair_index += 1
            valid_pairs_for_file += 1
            pair_dir = PAIRS_DIR / f"pair_{pair_index:04d}"
            pair_dir.mkdir(parents=True, exist_ok=True)
            (pair_dir / "old.json").write_bytes(old_data)
            (pair_dir / "new.json").write_bytes(new_data)
            metadata = {
                "pair_id": f"pair_{pair_index:04d}",
                "repo": REPO_URL,
                "path": path,
                "old_commit": older,
                "new_commit": newer,
                "old_date": (((older_info.get("commit") or {}).get("committer") or {}).get("date") or ""),
                "new_date": (((newer_info.get("commit") or {}).get("committer") or {}).get("date") or ""),
                "old_path": str((pair_dir / "old.json").relative_to(ROOT)),
                "new_path": str((pair_dir / "new.json").relative_to(ROOT)),
                "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "retrieval_method": "github_api_commits_and_raw",
            }
            (pair_dir / "metadata.json").write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")
            rows.append(metadata)
            if pair_index >= args.max_pairs:
                break
        if valid_pairs_for_file:
            selected_files += 1
        if pair_index >= args.max_pairs or selected_files >= args.max_files:
            break

    write_csv(DATA_DIR / "manifest.csv", rows)
    write_json(DATA_DIR / "manifest.json", rows)
    summary = {
        "repo": REPO_URL,
        "files_with_pairs": selected_files,
        "pairs": pair_index,
        "max_files": args.max_files,
        "max_commits_per_file": args.max_commits_per_file,
        "max_pairs": args.max_pairs,
        "method": "github_api",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    write_json(DATA_DIR / "summary.json", summary)
    return summary


def version_sort_key(value: str) -> Tuple[int, List[Any]]:
    parts: List[Any] = []
    for token in value.replace("-", ".").replace("_", ".").split("."):
        if token.isdigit():
            parts.append(int(token))
        else:
            parts.append(token)
    return (0 if parts else 1, parts)


def fetch_apis_guru_version_pairs(args: argparse.Namespace) -> Dict[str, Any]:
    if not APIS_GURU_LIST.exists():
        raise SystemExit("Missing data/apis_guru/list.json. Run fetch_public_datasets.py first.")
    raw = json.loads(APIS_GURU_LIST.read_text(encoding="utf-8"))
    PAIRS_DIR.mkdir(parents=True, exist_ok=True)
    rows: List[Dict[str, Any]] = []
    pair_index = 0
    files_with_pairs = 0
    for api_name, api_meta in raw.items():
        versions = api_meta.get("versions") or {}
        version_keys = sorted(versions.keys(), key=version_sort_key)
        if len(version_keys) < 2:
            continue
        valid_for_api = 0
        for old_version, new_version in zip(version_keys, version_keys[1:]):
            if valid_for_api >= args.max_pairs_per_api:
                break
            old_meta = versions.get(old_version) or {}
            new_meta = versions.get(new_version) or {}
            old_url = old_meta.get("swaggerUrl") or old_meta.get("openapiUrl")
            new_url = new_meta.get("swaggerUrl") or new_meta.get("openapiUrl")
            if not old_url or not new_url or not old_url.endswith(".json") or not new_url.endswith(".json"):
                continue
            old_data = None
            new_data = None
            try:
                old_data = fetch_bytes_url(old_url)
                new_data = fetch_bytes_url(new_url)
            except Exception:
                continue
            if parse_json(old_data) is None or parse_json(new_data) is None:
                continue
            pair_index += 1
            valid_for_api += 1
            pair_dir = PAIRS_DIR / f"pair_{pair_index:04d}"
            pair_dir.mkdir(parents=True, exist_ok=True)
            (pair_dir / "old.json").write_bytes(old_data)
            (pair_dir / "new.json").write_bytes(new_data)
            metadata = {
                "pair_id": f"pair_{pair_index:04d}",
                "repo": "APIs.guru public version directory",
                "path": api_name,
                "old_commit": old_version,
                "new_commit": new_version,
                "old_date": "",
                "new_date": "",
                "old_path": str((pair_dir / "old.json").relative_to(ROOT)),
                "new_path": str((pair_dir / "new.json").relative_to(ROOT)),
                "old_source_url": old_url,
                "new_source_url": new_url,
                "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "retrieval_method": "apis_guru_public_versions",
            }
            (pair_dir / "metadata.json").write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")
            rows.append(metadata)
            if pair_index >= args.max_pairs:
                break
        if valid_for_api:
            files_with_pairs += 1
        if pair_index >= args.max_pairs or files_with_pairs >= args.max_files:
            break

    write_csv(DATA_DIR / "manifest.csv", rows)
    write_json(DATA_DIR / "manifest.json", rows)
    summary = {
        "repo": "APIs.guru public version directory",
        "files_with_pairs": files_with_pairs,
        "pairs": pair_index,
        "max_files": args.max_files,
        "max_pairs": args.max_pairs,
        "method": "apis_guru_versions",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    write_json(DATA_DIR / "summary.json", summary)
    return summary


def list_candidate_files(max_files: int) -> List[str]:
    output = run_git(["ls-tree", "-r", "--name-only", "HEAD", "APIs"], cwd=REPO_DIR)
    candidates = [
        line.strip()
        for line in output.splitlines()
        if line.strip().endswith((".json", ".yaml", ".yml"))
        and (line.endswith("openapi.json") or line.endswith("swagger.json"))
    ]
    json_candidates = [path for path in candidates if path.endswith(".json")]
    return json_candidates[: max_files * 8]


def commit_history(path: str, max_commits: int) -> List[str]:
    output = run_git(["log", "--follow", "--format=%H", "--", path], cwd=REPO_DIR)
    commits = [line.strip() for line in output.splitlines() if line.strip()]
    return commits[:max_commits]


def show_file(commit: str, path: str) -> Optional[bytes]:
    result = subprocess.run(
        ["git", "show", f"{commit}:{path}"],
        cwd=str(REPO_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout


def commit_date(commit: str) -> str:
    return run_git(["show", "-s", "--format=%cI", commit], cwd=REPO_DIR).strip()


def parse_json(data: bytes) -> Optional[Dict[str, Any]]:
    try:
        parsed = json.loads(data.decode("utf-8"))
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-files", type=int, default=30)
    parser.add_argument("--max-commits-per-file", type=int, default=8)
    parser.add_argument("--max-pairs", type=int, default=80)
    parser.add_argument("--max-pairs-per-api", type=int, default=3)
    parser.add_argument("--method", choices=("apis-guru", "api", "git"), default="apis-guru")
    args = parser.parse_args()

    if args.method == "apis-guru":
        summary = fetch_apis_guru_version_pairs(args)
        print(json.dumps(summary, indent=2, sort_keys=True))
        return

    if args.method == "api":
        summary = fetch_with_github_api(args)
        print(json.dumps(summary, indent=2, sort_keys=True))
        return

    ensure_repo()
    PAIRS_DIR.mkdir(parents=True, exist_ok=True)

    rows: List[Dict[str, Any]] = []
    selected_files = 0
    pair_index = 0
    for path in list_candidate_files(args.max_files):
        commits_newest_first = commit_history(path, args.max_commits_per_file)
        if len(commits_newest_first) < 2:
            continue
        valid_pairs_for_file = 0
        for newer, older in zip(commits_newest_first, commits_newest_first[1:]):
            old_data = show_file(older, path)
            new_data = show_file(newer, path)
            if not old_data or not new_data:
                continue
            old_json = parse_json(old_data)
            new_json = parse_json(new_data)
            if old_json is None or new_json is None:
                continue
            pair_index += 1
            valid_pairs_for_file += 1
            pair_dir = PAIRS_DIR / f"pair_{pair_index:04d}"
            pair_dir.mkdir(parents=True, exist_ok=True)
            (pair_dir / "old.json").write_bytes(old_data)
            (pair_dir / "new.json").write_bytes(new_data)
            metadata = {
                "pair_id": f"pair_{pair_index:04d}",
                "repo": REPO_URL,
                "path": path,
                "old_commit": older,
                "new_commit": newer,
                "old_date": commit_date(older),
                "new_date": commit_date(newer),
                "old_path": str((pair_dir / "old.json").relative_to(ROOT)),
                "new_path": str((pair_dir / "new.json").relative_to(ROOT)),
                "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
            (pair_dir / "metadata.json").write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")
            rows.append(metadata)
            if pair_index >= args.max_pairs:
                break
        if valid_pairs_for_file:
            selected_files += 1
        if pair_index >= args.max_pairs or selected_files >= args.max_files:
            break

    write_csv(DATA_DIR / "manifest.csv", rows)
    write_json(DATA_DIR / "manifest.json", rows)
    summary = {
        "repo": REPO_URL,
        "files_with_pairs": selected_files,
        "pairs": pair_index,
        "max_files": args.max_files,
        "max_commits_per_file": args.max_commits_per_file,
        "max_pairs": args.max_pairs,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    write_json(DATA_DIR / "summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
