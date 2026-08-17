"""registry_manifest.py - 从 REGISTRY.md 生成发布清单。

输出格式与旧 publish.sh MANIFEST 一致：
  <md 相对路径>|<docx 输出文件名>
  ...
  sops/REGISTRY.md|NONE

规则：
- 以 REGISTRY「已分配编号」表为唯一来源，Retired 文档不进入清单。
- docx 输出名 = 源文件 basename 的 .md 换成 .docx。
- REGISTRY.md 不生成 docx（输出为 NONE），源码随仓库 bundle 备份。
"""
import os
import sys

from registry_lib import REGISTRY_REL, ROOT, parse_registry, validate_registry_entries


def main():
    entries, errors = parse_registry()
    issues, _ = validate_registry_entries(entries, errors)
    if issues:
        sys.exit(1)

    seen_sources = set()
    for entry in entries:
        if entry["status"] == "Retired":
            continue
        src = entry["source"].replace(os.sep, "/")
        if src in seen_sources:
            print("[FAIL] 发布清单源文件重复: %s" % src)
            sys.exit(1)
        seen_sources.add(src)
        docx_name = os.path.splitext(os.path.basename(src))[0] + ".docx"
        print("%s|%s" % (src, docx_name))

    print("%s|NONE" % REGISTRY_REL)


if __name__ == "__main__":
    main()
