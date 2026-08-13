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

FONT = "微软雅黑"
MONO = "Consolas"


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
                       % (MONO, MONO, FONT))
            rpr.append('<w:shd w:val="clear" w:color="auto" w:fill="F3F4F6"/>')
        else:
            rpr.append('<w:rFonts w:eastAsia="%s" w:ascii="%s" w:hAnsi="%s"/>'
                       % (FONT, FONT, FONT))
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


def table(rows, header=True):
    ncol = max(len(r) for r in rows) if rows else 1
    col_w = 9000 // ncol
    grid = ("<w:tblGrid>" +
            "".join('<w:gridCol w:w="%d"/>' % col_w for _ in range(ncol)) +
            "</w:tblGrid>")
    borders = ("<w:tblBorders>"
               '<w:top w:val="single" w:sz="4" w:space="0" w:color="D0D5DD"/>'
               '<w:left w:val="single" w:sz="4" w:space="0" w:color="D0D5DD"/>'
               '<w:bottom w:val="single" w:sz="4" w:space="0" w:color="D0D5DD"/>'
               '<w:right w:val="single" w:sz="4" w:space="0" w:color="D0D5DD"/>'
               '<w:insideH w:val="single" w:sz="4" w:space="0" w:color="D0D5DD"/>'
               '<w:insideV w:val="single" w:sz="4" w:space="0" w:color="D0D5DD"/>'
               "</w:tblBorders>")
    tblpr = ('<w:tblPr><w:tblStyle w:val="TableGrid"/>'
             '<w:tblW w:w="5000" w:type="pct"/>%s</w:tblPr>' % borders)
    body = ""
    for ri, row in enumerate(rows):
        is_header = header and ri == 0
        cells = ""
        for ci in range(ncol):
            val = row[ci] if ci < len(row) else ""
            tcpr = '<w:tcPr><w:tcW w:w="%d" w:type="dxa"/>' % col_w
            if is_header:
                tcpr += '<w:shd w:val="clear" w:color="auto" w:fill="FEF3C7"/>'
            tcpr += "</w:tcPr>"
            p = "<w:p>%s</w:p>" % runs_xml(val, base_bold=is_header)
            cells += "<w:tc>%s%s</w:tc>" % (tcpr, p)
        body += "<w:tr>%s</w:tr>" % cells
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

    body = ""
    fm_rows = [[k, v] for k, v in fm.items() if k != "title"]
    if fm_rows:
        body += para("文档信息", style="Heading2")
        body += table(fm_rows, header=False)

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
            body += para(st[2:].strip(), style="Heading1"); i += 1; continue
        if st.startswith("## "):
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
    doc_number = fm.get("doc_number", "") or ""
    version = fm.get("version", "") or ""
    label = ("%s %s" % (doc_number, version)).strip()
    left = '<w:r><w:rPr><w:rFonts w:eastAsia="%s" w:ascii="%s" w:hAnsi="%s"/>' \
           '<w:sz w:val="18"/></w:rPr><w:t xml:space="preserve">%s</w:t></w:r>' \
           % (FONT, FONT, FONT, esc(title))
    right = ('<w:r><w:rPr><w:rFonts w:eastAsia="%s" w:ascii="%s" w:hAnsi="%s"/>'
             '<w:sz w:val="18"/></w:rPr><w:t xml:space="preserve">%s</w:t></w:r>'
             % (FONT, FONT, FONT, esc(label)))
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
            % (FONT, FONT, FONT) + nopage +
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
    '<w:rFonts w:eastAsia="%s" w:ascii="%s" w:hAnsi="%s"/>'
    '<w:sz w:val="21"/></w:rPr></w:rPrDefault>'
    '<w:pPrDefault><w:pPr><w:spacing w:after="120" w:line="276" '
    'w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>'
    '<w:style w:type="paragraph" w:styleId="Normal"><w:name w:val="Normal"/>'
    '<w:rPr><w:rFonts w:eastAsia="%s"/></w:rPr></w:style>'
    '<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/>'
    '<w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>'
    '<w:pPr><w:outlineLvl w:val="0"/><w:spacing w:before="240" w:after="120"/>'
    '</w:pPr><w:rPr><w:b/><w:sz w:val="32"/><w:color w:val="1F3864"/></w:rPr>'
    '</w:style>'
    '<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/>'
    '<w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>'
    '<w:pPr><w:outlineLvl w:val="1"/><w:spacing w:before="200" w:after="100"/>'
    '</w:pPr><w:rPr><w:b/><w:sz w:val="26"/><w:color w:val="1F3864"/></w:rPr>'
    '</w:style>'
    '<w:style w:type="paragraph" w:styleId="Heading3"><w:name w:val="heading 3"/>'
    '<w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>'
    '<w:pPr><w:outlineLvl w:val="2"/><w:spacing w:before="160" w:after="80"/>'
    '</w:pPr><w:rPr><w:b/><w:sz w:val="23"/><w:color w:val="2E5496"/></w:rPr>'
    '</w:style>'
    '<w:style w:type="paragraph" w:styleId="Heading4"><w:name w:val="heading 4"/>'
    '<w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>'
    '<w:pPr><w:outlineLvl w:val="3"/><w:spacing w:before="120" w:after="60"/>'
    '</w:pPr><w:rPr><w:b/><w:sz w:val="21"/><w:color w:val="2E5496"/></w:rPr>'
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
    '</w:styles>') % (FONT, FONT, FONT, FONT)

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
