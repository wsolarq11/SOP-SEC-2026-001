"""registry_lib.py - SOP 发布契约解析与校验共享库。

sops/registry.json 是「已分配编号」的机器唯一来源；
sops/REGISTRY.md 的「已分配编号」表由 registry_render.py 生成，仅作人工审计视图。
本模块供 check_docs.py、registry_manifest.py 与 registry_render.py 共用。
"""
from __future__ import annotations

import json
import os
import re
from collections.abc import Callable, Sequence
from pathlib import Path

# 仓库根 = 本文件所在 tools 目录上一级（不依赖运行时 cwd）
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

REGISTRY_REL = "sops/REGISTRY.md"
REGISTRY_JSON_REL = "sops/registry.json"
TABLE_HEADING = "## 已分配编号"
VERSION_HEADING = "## 版本修订记录"
DOC_TYPES = {"policy", "standard", "procedure", "guideline", "reference"}
DOMAINS = {"INFRA", "SEC", "APP", "DESK", "DR", "GEN"}
VALID_STATUSES = {"Draft", "Approved"}
PUBLISHABLE_STATUSES = frozenset({"Draft", "Approved"})
VERSION_RE = re.compile(r"^\d+\.\d+$")
COLUMNS = [
    "document_id",
    "title",
    "doc_type",
    "domain",
    "version",
    "author",
    "status",
    "source",
    "target_dir",
]
OPTIONAL_FIELDS = [
    "requirement_ref",
    "approver",
    "effective_date",
    "reviewer",
    "reviewed_at",
    "approved_at",
    "last_published_at",
]
ALLOWED_FIELDS = frozenset(COLUMNS + OPTIONAL_FIELDS)
FRONT_MATTER_OPTIONAL_MATCH = [
    ("requirement_ref", "requirement_ref"),
    ("approver", "approver"),
    ("effective_date", "effective_date"),
    ("reviewer", "reviewer"),
    ("reviewed_at", "reviewed_at"),
    ("approved_at", "approved_at"),
]
DATE_FIELDS = ("reviewed_at", "approved_at", "last_published_at")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
HEADER_ALIASES = {
    "文档号": "document_id",
    "标题": "title",
    "类型": "doc_type",
    "域名": "domain",
    "版本": "version",
    "编制人": "author",
    "状态": "status",
    "源文件": "source",
    "目标目录": "target_dir",
    "需求来源": "requirement_ref",
    "签批人": "approver",
    "生效日期": "effective_date",
    "评审人": "reviewer",
    "评审时间": "reviewed_at",
    "签批时间": "approved_at",
    "最近发布": "last_published_at",
}
FRONT_MATTER_MATCH = [
    ("document_id", "document_id"),
    ("title", "title"),
    ("category", "domain"),
    ("doc_type", "doc_type"),
    ("version", "version"),
    ("status", "status"),
    ("author", "author"),
]


def parse_fm(text: str) -> dict[str, str]:
    """Parse front matter; returns an empty dict when none exists."""
    fm: dict[str, str] = {}
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return fm
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" in line:
            key, value = line.split(":", 1)
            fm[key.strip()] = value.strip()
    return fm


def _find_section(lines: Sequence[str], heading: str) -> int | None:
    for i, line in enumerate(lines):
        if line.strip() == heading:
            return i
    return None


def _table_cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _is_separator(cells: Sequence[str]) -> bool:
    return bool(cells) and all(set(cell) <= set("-: ") for cell in cells)


def _version_pairs(rows: Sequence[Sequence[str]]) -> list[tuple[int, int]]:
    versions = []
    for row in rows:
        if not row or not VERSION_RE.match(row[0]):
            continue
        left, right = row[0].split(".", 1)
        versions.append((int(left), int(right)))
    return versions


