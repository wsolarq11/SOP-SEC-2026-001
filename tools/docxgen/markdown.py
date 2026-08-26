"""Markdown parsing for the stdlib docx builder.

The renderer is intentionally line-based: it supports the fixed markdown
subset used by this knowledge base and preserves the original page-break and
metadata-table behavior.
"""
from __future__ import annotations

import re
from typing import Sequence

from registry_lib import parse_fm

from docxgen.constants import DOC_TYPE_ZH, FM_LABELS
from docxgen.formatting import para, table

_REQUIRED_FM = ["document_id", "title", "category", "version", "status", "author"]

SECT_XML = ('<w:sectPr>'
            '<w:headerReference w:type="default" r:id="rIdHdr"/>'
            '<w:footerReference w:type="default" r:id="rIdFtr"/>'
            '<w:pgSz w:w="11906" w:h="16838"/>'
            '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" '
            'w:header="720" w:footer="720" w:gutter="0"/></w:sectPr>')

DOCUMENT_TEMPLATE = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    '<w:document '
    'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/'
    'relationships">'
    '<w:body>%s' + SECT_XML + '</w:body></w:document>')


def _front_matter_end(lines: Sequence[str]) -> int:
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return i
    return -1


def _strip_front_matter(lines: list[str], fm: dict[str, str]) -> list[str]:
    if not fm:
        return lines
    end = _front_matter_end(lines)
    if end >= 0:
        return lines[end + 1:]
    return lines


def _missing_fields(fm: dict[str, str]) -> list[str]:
    return [key for key in _REQUIRED_FM if key not in fm]


def _is_separator_row(row: list[str]) -> bool:
    return (len(row) > 0 and any("-" in cell for cell in row)
            and all(set(cell) <= set("-: ") for cell in row))


def _table_rows(lines: Sequence[str], start: int) -> tuple[list[list[str]], int]:
    rows = []
    i = start
    while i < len(lines) and lines[i].strip().startswith("|"):
        cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
        rows.append(cells)
        i += 1
    return rows, i


def _approval_extra_from_table(rows: list[list[str]]) -> list[list[str]]:
    if len(rows) < 2:
        return []
    header = rows[0]
    result = []
    for data_row in rows[1:]:
        for ci, label in enumerate(header):
            value = data_row[ci] if ci < len(data_row) else ""
            if value.strip():
                result.append([label, value])
    return result


def _collect_approval_table(lines: Sequence[str]) -> list[list[str]]:
    for idx, line in enumerate(lines):
        if line.strip() != "## 审批信息":
            continue
        start = idx + 1
        while start < len(lines) and not lines[start].strip().startswith("|"):
            start += 1
        if start >= len(lines):
            break
        rows, _ = _table_rows(lines, start)
        rows = [row for row in rows if not _is_separator_row(row)]
        extra = _approval_extra_from_table(rows)
        if extra:
            return extra
    return []


def _merge_fm_rows(fm: dict[str, str],
                   approval_extra: Sequence[Sequence[str]]) -> list[list[str]]:
    rows = []
    for key, value in fm.items():
        if key == "title":
            continue
        if key == "doc_type":
            value = DOC_TYPE_ZH.get(value, value)
        rows.append([FM_LABELS.get(key, key), value])
    existing = [row[0] for row in rows]
    for label, value in approval_extra:
        if label not in existing and value.strip():
            rows.append([label, value])
            existing.append(label)
    return rows


