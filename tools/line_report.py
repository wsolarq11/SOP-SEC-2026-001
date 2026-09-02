"""line_report.py - summarize the SOP production line.

Reads only local data: registry, source front matter, and the publish log.
Never prints file tokens or secret values.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence

from publish_log import (
    default_log_path,
    durable_log_path,
    legacy_temp_log_path,
    repo_history_path,
)
import publish_tokens
from registry_lib import ROOT, parse_registry

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

STAGE_PUBLISHED = "已发布"
STAGE_APPROVED = "已签批"
STAGE_REVIEW = "待审"
STAGE_PENDING = "待签批"
BLOCKED = "阻塞"
NORMAL = "正常"


def _read_publish_records(log_path: str,
                          repo_history: str | None = None) -> list[dict[str, object]]:
    paths = [log_path, repo_history or repo_history_path(),
             durable_log_path(), legacy_temp_log_path()]
    records: list[dict[str, object]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for path in paths:
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(data, dict):
                    continue
                key = (str(data.get("document_id", "")),
                       str(data.get("version", "")),
                       str(data.get("time", "")),
                       str(data.get("result", "")))
                if key in seen:
                    continue
                seen.add(key)
                records.append(data)
    return records


def _latest_record(records: list[dict[str, object]],
                   source: str) -> dict[str, object] | None:
    matched = [record for record in records
               if str(record.get("source", "")) == source]
    if not matched:
        return None
    return max(matched, key=lambda record: str(record.get("time", "")))


def _latest_publish(records: list[dict[str, object]],
                    source: str) -> dict[str, object] | None:
    matched = [
        record for record in records
        if str(record.get("source", "")) == source
        and record.get("result") == "success"
    ]
    if not matched:
        return None
    return max(matched, key=lambda record: str(record.get("time", "")))


def _read_tokens(path: str) -> dict[str, str]:
    return publish_tokens.read_publish_tokens(path)


def _has_published_fact(entry: dict[str, str],
                        publish: dict[str, object] | None) -> bool:
    return bool(publish or entry.get("last_published_at"))


def _line_stage(entry: dict[str, str],
                publish: dict[str, object] | None) -> str:
    if _has_published_fact(entry, publish):
        return STAGE_PUBLISHED
    if entry.get("status") == "Approved":
        return STAGE_APPROVED
    approver = entry.get("approver", "")
    if approver and approver != "待定":
        return STAGE_REVIEW
    return STAGE_PENDING


def _is_blocked(entry: dict[str, str],
                records: Sequence[dict[str, object]],
                tokens: dict[str, str]) -> bool:
    source = entry.get("source", "")
    if not source or not os.path.isfile(os.path.join(ROOT, source)):
        return True
    if source not in tokens or not tokens[source] or tokens[source] == "NONE":
        return True
    latest = _latest_record(records, source)
    return latest is not None and latest.get("result") == "failed"


def _build_lines(entries: Sequence[dict[str, str]],
                 records: Sequence[dict[str, object]],
                 tokens: dict[str, str]) -> list[dict[str, str]]:
    lines = []
    for entry in entries:
        source = entry.get("source", "")
        publish = _latest_publish(records, source)
        lines.append({
            "document_id": entry.get("document_id", ""),
            "title": entry.get("title", ""),
            "status": entry.get("status", ""),
            "stage": _line_stage(entry, publish),
            "requirement_ref": entry.get("requirement_ref", ""),
            "approver": entry.get("approver", ""),
            "effective_date": entry.get("effective_date", ""),
            "reviewer": entry.get("reviewer", ""),
            "reviewed_at": entry.get("reviewed_at", ""),
            "approved_at": entry.get("approved_at", ""),
            "last_publish": entry.get("last_published_at", ""),
            "blocked": BLOCKED if _is_blocked(entry, records, tokens) else NORMAL,
        })
    return lines


def _summary(lines: Sequence[dict[str, str]],
             records: Sequence[dict[str, object]]) -> dict[str, int]:
    return {
        "production_lines": 1,
        "lines": len(lines),
        "active": len(lines),
        "publish_records": len(records),
        "published": sum(line["stage"] == STAGE_PUBLISHED for line in lines),
        "approved": sum(line["stage"] == STAGE_APPROVED for line in lines),
        "review": sum(line["stage"] == STAGE_REVIEW for line in lines),
        "pending_approval": sum(line["stage"] == STAGE_PENDING for line in lines),
        "blocked": sum(line["blocked"] == BLOCKED for line in lines),
    }


def _print_text(summary: dict[str, int], lines: Sequence[dict[str, str]]) -> None:
    print("== SOP 产线报告 ==")
    print("产线数: %d" % summary["production_lines"])
    print("在产文档: %d | 发布记录: %d"
          % (summary["active"], summary["publish_records"]))
    print("已发布: %d | 已签批: %d | 待审: %d | 待签批: %d | 阻塞: %d"
          % (summary["published"], summary["approved"], summary["review"],
             summary["pending_approval"], summary["blocked"]))
    print("| 文档号 | 标题 | 状态 | 阶段 | 需求来源 | 签批人 | 最近发布 | 阻塞 |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for line in lines:
        print("| %s | %s | %s | %s | %s | %s | %s | %s |"
              % (line["document_id"], line["title"], line["status"],
                 line["stage"], line["requirement_ref"] or "未知",
                 line["approver"] or "未知",
                 line["last_publish"] or "无", line["blocked"]))


def _filter_entries(entries: list[dict[str, str]],
                    document_id: str) -> list[dict[str, str]]:
    matched = [entry for entry in entries
               if entry.get("document_id") == document_id]
    if not matched:
        raise ValueError("document not found: %s" % document_id)
    return matched


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="report SOP production line")
    parser.add_argument("--doc", help="show only one document_id")
    parser.add_argument("--log", default=default_log_path(), help="publish log path")
    parser.add_argument("--repo-history",
                        default=repo_history_path(),
                        help="token-free repo publish history path")
    parser.add_argument("--tokens",
                        default=os.path.join(ROOT, ".publish-tokens"),
                        help="token mapping path")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv if argv is not None else sys.argv[1:])
    entries, errors = parse_registry()
    if errors:
        for error in errors:
            print("[FAIL] %s" % error, file=sys.stderr)
        return 1
    if args.doc:
        try:
            entries = _filter_entries(entries, args.doc)
        except ValueError as exc:
            print("[FAIL] %s" % exc, file=sys.stderr)
            return 1
    records = _read_publish_records(args.log, args.repo_history)
    tokens = _read_tokens(args.tokens)
    lines = _build_lines(entries, records, tokens)
    summary = _summary(lines, records)
    if args.json:
        print(json.dumps({"summary": summary, "entries": lines},
                         ensure_ascii=False, indent=2))
    else:
        _print_text(summary, lines)
    return 0


if __name__ == "__main__":
    sys.exit(main())
