"""Formatting helpers for the stdlib docx builder.

These functions own the exact OOXML fragment rendering. Keep behavior aligned
with the published formatting baseline documented at 103c977.
"""
from __future__ import annotations

import re
from typing import Sequence

from docxgen.constants import FONT_EA, FONT_LATIN, HEAD_EA, MONO

_INT_RE = re.compile(r"^\d{1,3}$")
_DATE_RE = re.compile(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}$")
_VER_RE = re.compile(r"^\d+\.\d+$")
_NUM_RE = re.compile(r"^[\d.\-/:\s]+$")


def esc(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def inline_runs(text: str) -> list[tuple[str, bool, bool]]:
    """Split text into (text, bold, code) tokens honoring **bold** and `code`."""
    out = []
    pattern = re.compile(r"(\*\*[^*]+\*\*|`[^`]+`)")
    for part in pattern.split(text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            out.append((part[2:-2], True, False))
        elif part.startswith("`") and part.endswith("`"):
            out.append((part[1:-1], False, True))
        else:
            out.append((part, False, False))
    return out


def _run_properties(base_bold: bool, base_italic: bool, base_color: str | None,
                    base_sz: int | None, bold: bool, code: bool) -> str:
    props = []
    if base_bold or bold:
        props.append("<w:b/>")
    if base_italic:
        props.append("<w:i/>")
    if base_color and not code:
        props.append('<w:color w:val="%s"/>' % base_color)
    if base_sz:
        props.append('<w:sz w:val="%s"/>' % base_sz)
    if code:
        props.append('<w:rFonts w:ascii="%s" w:hAnsi="%s" w:eastAsia="%s"/>'
                     % (MONO, MONO, FONT_EA))
        props.append('<w:shd w:val="clear" w:color="auto" w:fill="F3F4F6"/>')
    else:
        props.append('<w:rFonts w:eastAsia="%s" w:ascii="%s" w:hAnsi="%s"/>'
                     % (FONT_EA, FONT_LATIN, FONT_LATIN))
    return "<w:rPr>%s</w:rPr>" % "".join(props)


def runs_xml(text: str, base_bold: bool = False, base_italic: bool = False,
             base_color: str | None = None, base_sz: int | None = None) -> str:
    out = []
    for token, bold, code in inline_runs(text):
        props = _run_properties(base_bold, base_italic, base_color, base_sz,
                                bold, code)
        out.append('<w:r>%s<w:t xml:space="preserve">%s</w:t></w:r>'
                   % (props, esc(token)))
    if not out:
        out.append('<w:r><w:t xml:space="preserve"></w:t></w:r>')
    return "".join(out)


def para(text: str = "", style: str | None = None, bold: bool = False,
         italic: bool = False, color: str | None = None, sz: int | None = None,
         ppr_extra: str = "") -> str:
    ppr = "<w:pPr>"
    if style:
        ppr += '<w:pStyle w:val="%s"/>' % style
    ppr += ppr_extra
    ppr += "</w:pPr>"
    return "<w:p>%s%s</w:p>" % (ppr, runs_xml(text, base_bold=bold,
                                               base_italic=italic,
                                               base_color=color, base_sz=sz))


def render_w(text: str) -> int:
    """Estimate rendered width in twips; CJK glyphs get a safety margin."""
    return sum(240 if ord(char) > 127 else 120 for char in text)


def _form_label_width(rows: Sequence[Sequence[str]]) -> int:
    label_w = 1
    for row in rows:
        text = row[0] if row else ""
        label_w = max(label_w, render_w(text))
    return label_w + 226 + 150


def _form_value_weights(rows: Sequence[Sequence[str]], ncol: int) -> list[int]:
    weights = [1] * max(ncol - 1, 1)
    for row in rows:
        for ci in range(1, ncol):
            text = row[ci] if ci < len(row) else ""
            weight = sum(2 if ord(char) > 127 else 1 for char in text)
            if weight > weights[ci - 1]:
                weights[ci - 1] = weight
    return weights


def _form_col_widths(rows: Sequence[Sequence[str]], total: int,
                     ncol: int) -> list[int]:
    label_w = _form_label_width(rows)
    rest = total - label_w
    weights = _form_value_weights(rows, ncol)
    total_weight = sum(weights) or 1
    result = [label_w]
    for weight in weights[:-1]:
        result.append(max(900, int(rest * weight / total_weight)))
    result.append(rest - sum(result[1:]))
    return result


def _data_content_widths(rows: Sequence[Sequence[str]],
                         ncol: int) -> list[int]:
    widths = [1] * ncol
    for ri, row in enumerate(rows):
        factor = 2.0 if ri == 0 else 1.0
        for ci in range(min(ncol, len(row))):
            weight = int(sum(2 if ord(char) > 127 else 1
                             for char in row[ci]) * factor)
            if weight > widths[ci]:
                widths[ci] = weight
    return widths


def _short_bump_widths(rows: Sequence[Sequence[str]], ncol: int,
                       col_w: list[int]) -> dict[int, int]:
    bump = {}
    for ci in range(ncol):
        values = [row[ci] for row in rows if ci < len(row)]
        if values and all(len(value) <= 8 for value in values):
            required = max(render_w(value) for value in values) + 226
            if col_w[ci] < required:
                bump[ci] = required - col_w[ci]
                col_w[ci] = required
    return bump


def _deduct_width_overage(col_w: list[int], total: int,
                          short_bump: dict[int, int]) -> list[int]:
    over = sum(col_w) - total
    if over > 0:
        free = [ci for ci in range(len(col_w))
                if ci not in short_bump and col_w[ci] > 900]
        free_total = sum(col_w[ci] for ci in free) or 1
        for ci in free:
            cut = min(col_w[ci] - 900, int(over * col_w[ci] / free_total))
            col_w[ci] -= cut
    col_w[-1] += total - sum(col_w)
    return col_w


def _data_col_widths(rows: Sequence[Sequence[str]], total: int,
                     ncol: int) -> list[int]:
    widths = _data_content_widths(rows, ncol)
    total_weight = sum(widths) or 1
    col_w = [max(900, int(total * width / total_weight)) for width in widths]
    short_bump = _short_bump_widths(rows, ncol, col_w)
    return _deduct_width_overage(col_w, total, short_bump)


def col_widths(rows: Sequence[Sequence[str]], header: bool = True,
               total: int = 9000) -> list[int]:
    ncol = max(len(row) for row in rows) if rows else 1
    if not header:
        return _form_col_widths(rows, total, ncol)
    return _data_col_widths(rows, total, ncol)


def _alignment_for_column(rows: Sequence[Sequence[str]], ci: int,
                          header: bool) -> str:
    data = rows[1:] if header else rows
    values = [row[ci].strip() for row in data
              if ci < len(row) and row[ci].strip()]
    if not header:
        return "center" if ci == 0 else "left"
    if ci == 0:
        return "center"
    if not values:
        return "center"
    if all(_DATE_RE.match(value) or _VER_RE.match(value)
           or _INT_RE.match(value) for value in values):
        return "center"
    if all(_NUM_RE.match(value) for value in values):
        return "right"
    if all(len(value) <= 8 for value in values):
        return "center"
    return "left"


def compute_col_aligns(rows: Sequence[Sequence[str]],
                       header: bool = True) -> list[str]:
    ncol = max(len(row) for row in rows) if rows else 1
    return [_alignment_for_column(rows, ci, header) for ci in range(ncol)]


def _table_grid(col_w: list[int]) -> str:
    return ("<w:tblGrid>" +
            "".join('<w:gridCol w:w="%d"/>' % width for width in col_w) +
            "</w:tblGrid>")


def _table_properties() -> str:
    borders = ("<w:tblBorders>"
               '<w:top w:val="single" w:sz="4" w:space="0" w:color="D0D5DD"/>'
               '<w:left w:val="single" w:sz="4" w:space="0" w:color="D0D5DD"/>'
               '<w:bottom w:val="single" w:sz="4" w:space="0" w:color="D0D5DD"/>'
               '<w:right w:val="single" w:sz="4" w:space="0" w:color="D0D5DD"/>'
               '<w:insideH w:val="single" w:sz="4" w:space="0" w:color="D0D5DD"/>'
               '<w:insideV w:val="single" w:sz="4" w:space="0" w:color="D0D5DD"/>'
               "</w:tblBorders>")
    cellmar = ("<w:tblCellMar>"
               '<w:top w:w="57" w:type="dxa"/>'
               '<w:left w:w="113" w:type="dxa"/>'
               '<w:bottom w:w="57" w:type="dxa"/>'
               '<w:right w:w="113" w:type="dxa"/>'
               "</w:tblCellMar>")
    return ('<w:tblPr><w:tblStyle w:val="TableGrid"/>'
            '<w:tblW w:w="5000" w:type="pct"/>%s%s</w:tblPr>'
            % (cellmar, borders))


def _render_row(row: Sequence[str], ri: int, ncol: int,
                col_w: list[int], col_aligns: list[str],
                header: bool) -> str:
    is_header = header and ri == 0
    trpr = "<w:trPr><w:cantSplit/>"
    if is_header:
        trpr += "<w:tblHeader/>"
    trpr += "</w:trPr>"
    cells = ""
    for ci in range(ncol):
        value = row[ci] if ci < len(row) else ""
        tcpr = ('<w:tcPr><w:tcW w:w="%d" w:type="dxa"/>' % col_w[ci])
        if is_header:
            tcpr += '<w:shd w:val="clear" w:color="auto" w:fill="E6E6E6"/>'
        tcpr += '<w:vAlign w:val="center"/></w:tcPr>'
        jc = "center" if is_header else col_aligns[ci]
        ppr = '<w:pPr><w:jc w:val="%s"/></w:pPr>' % jc
        p = "<w:p>%s%s</w:p>" % (ppr, runs_xml(value, base_bold=is_header))
        cells += "<w:tc>%s%s</w:tc>" % (tcpr, p)
    return "<w:tr>%s%s</w:tr>" % (trpr, cells)


def table(rows: Sequence[Sequence[str]], header: bool = True) -> str:
    ncol = max(len(row) for row in rows) if rows else 1
    col_w = col_widths(rows, header)
    col_aligns = compute_col_aligns(rows, header)
    body = "".join(_render_row(row, ri, ncol, col_w, col_aligns, header)
                   for ri, row in enumerate(rows))
    return "<w:tbl>%s%s%s</w:tbl>" % (_table_properties(),
                                      _table_grid(col_w), body)


def _header_run(text: str) -> str:
    return ('<w:r><w:rPr><w:rFonts w:eastAsia="%s" w:ascii="%s" w:hAnsi="%s"/>'
            '<w:sz w:val="18"/></w:rPr><w:t xml:space="preserve">%s</w:t></w:r>'
            % (FONT_EA, FONT_LATIN, FONT_LATIN, esc(text)))


def header_xml(fm: dict[str, str]) -> str:
    title = fm.get("title", "") or ""
    doc_number = (fm.get("document_id") or fm.get("doc_number") or "") or ""
    version = fm.get("version", "") or ""
    label = ("%s %s" % (doc_number, version)).strip()
    left = _header_run(title)
    right = _header_run(label)
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<w:hdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/'
            '2006/main">'
            '<w:p><w:pPr><w:pStyle w:val="Header"/>'
            '<w:tabs><w:tab w:val="right" w:pos="9360"/></w:tabs>'
            '<w:jc w:val="left"/></w:pPr>'
            + left +
            '<w:r><w:tab/></w:r>'
            + right +
            '</w:p></w:hdr>')


def footer_xml() -> str:
    page = ('<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
            '<w:r><w:instrText xml:space="preserve"> PAGE </w:instrText></w:r>'
            '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
            '<w:r><w:t>1</w:t></w:r>'
            '<w:r><w:fldChar w:fldCharType="end"/></w:r>')
    nopage = ('<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
              '<w:r><w:instrText xml:space="preserve"> NUMPAGES </w:instrText>'
              '</w:r><w:r><w:fldChar w:fldCharType="separate"/></w:r>'
              '<w:r><w:t>1</w:t></w:r>'
              '<w:r><w:fldChar w:fldCharType="end"/></w:r>')
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/'
            '2006/main">'
            '<w:p><w:pPr><w:pStyle w:val="Footer"/><w:jc w:val="center"/></w:pPr>'
            + page +
            '<w:r><w:rPr><w:rFonts w:eastAsia="%s" w:ascii="%s" w:hAnsi="%s"/>'
            '<w:sz w:val="18"/></w:rPr><w:t xml:space="preserve"> / </w:t></w:r>'
            % (FONT_EA, FONT_LATIN, FONT_LATIN) + nopage +
            '</w:p></w:ftr>')
