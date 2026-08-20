"""check_docs.py - SOP 源文件健康检查

校验全部 md 源（sops/*.md + 根目录 SOP-通用-系统说明.md）的 front matter
完整性、REGISTRY 发布契约一致性，并检测文件是否被外部进程静默改写（对比 git HEAD）。

背景：2026-08-14 规文源文件曾被外部进程改写（front matter 丢字段 +
表格被格式化），生成 docx 时才发现。此脚本用于定期/手动巡检。

用法：
  python check_docs.py            # 扫 sops/ + 根目录系统说明
  python check_docs.py <dir>...   # 扫指定目录（每目录下所有 .md）
"""
import os
import re
import subprocess
import sys

from registry_lib import (
    ROOT,
    parse_registry,
    validate_registry_entries,
)

# 新 schema（faa3c44 起）：8 字段。旧字段 doc_number/domain/owner 已废弃。
REQUIRED = ["document_id", "title", "category", "doc_type",
            "version", "status", "author", "approver"]

# 根目录（非 sops/）里同样纳入巡检的 md 源文件（相对仓库根）
ROOT_EXTRAS = ["SOP-通用-系统说明.md"]


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


def collect_md(dirs):
    """dirs: 目录（可绝对或相对）；额外追加 ROOT_EXTRAS 中存在的文件。"""
    files = []
    for d in dirs:
        if not os.path.isdir(d):
            print("[WARN] 目录不存在: %s" % d)
            continue
        for name in sorted(os.listdir(d)):
            if name.endswith(".md"):
                files.append(os.path.abspath(os.path.join(d, name)))
    for rel in ROOT_EXTRAS:
        p = os.path.join(ROOT, rel)
        if os.path.isfile(p):
            files.append(os.path.abspath(p))
    return files


def validate_registry_contract(files):
    """REGISTRY 发布契约：结构、源文件、front matter 一致性、未登记 md。"""
    issues = 0
    entries, errors = parse_registry()
    reg_issues, registered_sources = validate_registry_entries(entries, errors)
    issues += reg_issues

    unregistered = []
    for abspath in sorted(set(files)):
        rel = os.path.relpath(abspath, ROOT).replace(os.sep, "/")
        with open(abspath, encoding="utf-8") as f:
            text = f.read()
        if not text.startswith("---\n"):
            continue
        fm = parse_fm(text)
        if rel not in registered_sources and fm.get("document_id") not in {
            e["document_id"] for e in entries
        }:
            unregistered.append(rel)
    for rel in unregistered:
        issues += 1
        print("[FAIL] %s: 未在 REGISTRY「已分配编号」登记" % rel)
    return issues


def main():
    dirs = sys.argv[1:] or [os.path.join(ROOT, "sops")]
    issues = 0
    files = collect_md(dirs)
    for abspath in sorted(set(files)):
        rel = os.path.relpath(abspath, ROOT).replace(os.sep, "/")
        with open(abspath, encoding="utf-8") as f:
            text = f.read()
        fm = parse_fm(text)
        has_fm = text.startswith("---\n")
        # 1) front matter 完整性（索引类文档如 REGISTRY 无 front matter，属正常）
        if has_fm:
            missing = [k for k in REQUIRED if k not in fm]
            if missing:
                issues += 1
                print("[FAIL] %s: front matter 缺 %s" % (rel, missing))
        else:
            print("[SKIP] %s: 无 front matter（索引/说明类文档）" % rel)
        # 1.1) procedure 正文标题括号校验：L3 程序类标题只写操作对象，
        # 限定词放正文首句，避免各 SOP 命名风格不一致（2026-08-20 起）。
        if has_fm and fm.get("doc_type") == "procedure":
            for ln in text.split("\n"):
                st = ln.strip()
                if st.startswith("## ") and re.search(r"[（(]", st):
                    issues += 1
                    print("[FAIL] %s: procedure 标题含括号，请改为无括号表述: %s"
                          % (rel, st))
        # 2) 与 git HEAD 对比（未提交的变更 = 可能是外部改写或未提交修改）
        r = subprocess.run(
            ["git", "-C", ROOT, "diff", "--quiet", "HEAD", "--", rel],
            capture_output=True,
        )
        if r.returncode == 1:
            print("[DIFF] %s: 与 git HEAD 不一致（未提交修改，如非本人操作请核查）" % rel)
    # 3) REGISTRY 发布契约
    issues += validate_registry_contract(files)
    total = len(files)
    if issues == 0:
        print("OK: 全部 %d 个文档 front matter 完整，REGISTRY 契约一致" % total)
    else:
        print("发现 %d 个问题" % issues)
        sys.exit(1)


if __name__ == "__main__":
    main()
