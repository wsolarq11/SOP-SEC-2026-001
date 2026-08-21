#!/usr/bin/env python3
"""Root entrypoint for the SOP publishing toolchain.

Usage:
  python tools/kb.py check [dir ...]
  python tools/kb.py secrets --all|--staged
  python tools/kb.py manifest
  python tools/kb.py registry-render [--write|--check]
  python tools/kb.py build <input.md> <output.docx>
  python tools/kb.py publish [--dry-run] [target]
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

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TOOLS = HERE


def find_bash():
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


def run(args):
    return subprocess.run(args, cwd=ROOT).returncode


def usage():
    print(__doc__.strip())
    return 2


def main(argv):
    if not argv:
        return usage()
    cmd, rest = argv[0], argv[1:]
    py = sys.executable

    if cmd == "stage":
        print(TOOLS)
        return 0
    if cmd == "check":
        return run([py, os.path.join(TOOLS, "check_docs.py")] + rest)
    if cmd == "secrets":
        return run([py, os.path.join(TOOLS, "check_secrets.py")] + rest)
    if cmd == "manifest":
        return run([py, os.path.join(TOOLS, "registry_manifest.py")])
    if cmd == "registry-render":
        return run([py, os.path.join(TOOLS, "registry_render.py")] + rest)
    if cmd == "cleanup":
        return run([py, os.path.join(TOOLS, "cleanup_90_md.py")] + rest)
    if cmd == "build":
        if len(rest) < 2:
            return usage()
        return run([py, os.path.join(TOOLS, "sop_to_docx_stdlib.py")] + rest)
    if cmd == "test":
        return run([py, os.path.join(TOOLS, "test_pipeline.py")] + rest)

    bash = find_bash()
    if bash is None:
        return 2
    if cmd == "publish":
        return run([bash, os.path.join(TOOLS, "publish.sh")] + rest)
    if cmd == "backup":
        return run([bash, os.path.join(TOOLS, "backup_commit.sh")] + rest)
    if cmd == "auth":
        return run([bash, os.path.join(TOOLS, "check_git_auth.sh")] + rest)

    print("unknown command: %s" % cmd, file=sys.stderr)
    return usage()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
