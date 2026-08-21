#!/usr/bin/env python3
"""Render sops/registry.json into the REGISTRY.md allocation table.

Usage:
  python registry_render.py            # print generated table
  python registry_render.py --write    # update sops/REGISTRY.md
  python registry_render.py --check    # exit 1 if REGISTRY.md is stale
"""
import os
import sys

from registry_lib import (
    COLUMNS,
    REGISTRY_JSON_REL,
    REGISTRY_REL,
    ROOT,
    parse_registry,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

HEADER_LABELS = {
    "document_id": "文档号",
    "title": "标题",
    "level": "层级",
    "doc_type": "类型",
    "domain": "域名",
    "version": "版本",
    "related_standards": "关联标准",
    "author": "编制人",
    "status": "状态",
    "source": "源文件",
    "target_dir": "目标目录",
}

MARKER = "<!-- generated from sops/registry.json; do not edit by hand -->\n"


def render_table(entries):
    rows = [HEADER_LABELS[c] for c in COLUMNS]
    lines = ["## 已分配编号"]
    lines.append("| %s |" % " | ".join(rows))
    lines.append("| %s |" % " | ".join(["---"] * len(rows)))
    for entry in entries:
        cells = [str(entry.get(c, "")) for c in COLUMNS]
        lines.append("| %s |" % " | ".join(cells))
    return "\n".join(lines) + "\n"


def replace_section(text, table):
    lines = text.splitlines(keepends=True)
    start = None
    end = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if start is None and stripped == "## 已分配编号":
            start = i
        elif start is not None and stripped.startswith("## "):
            end = i
            break
    if start is None:
        return None
    if end is None:
        end = len(lines)
    before = "".join(lines[:start]).replace(MARKER, "")
    after = "".join(lines[end:])
    if not after.startswith(("\n", "\r\n")):
        after = "\n" + after
    return before + MARKER + table + after


def main():
    entries, errors = parse_registry()
    if errors:
        for error in errors:
            print("[FAIL] %s" % error, file=sys.stderr)
        return 1
    table = render_table(entries)
    registry_path = os.path.join(ROOT, REGISTRY_REL)
    if "--write" in sys.argv:
        with open(registry_path, encoding="utf-8") as f:
            text = f.read()
        updated = replace_section(text, table)
        if updated is None:
            print("[FAIL] REGISTRY.md 未找到「已分配编号」表", file=sys.stderr)
            return 1
        with open(registry_path, "w", encoding="utf-8") as f:
            f.write(updated)
        print("OK updated: %s" % REGISTRY_REL)
        return 0
    if "--check" in sys.argv:
        with open(registry_path, encoding="utf-8") as f:
            text = f.read()
        if table in text:
            print("OK REGISTRY.md 与 %s 一致" % REGISTRY_JSON_REL)
            return 0
        print("[FAIL] REGISTRY.md 已过期，请运行 python registry_render.py --write",
              file=sys.stderr)
        return 1
    print(table, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
