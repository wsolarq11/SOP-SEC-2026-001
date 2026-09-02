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
import fact_ops
import line_report
import proxy_certs
from proxy_core import (
    DEFAULT_CONFIG,
    BufferedSocket,
    add_cors_headers,
    ensure_certs,
    forward_response_body,
    load_config,
    rewrite_request,
    safe_headers,
    write_pac,
)
import publish_log
import registry_lib
import registry_render
import sop_to_docx_stdlib
import token_bootstrap

_SAMPLE_SOP_MD = """---
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

_SAMPLE_DOCX_HIDE_MD = """---
document_id: SOP-GEN-2026-TEST
title: Test SOP
category: GEN
doc_type: procedure
version: 1.0
status: Draft
author: Tester
approver: Tester
requirement_ref: hidden source fact
---
# Test SOP
<!-- docx-hide: 文档信息 -->

## 保留
| A | B |
| --- | --- |
| 1 | 2 |

<!-- docx-hide: 隐藏章节 -->

## 隐藏章节
| X | Y |
| --- | --- |
| 3 | 4 |

<!-- docx-hide: 版本修订记录 -->

## 版本修订记录
| 版本 | 内容 |
| --- | --- |
|  |  |
"""


class PipelineTests(unittest.TestCase):
    def test_registry_contract_is_clean(self) -> None:
        entries, errors = registry_lib.parse_registry()
        issues, _ = registry_lib.validate_registry_entries(entries, errors)
        self.assertEqual(errors, [])
        self.assertEqual(issues, 0)

    def test_registry_json_is_machine_source(self) -> None:
        json_path = os.path.join(ROOT, registry_lib.REGISTRY_JSON_REL)
        self.assertTrue(os.path.isfile(json_path))
        entries, errors = registry_lib.parse_registry()
        self.assertEqual(errors, [])
        self.assertGreaterEqual(len(entries), 5)

    def test_front_matter_version_matches_latest_revision(self) -> None:
        entries, errors = registry_lib.parse_registry()
        self.assertEqual(errors, [])
        for entry in entries:
            with open(os.path.join(ROOT, entry["source"]), encoding="utf-8") as f:
                text = f.read()
            latest = registry_lib.latest_revision_version(text)
            if latest is not None:
                self.assertEqual(
                    registry_lib.parse_fm(text).get("version"),
                    latest,
                    entry["document_id"],
                )

    def test_registry_render_matches_generated_md(self) -> None:
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

    def test_registry_parser_uses_header_order(self) -> None:
        registry_md = """## 已分配编号
