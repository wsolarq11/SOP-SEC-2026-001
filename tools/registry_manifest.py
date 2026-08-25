"""registry_manifest.py - 从 sops/registry.json 生成发布清单。

输出格式与旧 publish.sh MANIFEST 一致：
  <md 相对路径>|<docx 输出文件名>
  ...
  sops/REGISTRY.md|NONE
  sops/registry.json|NONE

规则：
- 以 sops/registry.json 为机器唯一来源，Retired 文档不进入清单。
- docx 输出名 = 源文件 basename 的 .md 换成 .docx。
- REGISTRY.md 与 registry.json 不生成 docx（输出为 NONE），源码随仓库 bundle 备份。
"""
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from registry_lib import REGISTRY_JSON_REL, REGISTRY_REL, parse_registry, validate_registry_entries


def main():
    entries, errors = parse_registry()
    issues, _ = validate_registry_entries(entries, errors)
    if issues:
        sys.exit(1)

    drafts = [e["document_id"] for e in entries if e.get("status") == "Draft"]
    if drafts:
        print("[FAIL] Draft 状态禁止生成发布清单: %s" % ", ".join(drafts), file=sys.stderr)
        sys.exit(1)

    seen_sources = set()
    for entry in entries:
        if entry.get("status") == "Retired":
            continue
        src = entry.get("source", "").replace(os.sep, "/")
        if src in seen_sources:
            print("[FAIL] 发布清单源文件重复: %s" % src)
            sys.exit(1)
        seen_sources.add(src)
        docx_name = os.path.splitext(os.path.basename(src))[0] + ".docx"
        print("%s|%s" % (src, docx_name))

    print("%s|NONE" % REGISTRY_REL)
    print("%s|NONE" % REGISTRY_JSON_REL)


if __name__ == "__main__":
    main()
