"""token_bootstrap.py - bootstrap a missing Feishu docx token.

The publish line can no longer be blocked by a missing first upload:
  python tools/kb.py token-bootstrap --source sops/SOP-...md

It resolves the wiki space and target directory from registry data, creates
the file node with lark-cli when needed, and updates .publish-tokens.
Tokens are never printed or committed.
"""
from __future__ import annotations

import argparse
import base64
import os
import subprocess
import sys
from collections.abc import Sequence

import lark_json
import publish_tokens
import registry_lib
import sop_to_docx_stdlib

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

SPACE_NAME = "企业IT-SOP知识库"


def _command(cli_args: Sequence[str]) -> list[str]:
    """Return the subprocess argv for lark-cli.

    On Windows lark-cli is shipped as a .cmd npm shim, which Python's
    CreateProcess can't launch directly; route through cmd.exe instead.
    """
    if os.name == "nt":
        return ["cmd", "/c"] + list(cli_args)
    return list(cli_args)


def _run_cli(args: Sequence[str]) -> dict[str, object]:
    proc = subprocess.run(
        _command(args),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        raise RuntimeError("lark-cli failed: %s\n%s" % (proc.stderr.strip(),
                                                        proc.stdout.strip()))
    return lark_json.parse_json(proc.stdout)


def _data(payload: dict[str, object], key: str) -> list[dict[str, object]]:
    data = payload.get("data")
    if not isinstance(data, dict):
        return []
    value = data.get(key)
    return value if isinstance(value, list) else []


def _space_id(cli: str, as_identity: str) -> str:
    payload = _run_cli([cli, "wiki", "+space-list", "--as", as_identity,
                        "--format", "json", "--page-all"])
    for space in _data(payload, "spaces"):
        if space.get("name") == SPACE_NAME:
            return str(space.get("space_id", ""))
    for space in _data(payload, "spaces"):
        if "SOP" in str(space.get("description", "")):
            return str(space.get("space_id", ""))
    raise RuntimeError("no SOP wiki space found for %r" % SPACE_NAME)


def _node_by_title(cli: str, space_id: str, parent_token: str,
                   title: str, as_identity: str) -> dict[str, object] | None:
    args = [cli, "wiki", "+node-list", "--space-id", space_id,
            "--as", as_identity, "--format", "json", "--page-all"]
    if parent_token:
        args += ["--parent-node-token", parent_token]
    payload = _run_cli(args)
    for node in _data(payload, "nodes"):
        if node.get("title") == title:
            return node
    return None


def _target_node(cli: str, space_id: str, target_dir: str,
                 as_identity: str) -> str:
    node = _node_by_title(cli, space_id, "", target_dir, as_identity)
    if not node:
        raise RuntimeError("wiki target node not found: %s" % target_dir)
    return str(node.get("node_token", ""))


def _entry(source: str) -> dict[str, str]:
    return registry_lib.entry_by_source(source)


def _read_tokens(path: str) -> dict[str, str]:
    return publish_tokens.read_publish_tokens(path)


def _repo_name() -> str:
    proc = subprocess.run(
        ["git", "-C", registry_lib.ROOT, "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    url = proc.stdout.strip() if proc.returncode == 0 else ""
    for prefix in ("https://github.com/", "git@github.com:"):
        if url.startswith(prefix):
            return url[len(prefix):].removesuffix(".git")
    return "wsolarq11/SOP-SEC-2026-001"


def _sync_ci_secret() -> None:
    path = os.path.join(registry_lib.ROOT, ".publish-tokens")
    with open(path, "rb") as f:
        payload = f.read()
    encoded = base64.b64encode(payload).decode("ascii")
    proc = subprocess.run(
        ["gh", "secret", "set", "PUBLISH_TOKENS_B64", "--repo", _repo_name()],
        input=encoded,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        raise RuntimeError("GitHub secret sync failed: %s"
                           % proc.stderr.strip())


def _update_tokens(path: str, source: str, token: str) -> None:
    publish_tokens.write_publish_token(path, source, token)


def _exclude_backup_token(source: str, token: str) -> str:
    backup_prefix = "BACKUP_"
    if not source.startswith(backup_prefix):
        return token
    return "NONE"


def _build_docx(source: str, pub: str) -> str:
    docxname = registry_lib.docx_output_name(source)
    output = os.path.join(pub, docxname)
    os.makedirs(pub, exist_ok=True)
    sop_to_docx_stdlib.build(os.path.join(registry_lib.ROOT, source), output)
    return output


def _upload_new(cli: str, parent_token: str, docx_path: str,
                as_identity: str) -> str:
    name = os.path.basename(docx_path)
    proc = subprocess.run(
        _command([cli, "drive", "+upload", "--file", "./" + name, "--wiki-token",
                  parent_token, "--as", as_identity, "--format", "json"]),
        cwd=os.path.dirname(docx_path) or ".",
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        raise RuntimeError("first upload failed: %s\n%s"
                           % (proc.stderr.strip(), proc.stdout.strip()))
    payload = lark_json.parse_json(proc.stdout)
    token = lark_json.file_token(payload)
    if not token:
        raise RuntimeError("first upload returned no file_token: %s"
                           % lark_json.message_text(payload))
    return token


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="bootstrap a missing docx token")
    parser.add_argument("--source", required=True)
    parser.add_argument("--space-id", default="")
    parser.add_argument("--as", dest="as_identity", default="user")
    parser.add_argument("--pub", default="")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--sync-secret", action="store_true",
                        help="also sync PUBLISH_TOKENS_B64 to GitHub Actions")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    entry = _entry(args.source)
    target_dir = entry.get("target_dir", "")
    if not target_dir:
        print("[FAIL] registry entry has no target_dir: %s" % args.source,
              file=sys.stderr)
        return 1
    tokens_path = os.path.join(registry_lib.ROOT, ".publish-tokens")
    tokens = _read_tokens(tokens_path)
    if tokens.get(args.source) and tokens[args.source] != "NONE":
        print("[OK] token 已存在: %s" % args.source)
        if args.sync_secret:
            _sync_ci_secret()
            print("[OK] GitHub Actions secret 已同步")
        return 0

    cli = "lark-cli"
    try:
        space_id = args.space_id or _space_id(cli, args.as_identity)
        parent = _target_node(cli, space_id, target_dir, args.as_identity)
        existing = _node_by_title(cli, space_id, parent,
                                  registry_lib.docx_output_name(args.source),
                                  args.as_identity)
        if existing:
            token = str(existing.get("obj_token", ""))
            if not token:
                raise RuntimeError("existing wiki file has no obj_token")
            print("[OK] 复用已存在节点: %s" % registry_lib.docx_output_name(args.source))
            if args.dry_run:
                print("[DRY] 将登记已有 file token，不写入")
                return 0
        else:
            if args.dry_run:
                print("[DRY] 将首次上传到 wiki node %s" % parent)
                return 0
            base = args.pub or os.environ.get("PUB") or os.path.join(
                os.environ.get("TEMP") or os.environ.get("TMP") or "/tmp",
                "sop-exports", "publish")
            docx_path = _build_docx(args.source, base)
            token = _upload_new(cli, parent, docx_path, args.as_identity)
            print("[OK] 首次上传并登记 token: %s" % args.source)
        token = _exclude_backup_token(args.source, token)
        _update_tokens(tokens_path, args.source, token)
        if args.sync_secret:
            _sync_ci_secret()
            print("[OK] GitHub Actions secret 已同步")
        return 0
    except Exception as exc:
        print("[FAIL] %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
