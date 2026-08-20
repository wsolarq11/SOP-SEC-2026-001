"""sop_to_docx_stdlib.py - Markdown -> .docx using ONLY the Python standard library.

Zero third-party dependencies (no python-docx, no bs4). Builds a valid OOXML
.docx package by hand so it works in locked-down environments where pip is
blocked. Supports the markdown subset used by the SOP knowledge base:

  - front-matter (--- delimited key: value ---) rendered as a metadata table
  - headings # .. #### (mapped to real Heading styles with outline levels)
  - tables (with header row shaded)
  - blockquotes (> )
  - unordered lists (- / *) and ordered lists (1. )
  - inline **bold** and `code`
  - horizontal rule (---)

Usage:
  python sop_to_docx_stdlib.py <input.md> <output.docx>
"""
import os
import re
import sys
import zipfile
import datetime

# 字体与颜色（对齐中文正式文档规范 + Few/微软颜色建议）
FONT_EA = "宋体"                  # 正文字体（中文正式文档规范）
FONT_LATIN = "Times New Roman"    # 正文西文/数字（中文文档惯例）
HEAD_EA = "黑体"                  # 标题字体（中文文档惯例）
MONO = "Consolas"                 # 代码/参数等宽字体
TEXT_COLOR = "3F3F3F"             # 正文字色：深灰（Stephen Few 推荐 + 微软安全灰）

# front matter 键名 -> 文档信息表中文标签（展示层中文，机器层保持英文键）
FM_LABELS = {
    "document_id": "文档编号",
    "title": "标题",
    "category": "分类",
    "doc_type": "文档类型",
    "version": "版本",
    "status": "状态",
    "author": "编制人",
    "approver": "批准人",
    "effective_date": "生效日期",
    "review_due": "复审日期",
    "last_reviewed": "上次复审",
}

# doc_type 值 -> 中文（展示层翻译，机器层保持英文枚举）
DOC_TYPE_ZH = {
    "policy": "方针",
    "standard": "标准",
    "procedure": "程序",
    "guideline": "指南",
    "reference": "参考说明",
}


def esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def inline_runs(text):
    """Split text into (text, bold, code) tokens honoring **bold** and `code`."""
    out = []
    pattern = re.compile(r"(\*\*[^*]+\*\*|`[^`]+`)")
    for p in pattern.split(text):
        if not p:
            continue
        if p.startswith("**") and p.endswith("**"):
            out.append((p[2:-2], True, False))
        elif p.startswith("`") and p.endswith("`"):
            out.append((p[1:-1], False, True))
        else:
            out.append((p, False, False))
    return out


def runs_xml(text, base_bold=False, base_italic=False, base_color=None,
             base_sz=None):
    out = []
    for t, b, c in inline_runs(text):
        rpr = []
        if base_bold or b:
            rpr.append("<w:b/>")
        if base_italic:
            rpr.append("<w:i/>")
        if base_color and not c:
            rpr.append('<w:color w:val="%s"/>' % base_color)
        if base_sz:
            rpr.append('<w:sz w:val="%s"/>' % base_sz)
        if c:
            rpr.append('<w:rFonts w:ascii="%s" w:hAnsi="%s" w:eastAsia="%s"/>'
                       % (MONO, MONO, FONT_EA))
            rpr.append('<w:shd w:val="clear" w:color="auto" w:fill="F3F4F6"/>')
        else:
            rpr.append('<w:rFonts w:eastAsia="%s" w:ascii="%s" w:hAnsi="%s"/>'
                       % (FONT_EA, FONT_LATIN, FONT_LATIN))
        rpr_xml = "<w:rPr>%s</w:rPr>" % "".join(rpr)
        out.append('<w:r>%s<w:t xml:space="preserve">%s</w:t></w:r>'
                   % (rpr_xml, esc(t)))
    if not out:
        out.append('<w:r><w:t xml:space="preserve"></w:t></w:r>')
    return "".join(out)


def para(text="", style=None, bold=False, italic=False, color=None, sz=None,
         ppr_extra=""):
    ppr = "<w:pPr>"
    if style:
        ppr += '<w:pStyle w:val="%s"/>' % style
    ppr += ppr_extra
    ppr += "</w:pPr>"
    return "<w:p>%s%s</w:p>" % (ppr, runs_xml(text, base_bold=bold,
                                                base_italic=italic,
                                                base_color=color, base_sz=sz))