| 标题 | 文档号 | 状态 | 源文件 | 目标目录 | 类型 | 域名 | 版本 | 编制人 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Test | SOP-TEST-2026-001 | Draft | sops/test.md | 06-GEN-通用 | procedure | GEN | 1.0 | Tester |
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "REGISTRY.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write(registry_md)
            entries, errors = registry_lib.parse_registry(path)
        self.assertEqual(errors, [])
        self.assertEqual(entries[0]["document_id"], "SOP-TEST-2026-001")
        self.assertEqual(entries[0]["author"], "Tester")

    def test_generator_writes_well_formed_docx(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "input.md")
            out = os.path.join(tmp, "output.docx")
            with open(src, "w", encoding="utf-8") as f:
                f.write(_SAMPLE_SOP_MD)
            sop_to_docx_stdlib.build(src, out)
            self._assert_docx_xml(out)

    def test_generator_hides_requirement_ref_in_docx(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "input.md")
            out = os.path.join(tmp, "output.docx")
            md = _SAMPLE_SOP_MD.replace(
                "approver: Tester\n",
                "approver: Tester\nrequirement_ref: 2026-08 test requirement\n",
                1,
            )
            with open(src, "w", encoding="utf-8") as f:
                f.write(md)
            sop_to_docx_stdlib.build(src, out)
            with zipfile.ZipFile(out) as zf:
                xml = zf.read("word/document.xml").decode("utf-8")
            self.assertIn("requirement_ref", xml)
            self.assertIn("2026-08 test requirement", xml)
            self.assertIn('<w:trHeight w:val="0" w:hRule="exact"/>', xml)
            self.assertIn("<w:hidden/>", xml)
            self.assertGreaterEqual(xml.count("<w:vanish/>"), 2)

    def test_generator_hides_marked_sections_and_front_matter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "input.md")
            out = os.path.join(tmp, "output.docx")
            with open(src, "w", encoding="utf-8") as f:
                f.write(_SAMPLE_DOCX_HIDE_MD)
            sop_to_docx_stdlib.build(src, out)
            with zipfile.ZipFile(out) as zf:
                xml = zf.read("word/document.xml").decode("utf-8")
            self.assertIn("保留", xml)
            self.assertNotIn("文档编号", xml)
            self.assertNotIn("SOP-GEN-2026-TEST", xml)
            self.assertNotIn("隐藏章节", xml)
            self.assertNotIn("版本修订记录", xml)
            self.assertNotIn("hidden source fact", xml)

    def _assert_docx_xml(self, out: str) -> None:
        with zipfile.ZipFile(out) as zf:
            self.assertIn("word/document.xml", zf.namelist())
            self.assertIn("word/styles.xml", zf.namelist())
            for part in ("word/document.xml", "word/header1.xml", "word/footer1.xml"):
                ET.fromstring(zf.read(part).decode("utf-8"))

    def test_secret_scanner_rejects_high_confidence_token(self) -> None:
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

    def test_lark_json_ok_accepts_true(self) -> None:
        proc = self._run_lark("ok", 'log prefix\n{"ok": true}')
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_lark_json_token_flat_and_nested(self) -> None:
        flat = self._run_lark("token", '{"ok": true, "file_token": "abc"}')
        self.assertEqual(flat.stdout.strip(), "abc")
        nested = self._run_lark(
            "token", '{"ok": true, "data": {"file_token": "abc"}}'
        )
        self.assertEqual(nested.stdout.strip(), "abc")

    def test_lark_json_output_is_lf(self) -> None:
        raw = subprocess.run(
            [sys.executable, os.path.join(HERE, "lark_json.py"), "token"],
            input=b'{"ok": true, "data": {"file_token": "abc"}}',
            capture_output=True,
        )
        self.assertNotIn(b"\r", raw.stdout)
        self.assertEqual(raw.stdout.strip(), b"abc")

    def test_lark_json_failure_and_message(self) -> None:
        bad = self._run_lark("ok", '{"ok": false, "message": "denied"}')
        self.assertEqual(bad.returncode, 1)
        msg = self._run_lark("message", '{"ok": false, "message": "denied"}')
        self.assertIn("denied", msg.stdout)

    def _run_lark(self, field: str, payload: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, os.path.join(HERE, "lark_json.py"), field],
            input=payload,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

    def test_docs_health_check_runs_clean(self) -> None:
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

    def test_manifest_includes_draft_and_approved(self) -> None:
        proc = subprocess.run(
            [sys.executable, os.path.join(HERE, "registry_manifest.py")],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("SOP-GEN-2026-001-合规与标准定位.docx", proc.stdout)
        self.assertIn("SOP-通用-系统说明.docx", proc.stdout)
        self.assertNotIn("\ufffd", proc.stdout + proc.stderr)

    def test_kb_cli_dispatches_health_check(self) -> None:
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

    def test_registry_json_accepts_optional_production_fields(self) -> None:
        payload = {
            "entries": [{
                "document_id": "SOP-TEST-2026-001",
                "title": "Test",
                "doc_type": "procedure",
                "domain": "GEN",
                "version": "1.0",
                "author": "Tester",
                "status": "Draft",
                "source": "sops/test.md",
                "target_dir": "06-GEN-通用",
                "requirement_ref": "REQ-1",
                "reviewer": "Reviewer",
                "reviewed_at": "2026-08-27",
                "approved_at": "",
                "last_published_at": "",
            }]
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "registry.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False)
            entries, errors = registry_lib.parse_registry(path)
        self.assertEqual(errors, [])
        self.assertEqual(entries[0]["requirement_ref"], "REQ-1")
        self.assertEqual(entries[0]["reviewed_at"], "2026-08-27")

    def test_publish_log_appends_jsonl_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log = os.path.join(tmp, "publish-log.jsonl")
            record = publish_log.append_publish(
                log, "sop/AI会话知识库维护流程.md", "tok-1"
            )
            with open(log, encoding="utf-8") as f:
                line = json.loads(f.readline())
        self.assertEqual(record["document_id"], "SOP-GEN-2026-004")
        self.assertEqual(line["source"], "sop/AI会话知识库维护流程.md")
        self.assertEqual(line["file_token"], "tok-1")
        self.assertEqual(line["result"], "success")

    def test_publish_log_rejects_unregistered_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log = os.path.join(tmp, "publish-log.jsonl")
            with self.assertRaises(KeyError):
                publish_log.append_publish(log, "sops/not-registered.md", "tok")

    def test_publish_log_records_source_hash_and_dirty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log = os.path.join(tmp, "publish-log.jsonl")
            record = publish_log.append_publish(
                log, "sop/AI会话知识库维护流程.md", "tok-1"
            )
        self.assertEqual(len(record["source_hash"]), 64)
        self.assertIn("dirty", record)
        self.assertTrue(record["commit"])

    def test_publish_log_updates_registry_last_published(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log = os.path.join(tmp, "publish-log.jsonl")
            registry_path = os.path.join(tmp, "registry.json")
            payload = {
                "schema_version": 1,
                "entries": [{
                    "document_id": "SOP-GEN-2026-004",
                    "title": "AI 会话知识库维护流程",
                    "source": "sop/AI会话知识库维护流程.md",
                }],
            }
            with open(registry_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False)
            record = publish_log.append_publish(
                log, "sop/AI会话知识库维护流程.md", "tok-1",
                update_registry=True, registry_path=registry_path
            )
            with open(registry_path, encoding="utf-8") as f:
                data = json.load(f)
        self.assertEqual(data["entries"][0]["last_published_at"],
                         record["time"][:10])

    def test_publish_log_writes_safe_repo_summary_without_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log = os.path.join(tmp, "publish-log.jsonl")
            history = os.path.join(tmp, "publish-history.jsonl")
            record = publish_log.append_publish(
                log, "sop/AI会话知识库维护流程.md", "tok-1",
                repo_summary=True, repo_history=history
            )
            with open(history, encoding="utf-8") as f:
                safe = json.loads(f.readline())
        self.assertEqual(safe["document_id"], "SOP-GEN-2026-004")
        self.assertEqual(safe["source"], "sop/AI会话知识库维护流程.md")
        self.assertEqual(safe["time"], record["time"])
        self.assertNotIn("file_token", safe)

    def test_line_report_deduplicates_publish_after_source_rename(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log = os.path.join(tmp, "publish-log.jsonl")
            history = os.path.join(tmp, "publish-history.jsonl")
            tokens = os.path.join(tmp, "tokens")
            with open(tokens, "w", encoding="utf-8") as f:
                f.write("sop/AI会话知识库维护流程.md|md|docx\n")
            old_event = {
                "document_id": "SOP-GEN-2026-004",
                "version": "1.0",
                "source": ".sop/AI会话知识库维护流程.md",
                "time": "2026-08-27T06:40:05+00:00",
                "result": "success",
                "file_token": "tok-1",
            }
            new_summary = dict(old_event, source="sop/AI会话知识库维护流程.md")
            new_summary.pop("file_token")
            with open(log, "w", encoding="utf-8") as f:
                f.write(json.dumps(old_event, ensure_ascii=False) + "\n")
            with open(history, "w", encoding="utf-8") as f:
                f.write(json.dumps(new_summary, ensure_ascii=False) + "\n")
            proc = subprocess.run(
                [sys.executable, os.path.join(HERE, "line_report.py"),
                 "--doc", "SOP-GEN-2026-004", "--json", "--log", log,
                 "--repo-history", history, "--tokens", tokens],
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=dict(os.environ, LOCALAPPDATA=tmp, TEMP=tmp),
            )
            data = json.loads(proc.stdout)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(data["summary"]["publish_records"], 1)
        self.assertEqual(data["entries"][0]["stage"], "已发布")

    def test_line_report_blocks_missing_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log = os.path.join(tmp, "publish-log.jsonl")
            tokens = os.path.join(tmp, "tokens")
            with open(tokens, "w", encoding="utf-8") as f:
                f.write("# empty\n")
            proc = subprocess.run(
                [sys.executable, os.path.join(HERE, "line_report.py"),
                 "--doc", "SOP-GEN-2026-004", "--json", "--log", log,
                 "--tokens", tokens],
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        data = json.loads(proc.stdout)
        self.assertEqual(data["entries"][0]["blocked"], "阻塞")
        self.assertEqual(data["summary"]["blocked"], 1)
        self.assertEqual(data["summary"]["lines"], 1)
        self.assertIn("publish_records", data["summary"])

    def test_token_bootstrap_updates_and_replaces_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tokens = os.path.join(tmp, "tokens")
            token_bootstrap._update_tokens(
                tokens, "sop/AI会话知识库维护流程.md", "tok-a"
            )
            first = token_bootstrap._read_tokens(tokens)
            token_bootstrap._update_tokens(
                tokens, "sop/AI会话知识库维护流程.md", "tok-b"
            )
            second = token_bootstrap._read_tokens(tokens)
            with open(tokens, encoding="utf-8") as f:
                count = sum(line.startswith("sop/") for line in f)
        self.assertEqual(first["sop/AI会话知识库维护流程.md"], "tok-a")
        self.assertEqual(second["sop/AI会话知识库维护流程.md"], "tok-b")
        self.assertEqual(count, 1)

    def test_token_bootstrap_backup_token_stays_none(self) -> None:
        self.assertEqual(
            token_bootstrap._exclude_backup_token("BACKUP_BUNDLE", "tok"),
            "NONE")
        self.assertEqual(
            token_bootstrap._exclude_backup_token(
                "sop/AI会话知识库维护流程.md", "tok"),
            "tok")

    def test_registry_render_syncs_front_matter_one_way(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "test.md")
            with open(source, "w", encoding="utf-8") as f:
                f.write(_SAMPLE_SOP_MD)
            entry = {
                "document_id": "SOP-GEN-2026-TEST",
                "title": "Test SOP",
                "domain": "GEN",
                "doc_type": "procedure",
                "version": "1.0",
                "status": "Draft",
                "author": "Tester",
                "approver": "审批人",
                "effective_date": "2026-08-27",
                "requirement_ref": "REQ-1",
                "reviewer": "",
                "reviewed_at": "",
                "approved_at": "",
            }
            changed = registry_render.sync_source_front_matter(
                "test.md", entry, root=tmp
            )
            with open(source, encoding="utf-8") as f:
                text = f.read()
            fm = registry_lib.parse_fm(text)
        self.assertTrue(changed)
        self.assertEqual(fm["approver"], "审批人")
        self.assertEqual(fm["requirement_ref"], "REQ-1")
        self.assertEqual(fm["effective_date"], "2026-08-27")
        self.assertNotIn("reviewer", fm)

    def test_line_report_marks_published_and_hides_tokens(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log = os.path.join(tmp, "publish-log.jsonl")
            publish_log.append_publish(
                log, "sop/AI会话知识库维护流程.md", "token-should-not-print"
            )
            proc = subprocess.run(
                [sys.executable, os.path.join(HERE, "line_report.py"),
                 "--doc", "SOP-GEN-2026-004", "--json", "--log", log],
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        data = json.loads(proc.stdout)
        self.assertEqual(data["entries"][0]["stage"], "已发布")
        self.assertNotIn("token-should-not-print", proc.stdout)


class FeishuPreviewProxyTests(unittest.TestCase):
    def test_default_routes_cover_three_preview_hosts(self) -> None:
        routes = DEFAULT_CONFIG["routes"]
        self.assertEqual(set(routes), {
            "internal-api-drive-stream.feishu.cn",
            "internal-api-lark-api.feishu.cn",
            "weboffice.feishu-3rd-party-services.com",
        })

    def test_config_overrides_routes_and_keeps_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "config.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"routes": {"example.test": "upstream.test"}}, f)
            config = load_config(path)
        self.assertEqual(config["routes"], {"example.test": "upstream.test"})
        self.assertEqual(config["listen_port"], 18080)

    def test_pac_generation_contains_configured_hosts_and_port(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = dict(DEFAULT_CONFIG)
            config["listen_port"] = 19090
            pac = write_pac(Path(tmp), config)
            text = pac.read_text(encoding="utf-8")
        self.assertIn("internal-api-drive-stream.feishu.cn", text)
        self.assertIn("PROXY 127.0.0.1:19090", text)
        self.assertIn('"weboffice.feishu-3rd-party-services.com": true', text)

    def test_ensure_certs_rebuilds_leaf_when_routes_change(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            first = ensure_certs(base, {
                "old-internal.example": "public.example",
            })
            self.assertIn("DNS:old-internal.example",
                          self._leaf_san(base, first))
            second = ensure_certs(base, {
                "new-internal.example": "public.example",
            })
            second_san = self._leaf_san(base, second)
            self.assertIn("DNS:new-internal.example", second_san)
            self.assertNotIn("DNS:old-internal.example", second_san)

    def _leaf_san(self, base: Path, cert_dir: Path) -> str:
        proc = proxy_certs.openssl([
            "x509", "-in", str(cert_dir / "leaf.crt"),
            "-noout", "-ext", "subjectAltName",
        ], cert_dir)
        return proc.stdout

    def test_safe_headers_redacts_cookie_and_authorization(self) -> None:
        headers = [
            (b"Cookie", b"session=secret"),
            (b"Authorization", b"Bearer token"),
            (b"Host", b"example.test"),
        ]
        text = safe_headers(headers)
        self.assertNotIn("session", text)
        self.assertNotIn("Bearer", text)
        self.assertIn("Host=", text)

    def test_cors_headers_are_injected(self) -> None:
        head = b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n"
        origin = b"https://xcn87k1zyro7.feishu.cn"
        out = add_cors_headers(head, origin, [(b"Origin", origin)])
        self.assertIn(b"Access-Control-Allow-Origin: " + origin, out)
        self.assertIn(b"Content-Type: application/json", out)

    def test_rewrite_request_preserves_original_host(self) -> None:
        request_line = b"GET /space/api/box/stream/download HTTP/1.1"
        headers = [
            (b"Host", b"internal-api-drive-stream.feishu.cn"),
            (b"Proxy-Connection", b"keep-alive"),
        ]
        out = rewrite_request(request_line, headers, b"")
        self.assertIn(b"Host: internal-api-drive-stream.feishu.cn", out)
        self.assertNotIn(b"Proxy-Connection", out)

    def test_forward_response_body_streams_content_length(self) -> None:
        upstream = BufferedSocket(FakeSocket(b"hello"))
        client = RecordingClient()
        forward_response_body(
            upstream,
            client,
            b"GET",
            [(b"Content-Length", b"5")],
            200,
        )
        self.assertEqual(client.data, b"hello")

    def test_forward_response_body_streams_chunked(self) -> None:
        body = b"5\r\nhello\r\n0\r\n\r\n"
        upstream = BufferedSocket(FakeSocket(body))
        client = RecordingClient()
        forward_response_body(
            upstream,
            client,
            b"GET",
            [(b"Transfer-Encoding", b"chunked")],
            200,
        )
        self.assertEqual(client.data, body)


class FakeSocket:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.offset = 0

    def recv(self, size: int) -> bytes:
        if self.offset >= len(self.data):
            return b""
        end = min(len(self.data), self.offset + size)
        out = self.data[self.offset:end]
        self.offset = end
        return out


class RecordingClient:
    def __init__(self) -> None:
        self.sent: list[bytes] = []

    def sendall(self, data: bytes) -> None:
        self.sent.append(data)

    @property
    def data(self) -> bytes:
        return b"".join(self.sent)


if __name__ == "__main__":
    unittest.main(verbosity=2)
