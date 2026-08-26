"""registry_manifest.py - 从 sops/registry.json 生成发布清单。

输出格式与 publish.sh MANIFEST 一致：
  <md 相对路径>|<docx 输出文件名>
  ...
  sops/REGISTRY.md|NONE
  sops/registry.json|NONE

规则：
- 以 sops/registry.json 为机器唯一来源；Retired 文档不进入清单。
- Draft 与 Approved 文档进入发布清单；Draft 发布不代表已签批。
- docx 输出名 = 源文件 basename 的 .md 换成 .docx。
- REGISTRY.md 与 registry.json 属于元数据，docx 列为 NONE，源码另行 bundle 备份。
"""
from __future__ import annotations

import os
import sys
from collections.abc import Sequence

from registry_lib import (
    PUBLISHABLE_STATUSES,
    REGISTRY_JSON_REL,
    REGISTRY_REL,
    parse_registry,
    validate_registry_entries,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def _warn_retired(entries: Sequence[dict[str, str]]) -> None:
    retired = [entry["document_id"] for entry in entries
               if entry.get("status") == "Retired"]
    if retired:
        print("[WARN] Retired 文档不进入发布清单: %s" % ", ".join(retired),
              file=sys.stderr)


def _docx_name(source: str) -> str:
    return os.path.splitext(os.path.basename(source))[0] + ".docx"


def _manifest_lines(entries: Sequence[dict[str, str]]) -> list[str]:
    lines = []
    seen_sources: set[str] = set()
    for entry in entries:
        if entry.get("status") not in PUBLISHABLE_STATUSES:
            continue
        source = entry.get("source", "").replace(os.sep, "/")
        if source in seen_sources:
            print("[FAIL] 发布清单源文件重复: %s" % source)
            sys.exit(1)
        seen_sources.add(source)
        lines.append("%s|%s" % (source, _docx_name(source)))
    return lines


def main(argv: Sequence[str] | None = None) -> int:
    _ = argv
    entries, errors = parse_registry()
    issues, _ = validate_registry_entries(entries, errors)
    if issues:
        return 1
    _warn_retired(entries)
    lines = _manifest_lines(entries)
    if not lines:
        print("[WARN] 当前没有可发布文档（Draft/Approved），无可发布项目",
              file=sys.stderr)
    for line in lines:
        print(line)
    print("%s|NONE" % REGISTRY_REL)
    print("%s|NONE" % REGISTRY_JSON_REL)
    return 0


if __name__ == "__main__":
    sys.exit(main())
