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
from collections.abc import Callable, Sequence
from pathlib import Path

import publish_tokens

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


def run_lark(args: list[str]) -> dict[str, object]:
    cmd = "lark-cli " + subprocess.list2cmdline(args)
    proc = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                          encoding="utf-8")
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
    tokens = publish_tokens.read_publish_tokens(str(TOKEN_FILE))
    wiki = tokens.get("BACKUP_WIKI", "")
    folder = tokens.get("BACKUP_FOLDER", "")
    return wiki, folder


def resolve_space_id(wiki_token: str) -> str:
    data = run_lark(["wiki", "+node-get", "--node-token", wiki_token,
                     "--format", "json"])
    node = data.get("data", {})
    space_id = str(node.get("space_id", ""))
    if not space_id:
        die("无法从 wiki 节点解析 space_id")
    return space_id


def _md_items(items: object, name_key: str) -> list[dict[str, object]]:
    if not isinstance(items, list):
        return []
    result = []
    for item in items:
        if isinstance(item, dict) and str(item.get(name_key, "")).lower().endswith(".md"):
            result.append(item)
    return result


def list_wiki_md(wiki_token: str, space_id: str) -> list[dict[str, object]]:
    data = run_lark([
        "wiki", "nodes", "list",
        "--space-id", space_id,
        "--parent-node-token", wiki_token,
        "--page-all",
        "--format", "json",
    ])
    items = data.get("data", {})
    return _md_items(items.get("items", []) if isinstance(items, dict) else [], "title")


def delete_wiki_file(node_token: str, space_id: str) -> bool:
    data = run_lark([
        "wiki", "+node-delete",
        "--node-token", node_token,
        "--obj-type", "wiki",
        "--space-id", space_id,
        "--yes",
        "--format", "json",
    ])
    return bool(data.get("ok", False))


def list_folder_md(folder_token: str) -> list[dict[str, object]]:
    data = run_lark([
        "drive", "files", "list",
        "--folder-token", folder_token,
        "--format", "json",
        "--page-all",
    ])
    files = data.get("data", {})
    return _md_items(files.get("files", []) if isinstance(files, dict) else [], "name")


def delete_drive_file(token: str) -> bool:
    data = run_lark([
        "drive", "+delete",
        "--file-token", token,
        "--type", "file",
        "--yes",
        "--format", "json",
    ])
    return bool(data.get("ok", False))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="清理飞书 90 目录中的散装 md 源文件")
    parser.add_argument("--wiki-token", help="90 目录 wiki node token")
    parser.add_argument("--space-id", help="wiki space ID；省略时自动解析")
    parser.add_argument("--folder-token", help="Drive 文件夹 token（旧模式）")
    parser.add_argument("--dry-run", action="store_true", help="只列出待删文件，不执行删除")
    parser.add_argument("--yes", action="store_true", help="确认执行删除（高风险操作）")
    parser.add_argument("--output", help="审计 TSV 输出路径")
    return parser


def _resolve_targets(args: argparse.Namespace) -> tuple[str, str]:
    saved_wiki, saved_folder = read_target_tokens()
    wiki_token = args.wiki_token or saved_wiki
    folder_token = args.folder_token or saved_folder
    if not wiki_token and not folder_token:
        die("未提供 90 目录 token；请用 --wiki-token，或用 --folder-token，或先运行 backup_commit.sh --init")
    return wiki_token, folder_token


def _md_manifest(is_wiki: bool, wiki_token: str, folder_token: str,
                 args: argparse.Namespace) -> tuple[list[dict[str, object]],
                                                    Callable[[dict[str, object]], bool]]:
    if is_wiki:
        space_id = args.space_id or resolve_space_id(wiki_token)
        files = list_wiki_md(wiki_token, space_id)
        delete_func: Callable[[dict[str, object]], bool] = (
            lambda f: delete_wiki_file(str(f.get("node_token", "")), space_id)
        )
        return files, delete_func
    files = list_folder_md(folder_token)
    delete_func = lambda f: delete_drive_file(str(f.get("token", "")))
    return files, delete_func


def _print_md_manifest(files: Sequence[dict[str, object]]) -> None:
    for f in files:
        name = f.get("title") or f.get("name")
        token = f.get("node_token") or f.get("token")
        print(f"  {name}\t{token}")


def _write_dry_run_audit(tsv_path: Path,
                         files: Sequence[dict[str, object]]) -> None:
    with tsv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, delimiter="\t")
        writer.writerow(["name", "token", "type", "status"])
        for f in files:
            writer.writerow([
                f.get("title") or f.get("name"),
                f.get("node_token") or f.get("token"),
                f.get("obj_type") or f.get("type"),
                "dry-run",
            ])


def _write_results(tsv_path: Path,
                   results: Sequence[tuple[str, str, str]]) -> None:
    with tsv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, delimiter="\t")
        writer.writerow(["name", "token", "status"])
        for row in results:
            writer.writerow(row)


def _delete_one_file(file_item: dict[str, object],
                     delete_func: Callable[[dict[str, object]], bool]
                     ) -> tuple[tuple[str, str, str], bool]:
    name = str(file_item.get("title") or file_item.get("name") or "")
    token = str(file_item.get("node_token") or file_item.get("token") or "")
    if not token:
        print(f"  [SKIP] {name}: 缺少 token")
        return (name, "", "skip"), True
    ok = delete_func(file_item)
    if ok:
        print(f"  [OK] {name}")
        return (name, token, "deleted"), False
    print(f"  [FAIL] {name}")
    return (name, token, "failed"), True


def _delete_md_files(files: Sequence[dict[str, object]],
                     delete_func: Callable[[dict[str, object]], bool],
                     tsv_path: Path) -> int:
    results: list[tuple[str, str, str]] = []
    failed = 0
    for file_item in files:
        result, failed_this = _delete_one_file(file_item, delete_func)
        results.append(result)
        failed += int(failed_this)
    _write_results(tsv_path, results)
    print(f"完成：删除 {len(files) - failed}/{len(files)}；审计清单: {tsv_path}")
    return 1 if failed else 0


def _run_cleanup(args: argparse.Namespace, files: Sequence[dict[str, object]],
                 delete_func: Callable[[dict[str, object]], bool]) -> int:
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    tsv_path = Path(args.output) if args.output else ARCHIVE_DIR / f"90-md-{stamp}.tsv"
    if not files:
        print("90 目录没有 md 文件，无需清理")
        return 0
    if args.dry_run:
        _write_dry_run_audit(tsv_path, files)
        print(f"dry-run：以上 {len(files)} 个 md 会被删除；审计清单: {tsv_path}")
        print("确认后执行: python cleanup_90_md.py --wiki-token <token> --yes")
        return 0
    print(f"== 删除 {len(files)} 个 md（--yes 已确认）==")
    return _delete_md_files(files, delete_func, tsv_path)


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    if args.dry_run and args.yes:
        parser.error("--dry-run 与 --yes 不能同时使用")
    wiki_token, folder_token = _resolve_targets(args)
    is_wiki = bool(wiki_token)
    print(f"== 列出 {'wiki 节点' if is_wiki else 'Drive 文件夹'}内容 ==")
    md_files, delete_func = _md_manifest(is_wiki, wiki_token, folder_token, args)
    print(f"共找到 {len(md_files)} 个 md 文件")
    _print_md_manifest(md_files)
    return _run_cleanup(args, md_files, delete_func)


if __name__ == "__main__":
    sys.exit(main())
