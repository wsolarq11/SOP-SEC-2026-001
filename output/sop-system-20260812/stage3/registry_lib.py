"""registry_lib.py - REGISTRY.md 发布契约解析与校验共享库。

REGISTRY.md 的「已分配编号」表是 publish.sh 构建/发布清单的唯一来源。
本模块供 check_docs.py 与 registry_manifest.py 共用，避免两处各自解析导致漂移。
"""
import os
import re

# 仓库根 = 本文件所在 stage3 目录上三级（不依赖运行时 cwd）
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))

REGISTRY_REL = "sops/REGISTRY.md"
TABLE_HEADING = "## 已分配编号"
DOC_TYPES = {"policy", "standard", "procedure", "guideline", "reference"}
DOMAINS = {"INFRA", "SEC", "APP", "DESK", "DR", "GEN"}
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
FRONT_MATTER_MATCH = [
    ("document_id", "document_id"),
    ("title", "title"),
    ("category", "domain"),
    ("doc_type", "doc_type"),
    ("version", "version"),
    ("status", "status"),
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
    """解析 REGISTRY 的「已分配编号」表。

    返回 (entries, errors)。errors 为表格结构层面的错误；
    业务校验（源文件存在性、front matter 一致性等）由调用方执行。
    """
    path = registry_path or os.path.join(ROOT, REGISTRY_REL)
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()

    entries = []
    errors = []
    in_table = False
    table_found = False
    for lineno, raw in enumerate(lines, 1):
        stripped = raw.strip()
        if stripped.startswith("## "):
            in_table = stripped == TABLE_HEADING
            if in_table:
                table_found = True
            continue
        if not in_table or not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if cells[0] == "文档号":
            continue
        if all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
            continue
        if len(cells) != len(COLUMNS):
            errors.append(
                "第 %d 行应为 %d 列，实际 %d 列: %s"
                % (lineno, len(COLUMNS), len(cells), raw[:80])
            )
            continue
        entry = dict(zip(COLUMNS, cells))
        if not entry["document_id"] and not entry["source"]:
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

    def fail(msg):
        nonlocal issues
        issues += 1
        print("[FAIL] REGISTRY: %s" % msg)

    for err in errors:
        fail(err)
        if not verbose:
            continue

    for entry in entries:
        did = entry["document_id"]
        src = entry["source"]
        if did in seen_ids:
            fail("文档号重复: %s" % did)
        if src in seen_sources:
            fail("源文件重复: %s" % src)
        seen_ids.add(did)
        seen_sources.add(src)

        if entry["status"] == "Retired":
            continue

        if entry["doc_type"] not in DOC_TYPES:
            fail("%s: 未知 doc_type=%s" % (did, entry["doc_type"]))
        if entry["domain"] not in DOMAINS:
            fail("%s: 未知域名=%s" % (did, entry["domain"]))
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
            if fm.get(fm_key) != entry[reg_key]:
                fail(
                    "%s: front matter %s=%r 与 REGISTRY %s=%r 不一致"
                    % (src, fm_key, fm.get(fm_key), reg_key, entry[reg_key])
                )
    return issues, registered_sources
