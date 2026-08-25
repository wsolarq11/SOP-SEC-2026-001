"""check_docs.py - SOP 源文件健康检查

校验全部 md 源（sops/*.md + 根目录 SOP-通用-系统说明.md）的 front matter
完整性、registry.json 发布契约一致性，并检测文件是否被外部进程静默改写（对比 git HEAD）。

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

# Windows runner/console 默认可能用 cp1252，中文检查结果会直接变成乱码。
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from registry_lib import (
    REGISTRY_JSON_REL,
    REGISTRY_REL,
    ROOT,
    parse_fm,
    parse_registry,
    validate_registry_entries,
)

# 新 schema（faa3c44 起）：8 字段。旧字段 doc_number/domain/owner 已废弃。
REQUIRED = ["document_id", "title", "category", "doc_type",
            "version", "status", "author", "approver"]

# 根目录（非 sops/）里同样纳入巡检的 md 源文件（相对仓库根）
ROOT_EXTRAS = ["SOP-通用-系统说明.md"]


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


SOURCE_MANIFEST_HEADINGS = {"## 6 源文件清单", "## 源文件清单"}
SOURCE_MANIFEST_COLUMNS = {"引用 ID", "用途", "源路径"}


def validate_source_manifest(text, rel):
    """校验文档内的外部源文件清单：列完整、行完整、引用 ID 唯一。"""
    issues = 0
    lines = text.split("\n")
    start = None
    for i, line in enumerate(lines):
        if line.strip() in SOURCE_MANIFEST_HEADINGS:
            start = i
            break
    if start is None:
        return 0

    header = None
    rows = []
    for line in lines[start + 1:]:
        st = line.strip()
        if st.startswith("## "):
            break
        if not st.startswith("|"):
            continue
        cells = [c.strip() for c in st.strip("|").split("|")]
        if cells and all(set(c) <= set("-: ") for c in cells):
            continue
        if header is None:
            header = cells
            missing = [c for c in SOURCE_MANIFEST_COLUMNS if c not in header]
            if missing:
                issues += 1
                print("[FAIL] %s: 源文件清单缺列 %s" % (rel, ",".join(missing)))
                return issues
            continue
        rows.append(cells)

    if not rows:
        issues += 1
        print("[FAIL] %s: 源文件清单没有数据行" % rel)
        return issues

    ids = []
    paths = []
    for idx, cells in enumerate(rows, 1):
        if len(cells) < len(header):
            cells = cells + [""] * (len(header) - len(cells))
        for col in SOURCE_MANIFEST_COLUMNS:
            if not cells[header.index(col)]:
                issues += 1
                print("[FAIL] %s: 源文件清单第 %d 行缺 %s" % (rel, idx, col))
        rid = cells[header.index("引用 ID")]
        if rid:
            ids.append(rid)
        path = cells[header.index("源路径")].strip("`")
        if path:
            paths.append(path)

    if len(ids) != len(set(ids)):
        issues += 1
        print("[FAIL] %s: 源文件清单引用 ID 重复" % rel)

    for i, line in enumerate(lines):
        if i > start:
            break
        st = line.strip()
        if st.startswith("|"):
            continue
        for code in re.findall(r"`([^`]*\\\\[^`]*)`", line):
            if code not in paths:
                issues += 1
                print("[FAIL] %s: 正文引用的源路径未登记到源文件清单: %s" % (rel, code))
    return issues


def validate_registry_contract(files):
    """REGISTRY 发布契约：结构、源文件、front matter 一致性、未登记 md。"""
    issues = 0
    entries, errors = parse_registry()
    reg_issues, registered_sources = validate_registry_entries(entries, errors)
    issues += reg_issues

    if os.path.isfile(os.path.join(ROOT, REGISTRY_JSON_REL)):
        import registry_render

        table = registry_render.render_table(entries)
        with open(os.path.join(ROOT, REGISTRY_REL), encoding="utf-8") as f:
            md = f.read()
        if table not in md:
            issues += 1
            print("[FAIL] REGISTRY.md 与 sops/registry.json 不一致，请运行 python tools/kb.py registry-render --write")

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
        print("[FAIL] %s: 未在 sops/registry.json 登记" % rel)
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
        # 1.1) 全库标题括号校验：所有 md 的 H1-H6 一律不得含括号，
        # 限定词放正文首句，避免文档命名风格不一致（2026-08-20 起）。
        for ln in text.split("\n"):
            st = ln.strip()
            if re.match(r"^#{1,6} ", st) and re.search(r"[（(]", st):
                issues += 1
                print("[FAIL] %s: 标题含括号，请改为无括号表述: %s"
                      % (rel, st))
        # 1.2) 外部源文件清单完整性（带 `## 6 源文件清单` 的文档）
        issues += validate_source_manifest(text, rel)
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
        print("OK: 全部 %d 个文档 front matter 完整，registry.json 契约一致" % total)
    else:
        print("发现 %d 个问题" % issues)
        sys.exit(1)


if __name__ == "__main__":
    main()
