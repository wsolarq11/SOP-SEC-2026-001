"""cleanup_90_md.py - 清理飞书 90 目录中散装 md 源文件。

背景：md 源已由 git 跟踪，并随 backup_commit.sh 的完整 git bundle 备份，
不再单独上传到 90 目录。本脚本用于列出 90 目录（Wiki 节点）中的 md
文件、生成审计清单，并在 --yes 确认后删除云端节点。

用法：
  python cleanup_90_md.py --wiki-token <node_token> --dry-run
  python cleanup_90_md.py --wiki-token <node_token> --yes
  python cleanup_90_md.py --folder-token <folder_token> --dry-run
  python cleanup_90_md.py --folder-token <folder_token> --yes

token 来源：命令行优先；否则读取 .publish-tokens 的 BACKUP_WIKI / BACKUP_FOLDER。
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
TOKEN_FILE = ROOT / ".publish-tokens"
TEMP = Path(os.environ.get("TEMP", os.environ.get("TMP", "/tmp")))
ARCHIVE_DIR = Path(os.environ.get("ARCHIVE_DIR", TEMP / "sop-exports" / "archive"))


def die(msg: str) -> None:
    print(f"[FAIL] {msg}", file=sys.stderr)
    sys.exit(1)


def run_lark(args: list[str]) -> dict:
    cmd = "lark-cli " + subprocess.list2cmdline(args)
    proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, encoding="utf-8")
    if proc.returncode != 0:
        die(f"lark-cli 失败: {cmd}\n{proc.stderr.strip()}")
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        die(f"lark-cli 输出不是 JSON:\n{proc.stdout}")
    if not data.get("ok", False):
        die(f"lark-cli 返回失败:\n{proc.stdout}")
    return data


def read_target_tokens() -> tuple[str, str]:
    wiki = ""
    folder = ""
    if not TOKEN_FILE.is_file():
        return wiki, folder
    for raw in TOKEN_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, _, rest = line.partition("|")
        value = rest.split("|", 1)[0].strip()
        if key == "BACKUP_WIKI":
            wiki = value
        elif key == "BACKUP_FOLDER":
            folder = value
    return wiki, folder


def resolve_space_id(wiki_token: str) -> str:
    data = run_lark(["wiki", "+node-get", "--node-token", wiki_token, "--format", "json"])
    node = data.get("data", {})
    space_id = str(node.get("space_id", ""))
    if not space_id:
        die("无法从 wiki 节点解析 space_id")
    return space_id


def list_wiki_md(wiki_token: str, space_id: str) -> list[dict]:
    data = run_lark([
        "wiki", "nodes", "list",
        "--space-id", space_id,
        "--parent-node-token", wiki_token,
        "--page-all",
        "--format", "json",
    ])
    items = data.get("data", {}).get("items", [])
    return [f for f in items if str(f.get("title", "")).lower().endswith(".md")]


def delete_wiki_file(node_token: str, space_id: str) -> bool:
    data = run_lark([
        "wiki", "+node-delete",
        "--node-token", node_token,
        "--obj-type", "wiki",
        "--space-id", space_id,
        "--yes",
        "--format", "json",
    ])
    return data.get("ok", False)


def list_folder_md(folder_token: str) -> list[dict]:
    data = run_lark([
        "drive", "files", "list",
        "--folder-token", folder_token,
        "--format", "json",
        "--page-all",
    ])
    files = data.get("data", {}).get("files", [])
    return [f for f in files if str(f.get("name", "")).lower().endswith(".md")]


def delete_drive_file(token: str) -> bool:
    data = run_lark([
        "drive", "+delete",
        "--file-token", token,
        "--type", "file",
        "--yes",
        "--format", "json",
    ])
    return data.get("ok", False)


def main() -> int:
    parser = argparse.ArgumentParser(description="清理飞书 90 目录中的散装 md 源文件")
    parser.add_argument("--wiki-token", help="90 目录 wiki node token")
    parser.add_argument("--space-id", help="wiki space ID；省略时自动解析")
    parser.add_argument("--folder-token", help="Drive 文件夹 token（旧模式）")
    parser.add_argument("--dry-run", action="store_true", help="只列出待删文件，不执行删除")
    parser.add_argument("--yes", action="store_true", help="确认执行删除（高风险操作）")
    parser.add_argument("--output", help="审计 TSV 输出路径")
    args = parser.parse_args()
    if args.dry_run and args.yes:
        parser.error("--dry-run 与 --yes 不能同时使用")

    saved_wiki, saved_folder = read_target_tokens()
    wiki_token = args.wiki_token or saved_wiki
    folder_token = args.folder_token or saved_folder
    if not wiki_token and not folder_token:
        die("未提供 90 目录 token；请用 --wiki-token，或用 --folder-token，或先运行 backup_commit.sh --init")

    is_wiki = bool(wiki_token)
    print(f"== 列出 {'wiki 节点' if is_wiki else 'Drive 文件夹'}内容 ==")

    if is_wiki:
        space_id = args.space_id or resolve_space_id(wiki_token)
        md_files = list_wiki_md(wiki_token, space_id)

        def delete_func(f: dict) -> bool:
            return delete_wiki_file(str(f.get("node_token", "")), space_id)
    else:
        md_files = list_folder_md(folder_token)

        def delete_func(f: dict) -> bool:
            return delete_drive_file(str(f.get("token", "")))

    print(f"共找到 {len(md_files)} 个 md 文件")
    for f in md_files:
        name = f.get("title") or f.get("name")
        token = f.get("node_token") or f.get("token")
        print(f"  {name}\t{token}")

    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    tsv_path = Path(args.output) if args.output else ARCHIVE_DIR / f"90-md-{stamp}.tsv"

    if not md_files:
        print("90 目录没有 md 文件，无需清理")
        return 0

    if args.dry_run:
        with tsv_path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh, delimiter="\t")
            writer.writerow(["name", "token", "type", "status"])
            for f in md_files:
                writer.writerow([
                    f.get("title") or f.get("name"),
                    f.get("node_token") or f.get("token"),
                    f.get("obj_type") or f.get("type"),
                    "dry-run",
                ])
        print(f"dry-run：以上 {len(md_files)} 个 md 会被删除；审计清单: {tsv_path}")
        print("确认后执行: python cleanup_90_md.py --wiki-token <token> --yes")
        return 0

    print(f"== 删除 {len(md_files)} 个 md（--yes 已确认）==")
    results: list[tuple[str, str, str]] = []
    failed = 0
    for f in md_files:
        name = str(f.get("title") or f.get("name") or "")
        token = str(f.get("node_token") or f.get("token") or "")
        if not token:
            print(f"  [SKIP] {name}: 缺少 token")
            results.append((name, "", "skip"))
            failed += 1
            continue
        ok = delete_func(f)
        results.append((name, token, "deleted" if ok else "failed"))
        if ok:
            print(f"  [OK] {name}")
        else:
            print(f"  [FAIL] {name}")
            failed += 1

    with tsv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, delimiter="\t")
        writer.writerow(["name", "token", "status"])
        for row in results:
            writer.writerow(row)

    print(f"完成：删除 {len(md_files) - failed}/{len(md_files)}；审计清单: {tsv_path}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