_INT_RE = re.compile(r"^\d{1,3}$")       # 序号/短数字 -> 居中
_DATE_RE = re.compile(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}$")  # 日期 -> 居中
_VER_RE = re.compile(r"^\d+\.\d+$")      # 版本号 1.0 -> 居中
_NUM_RE = re.compile(r"^[\d.\-/:\s]+$")  # 可运算数值/IP -> 右对齐


def render_w(txt):
    """估算文本渲染宽度（twips）：中文 240、西文 120。

    10.5pt 中文字理论宽约 210 twips，但实际渲染（字形、字距、字体渲染
    差异）会略宽——取 240 留安全余量，避免单行内容临界溢出换行。
    """
    return sum(240 if ord(c) > 127 else 120 for c in txt)


def col_widths(rows, header=True, total=9000):
    """列宽分配。

    - 表单类（header=False，如文件信息表）：标签列档位宽 = 内容需求 + 边距
      + 呼吸富余，全表统一（SAP Fiori label-field ratio / ANU 20% / 语雀
      80-120px 档位制）；剩余宽度全部给值列。
    - 数据类（header=True）：AutoFit Window——按内容加权分配 9000（100%
      页面宽），表头行（第一行）权重 x2，保证标题单元格单行显示（微软官方
      风格指南 "Balance row height by increasing the width of text-heavy
      columns" 与 "keep text in each cell brief—ideally one line"）。
    """
    ncol = max(len(r) for r in rows) if rows else 1
    if not header:
        label_w = 1
        for r in rows:
            txt = r[0] if r else ""
            label_w = max(label_w, render_w(txt))
        label_w += 226 + 150  # 内容需求 + 单元格边距 + 呼吸富余（档位制）
        rest = total - label_w
        val_weights = [1] * max(ncol - 1, 1)
        for r in rows:
            for ci in range(1, ncol):
                txt = r[ci] if ci < len(r) else ""
                w = sum(2 if ord(c) > 127 else 1 for c in txt)
                if w > val_weights[ci - 1]:
                    val_weights[ci - 1] = w
        tw = sum(val_weights) or 1
        ws = [label_w]
        for w in val_weights[:-1]:
            ws.append(max(900, int(rest * w / tw)))
        ws.append(rest - sum(ws[1:]))  # 末列补差，保证合计=total
        return ws
    widths = [1] * ncol
    for ri, r in enumerate(rows):
        factor = 2.0 if (header and ri == 0) else 1.0
        for ci in range(min(ncol, len(r))):
            w = int(sum(2 if ord(c) > 127 else 1 for c in r[ci]) * factor)
            if w > widths[ci]:
                widths[ci] = w
    tw = sum(widths) or 1
    col_w = [max(900, int(total * w / tw)) for w in widths]
    # 短内容列（行标签/短标签：列内所有单元格 <=8 字符）保证单行——
    # 宽度 >= 该列最长内容渲染宽（含安全余量）+ 边距；超出从长文本列扣回。
    short_bump = {}
    for ci in range(ncol):
        vals = [r[ci] for r in rows if ci < len(r)]
        if vals and all(len(v) <= 8 for v in vals):
            wid = max(render_w(v) for v in vals) + 226
            if col_w[ci] < wid:
                short_bump[ci] = wid - col_w[ci]
                col_w[ci] = wid
    over = sum(col_w) - total
    if over > 0:
        free = [ci for ci in range(ncol)
                if ci not in short_bump and col_w[ci] > 900]
        ftot = sum(col_w[ci] for ci in free) or 1
        for ci in free:
            cut = min(col_w[ci] - 900, int(over * col_w[ci] / ftot))
            col_w[ci] -= cut
    col_w[-1] += total - sum(col_w)  # 修正总和=页面内容宽
    return col_w


def compute_col_aligns(rows, header=True):
    """列级统一对齐（黄金规则：一列内不混用对齐）。

    - 表单类（header=False，如文件信息表）：值列统一左对齐
    - 记录/数据类（header=True）：表头恒居中；数据列按内容类型——
      日期/版本号/序号/短标签（<=8 字符）列居中；可运算数值列右对齐；
      含长文本列左对齐
    """
    ncol = max(len(r) for r in rows) if rows else 1
    data = rows[1:] if header else rows
    aligns = []
    for ci in range(ncol):
        vals = [r[ci].strip() for r in data if ci < len(r) and r[ci].strip()]
        if not header:
            # 表单类（如文件信息表）：第一列行标签居中（W3C th scope=row），值列左对齐
            aligns.append("center" if ci == 0 else "left")
        elif ci == 0:
            # 行标签列（第一列）恒居中（W3C th scope="row"，§5.1 规则），
            # 不随内容长短变化——保证所有表格第一列视觉统一
            aligns.append("center")
        elif not vals:
            aligns.append("center")
        elif all(_DATE_RE.match(v) or _VER_RE.match(v) or _INT_RE.match(v)
                 for v in vals):
            aligns.append("center")
        elif all(_NUM_RE.match(v) for v in vals):
            aligns.append("right")
        elif all(len(v) <= 8 for v in vals):
            aligns.append("center")
        else:
            aligns.append("left")
    return aligns