def _revision_rows(lines: Sequence[str], start: int) -> list[list[str]]:
    rows = []
    for row in lines[start + 1:]:
        stripped = row.strip()
        if stripped.startswith("#"):
            break
        if not stripped.startswith("|"):
            continue
        cells = _table_cells(stripped)
        if not _is_separator(cells):
            rows.append(cells)
    return rows


def latest_revision_version(text: str) -> str | None:
    """Return the latest revision version from the revision table, if present."""
    lines = text.splitlines()
    start = _find_section(lines, VERSION_HEADING)
    if start is None:
        return None
    versions = _version_pairs(_revision_rows(lines, start))
    if not versions:
        return None
    left, right = max(versions)
    return "%d.%d" % (left, right)


def _default_registry_path() -> str:
    json_path = os.path.join(ROOT, REGISTRY_JSON_REL)
    if os.path.isfile(json_path):
        return json_path
    return os.path.join(ROOT, REGISTRY_REL)


def parse_registry(
    registry_path: str | os.PathLike[str] | None = None,
) -> tuple[list[dict[str, str]], list[str]]:
    """Parse the allocation table; JSON is preferred over Markdown.

    An explicit .json path is parsed as JSON; any other explicit path is parsed
    as Markdown. Returns (entries, errors); business validation belongs to
    validate_registry_entries.
    """
    if registry_path is None:
        registry_path = _default_registry_path()
    path = os.fspath(registry_path)
    if path.lower().endswith(".json"):
        return _parse_registry_json(path)
    return _parse_registry_markdown(path)


def _normalize_entry(entry: dict[str, object], columns: Sequence[str]) -> dict[str, str]:
    return {column: "" if entry.get(column) is None else str(entry.get(column))
            for column in columns}


def _append_json_entry(entry: object, idx: int,
                       entries: list[dict[str, str]],
                       errors: list[str]) -> None:
    if not isinstance(entry, dict):
        errors.append("registry JSON 第 %d 项必须是对象" % idx)
        return
    unknown = [key for key in entry if key not in ALLOWED_FIELDS]
    if unknown:
        errors.append("registry JSON 第 %d 项含未知字段: %s"
                      % (idx, ",".join(unknown)))
        return
    entries.append(_normalize_entry(entry, COLUMNS + OPTIONAL_FIELDS))


def _parse_registry_json(path: str) -> tuple[list[dict[str, str]], list[str]]:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as exc:
        return [], ["无法读取 registry JSON %s: %s" % (path, exc)]
    raw_entries = data.get("entries", []) if isinstance(data, dict) else data
    if not isinstance(raw_entries, list):
        return [], ["registry JSON 顶层 entries 必须是数组"]
    entries: list[dict[str, str]] = []
    errors: list[str] = []
    for idx, entry in enumerate(raw_entries, 1):
        _append_json_entry(entry, idx, entries, errors)
    return entries, errors


def _markdown_header(cells: Sequence[str], lineno: int, raw: str,
                     errors: list[str]) -> list[str]:
    header = [HEADER_ALIASES.get(cell, cell) for cell in cells]
    if "document_id" not in header:
        errors.append("第 %d 行表头缺少文档号/document_id: %s" % (lineno, raw[:80]))
    return header


def _append_markdown_entry(cells: Sequence[str], header: Sequence[str],
                           lineno: int, raw: str, entries: list[dict[str, str]],
                           errors: list[str]) -> None:
    if len(cells) != len(header):
        errors.append(
            "第 %d 行应为 %d 列，实际 %d 列: %s"
            % (lineno, len(header), len(cells), raw[:80])
        )
        return
    entry = dict(zip(header, cells))
    if not entry.get("document_id") and not entry.get("source"):
        return
    entries.append(entry)


def _process_markdown_heading(
    stripped: str, in_table: bool, table_found: bool,
    header: list[str] | None,
) -> tuple[bool, bool, list[str] | None]:
    next_in_table = stripped == TABLE_HEADING
    return (next_in_table, table_found or next_in_table,
            None if next_in_table else header)


