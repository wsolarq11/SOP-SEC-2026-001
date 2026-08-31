"""publish_tokens.py - canonical reader/writer for .publish-tokens.

The <key>|<flag>|<token> line file is the single source of upload/backup
tokens shared by the whole publish pipeline. Every consumer reads/writes it
through this module so the contract (and its quirk below) has one home.

Format quirk: the effective token sits in a key-dependent field.
- Document keys store the token after the '|NONE|' separator field:
    sop/SOP-SEC-2026-001.md|NONE|<docx file_token>
- BACKUP_* keys store the token in the first field after the key:
    BACKUP_BUNDLE|<bundle file_token>|NONE
read_publish_tokens() hides this asymmetry by returning the effective token
per key.
"""
from __future__ import annotations

import os
from typing import IO

TOKENS_REL = ".publish-tokens"
BACKUP_PREFIX = "BACKUP_"


def tokens_path(repo_root: str) -> str:
    return os.path.join(repo_root, TOKENS_REL)


def read_publish_tokens(path: str) -> dict[str, str]:
    """Return {key: effective_token}; an absent file yields an empty dict."""
    result: dict[str, str] = {}
    if not os.path.isfile(path):
        return result
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            fields = line.split("|")
            key = fields[0]
            if not key:
                continue
            if key.startswith(BACKUP_PREFIX):
                result[key] = fields[1] if len(fields) > 1 else ""
            elif len(fields) >= 3:
                result[key] = fields[2]
    return result


def _doc_token_line(key: str, token: str) -> str:
    return "%s|NONE|%s\n" % (key, token)


def write_publish_token(path: str, key: str, token: str) -> None:
    """Write/upsert a document token line, preserving comments and other lines.

    BACKUP_* keys are never written here; the backup pipeline owns them (and
    token_bootstrap guards against touching them via _exclude_backup_token).
    """
    lines: list[str] = []
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines(keepends=True)
    output: list[str] = []
    replaced = False
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            # preserve blank/comment lines instead of dropping them
            output.append(line)
            continue
        fields = stripped.split("|")
        if fields and fields[0] == key:
            output.append(_doc_token_line(key, token))
            replaced = True
            continue
        output.append(line)
    if not replaced:
        output.append(_doc_token_line(key, token))
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("".join(output))