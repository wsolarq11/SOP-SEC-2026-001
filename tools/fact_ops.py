"""fact_ops.py - register requirement/review/signoff facts.

Updates both sops/registry.json and source front matter, then regenerates
REGISTRY.md. These commands do not invent approval data; they are the explicit
entry point after a real decision or signoff has happened.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
from collections.abc import Sequence

import registry_lib
import registry_render

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _registry_path() -> str:
    return os.path.join(registry_lib.ROOT, registry_lib.REGISTRY_JSON_REL)


def update_registry(document_id: str, updates: dict[str, str],
                    path: str | None = None) -> None:
    path = path or _registry_path()
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    raw_entries = data.get("entries", []) if isinstance(data, dict) else data
    if not isinstance(raw_entries, list):
        raise ValueError("registry entries must be a list")
    for entry in raw_entries:
        if not isinstance(entry, dict):
            continue
        if entry.get("document_id") == document_id:
            entry.update(updates)
            break
    else:
        raise ValueError("document not found: %s" % document_id)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _require_date(value: str, label: str) -> str:
    if not DATE_RE.match(value):
        raise ValueError("%s must be YYYY-MM-DD, got %r" % (label, value))
    return value


def _write_registry_and_render(document_id: str,
                               updates: dict[str, str]) -> int:
    update_registry(document_id, updates)
    return registry_render.main(["--write"])


def cmd_link(document_id: str, requirement_ref: str) -> int:
    if not requirement_ref:
        print("[FAIL] requirement_ref is required", file=sys.stderr)
        return 1
    return _write_registry_and_render(document_id, {
        "requirement_ref": requirement_ref,
    })


def cmd_review(document_id: str, reviewer: str, reviewed_at: str) -> int:
    _require_date(reviewed_at, "reviewed_at")
    return _write_registry_and_render(document_id, {
        "reviewer": reviewer,
        "reviewed_at": reviewed_at,
    })


def cmd_signoff(document_id: str, approver: str, effective_date: str,
                reviewer: str = "", reviewed_at: str = "") -> int:
    today = dt.date.today().isoformat()
    _require_date(effective_date, "effective_date")
    updates = {
        "status": "Approved",
        "approver": approver,
        "effective_date": effective_date,
        "approved_at": today,
    }
    if reviewer:
        updates["reviewer"] = reviewer
    if reviewed_at:
        updates["reviewed_at"] = _require_date(reviewed_at, "reviewed_at")
    return _write_registry_and_render(document_id, updates)


def cmd_sync(document_id: str) -> int:
    entries, errors = registry_lib.parse_registry()
    if errors:
        for error in errors:
            print("[FAIL] %s" % error, file=sys.stderr)
        return 1
    if not any(entry.get("document_id") == document_id for entry in entries):
        print("[FAIL] document not found: %s" % document_id, file=sys.stderr)
        return 1
    return registry_render.main(["--write"])


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="register production facts")
    sub = parser.add_subparsers(dest="action", required=True)
    link = sub.add_parser("link", help="link requirement source")
    link.add_argument("document_id")
    link.add_argument("requirement_ref")
    review = sub.add_parser("review", help="register review fact")
    review.add_argument("document_id")
    review.add_argument("reviewer")
    review.add_argument("reviewed_at")
    signoff = sub.add_parser("signoff", help="register signoff fact")
    signoff.add_argument("document_id")
    signoff.add_argument("approver")
    signoff.add_argument("effective_date")
    signoff.add_argument("--reviewer", default="")
    signoff.add_argument("--reviewed-at", default="")
    sync = sub.add_parser("sync", help="copy front matter facts to registry")
    sync.add_argument("document_id")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv if argv is not None else sys.argv[1:])
    if args.action == "link":
        return cmd_link(args.document_id, args.requirement_ref)
    if args.action == "review":
        return cmd_review(args.document_id, args.reviewer, args.reviewed_at)
    if args.action == "signoff":
        return cmd_signoff(args.document_id, args.approver,
                           args.effective_date, args.reviewer,
                           args.reviewed_at)
    if args.action == "sync":
        return cmd_sync(args.document_id)
    return 2


if __name__ == "__main__":
    sys.exit(main())
