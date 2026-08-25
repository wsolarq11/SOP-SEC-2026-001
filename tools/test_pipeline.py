"""Toolchain regression tests for the SOP publishing pipeline.

Runs without third-party packages. Exercises the registry contract,
the stdlib docx generator, the secret scanner, and the docs health check.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)
if os.path.join(HERE, "feishu_preview_proxy") not in sys.path:
    sys.path.insert(0, os.path.join(HERE, "feishu_preview_proxy"))

import check_secrets
import feishu_mitm_proxy as feishu_proxy
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
        self.assertGreaterEqual(len(entries), 5)

    def test_front_matter_version_matches_latest_revision(self):
        entries, errors = registry_lib.parse_registry()
        self.assertEqual(errors, [])
        for entry in entries:
            if entry.get("status") == "Retired":
                continue
            with open(os.path.join(ROOT, entry["source"]), encoding="utf-8") as f:
                text = f.read()
            latest = registry_lib.latest_revision_version(text)
            if latest is not None:
                self.assertEqual(
                    registry_lib.parse_fm(text).get("version"),
                    latest,
                    entry["document_id"],
                )

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

    def test_manifest_rejects_draft_publish(self):
        proc = subprocess.run(
            [sys.executable, os.path.join(HERE, "registry_manifest.py")],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("Draft", proc.stdout + proc.stderr)
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


class FeishuPreviewProxyTests(unittest.TestCase):
    def test_default_routes_cover_three_preview_hosts(self):
        routes = feishu_proxy.DEFAULT_CONFIG["routes"]
        self.assertEqual(set(routes), {
            "internal-api-drive-stream.feishu.cn",
            "internal-api-lark-api.feishu.cn",
            "weboffice.feishu-3rd-party-services.com",
        })

    def test_config_overrides_routes_and_keeps_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "config.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"routes": {"example.test": "upstream.test"}}, f)
            config = feishu_proxy.load_config(path)
        self.assertEqual(config["routes"], {"example.test": "upstream.test"})
        self.assertEqual(config["listen_port"], 18080)

    def test_pac_generation_contains_configured_hosts_and_port(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = dict(feishu_proxy.DEFAULT_CONFIG)
            config["listen_port"] = 19090
            pac = feishu_proxy.write_pac(Path(tmp), config)
            text = pac.read_text(encoding="utf-8")
        self.assertIn("internal-api-drive-stream.feishu.cn", text)
        self.assertIn("PROXY 127.0.0.1:19090", text)
        self.assertIn('"weboffice.feishu-3rd-party-services.com": true', text)

    def test_safe_headers_redacts_cookie_and_authorization(self):
        headers = [
            (b"Cookie", b"session=secret"),
            (b"Authorization", b"Bearer token"),
            (b"Host", b"example.test"),
        ]
        text = feishu_proxy.safe_headers(headers)
        self.assertNotIn("session", text)
        self.assertNotIn("Bearer", text)
        self.assertIn("Host=", text)

    def test_cors_headers_are_injected(self):
        head = b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n"
        origin = b"https://xcn87k1zyro7.feishu.cn"
        out = feishu_proxy.add_cors_headers(head, origin, [(b"Origin", origin)])
        self.assertIn(b"Access-Control-Allow-Origin: " + origin, out)
        self.assertIn(b"Content-Type: application/json", out)

    def test_rewrite_request_preserves_original_host(self):
        request_line = b"GET /space/api/box/stream/download HTTP/1.1"
        headers = [
            (b"Host", b"internal-api-drive-stream.feishu.cn"),
            (b"Proxy-Connection", b"keep-alive"),
        ]
        out = feishu_proxy.rewrite_request(request_line, headers, b"")
        self.assertIn(b"Host: internal-api-drive-stream.feishu.cn", out)
        self.assertNotIn(b"Proxy-Connection", out)

    def test_forward_response_body_streams_content_length(self):
        upstream = feishu_proxy.BufferedSocket(FakeSocket(b"hello"))
        client = RecordingClient()
        feishu_proxy.forward_response_body(
            upstream,
            client,
            b"GET",
            [(b"Content-Length", b"5")],
            200,
        )
        self.assertEqual(client.data, b"hello")

    def test_forward_response_body_streams_chunked(self):
        body = b"5\r\nhello\r\n0\r\n\r\n"
        upstream = feishu_proxy.BufferedSocket(FakeSocket(body))
        client = RecordingClient()
        feishu_proxy.forward_response_body(
            upstream,
            client,
            b"GET",
            [(b"Transfer-Encoding", b"chunked")],
            200,
        )
        self.assertEqual(client.data, body)


class FakeSocket:
    def __init__(self, data):
        self.data = data
        self.offset = 0

    def recv(self, size):
        if self.offset >= len(self.data):
            return b""
        end = min(len(self.data), self.offset + size)
        out = self.data[self.offset:end]
        self.offset = end
        return out


class RecordingClient:
    def __init__(self):
        self.sent = []

    def sendall(self, data):
        self.sent.append(data)

    @property
    def data(self):
        return b"".join(self.sent)


if __name__ == "__main__":
    unittest.main(verbosity=2)
