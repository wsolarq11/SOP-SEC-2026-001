"""test_check_secrets.py - check_secrets.py 回归测试

在真实仓库 staged 区注入运行时拼接的假 token，验证扫描器必须拦截；
清理后验证全量扫描放行。不会把真实或可复现 token 写进源码。
"""
from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Sequence

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SCRIPT_DIR)
SCANNER = os.path.join(SCRIPT_DIR, "check_secrets.py")
FAKE = os.path.join(ROOT, "secret-test.tmp")
FAKE_TOKEN = "ghp_" + ("A" * 24)


def git(args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", ROOT] + list(args),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def cleanup() -> None:
    git(["reset", "-q", "--", "secret-test.tmp"])
    if os.path.exists(FAKE):
        os.remove(FAKE)


def run_scanner(staged: bool) -> subprocess.CompletedProcess[str]:
    args = [sys.executable, SCANNER, "--staged" if staged else "--all"]
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )


def _stage_fake_token() -> int:
    with open(FAKE, "w", encoding="utf-8") as f:
        f.write("fake=%s\n" % FAKE_TOKEN)
    add_result = git(["add", "secret-test.tmp"])
    if add_result.returncode != 0:
        print("FAIL: git add 失败")
        return 1
    scan_result = run_scanner(True)
    if scan_result.returncode == 0:
        print("FAIL: staged 假 token 未被拦截")
        return 1
    print("OK: staged 假 token 被拦截")
    return 0


def _verify_clean_scan() -> int:
    scan_result = run_scanner(False)
    if scan_result.returncode != 0:
        print("FAIL: 清理后全量扫描未通过")
        return 1
    print("OK: 清理后全量扫描通过")
    return 0


def main() -> int:
    try:
        staged_rc = _stage_fake_token()
    finally:
        cleanup()
    if staged_rc != 0:
        return staged_rc
    return _verify_clean_scan()


if __name__ == "__main__":
    sys.exit(main())
