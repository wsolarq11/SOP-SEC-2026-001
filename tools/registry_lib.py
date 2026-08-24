"""registry_lib.py - SOP 发布契约解析与校验共享库。

sops/registry.json 是「已分配编号」的机器唯一来源；
sops/REGISTRY.md 的「已分配编号」表由 registry_render.py 生成，仅作人工审计视图。
本模块供 check_docs.py、registry_manifest.py 与 registry_render.py 共用。
"""
import json
import os
import re

# 仓库根 = 本文件所在 tools 目录上一级（不依赖运行时 cwd）
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

REGISTRY_REL = "sops/REGISTRY.md"
REGISTRY_JSON_REL = "sops/registry.json"
TABLE_HEADING = "## 已分配编号"
DOC_TYPES = {"policy", "standard", "procedure", "guideline", "reference"}
DOMAINS = {"INFRA", "SEC", "APP", "DESK", "DR", "GEN"}
VALID_STATUSES = {"Draft", "Review", "Approved", "Retired"}
LOCKED_VERSION = "1.0"
COLUMNS = [
    "document_id",
    "title",
    "level",
    "doc_type",
    "domain",
    "version",
    "related_standards",
    "author",
    "status",
    "source",
    "target_dir",
]
HEADER_ALIASES = {
    "文档号": "document_id",
    "标题": "title",
    "层级": "level",
    "类型": "doc_type",
    "域名": "domain",
    "版本": "version",
    "关联标准": "related_standards",
    "编制人": "author",
    "状态": "status",
    "源文件": "source",
    "目标目录": "target_dir",
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


def parse_fm(text):
    """解析 front matter；无 front matter 时返回空 dict。"""
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


def parse_registry(registry_path=None):
    """解析已分配编号表，优先读取 sops/registry.json。

    显式传入 .json 路径时按 JSON 解析，显式传入其他路径时按 Markdown 解析，
    保持测试和旧调用兼容。
    返回 (entries, errors)；业务校验由 validate_registry_entries 执行。
    """
    if registry_path is None:
        json_path = os.path.join(ROOT, REGISTRY_JSON_REL)
        if os.path.isfile(json_path):
            return _parse_registry_json(json_path)
        return _parse_registry_markdown(os.path.join(ROOT, REGISTRY_REL))
    if registry_path.lower().endswith(".json"):
        return _parse_registry_json(registry_path)
    return _parse_registry_markdown(registry_path)


def _parse_registry_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as exc:
        return [], ["无法读取 registry JSON %s: %s" % (path, exc)]
    raw_entries = data.get("entries", []) if isinstance(data, dict) else data
    if not isinstance(raw_entries, list):
        return [], ["registry JSON 顶层 entries 必须是数组"]
    entries = []
    errors = []
    for idx, entry in enumerate(raw_entries, 1):
        if not isinstance(entry, dict):
            errors.append("registry JSON 第 %d 项必须是对象" % idx)
            continue
        unknown = [k for k in entry if k not in COLUMNS]
        if unknown:
            errors.append("registry JSON 第 %d 项含未知字段: %s" % (idx, ",".join(unknown)))
            continue
        entries.append({k: "" if entry.get(k) is None else str(entry.get(k)) for k in COLUMNS})
    return entries, errors


def _parse_registry_markdown(path):
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()

    entries = []
    errors = []
    in_table = False
    table_found = False
    header = None
    for lineno, raw in enumerate(lines, 1):
        stripped = raw.strip()
        if stripped.startswith("## "):
            in_table = stripped == TABLE_HEADING
            if in_table:
                table_found = True
                header = None
            continue
        if not in_table or not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
            continue
        if header is None:
            header = [HEADER_ALIASES.get(c, c) for c in cells]
            if "document_id" not in header:
                errors.append(
                    "第 %d 行表头缺少文档号/document_id: %s" % (lineno, raw[:80])
                )
            continue
        if len(cells) != len(header):
            errors.append(
                "第 %d 行应为 %d 列，实际 %d 列: %s"
                % (lineno, len(header), len(cells), raw[:80])
            )
            continue
        entry = dict(zip(header, cells))
        if not entry.get("document_id") and not entry.get("source"):
            continue
        entries.append(entry)
    if not table_found:
        errors.append("未找到「%s」表" % TABLE_HEADING)
    return entries, errors


def validate_registry_entries(entries, errors, verbose=False):
    """执行发布契约的业务校验，返回 (issue_count, registered_sources)。

    Retired 条目只保留编号，不要求源文件仍存在，也不进入发布清单。
    """
    issues = 0
    registered_sources = set()
    seen_ids = set()
    seen_sources = set()
    seen_docx_names = set()

    def fail(msg):
        nonlocal issues
        issues += 1
        print("[FAIL] REGISTRY: %s" % msg)

    for err in errors:
        fail(err)
        if not verbose:
            continue

    for entry in entries:
        did = entry.get("document_id", "") or "<missing>"
        src = entry.get("source", "") or ""
        if did in seen_ids:
            fail("文档号重复: %s" % did)
        if src in seen_sources:
            fail("源文件重复: %s" % src)
        seen_ids.add(did)
        seen_sources.add(src)

        if entry.get("version") != LOCKED_VERSION:
            fail("%s: 版本已锁死为 %s，当前为 %r" % (did, LOCKED_VERSION, entry.get("version")))
        status = entry.get("status", "") or ""
        if status not in VALID_STATUSES:
            fail("%s: 未知 status=%r" % (did, status))
        if status == "Retired":
            continue

        if entry.get("doc_type") not in DOC_TYPES:
            fail("%s: 未知 doc_type=%r" % (did, entry.get("doc_type")))
        if entry.get("domain") not in DOMAINS:
            fail("%s: 未知域名=%r" % (did, entry.get("domain")))
        if not src:
            fail("%s: 缺少源文件列" % did)
            continue

        abs_src = os.path.abspath(os.path.join(ROOT, src))
        try:
            inside = os.path.commonpath([os.path.abspath(ROOT), abs_src]) == os.path.abspath(ROOT)
        except ValueError:
            inside = False
        if not inside:
            fail("%s: 源文件越出仓库根: %s" % (did, src))
            continue
        if not os.path.isfile(abs_src):
            fail("%s: 源文件缺失: %s" % (did, src))
            continue

        registered_sources.add(src.replace(os.sep, "/"))
        docx_name = os.path.splitext(os.path.basename(src))[0] + ".docx"
        if docx_name in seen_docx_names:
            fail("%s: docx 输出名冲突: %s" % (did, docx_name))
        seen_docx_names.add(docx_name)

        try:
            with open(abs_src, encoding="utf-8") as f:
                fm = parse_fm(f.read())
        except OSError as exc:
            fail("%s: 无法读取源文件: %s" % (did, exc))
            continue
        if not fm:
            fail("%s: 源文件缺少 front matter: %s" % (did, src))
            continue
        for fm_key, reg_key in FRONT_MATTER_MATCH:
            if fm.get(fm_key) != entry.get(reg_key, ""):
                fail(
                    "%s: front matter %s=%r 与 REGISTRY %s=%r 不一致"
                    % (src, fm_key, fm.get(fm_key), reg_key, entry.get(reg_key, ""))
                )
    return issues, registered_sources
