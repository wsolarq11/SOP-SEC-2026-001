"""Toolchain regression tests for the SOP publishing pipeline.

Runs without third-party packages. Exercises the registry contract,
the stdlib docx generator, the secret scanner, and the docs health check.
"""
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import check_secrets
import registry_lib
import registry_render
import sop_to_docx_stdlib


class PipelineTests(unittest.TestCase):
    def test_registry_contract_is_clean(self):
        entries, errors = registry_lib.parse_registry()
        issues, _ = registry_lib.validate_registry_entries(entries, errors)
        self.assertEqual(errors, [])
        self.assertEqual(issues, 0)

    def test_registry_json_is_machine_source(self):
        json_path = os.path.join(ROOT, registry_lib.REGISTRY_JSON_REL)
        self.assertTrue(os.path.isfile(json_path))
        entries, errors = registry_lib.parse_registry()
        self.assertEqual(errors, [])
        self.assertEqual(len(entries), 5)

    def test_all_registry_versions_locked_to_1_0(self):
        entries, errors = registry_lib.parse_registry()
        self.assertEqual(errors, [])
        for entry in entries:
            self.assertEqual(entry["version"], registry_lib.LOCKED_VERSION)

    def test_registry_render_matches_generated_md(self):
        entries, errors = registry_lib.parse_registry()
        self.assertEqual(errors, [])
        table = registry_render.render_table(entries)
        with open(os.path.join(ROOT, registry_lib.REGISTRY_REL), encoding="utf-8") as f:
            md = f.read()
        self.assertIn(table, md)
        proc = subprocess.run(
            [sys.executable, os.path.join(HERE, "registry_render.py"), "--check"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_registry_parser_uses_header_order(self):
        registry_md = """## 已分配编号
| 标题 | 文档号 | 状态 | 源文件 | 目标目录 | 类型 | 域名 | 版本 | 关联标准 | 编制人 | 层级 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Test | SOP-TEST-2026-001 | Draft | sops/test.md | 06-GEN-通用 | procedure | GEN | 1.0 | ISO 9001 | Tester | L3 |
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "REGISTRY.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write(registry_md)
            entries, errors = registry_lib.parse_registry(path)
        self.assertEqual(errors, [])
        self.assertEqual(entries[0]["document_id"], "SOP-TEST-2026-001")
        self.assertEqual(entries[0]["author"], "Tester")

    def test_generator_writes_well_formed_docx(self):
        md = """---
document_id: SOP-GEN-2026-TEST
title: Test SOP
category: GEN
doc_type: procedure
version: 1.0
status: Draft
author: Tester
approver: Tester
---
# Test SOP
## 1 Table
| A | B |
| --- | --- |
| 1 | 2 |
"""
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "input.md")
            out = os.path.join(tmp, "output.docx")
            with open(src, "w", encoding="utf-8") as f:
                f.write(md)
            sop_to_docx_stdlib.build(src, out)
            with zipfile.ZipFile(out) as zf:
                self.assertIn("word/document.xml", zf.namelist())
                self.assertIn("word/styles.xml", zf.namelist())
                for part in ("word/document.xml", "word/header1.xml", "word/footer1.xml"):
                    ET.fromstring(zf.read(part).decode("utf-8"))

    def test_secret_scanner_rejects_high_confidence_token(self):
        with tempfile.NamedTemporaryFile(
            "w", suffix=".tmp", delete=False, encoding="utf-8"
        ) as f:
            f.write("token=ghp_%s\n" % ("A" * 24))
            path = f.name
        try:
            hits = check_secrets.scan_file(path)
        finally:
            os.unlink(path)
        self.assertTrue(hits, "high-confidence GitHub token should be detected")

    def test_lark_json_cli_contract(self):
        helper = os.path.join(HERE, "lark_json.py")
        ok = subprocess.run(
            [sys.executable, helper, "ok"],
            input='log prefix\n{"ok": true}',
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)
        token = subprocess.run(
            [sys.executable, helper, "token"],
            input='{"ok": true, "file_token": "abc"}',
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(token.stdout.strip(), "abc")
        nested = subprocess.run(
            [sys.executable, helper, "token"],
            input='{"ok": true, "data": {"file_token": "abc"}}',
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(nested.stdout.strip(), "abc")
        raw = subprocess.run(
            [sys.executable, helper, "token"],
            input=b'{"ok": true, "data": {"file_token": "abc"}}',
            capture_output=True,
        )
        self.assertNotIn(b"\r", raw.stdout)
        self.assertEqual(raw.stdout.strip(), b"abc")
        bad = subprocess.run(
            [sys.executable, helper, "ok"],
            input='{"ok": false, "message": "denied"}',
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(bad.returncode, 1)
        msg = subprocess.run(
            [sys.executable, helper, "message"],
            input='{"ok": false, "message": "denied"}',
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertIn("denied", msg.stdout)

    def test_docs_health_check_runs_clean(self):
        proc = subprocess.run(
            [sys.executable, os.path.join(HERE, "check_docs.py")],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("OK:", proc.stdout)
        self.assertNotIn("\ufffd", proc.stdout + proc.stderr)

    def test_manifest_emits_registry_placeholder(self):
        proc = subprocess.run(
            [sys.executable, os.path.join(HERE, "registry_manifest.py")],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("sops/REGISTRY.md|NONE", proc.stdout)
        self.assertIn("sops/registry.json|NONE", proc.stdout)
        self.assertNotIn("\ufffd", proc.stdout + proc.stderr)


    def test_kb_cli_stage_path_resolves_toolchain(self):
        proc = subprocess.run(
            [sys.executable, os.path.join(ROOT, "tools", "kb.py"), "stage"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("tools", proc.stdout)

    def test_kb_cli_dispatches_health_check(self):
        proc = subprocess.run(
            [sys.executable, os.path.join(ROOT, "tools", "kb.py"), "check"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("OK:", proc.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
