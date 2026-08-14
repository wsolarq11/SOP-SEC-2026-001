"""check_docs.py - SOP 源文件健康检查

校验 sops/*.md 的 front matter 完整性，并检测文件是否被外部进程
静默改写（对比 git HEAD）。

背景：2026-08-14 规文源文件曾被外部进程改写（front matter 丢 9 字段 +
表格被格式化），生成 docx 时才发现。此脚本用于定期/手动巡检。

用法：
  python check_docs.py [sops 目录]
"""
import os
import re
import subprocess
import sys

REQUIRED = ["document_id", "title", "category", "version", "status", "author"]


def parse_fm(text):
    fm = {}
    lines = text.split("\n")
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                break
            if ":" in lines[i]:
                k, v = lines[i].split(":", 1)
                fm[k.strip()] = v.strip()
    return fm


def main():
    sops_dir = sys.argv[1] if len(sys.argv) > 1 else "sops"
    issues = 0
    for name in sorted(os.listdir(sops_dir)):
        if not name.endswith(".md"):
            continue
        path = os.path.join(sops_dir, name)
        with open(path, encoding="utf-8") as f:
            text = f.read()
        fm = parse_fm(text)
        has_fm = text.startswith("---\n")
        # 1) front matter 完整性（索引类文档如 REGISTRY 无 front matter，属正常）
        if has_fm:
            missing = [k for k in REQUIRED if k not in fm]
            if missing:
                issues += 1
                print("[FAIL] %s: front matter 缺 %s" % (name, missing))
        else:
            print("[SKIP] %s: 无 front matter（索引/说明类文档）" % name)
        # 2) 与 git HEAD 对比（未提交的变更 = 可能是外部改写或未提交修改）
        r = subprocess.run(
            ["git", "diff", "--quiet", "HEAD", "--", path],
            cwd=os.path.dirname(os.path.abspath(path)) + "/..",
            capture_output=True,
        )
        if r.returncode == 1:
            print("[DIFF] %s: 与 git HEAD 不一致（未提交修改，如非本人操作请核查）" % name)
    if issues == 0:
        print("OK: 全部 %d 个文档 front matter 完整" %
              len([n for n in os.listdir(sops_dir) if n.endswith(".md")]))
    else:
        print("发现 %d 个问题" % issues)
        sys.exit(1)


if __name__ == "__main__":
    main()