class BodyRenderer:
    """Renders the markdown body into OOXML fragments in document order."""

    def __init__(self, fm_rows: Sequence[Sequence[str]]) -> None:
        self.body: list[str] = []
        self.fm_block = table(fm_rows, header=False) if fm_rows else ""
        self.fm_rendered = False
        self.approval_pending = False

    def render(self, lines: Sequence[str]) -> str:
        i = 0
        while i < len(lines):
            stripped = lines[i].strip()
            i = i + 1 if not stripped else self._render_line(lines, i, stripped)
        return "".join(self.body)

    def _render_heading(self, stripped: str) -> int:
        if stripped.startswith("# "):
            self._render_h1(stripped[2:].strip())
            return 1
        if stripped.startswith("## "):
            self._render_h2(stripped[3:].strip())
            return 1
        if stripped.startswith("### "):
            self.body.append(para(stripped[4:].strip(), style="Heading3"))
            return 1
        self.body.append(para(stripped[5:].strip(), style="Heading4"))
        return 1

    def _render_line(self, lines: Sequence[str], i: int, stripped: str) -> int:
        if stripped == "---":
            self.body.append(_horizontal_rule())
            return i + 1
        if re.match(r"^#{1,6} ", stripped):
            return i + self._render_heading(stripped)
        if stripped.startswith("|"):
            return self._render_table(lines, i)
        if stripped.startswith(">"):
            return self._render_quote(lines, i)
        if re.match(r"^[-*] ", stripped):
            return self._render_unordered(lines, i)
        if re.match(r"^\d+\. ", stripped):
            return self._render_ordered(lines, i)
        self.body.append(para(stripped))
        return i + 1

    def _render_h1(self, text: str) -> None:
        h1_ppr = ('<w:jc w:val="center"/>'
                  '<w:spacing w:before="240" w:after="240"/>')
        self.body.append(para(text, style="Heading1", ppr_extra=h1_ppr))
        if self.fm_block and not self.fm_rendered:
            self.body.append(self.fm_block)
            self.body.append('<w:p><w:r><w:br w:type="page"/></w:r></w:p>')
            self.fm_rendered = True

    def _render_h2(self, text: str) -> None:
        if text == "审批信息":
            self.approval_pending = True
            return
        if text == "版本修订记录":
            self.body.append('<w:p><w:r><w:br w:type="page"/></w:r></w:p>')
        self.body.append(para(text, style="Heading2"))

    def _render_table(self, lines: Sequence[str], i: int) -> int:
        rows = []
        while i < len(lines) and lines[i].strip().startswith("|"):
            cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
            rows.append(cells)
            i += 1
        rows = [row for row in rows if not _is_separator_row(row)]
        if rows:
            if self.approval_pending:
                self.approval_pending = False
            else:
                self.body.append(table(rows, header=True))
        return i

    def _render_quote(self, lines: Sequence[str], i: int) -> int:
        quote = []
        while i < len(lines) and lines[i].strip().startswith(">"):
            quote.append(lines[i].strip()[1:].strip())
            i += 1
        ppr = ('<w:pBdr><w:left w:val="single" w:sz="18" w:space="8" '
               'w:color="2563EB"/></w:pBdr><w:ind w:left="240"/>')
        self.body.append(para(" ".join(quote), italic=True, color="475467",
                              ppr_extra=ppr))
        return i

    def _render_unordered(self, lines: Sequence[str], i: int) -> int:
        items = []
        while i < len(lines) and re.match(r"^[-*] ", lines[i].strip()):
            items.append(re.sub(r"^[-*] ", "", lines[i].strip()))
            i += 1
        ppr = '<w:ind w:left="420" w:hanging="240"/>'
        for item in items:
            self.body.append(para("•  " + item, ppr_extra=ppr))
        return i

    def _render_ordered(self, lines: Sequence[str], i: int) -> int:
        items = []
        while i < len(lines) and re.match(r"^\d+\. ", lines[i].strip()):
            items.append(re.sub(r"^\d+\. ", "", lines[i].strip()))
            i += 1
        ppr = '<w:ind w:left="420" w:hanging="240"/>'
        for idx, item in enumerate(items, 1):
            self.body.append(para("%d.  %s" % (idx, item), ppr_extra=ppr))
        return i


def _horizontal_rule() -> str:
    return ('<w:p><w:pPr><w:pBdr><w:bottom w:val="single" w:sz="6" '
            'w:space="1" w:color="D0D5DD"/></w:pBdr></w:pPr></w:p>')


def parse_md(md: str) -> tuple[str, dict[str, str]]:
    lines = md.split("\n")
    fm = parse_fm(md)
    lines = _strip_front_matter(lines, fm)
    missing = _missing_fields(fm)
    if fm and missing:
        print("WARNING: front matter 缺失字段 %s（源文件可能被外部改写）" % missing)
    fm_rows = _merge_fm_rows(fm, _collect_approval_table(lines))
    body = BodyRenderer(fm_rows).render(lines)
    return DOCUMENT_TEMPLATE % body, fm
