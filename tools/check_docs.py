"""check_docs.py - SOP 源文件健康检查

校验全部 md 源（sops/*.md）的 front matter 完整性、registry.json 发布契约
一致性，并检测文件是否被外部进程静默改写（对比 git HEAD）。

背景：2026-08-14 规文源文件曾被外部进程改写（front matter 丢字段 +
表格被格式化），生成 docx 时才发现。此脚本用于定期/手动巡检。

用法：
  python check_docs.py            # 扫 sops/
  python check_docs.py <dir>...   # 扫指定目录（每目录下所有 .md）
"""
import os
import re
import subprocess
import sys
from collections.abc import Sequence

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

# 系统说明已移入 sops/，不再需要根目录附加巡检文件。
ROOT_EXTRAS: list[str] = []

SOURCE_MANIFEST_HEADINGS = {"## 6 源文件清单", "## 源文件清单"}
SOURCE_MANIFEST_COLUMNS = {"引用 ID", "用途", "源路径"}


def collect_md(dirs: Sequence[str]) -> list[str]:
    """Return absolute paths for all markdown files under each directory."""
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


def _find_manifest_start(lines: list[str]) -> int | None:
    for i, line in enumerate(lines):
        if line.strip() in SOURCE_MANIFEST_HEADINGS:
            return i
    return None


def _read_manifest_table(lines: list[str],
                         start: int) -> tuple[list[str] | None, list[list[str]]]:
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
            continue
        rows.append(cells)
    return header, rows


def _check_row_cells(rel: str, idx: int, header: list[str],
                     cells: list[str]) -> tuple[int, str, str]:
    if len(cells) < len(header):
        cells = cells + [""] * (len(header) - len(cells))
    issues = 0
    for col in SOURCE_MANIFEST_COLUMNS:
        if not cells[header.index(col)]:
            issues += 1
            print("[FAIL] %s: 源文件清单第 %d 行缺 %s" % (rel, idx, col))
    rid = cells[header.index("引用 ID")]
    path = cells[header.index("源路径")].strip("`")
    return issues, rid, path


def _collect_manifest_rows(rel: str, header: list[str],
                           rows: list[list[str]]) -> tuple[int, list[str], list[str]]:
    issues = 0
    ids = []
    paths = []
    for idx, cells in enumerate(rows, 1):
        row_issues, rid, path = _check_row_cells(rel, idx, header, cells)
        issues += row_issues
        if rid:
            ids.append(rid)
        if path:
            paths.append(path)
    return issues, ids, paths


def _check_manifest_cells(rel: str, header: list[str] | None,
                          rows: list[list[str]]) -> tuple[int, list[str], bool]:
    if header is None:
        print("[FAIL] %s: 源文件清单没有表头" % rel)
        return 1, [], True
    missing = [c for c in SOURCE_MANIFEST_COLUMNS if c not in header]
    if missing:
        print("[FAIL] %s: 源文件清单缺列 %s" % (rel, ",".join(missing)))
        return 1, [], True
    if not rows:
        print("[FAIL] %s: 源文件清单没有数据行" % rel)
        return 1, [], True
    issues, ids, paths = _collect_manifest_rows(rel, header, rows)
    if len(ids) != len(set(ids)):
        issues += 1
        print("[FAIL] %s: 源文件清单引用 ID 重复" % rel)
    return issues, paths, False


def _check_manifest_refs(text: str, rel: str, paths: list[str],
                         start: int) -> int:
    issues = 0
    for i, line in enumerate(text.split("\n")):
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


def validate_source_manifest(text: str, rel: str) -> int:
    """Validate the external source manifest section if present."""
    lines = text.split("\n")
    start = _find_manifest_start(lines)
    if start is None:
        return 0
    header, rows = _read_manifest_table(lines, start)
    issues, paths, early = _check_manifest_cells(rel, header, rows)
    if early:
        return issues
    return issues + _check_manifest_refs(text, rel, paths, start)


def _check_registry_render(entries: list[dict[str, str]]) -> int:
    if not os.path.isfile(os.path.join(ROOT, REGISTRY_JSON_REL)):
        return 0
    import registry_render

    table = registry_render.render_table(entries)
    with open(os.path.join(ROOT, REGISTRY_REL), encoding="utf-8") as f:
        md = f.read()
    if table not in md:
        print("[FAIL] REGISTRY.md 与 sops/registry.json 不一致，请运行 python tools/kb.py registry-render --write")
        return 1
    return 0


def _unregistered_sources(files: Sequence[str], entries: list[dict[str, str]],
                          registered_sources: set[str]) -> list[str]:
    ids = {e["document_id"] for e in entries}
    unregistered = []
    for abspath in sorted(set(files)):
        rel = os.path.relpath(abspath, ROOT).replace(os.sep, "/")
        with open(abspath, encoding="utf-8") as f:
            text = f.read()
        if not text.startswith("---\n"):
            continue
        fm = parse_fm(text)
        if rel not in registered_sources and fm.get("document_id") not in ids:
            unregistered.append(rel)
    return unregistered


def validate_registry_contract(files: Sequence[str]) -> int:
    """REGISTRY 发布契约：结构、源文件、front matter 一致性、未登记 md。"""
    issues = 0
    entries, errors = parse_registry()
    reg_issues, registered_sources = validate_registry_entries(entries, errors)
    issues += reg_issues + _check_registry_render(entries)
    for rel in _unregistered_sources(files, entries, registered_sources):
        issues += 1
        print("[FAIL] %s: 未在 sops/registry.json 登记" % rel)
    return issues


def _check_front_matter(text: str, rel: str) -> int:
    if not text.startswith("---\n"):
        print("[SKIP] %s: 无 front matter（索引/说明类文档）" % rel)
        return 0
    fm = parse_fm(text)
    missing = [k for k in REQUIRED if k not in fm]
    if missing:
        print("[FAIL] %s: front matter 缺 %s" % (rel, missing))
        return 1
    return 0


def _check_headings(text: str, rel: str) -> int:
    issues = 0
    for ln in text.split("\n"):
        st = ln.strip()
        if re.match(r"^#{1,6} ", st) and re.search(r"[（(]", st):
            issues += 1
            print("[FAIL] %s: 标题含括号，请改为无括号表述: %s" % (rel, st))
    return issues


def _check_git_diff(rel: str) -> None:
    result = subprocess.run(
        ["git", "-C", ROOT, "diff", "--quiet", "HEAD", "--", rel],
        capture_output=True,
    )
    if result.returncode == 1:
        print("[DIFF] %s: 与 git HEAD 不一致（未提交修改，如非本人操作请核查）" % rel)


def _inspect_document(abspath: str) -> tuple[int, str]:
    rel = os.path.relpath(abspath, ROOT).replace(os.sep, "/")
    with open(abspath, encoding="utf-8") as f:
        text = f.read()
    issues = _check_front_matter(text, rel)
    issues += _check_headings(text, rel)
    issues += validate_source_manifest(text, rel)
    _check_git_diff(rel)
    return issues, rel


def main() -> int:
    dirs = sys.argv[1:] or [os.path.join(ROOT, "sops")]
    files = collect_md(dirs)
    issues = 0
    for abspath in sorted(set(files)):
        file_issues, _ = _inspect_document(abspath)
        issues += file_issues
    issues += validate_registry_contract(files)
    if issues == 0:
        print("OK: 全部 %d 个文档 front matter 完整，registry.json 契约一致" % len(files))
        return 0
    print("发现 %d 个问题" % issues)
    return 1


if __name__ == "__main__":
    sys.exit(main())
