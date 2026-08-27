"""publish_log.py - append machine-readable publish records.

The log lives outside the repo so tokens and operational facts are never
committed. publish.sh calls this only after a real successful upload;
--dry-run must not write records.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
from collections.abc import Sequence

from registry_lib import REGISTRY_JSON_REL, ROOT, parse_registry

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

TEMP = os.environ.get("TEMP") or os.environ.get("TMP") or "/tmp"
PUB = os.environ.get("PUB")
REPO_HISTORY_REL = "sops/publish-history.jsonl"


def durable_log_path() -> str:
    local = os.environ.get("LOCALAPPDATA") or os.environ.get("HOME") or TEMP
    return os.path.join(local, "sopworks", "logs", "publish-log.jsonl")


def repo_history_path() -> str:
    """Versioned event summary; safe because it never contains file tokens."""
    return os.path.join(ROOT, REPO_HISTORY_REL)


def legacy_temp_log_path() -> str:
    return os.path.join(TEMP, "sop-exports", "publish", "publish-log.jsonl")


def default_log_path() -> str:
    if PUB:
        return os.path.join(PUB, "publish-log.jsonl")
    return durable_log_path()


def _git_head() -> str:
    proc = subprocess.run(
        ["git", "-C", ROOT, "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc.stdout.strip() if proc.returncode == 0 else "unknown"


def _git_dirty() -> bool:
    proc = subprocess.run(
        ["git", "-C", ROOT, "status", "--porcelain"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        return True
    return bool(proc.stdout.strip())


def _source_hash(source: str) -> str:
    path = os.path.join(ROOT, source.replace(os.sep, "/"))
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _entry_for_source(source: str) -> dict[str, str]:
    normalized = source.replace(os.sep, "/")
    entries, errors = parse_registry()
    if errors:
        raise RuntimeError("registry parse failed: %s" % "; ".join(errors))
    for entry in entries:
        if entry.get("source", "").replace(os.sep, "/") == normalized:
            return entry
    raise KeyError("source not registered: %s" % source)


def _update_registry_last_published(document_id: str, published_on: str,
                                    registry_path: str | None = None) -> None:
    path = registry_path or os.path.join(ROOT, REGISTRY_JSON_REL)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    raw_entries = data.get("entries", []) if isinstance(data, dict) else data
    if not isinstance(raw_entries, list):
        raise ValueError("registry entries must be a list")
    for entry in raw_entries:
        if not isinstance(entry, dict):
            continue
        if entry.get("document_id") == document_id:
            entry["last_published_at"] = published_on
            break
    else:
        raise KeyError("document not found: %s" % document_id)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _write_record(log_path: str, record: dict[str, str]) -> None:
    os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def append_publish(log_path: str, source: str, file_token: str,
                   result: str = "success", update_registry: bool = False,
                   registry_path: str | None = None,
                   persist: bool = False,
                   repo_summary: bool = False,
                   repo_history: str | None = None) -> dict[str, str]:
    entry = _entry_for_source(source)
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    record = {
        "document_id": entry.get("document_id", ""),
        "version": entry.get("version", ""),
        "source": source.replace(os.sep, "/"),
        "commit": _git_head(),
        "dirty": _git_dirty(),
        "source_hash": _source_hash(source),
        "time": now,
        "result": result,
        "file_token": file_token,
    }
    _write_record(log_path, record)
    if persist:
        durable = durable_log_path()
        if os.path.abspath(durable) != os.path.abspath(log_path):
            _write_record(durable, record)
    if repo_summary:
        safe_record = {key: value for key, value in record.items()
                       if key != "file_token"}
        _write_record(repo_history or repo_history_path(), safe_record)
    if update_registry:
        _update_registry_last_published(entry.get("document_id", ""),
                                        now[:10], registry_path)
    return record


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="append a publish record")
    parser.add_argument("source", help="registered md path relative to repo root")
    parser.add_argument("file_token", help="Feishu drive file token")
    parser.add_argument("--log", default=default_log_path(), help="JSONL log path")
    parser.add_argument("--result", default="success",
                        choices=("success", "failed"), help="record result")
    parser.add_argument("--update-registry", action="store_true",
                        help="write last_published_at into registry.json")
    parser.add_argument("--persist", action="store_true",
                        help="also append to durable user log")
    parser.add_argument("--repo-summary", action="store_true",
                        help="append token-free summary to sops/publish-history.jsonl")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv if argv is not None else sys.argv[1:])
    append_publish(args.log, args.source, args.file_token, args.result,
                   update_registry=args.update_registry, persist=args.persist,
                   repo_summary=args.repo_summary)
    print("OK publish log: %s" % args.log)
    return 0


if __name__ == "__main__":
    sys.exit(main())
