"""sop_to_docx_stdlib.py - Markdown -> .docx using ONLY the Python standard library.

Zero third-party dependencies (no python-docx, no bs4). Builds a valid OOXML
.docx package by hand so it works in locked-down environments where pip is
blocked. Supports the markdown subset used by the SOP knowledge base:
front matter, headings, tables, blockquotes, lists, inline formatting, and
horizontal rules.

Usage:
  python sop_to_docx_stdlib.py <input.md> <output.docx>
"""
import sys
import zipfile
import xml.etree.ElementTree as ET

from docxgen.constants import APP, CONTENT_TYPES, CORE, DOC_RELS, RELS, STYLES
from docxgen.formatting import footer_xml, header_xml
from docxgen.markdown import parse_md

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def _write_zip(parts: dict[str, str], docx_path: str) -> None:
    with zipfile.ZipFile(docx_path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in parts.items():
            z.writestr(name, data)


def _validate_docx(docx_path: str) -> tuple[int, int]:
    # Validate in the same process (the env clobbers .docx between runs).
    with zipfile.ZipFile(docx_path) as z:
        for part in ("word/document.xml", "word/header1.xml",
                     "word/footer1.xml"):
            ET.fromstring(z.read(part).decode("utf-8"))  # raises if malformed
        doc = z.read("word/document.xml").decode("utf-8")
    return doc.count("<w:p>"), doc.count("<w:tbl>")


def build(md_path: str, docx_path: str) -> None:
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
    _write_zip(parts, docx_path)
    para_count, tbl_count = _validate_docx(docx_path)
    print("OK saved:", docx_path)
    print("VERIFY well-formed XML: yes")
    print("VERIFY paragraphs:", para_count, "tables:", tbl_count)


def main() -> None:
    if len(sys.argv) < 3:
        print("usage: sop_to_docx_stdlib.py <input.md> <output.docx>")
        sys.exit(2)
    build(sys.argv[1], sys.argv[2])


if __name__ == "__main__":
    main()