def table(rows, header=True):
    ncol = max(len(r) for r in rows) if rows else 1
    col_ws = col_widths(rows, header)
    col_aligns = compute_col_aligns(rows, header)
    grid = ("<w:tblGrid>" +
            "".join('<w:gridCol w:w="%d"/>' % w for w in col_ws) +
            "</w:tblGrid>")
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
    # 所有表格统一 AutoFit Window（100% 页面宽）——多表格文档一致性
    # （myuptech: "Use AutoFit Window for a uniform table width when you have multiple tables"）
    tblpr = ('<w:tblPr><w:tblStyle w:val="TableGrid"/>'
             '<w:tblW w:w="5000" w:type="pct"/>%s%s</w:tblPr>'
             % (cellmar, borders))
    body = ""
    for ri, row in enumerate(rows):
        is_header = header and ri == 0
        trpr = "<w:trPr><w:cantSplit/>"
        if is_header:
            trpr += "<w:tblHeader/>"
        trpr += "</w:trPr>"
        cells = ""
        for ci in range(ncol):
            val = row[ci] if ci < len(row) else ""
            tcpr = ('<w:tcPr><w:tcW w:w="%d" w:type="dxa"/>' % col_ws[ci])
            if is_header:
                tcpr += '<w:shd w:val="clear" w:color="auto" w:fill="E6E6E6"/>'
            tcpr += '<w:vAlign w:val="center"/></w:tcPr>'
            jc = "center" if is_header else col_aligns[ci]
            ppr = '<w:pPr><w:jc w:val="%s"/></w:pPr>' % jc
            p = "<w:p>%s%s</w:p>" % (ppr, runs_xml(val, base_bold=is_header))
            cells += "<w:tc>%s%s</w:tc>" % (tcpr, p)
        body += "<w:tr>%s%s</w:tr>" % (trpr, cells)
    return "<w:tbl>%s%s%s</w:tbl>" % (tblpr, grid, body)