def _process_markdown_line(stripped: str, lineno: int, raw: str,
                           header: list[str] | None,
                           entries: list[dict[str, str]],
                           errors: list[str]) -> list[str] | None:
    cells = _table_cells(stripped)
    if _is_separator(cells):
        return header
    if header is None:
        return _markdown_header(cells, lineno, raw, errors)
    _append_markdown_entry(cells, header, lineno, raw, entries, errors)
    return header


def _finish_markdown(entries: list[dict[str, str]], errors: list[str],
                     table_found: bool) -> tuple[list[dict[str, str]], list[str]]:
    if not table_found:
        errors.append("未找到「%s」表" % TABLE_HEADING)
    return entries, errors


def _parse_registry_markdown(path: str) -> tuple[list[dict[str, str]], list[str]]:
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    entries: list[dict[str, str]] = []
    errors: list[str] = []
    header: list[str] | None = None
    table_found = False
    in_table = False
    for lineno, raw in enumerate(lines, 1):
        stripped = raw.strip()
        if stripped.startswith("## "):
            in_table, table_found, header = _process_markdown_heading(
                stripped, in_table, table_found, header
            )
            continue
        if in_table and stripped.startswith("|"):
            header = _process_markdown_line(stripped, lineno, raw, header,
                                            entries, errors)
    return _finish_markdown(entries, errors, table_found)


def _path_inside_repo(source: str) -> bool:
    root = os.path.abspath(ROOT)
    absolute = os.path.abspath(os.path.join(ROOT, source))
    try:
        return os.path.commonpath([root, absolute]) == root
    except ValueError:
        return False


def _check_entry_identity(entry: dict[str, str], seen_ids: set[str],
                          seen_sources: set[str],
                          fail: Callable[[str], None]) -> None:
    did = entry.get("document_id", "") or "<missing>"
    src = entry.get("source", "") or ""
    if did in seen_ids:
        fail("文档号重复: %s" % did)
    if src in seen_sources:
        fail("源文件重复: %s" % src)
    seen_ids.add(did)
    seen_sources.add(src)
    status = entry.get("status", "") or ""
    if status not in VALID_STATUSES:
        fail("%s: 未知 status=%r" % (did, status))


def _check_entry_shape(entry: dict[str, str], fail: Callable[[str], None]) -> bool:
    did = entry.get("document_id", "") or "<missing>"
    if entry.get("doc_type") not in DOC_TYPES:
        fail("%s: 未知 doc_type=%r" % (did, entry.get("doc_type")))
    if entry.get("domain") not in DOMAINS:
        fail("%s: 未知域名=%r" % (did, entry.get("domain")))
    if not entry.get("source"):
        fail("%s: 缺少源文件列" % did)
        return False
    return True


def _register_source(entry: dict[str, str], registered_sources: set[str],
                     seen_docx_names: set[str],
                     fail: Callable[[str], None]) -> bool:
    did = entry.get("document_id", "") or "<missing>"
    src = entry.get("source", "") or ""
    absolute = os.path.abspath(os.path.join(ROOT, src))
    if not _path_inside_repo(src):
        fail("%s: 源文件越出仓库根: %s" % (did, src))
        return False
    if not os.path.isfile(absolute):
        fail("%s: 源文件缺失: %s" % (did, src))
        return False
    registered_sources.add(src.replace(os.sep, "/"))
    docx_name = os.path.splitext(os.path.basename(src))[0] + ".docx"
    if docx_name in seen_docx_names:
        fail("%s: docx 输出名冲突: %s" % (did, docx_name))
    seen_docx_names.add(docx_name)
    return True


def _read_source_text(src: str) -> tuple[str | None, str | None]:
    try:
        with open(os.path.join(ROOT, src), encoding="utf-8") as f:
            return f.read(), None
    except OSError as exc:
        return None, str(exc)


