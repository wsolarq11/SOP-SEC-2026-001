#!/usr/bin/env python3
"""Render sops/registry.json into REGISTRY.md and source front matter.

Usage:
  python registry_render.py            # print generated table
  python registry_render.py --write    # update REGISTRY.md + source front matter
  python registry_render.py --check    # exit 1 if either generated view is stale
"""
from __future__ import annotations

import os
import sys
from collections.abc import Sequence

from registry_lib import (
    COLUMNS,
    FRONT_MATTER_FIELDS,
    OPTIONAL_FIELDS,
    REGISTRY_JSON_REL,
    REGISTRY_REL,
    REQUIRED_FRONT_MATTER,
    ROOT,
    parse_fm,
    parse_registry,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

RENDER_FIELDS = COLUMNS + OPTIONAL_FIELDS

HEADER_LABELS = {
    "document_id": "文档号",
    "title": "标题",
    "doc_type": "类型",
    "domain": "域名",
    "version": "版本",
    "author": "编制人",
    "status": "状态",
    "source": "源文件",
    "target_dir": "目标目录",
    "requirement_ref": "需求来源",
    "approver": "签批人",
    "effective_date": "生效日期",
    "reviewer": "评审人",
    "reviewed_at": "评审时间",
    "approved_at": "签批时间",
    "last_published_at": "最近发布",
}

MARKER = "<!-- generated from sops/registry.json; do not edit by hand -->\n"


def render_table(entries: Sequence[dict[str, str]]) -> str:
    rows = [HEADER_LABELS[column] for column in RENDER_FIELDS]
    lines = ["## 已分配编号"]
    lines.append("| %s |" % " | ".join(rows))
    lines.append("| %s |" % " | ".join(["---"] * len(rows)))
    for entry in entries:
        cells = [str(entry.get(column, "")) for column in RENDER_FIELDS]
        lines.append("| %s |" % " | ".join(cells))
    return "\n".join(lines) + "\n"


def _section_bounds(lines: list[str]) -> tuple[int, int] | None:
    start = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if start is None and stripped == "## 已分配编号":
            start = i
        elif start is not None and stripped.startswith("## "):
            return start, i
    if start is None:
        return None
    return start, len(lines)


def replace_section(text: str, table: str) -> str | None:
    lines = text.splitlines(keepends=True)
    bounds = _section_bounds(lines)
    if bounds is None:
        return None
    start, end = bounds
    before = "".join(lines[:start]).replace(MARKER, "")
    after = "".join(lines[end:])
    if not after.startswith(("\n", "\r\n")):
        after = "\n" + after
    return before + MARKER + table + after


def front_matter_fields(entry: dict[str, str]) -> dict[str, str]:
    """Map registry fields to generated front matter, omitting empty optional facts."""
    fields: dict[str, str] = {}
    for fm_key, reg_key in FRONT_MATTER_FIELDS:
        value = str(entry.get(reg_key, ""))
        if value or fm_key in REQUIRED_FRONT_MATTER:
            fields[fm_key] = value
    return fields


def render_front_matter(fields: dict[str, str]) -> str:
    """Render a deterministic front matter block from registry facts."""
    lines = ["---"]
    for fm_key, _ in FRONT_MATTER_FIELDS:
        if fm_key in fields:
            lines.append("%s: %s" % (fm_key, fields[fm_key]))
    lines.append("---")
    return "\n".join(lines) + "\n"


def _front_matter_bounds(text: str) -> tuple[int, int] | None:
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return 1, i
    return None


def sync_source_front_matter(rel_source: str, entry: dict[str, str],
                             root: str | None = None) -> bool:
    """Rewrite one source front matter from registry facts; returns changed."""
    path = os.path.join(root or ROOT, rel_source)
    with open(path, encoding="utf-8") as f:
        text = f.read()
    bounds = _front_matter_bounds(text)
    if bounds is None:
        raise ValueError("source has no front matter: %s" % rel_source)
    _, end = bounds
    lines = text.split("\n")
    body = lines[end + 1:]
    block = render_front_matter(front_matter_fields(entry)).rstrip("\n")
    updated = block + "\n" + "\n".join(body)
    if updated == text:
        return False
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(updated)
    return True


def _registry_path() -> str:
    return os.path.join(ROOT, REGISTRY_REL)


def _write_table(entries: Sequence[dict[str, str]]) -> int:
    table = render_table(entries)
    with open(_registry_path(), encoding="utf-8") as f:
        text = f.read()
    updated = replace_section(text, table)
    if updated is None:
        print("[FAIL] REGISTRY.md 未找到「已分配编号」", file=sys.stderr)
        return 1
    with open(_registry_path(), "w", encoding="utf-8") as f:
        f.write(updated)
    print("OK updated: %s" % REGISTRY_REL)
    return 0


def _check_table(entries: Sequence[dict[str, str]]) -> int:
    table = render_table(entries)
    with open(_registry_path(), encoding="utf-8") as f:
        text = f.read()
    if table in text:
        print("OK REGISTRY.md 与 %s 一致" % REGISTRY_JSON_REL)
        return 0
    print("[FAIL] REGISTRY.md 已过期，请运行 python registry_render.py --write",
          file=sys.stderr)
    return 1


def _sync_sources(entries: Sequence[dict[str, str]]) -> int:
    changed = 0
    for entry in entries:
        source = entry.get("source", "")
        if not source:
            continue
        try:
            if sync_source_front_matter(source, entry):
                changed += 1
        except (OSError, ValueError) as exc:
            print("[FAIL] front matter 同步失败: %s" % exc, file=sys.stderr)
            return 1
    if changed:
        print("OK front matter 已同步: %d 个源文件" % changed)
    else:
        print("OK front matter 与 %s 一致" % REGISTRY_JSON_REL)
    return 0


def _check_sources(entries: Sequence[dict[str, str]]) -> int:
    issues = 0
    for entry in entries:
        source = entry.get("source", "")
        if not source:
            continue
        path = os.path.join(ROOT, source)
        try:
            with open(path, encoding="utf-8") as f:
                text = f.read()
        except OSError as exc:
            print("[FAIL] front matter 读取失败: %s" % exc, file=sys.stderr)
            issues += 1
            continue
        fm = parse_fm(text)
        fields = front_matter_fields(entry)
        for fm_key, value in fields.items():
            if fm.get(fm_key, "") == value:
                continue
            print("[FAIL] %s: front matter %s=%r 应为 %r，请运行 registry_render.py --write"
                  % (source, fm_key, fm.get(fm_key, ""), value), file=sys.stderr)
            issues += 1
    if issues == 0:
        print("OK front matter 与 %s 一致" % REGISTRY_JSON_REL)
    return issues


def _write_all(entries: Sequence[dict[str, str]]) -> int:
    if _write_table(entries) != 0:
        return 1
    return _sync_sources(entries)


def _check_all(entries: Sequence[dict[str, str]]) -> int:
    if _check_table(entries) != 0:
        return 1
    return _check_sources(entries)


def main(argv: Sequence[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    entries, errors = parse_registry()
    if errors:
        for error in errors:
            print("[FAIL] %s" % error, file=sys.stderr)
        return 1
    if "--write" in args:
        return _write_all(entries)
    if "--check" in args:
        return _check_all(entries)
    print(render_table(entries), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