def parse_md(md):
    lines = md.split("\n")
    fm = {}
    if lines and lines[0].strip() == "---":
        end = None
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                end = i
                break
        if end is not None:
            for l in lines[1:end]:
                if ":" in l:
                    k, v = l.split(":", 1)
                    fm[k.strip()] = v.strip()
            lines = lines[end + 1:]
    # 完整性校验：front matter 必备字段缺失 → 警告（防止外部进程静默破坏源文件）
    # 历史教训：2026-08-14 规文被外部改写只剩 title，导致文档信息表丢失。
    required = ["document_id", "title", "category", "version", "status", "author"]
    missing = [k for k in required if k not in fm]
    if fm and missing:
        print("WARNING: front matter 缺失字段 %s（源文件可能被外部改写）" % missing)

    body = ""
    fm_rows = []
    for k, v in fm.items():
        if k == "title":
            continue
        # doc_type 值翻译为中文（展示层），其余原样
        if k == "doc_type":
            v = DOC_TYPE_ZH.get(v, v)
        fm_rows.append([FM_LABELS.get(k, k), v])

    # 预扫描：提取正文「审批信息」表（编制人/审核人/批准人/生效日期）并入信息表，
    # 形成一张合并的「文件信息表」（对齐质量管理 SOP 封面模板的单表格式）。
    approval_extra = []
    for idx, line in enumerate(lines):
        if line.strip() == "## 审批信息":
            j = idx + 1
            while j < len(lines) and not lines[j].strip().startswith("|"):
                j += 1
            if j < len(lines):
                tbl = []
                while j < len(lines) and lines[j].strip().startswith("|"):
                    row = [c.strip() for c in lines[j].strip().strip("|").split("|")]
                    tbl.append(row)
                    j += 1
                tbl = [r for r in tbl if not (
                    len(r) > 0 and any("-" in c for c in r) and
                    all(set(c) <= set("-: ") for c in r))]
                if len(tbl) >= 2:
                    header = tbl[0]
                    for data_row in tbl[1:]:
                        for ci, label in enumerate(header):
                            val = data_row[ci] if ci < len(data_row) else ""
                            if val.strip():
                                approval_extra.append([label, val])
            break
    existing = [r[0] for r in fm_rows]
    for label, val in approval_extra:
        if label not in existing and val.strip():
            fm_rows.append([label, val])
            existing.append(label)

    fm_rendered = False
    if fm_rows:
        fm_block = table(fm_rows, header=False)
    else:
        fm_block = ""

    # 首页信息页独立成页（流派 B）：H1 标题后紧跟合并的文件信息表，
    # 其后固定插分页符，正文（适用场景起）从第二页开始；不依赖源文档
    # 是否包含「审批信息」节，避免 SEC/DESK 等文档分页行为不一致。
    approval_pending = False

    i, n = 0, len(lines)
    while i < n:
        st = lines[i].strip()
        if st == "":
            i += 1
            continue
        if st == "---":
            body += ('<w:p><w:pPr><w:pBdr><w:bottom w:val="single" w:sz="6" '
                     'w:space="1" w:color="D0D5DD"/></w:pBdr></w:pPr></w:p>')
            i += 1
            continue
        if st.startswith("# "):
            # H1 文档标题：居中 + 段前段后间距（对齐医械临床试验操作手册/阳新县医院 SOP 规范）
            h1_ppr = ('<w:jc w:val="center"/>'
                      '<w:spacing w:before="240" w:after="240"/>')
            body += para(st[2:].strip(), style="Heading1", ppr_extra=h1_ppr)
            if fm_block and not fm_rendered:
                body += fm_block
                body += ('<w:p><w:r><w:br w:type="page"/></w:r></w:p>')
                fm_rendered = True
            i += 1
            continue
        if st.startswith("## "):
            if st[3:].strip() == "审批信息":
                # 审批信息已并入文件信息表，跳过其标题；封面分页已由文件信息表统一处理
                approval_pending = True
                i += 1
                continue
            if st[3:].strip() == "版本修订记录":
                body += ('<w:p><w:r><w:br w:type="page"/></w:r></w:p>')
            body += para(st[3:].strip(), style="Heading2"); i += 1; continue
        if st.startswith("### "):
            body += para(st[4:].strip(), style="Heading3"); i += 1; continue
        if st.startswith("#### "):
            body += para(st[5:].strip(), style="Heading4"); i += 1; continue
        if st.startswith("|"):
            tbl = []
            while i < n and lines[i].strip().startswith("|"):
                row = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                tbl.append(row)
                i += 1
            tbl = [r for r in tbl if not (
                len(r) > 0 and any("-" in c for c in r) and
                all(set(c) <= set("-: ") for c in r))]
            if tbl:
                if approval_pending:
                    # 审批信息表内容已并入文件信息表，此处跳过渲染
                    approval_pending = False
                else:
                    body += table(tbl, header=True)
            continue
        if st.startswith(">"):
            quote = []
            while i < n and lines[i].strip().startswith(">"):
                quote.append(lines[i].strip()[1:].strip())
                i += 1
            ppr = ('<w:pBdr><w:left w:val="single" w:sz="18" w:space="8" '
                   'w:color="2563EB"/></w:pBdr><w:ind w:left="240"/>')
            body += para(" ".join(quote), italic=True, color="475467",
                         ppr_extra=ppr)
            continue
        if re.match(r"^[-*] ", st):
            items = []
            while i < n and re.match(r"^[-*] ", lines[i].strip()):
                items.append(re.sub(r"^[-*] ", "", lines[i].strip()))
                i += 1
            for it in items:
                ppr = '<w:ind w:left="420" w:hanging="240"/>'
                body += para("•  " + it, ppr_extra=ppr)
            continue
        if re.match(r"^\d+\. ", st):
            items = []
            while i < n and re.match(r"^\d+\. ", lines[i].strip()):
                items.append(re.sub(r"^\d+\. ", "", lines[i].strip()))
                i += 1
            for idx, it in enumerate(items, 1):
                ppr = '<w:ind w:left="420" w:hanging="240"/>'
                body += para("%d.  %s" % (idx, it), ppr_extra=ppr)
            continue
        body += para(st)
        i += 1

    sect = ('<w:sectPr>'
            '<w:headerReference w:type="default" r:id="rIdHdr"/>'
            '<w:footerReference w:type="default" r:id="rIdFtr"/>'
            '<w:pgSz w:w="11906" w:h="16838"/>'
            '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" '
            'w:header="720" w:footer="720" w:gutter="0"/></w:sectPr>')
    doc = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
           '<w:document '
           'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
           'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/'
           'relationships">'
           '<w:body>' + body + sect + '</w:body></w:document>')
    return doc, fm