def _check_revision_match(text: str, fm: dict[str, str], src: str,
                          fail: Callable[[str], None]) -> None:
    latest = latest_revision_version(text)
    if latest is None or fm.get("version") == latest:
        return
    fail(
        "%s: front matter version=%r 与版本修订记录最新版 %s 不一致"
        % (src, fm.get("version"), latest)
    )


def _check_fm_matches(fm: dict[str, str], entry: dict[str, str], src: str,
                      fail: Callable[[str], None]) -> None:
    for fm_key, reg_key in FRONT_MATTER_MATCH:
        if fm.get(fm_key) == entry.get(reg_key, ""):
            continue
        fail(
            "%s: front matter %s=%r 与 REGISTRY %s=%r 不一致"
            % (src, fm_key, fm.get(fm_key), reg_key, entry.get(reg_key, ""))
        )


def _check_optional_fm_matches(fm: dict[str, str], entry: dict[str, str],
                               src: str, fail: Callable[[str], None]) -> None:
    for fm_key, reg_key in FRONT_MATTER_OPTIONAL_MATCH:
        fm_value = fm.get(fm_key, "")
        reg_value = entry.get(reg_key, "")
        if fm_value and reg_value and fm_value != reg_value:
            fail(
                "%s: front matter %s=%r 与 REGISTRY %s=%r 不一致"
                % (src, fm_key, fm_value, reg_key, reg_value)
            )


def _check_optional_field_shapes(entry: dict[str, str],
                                 fail: Callable[[str], None]) -> None:
    did = entry.get("document_id", "") or "<missing>"
    for field in DATE_FIELDS:
        value = entry.get(field, "")
        if value and not DATE_RE.match(value):
            fail("%s: 可选字段 %s=%r 必须是 YYYY-MM-DD" % (did, field, value))
    effective = entry.get("effective_date", "")
    if effective and effective != "待定" and not DATE_RE.match(effective):
        fail("%s: 可选字段 effective_date=%r 必须是 YYYY-MM-DD 或待定"
             % (did, effective))


def _check_front_matter_contract(src: str, entry: dict[str, str],
                                 fail: Callable[[str], None]) -> None:
    did = entry.get("document_id", "") or "<missing>"
    text, error = _read_source_text(src)
    if error:
        fail("%s: 无法读取源文件: %s" % (did, error))
        return
    fm = parse_fm(text or "")
    if not fm:
        fail("%s: 源文件缺少 front matter: %s" % (did, src))
        return
    _check_revision_match(text or "", fm, src, fail)
    _check_fm_matches(fm, entry, src, fail)
    _check_optional_fm_matches(fm, entry, src, fail)


def _report_issue(msg: str) -> int:
    print("[FAIL] REGISTRY: %s" % msg)
    return 1


def _validate_entry(entry: dict[str, str], registered_sources: set[str],
                    seen_ids: set[str], seen_sources: set[str],
                    seen_docx_names: set[str]) -> int:
    issues = 0

    def fail(msg: str) -> None:
        nonlocal issues
        issues += _report_issue(msg)

    _check_entry_identity(entry, seen_ids, seen_sources, fail)
    if not _check_entry_shape(entry, fail):
        return issues
    if not _register_source(entry, registered_sources, seen_docx_names, fail):
        return issues
    _check_optional_field_shapes(entry, fail)
    _check_front_matter_contract(entry["source"], entry, fail)
    return issues


def validate_registry_entries(
    entries: Sequence[dict[str, str]],
    errors: Sequence[str],
    verbose: bool = False,
) -> tuple[int, set[str]]:
    """Validate publish contract; returns (issue_count, registered_sources)."""
    _ = verbose
    issues = sum(_report_issue(error) for error in errors)
    registered_sources: set[str] = set()
    seen_ids: set[str] = set()
    seen_sources: set[str] = set()
    seen_docx_names: set[str] = set()
    for entry in entries:
        issues += _validate_entry(entry, registered_sources, seen_ids,
                                  seen_sources, seen_docx_names)
    return issues, registered_sources
