#!/usr/bin/env python3
"""Root entrypoint for the SOP publishing toolchain.

Usage:
  python tools/kb.py check [dir ...]
  python tools/kb.py secrets --all|--staged
  python tools/kb.py manifest
  python tools/kb.py registry-render [--write|--check]
  python tools/kb.py line [--doc <document_id>] [--json]
  python tools/kb.py fact link <document_id> <requirement_ref>
  python tools/kb.py fact review <document_id> <reviewer> <reviewed_at>
  python tools/kb.py fact signoff <document_id> <approver> <effective_date> [--reviewer ...] [--reviewed-at ...]
  python tools/kb.py fact sync <document_id>
  python tools/kb.py token-bootstrap --source <md> [--dry-run] [--sync-secret]
  python tools/kb.py build <input.md> <output.docx>
  python tools/kb.py publish [--dry-run] [--bootstrap] [target]
  python tools/kb.py ship [--dry-run] [--bootstrap]
  python tools/kb.py backup [args...]
  python tools/kb.py auth [--network] [--fix]
  python tools/kb.py cleanup [--dry-run|--yes]
  python tools/kb.py test
  python tools/kb.py stage
"""
import os
import shutil
import subprocess
import sys
from collections.abc import Sequence

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TOOLS = HERE

_PYTHON_SCRIPTS = {
    "check": "check_docs.py",
    "secrets": "check_secrets.py",
    "manifest": "registry_manifest.py",
    "registry-render": "registry_render.py",
    "cleanup": "cleanup_90_md.py",
    "line": "line_report.py",
    "fact": "fact_ops.py",
    "token-bootstrap": "token_bootstrap.py",
}

_SHELL_SCRIPTS = {
    "publish": "publish.sh",
    "ship": "ship.sh",
    "backup": "backup_commit.sh",
    "auth": "check_git_auth.sh",
}


def find_bash() -> str | None:
    exe = shutil.which("bash")
    if exe:
        return exe
    candidates = (
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files\Git\usr\bin\bash.exe",
        "/usr/bin/bash",
    )
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    print("bash not found; install Git Bash or set PATH", file=sys.stderr)
    return None


def run(args: Sequence[str]) -> int:
    return subprocess.run(args, cwd=ROOT).returncode


def run_test_suite(rest: Sequence[str]) -> int:
    for name in ("test_pipeline.py", "test_check_secrets.py"):
        rc = run([sys.executable, os.path.join(TOOLS, name)] + list(rest))
        if rc != 0:
            return rc
    bash = find_bash()
    if bash is None:
        return 2
    return run([bash, os.path.join(TOOLS, "test_check_git_auth.sh")])


def run_python_script(cmd: str, rest: Sequence[str]) -> int | None:
    if cmd == "test":
        return run_test_suite(rest)
    if cmd == "build":
        if len(rest) < 2:
            return None
        return run([sys.executable,
                    os.path.join(TOOLS, "sop_to_docx_stdlib.py")] + list(rest))
    script = _PYTHON_SCRIPTS.get(cmd)
    if script is None:
        return None
    return run([sys.executable, os.path.join(TOOLS, script)] + list(rest))


def run_shell_script(cmd: str, rest: Sequence[str]) -> int | None:
    script = _SHELL_SCRIPTS.get(cmd)
    if script is None:
        return None
    bash = find_bash()
    if bash is None:
        return 2
    return run([bash, os.path.join(TOOLS, script)] + list(rest))


def main(argv: list[str]) -> int:
    if not argv:
        return usage()
    cmd, rest = argv[0], argv[1:]
    if cmd == "stage":
        print(TOOLS)
        return 0
    if cmd == "build" and len(rest) < 2:
        return usage()
    rc = run_python_script(cmd, rest)
    if rc is not None:
        return rc
    rc = run_shell_script(cmd, rest)
    if rc is not None:
        return rc
    print("unknown command: %s" % cmd, file=sys.stderr)
    return usage()


def usage() -> int:
    print(__doc__.strip())
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