def header_xml(fm):
    title = fm.get("title", "") or ""
    doc_number = (fm.get("document_id") or fm.get("doc_number") or "") or ""
    version = fm.get("version", "") or ""
    label = ("%s %s" % (doc_number, version)).strip()
    left = '<w:r><w:rPr><w:rFonts w:eastAsia="%s" w:ascii="%s" w:hAnsi="%s"/>' \
           '<w:sz w:val="18"/></w:rPr><w:t xml:space="preserve">%s</w:t></w:r>' \
           % (FONT_EA, FONT_LATIN, FONT_LATIN, esc(title))
    right = ('<w:r><w:rPr><w:rFonts w:eastAsia="%s" w:ascii="%s" w:hAnsi="%s"/>'
             '<w:sz w:val="18"/></w:rPr><w:t xml:space="preserve">%s</w:t></w:r>'
             % (FONT_EA, FONT_LATIN, FONT_LATIN, esc(label)))
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


def footer_xml():
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


CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-'
    'package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" ContentType="application/vnd.'
    'openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    '<Override PartName="/word/styles.xml" ContentType="application/vnd.'
    'openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
    '<Override PartName="/word/header1.xml" ContentType="application/vnd.'
    'openxmlformats-officedocument.wordprocessingml.header+xml"/>'
    '<Override PartName="/word/footer1.xml" ContentType="application/vnd.'
    'openxmlformats-officedocument.wordprocessingml.footer+xml"/>'
    '<Override PartName="/docProps/core.xml" ContentType="application/vnd.'
    'openxmlformats-package.core-properties+xml"/>'
    '<Override PartName="/docProps/app.xml" ContentType="application/vnd.'
    'openxmlformats-officedocument.extended-properties+xml"/>'
    '</Types>')

RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
    'relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/'
    'officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
    '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/'
    '2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
    '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/'
    'officeDocument/2006/relationships/extended-properties" Target="docProps/'
    'app.xml"/>'
    '</Relationships>')

DOC_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
    'relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/'
    'officeDocument/2006/relationships/styles" Target="styles.xml"/>'
    '<Relationship Id="rIdHdr" Type="http://schemas.openxmlformats.org/'
    'officeDocument/2006/relationships/header" Target="header1.xml"/>'
    '<Relationship Id="rIdFtr" Type="http://schemas.openxmlformats.org/'
    'officeDocument/2006/relationships/footer" Target="footer1.xml"/>'
    '</Relationships>')

