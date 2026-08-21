"""test_check_secrets.py - check_secrets.py 回归测试

在真实仓库 staged 区注入运行时拼接的假 token，验证扫描器必须拦截；
清理后验证全量扫描放行。不会把真实或可复现 token 写进源码。
"""
import os
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(SCRIPT_DIR)))
SCANNER = os.path.join(SCRIPT_DIR, "check_secrets.py")
FAKE = os.path.join(ROOT, "secret-test.tmp")
FAKE_TOKEN = "ghp_" + ("A" * 24)


def git(args):
    return subprocess.run(
        ["git", "-C", ROOT] + args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def cleanup():
    git(["reset", "-q", "--", "secret-test.tmp"])
    if os.path.exists(FAKE):
        os.remove(FAKE)


def run_scanner(staged):
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


def main():
    try:
        with open(FAKE, "w", encoding="utf-8") as f:
            f.write("fake=%s\n" % FAKE_TOKEN)
        r = git(["add", "secret-test.tmp"])
        if r.returncode != 0:
            print("FAIL: git add 失败")
            return 1
        r = run_scanner(True)
        if r.returncode == 0:
            print("FAIL: staged 假 token 未被拦截")
            return 1
        print("OK: staged 假 token 被拦截")
    finally:
        cleanup()

    r = run_scanner(False)
    if r.returncode != 0:
        print("FAIL: 清理后全量扫描未通过")
        return 1
    print("OK: 清理后全量扫描通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
