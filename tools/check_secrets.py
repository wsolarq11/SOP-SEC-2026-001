"""check_secrets.py - git 敏感信息扫描守卫

扫描 git 已跟踪文件 / staged 内容中的高置信 token、密码、私钥等模式，
用于 pre-commit、pre-push、publish.sh 和 CI 的同一道入口。

设计原则：
- 只输出“文件:行:类别”，绝不输出命中的 token 明文。
- 只做高置信模式，避免把文档里“token/password”字段名误判为泄漏。
- 只扫 git 已跟踪内容，不扫 .publish-tokens（本地受控 token 文件）。

用法：
  python check_secrets.py --all        # 扫描全部 git 已跟踪文件
  python check_secrets.py --staged     # 扫描当前 staged 文件
"""
import os
import re
import subprocess
import sys
from collections.abc import Sequence

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SCRIPT_DIR)

# Windows runner 默认 stdout 可能是 cp1252，中文报错会直接 UnicodeEncodeError。
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

SECRET_PATTERNS = [
    (r"\bghp_[A-Za-z0-9]{20,}\b", "GitHub PAT"),
    (r"\bgho_[A-Za-z0-9]{20,}\b", "GitHub OAuth token"),
    (r"\bgithub_pat_[A-Za-z0-9_]{20,}\b", "GitHub fine-grained PAT"),
    (r"\bglpat-[A-Za-z0-9_-]{20,}\b", "GitLab PAT"),
    (r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b", "Slack token"),
    (r"\bAKIA[0-9A-Z]{16}\b", "AWS access key"),
    (r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----", "private key"),
    (r"(?i)\b(?:client|app)[_-]?secret\s*[:=]\s*[\"']?[A-Za-z0-9_\-]{16,}",
     "client/app secret"),
    (r"(?i)\bapi[_-]?key\s*[:=]\s*[\"']?[A-Za-z0-9_\-]{16,}", "API key"),
    (r"(?i)\bpassword\s*[:=]\s*[\"'][^\s|\"'\\]{8,}[\"']",
     "password assignment"),
]

SENSITIVE_FILENAMES = {
    ".publish-tokens", ".env", ".env.local", "id_rsa", "id_ed25519",
    "credentials", "secrets.json",
}

SENSITIVE_FILENAME_RE = re.compile(r"\.(pem|key|p12|pfx)$", re.IGNORECASE)

# 文档/脚本里允许出现模式名，但不应出现真实 token。
EXCLUDE_PATH_RE = re.compile(
    r"(^|/)(\.git/|tools/check_secrets\.py$)",
    re.IGNORECASE,
)

COMPILED = [(re.compile(pattern), label) for pattern, label in SECRET_PATTERNS]


def git(args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", ROOT] + list(args),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def collect_paths(staged: bool) -> list[str]:
    if staged:
        result = git(["diff", "--cached", "--name-only", "--diff-filter=ACM"])
    else:
        result = git(["ls-files"])
    if result.returncode != 0:
        print(result.stderr.strip())
        sys.exit(2)
    return [p for p in result.stdout.splitlines() if p]


def sensitive_filename(path: str) -> bool:
    base = os.path.basename(path).lower()
    if base in {s.lower() for s in SENSITIVE_FILENAMES}:
        return True
    return bool(SENSITIVE_FILENAME_RE.search(base))


def _decode_content(data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1", errors="replace")


def _scan_lines(text: str) -> list[tuple[int, str]]:
    hits = []
    for line_no, line in enumerate(text.splitlines(), 1):
        for regex, label in COMPILED:
            if regex.search(line):
                hits.append((line_no, label))
                break
    return hits


def scan_file(path: str) -> list[tuple[int, str]]:
    abspath = os.path.join(ROOT, path)
    if not os.path.isfile(abspath):
        return []
    with open(abspath, "rb") as f:
        data = f.read()
    if b"\x00" in data[:8192]:
        return [(0, "sensitive filename (binary)")] if sensitive_filename(path) else []
    hits = []
    if sensitive_filename(path):
        hits.append((0, "sensitive filename"))
    hits.extend(_scan_lines(_decode_content(data)))
    return hits


def _print_hits(path: str, hits: Sequence[tuple[int | str, str]]) -> int:
    for line_no, label in hits:
        if line_no:
            print("[SECRET] %s:%d: %s" % (path, line_no, label))
        else:
            print("[SECRET] %s: %s" % (path, label))
    return len(hits)


def _parse_mode(argv: Sequence[str]) -> bool:
    if "--staged" in argv:
        return True
    if "--all" in argv:
        return False
    print(__doc__)
    sys.exit(2)


def _scan_paths(paths: Sequence[str]) -> int:
    issues = 0
    for path in paths:
        norm = path.replace(os.sep, "/")
        if EXCLUDE_PATH_RE.search(norm):
            continue
        try:
            hits = scan_file(norm)
        except OSError as exc:
            issues += 1
            print("[FAIL] %s: 无法读取文件: %s" % (norm, exc))
            continue
        issues += _print_hits(norm, hits)
    return issues


def main(argv: Sequence[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    staged = _parse_mode(args)
    paths = collect_paths(staged)
    issues = _scan_paths(paths)
    if issues:
        print("发现 %d 个疑似敏感信息，禁止提交/发布" % issues)
        return 1
    print("OK: 未发现高置信敏感信息" if paths else "OK: 无待扫描文件")
    return 0


if __name__ == "__main__":
    sys.exit(main())