STYLES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/'
    '2006/main">'
    '<w:docDefaults><w:rPrDefault><w:rPr>'
    '<w:rFonts w:eastAsia="' + FONT_EA + '" w:ascii="' + FONT_LATIN
    + '" w:hAnsi="' + FONT_LATIN + '"/>'
    '<w:color w:val="' + TEXT_COLOR + '"/><w:sz w:val="21"/>'
    '</w:rPr></w:rPrDefault>'
    '<w:pPrDefault><w:pPr><w:spacing w:after="120" w:line="276" '
    'w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>'
    '<w:style w:type="paragraph" w:styleId="Normal"><w:name w:val="Normal"/>'
    '<w:rPr><w:rFonts w:eastAsia="' + FONT_EA + '"/></w:rPr></w:style>'
    '<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/>'
    '<w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>'
    '<w:pPr><w:outlineLvl w:val="0"/><w:spacing w:before="240" w:after="120"/>'
    '</w:pPr><w:rPr><w:rFonts w:eastAsia="' + HEAD_EA + '" w:ascii="'
    + FONT_LATIN + '" w:hAnsi="' + FONT_LATIN + '"/><w:b/><w:sz w:val="32"/>'
    '<w:color w:val="' + TEXT_COLOR + '"/></w:rPr>'
    '</w:style>'
    '<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/>'
    '<w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>'
    '<w:pPr><w:outlineLvl w:val="1"/><w:spacing w:before="200" w:after="100"/>'
    '</w:pPr><w:rPr><w:rFonts w:eastAsia="' + HEAD_EA + '" w:ascii="'
    + FONT_LATIN + '" w:hAnsi="' + FONT_LATIN + '"/><w:b/><w:sz w:val="26"/>'
    '<w:color w:val="' + TEXT_COLOR + '"/></w:rPr>'
    '</w:style>'
    '<w:style w:type="paragraph" w:styleId="Heading3"><w:name w:val="heading 3"/>'
    '<w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>'
    '<w:pPr><w:outlineLvl w:val="2"/><w:spacing w:before="160" w:after="80"/>'
    '</w:pPr><w:rPr><w:rFonts w:eastAsia="' + HEAD_EA + '" w:ascii="'
    + FONT_LATIN + '" w:hAnsi="' + FONT_LATIN + '"/><w:b/><w:sz w:val="23"/>'
    '<w:color w:val="' + TEXT_COLOR + '"/></w:rPr>'
    '</w:style>'
    '<w:style w:type="paragraph" w:styleId="Heading4"><w:name w:val="heading 4"/>'
    '<w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>'
    '<w:pPr><w:outlineLvl w:val="3"/><w:spacing w:before="120" w:after="60"/>'
    '</w:pPr><w:rPr><w:rFonts w:eastAsia="' + HEAD_EA + '" w:ascii="'
    + FONT_LATIN + '" w:hAnsi="' + FONT_LATIN + '"/><w:b/><w:sz w:val="21"/>'
    '<w:color w:val="' + TEXT_COLOR + '"/></w:rPr>'
    '</w:style>'
    '<w:style w:type="table" w:styleId="TableGrid"><w:name w:val="Table Grid"/>'
    '<w:tblPr><w:tblBorders>'
    '<w:top w:val="single" w:sz="4" w:space="0" w:color="auto"/>'
    '<w:left w:val="single" w:sz="4" w:space="0" w:color="auto"/>'
    '<w:bottom w:val="single" w:sz="4" w:space="0" w:color="auto"/>'
    '<w:right w:val="single" w:sz="4" w:space="0" w:color="auto"/>'
    '<w:insideH w:val="single" w:sz="4" w:space="0" w:color="auto"/>'
    '<w:insideV w:val="single" w:sz="4" w:space="0" w:color="auto"/>'
    '</w:tblBorders></w:tblPr></w:style>'
    '</w:styles>')

CORE = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    '<cp:coreProperties '
    'xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
    'xmlns:dc="http://purl.org/dc/elements/1.1/" '
    'xmlns:dcterms="http://purl.org/dc/terms/" '
    'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
    '<dc:title>SOP Knowledge Base</dc:title>'
    '<cp:lastModifiedBy>KB</cp:lastModifiedBy>'
    '<dcterms:created xsi:type="dcterms:W3CDTF">%s</dcterms:created>'
    '<dcterms:modified xsi:type="dcterms:W3CDTF">%s</dcterms:modified>'
    '</cp:coreProperties>') % (datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                               datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"))

APP = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/'
    'extended-properties"><Application>KB-DocGen</Application></Properties>')


def build(md_path, docx_path):
    with open(md_path, "r", encoding="utf-8") as f:
        md = f.read()
    document_xml, fm = parse_md(md)
    parts = {
        "[Content_Types].xml": CONTENT_TYPES,
        "_rels/.rels": RELS,
        "word/document.xml": document_xml,
        "word/_rels/document.xml.rels": DOC_RELS,
        "word/styles.xml": STYLES,
        "word/header1.xml": header_xml(fm),
        "word/footer1.xml": footer_xml(),
        "docProps/core.xml": CORE,
        "docProps/app.xml": APP,
    }
    with zipfile.ZipFile(docx_path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in parts.items():
            z.writestr(name, data)

    # Validate in the same process (the env clobbers .docx between runs).
    import xml.etree.ElementTree as ET
    with zipfile.ZipFile(docx_path) as z:
        for part in ("word/document.xml", "word/header1.xml",
                     "word/footer1.xml"):
            ET.fromstring(z.read(part).decode("utf-8"))  # raises if malformed
        doc = z.read("word/document.xml").decode("utf-8")
    para_count = doc.count("<w:p>")
    tbl_count = doc.count("<w:tbl>")
    print("OK saved:", docx_path)
    print("VERIFY well-formed XML: yes")
    print("VERIFY paragraphs:", para_count, "tables:", tbl_count)


def main():
    if len(sys.argv) < 3:
        print("usage: sop_to_docx_stdlib.py <input.md> <output.docx>")
        sys.exit(2)
    build(sys.argv[1], sys.argv[2])


if __name__ == "__main__":
    main()
