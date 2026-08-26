"""OOXML constants shared by the docx builder.

The XML strings here mirror the original single-file generator byte for byte;
changing them changes the published document baseline documented at 103c977.
"""
import datetime

FONT_EA = "宋体"
FONT_LATIN = "Times New Roman"
HEAD_EA = "黑体"
MONO = "Consolas"
TEXT_COLOR = "3F3F3F"

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

DOC_TYPE_ZH = {
    "policy": "方针",
    "standard": "标准",
    "procedure": "程序",
    "guideline": "指南",
    "reference": "参考说明",
}

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

_NOW_ISO = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

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
    '</cp:coreProperties>') % (_NOW_ISO, _NOW_ISO)

APP = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/'
    'extended-properties"><Application>KB-DocGen</Application></Properties>')
