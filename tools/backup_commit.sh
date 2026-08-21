#!/usr/bin/env bash
# =============================================================
# git 仓库备份：与 GitHub remote 互补的飞书云端 bundle（无远端服务器时的“git push”等价物）
#
# post-commit / pre-push hook 在本地 commit / push 时调用：
#   git bundle create --all HEAD  ->  %TEMP%\sop-exports\backup\*.bundle
#   lark-cli drive +upload        ->  飞书云盘同名覆盖
# GitHub 与飞书 bundle 为主副双备份；默认 hard 模式两者都必须成功，hook 失败会让 git 命令显式失败。
# KB_BACKUP_MODE=soft 时备份失败不阻断；KB_BACKUP_MODE=skip 时跳过备份（本地开发/临时故障用）。
#
# bundle 包含全部已提交历史与分支，可用 git clone <file> 恢复。
# 不包含工作区未提交改动，也不包含 .publish-tokens（gitignore 忽略）。
#
# 上传 token 登记在 ${ROOT}/.publish-tokens（gitignore 忽略，不入库）：
#   BACKUP_BUNDLE|<bundle file_token>|NONE
#   BACKUP_FOLDER|<90 目录 folder_token>|NONE
#   BACKUP_WIKI|<90 目录 wiki node_token>|NONE
# bundle 首次上传到 BACKUP_FOLDER/BACKUP_WIKI 指向的 90 目录，之后同名覆盖。
#
# 用法：
#   bash backup_commit.sh --install
#   bash backup_commit.sh --init [--folder-token <token>|--wiki-token <token>]
#   bash backup_commit.sh --dry-run
#   bash backup_commit.sh
#   bash backup_commit.sh --uninstall
# =============================================================
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -W)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd -W)"
PY="${PY:-python}"
LARK_JSON="$SCRIPT_DIR/lark_json.py"
if [ -z "${PUB:-}" ]; then
  _TEMP="${TEMP:-${TMP:-/tmp}}"
  PUB="${_TEMP//\\//}/sop-exports/publish"
fi
BACKUP_DIR="${BACKUP_DIR:-$(dirname "$PUB")/backup}"
TOKEN_FILE="$ROOT/.publish-tokens"
LOG="$ROOT/.git/backup-commit.log"
NAME="${BACKUP_NAME:-$(basename "$ROOT").bundle}"
BACKUP_MODE="${KB_BACKUP_MODE:-hard}"

INSTALL=0
UNINSTALL=0
INIT=0
DRY=0
FOLDER_TOKEN=""
SAVED_FOLDER_TOKEN=""
WIKI_TOKEN=""
SAVED_WIKI_TOKEN=""

while [ "$#" -gt 0 ]; do
  case "$1" in
    --install) INSTALL=1; shift ;;
    --uninstall) UNINSTALL=1; shift ;;
    --init) INIT=1; shift ;;
    --dry-run) DRY=1; shift ;;
    --folder-token) FOLDER_TOKEN="${2:-}"; [ "$#" -ge 2 ] && shift 2 || shift ;;
    --wiki-token) WIKI_TOKEN="${2:-}"; [ "$#" -ge 2 ] && shift 2 || shift ;;
    --name) NAME="${2:-}"; [ "$#" -ge 2 ] && shift 2 || shift ;;
    --backup-dir) BACKUP_DIR="${2:-}"; [ "$#" -ge 2 ] && shift 2 || shift ;;
    *) echo "未知参数: $1" >&2; exit 2 ;;
  esac
done

mkdir -p "$ROOT/.git"

say() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" | tee -a "$LOG"
}

die() {
  say "错误: $*"
  if [ "$BACKUP_MODE" = "soft" ]; then
    return 1
  fi
  exit 1
}

soft_fail() {
  say "仓库备份失败（KB_BACKUP_MODE=soft，不阻断）"
  exit 0
}

if [ "$UNINSTALL" = 1 ]; then
  rm -f "$ROOT/.git/hooks/pre-commit" "$ROOT/.git/hooks/post-commit" "$ROOT/.git/hooks/pre-push"
  say "已移除 pre-commit / post-commit / pre-push hook"
  exit 0
fi

if [ "$INSTALL" = 1 ]; then
  HOOKS_DIR="$ROOT/.git/hooks"
  mkdir -p "$HOOKS_DIR"
  for HOOK_NAME in pre-commit post-commit pre-push; do
    HOOK="$HOOKS_DIR/$HOOK_NAME"
    if [ "$HOOK_NAME" = "pre-commit" ]; then
      cat > "$HOOK" <<'HOOK_EOF'
#!/bin/sh
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
python "$ROOT/tools/kb.py" secrets --staged
HOOK_EOF
    elif [ "$HOOK_NAME" = "pre-push" ]; then
      cat > "$HOOK" <<'HOOK_EOF'
#!/bin/sh
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
python "$ROOT/tools/kb.py" secrets --all
python "$ROOT/tools/kb.py" auth --network
python "$ROOT/tools/kb.py" backup
HOOK_EOF
    else
      cat > "$HOOK" <<'HOOK_EOF'
#!/bin/sh
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
python "$ROOT/tools/kb.py" auth
python "$ROOT/tools/kb.py" backup
HOOK_EOF
    fi
    chmod +x "$HOOK"
    say "已安装 $HOOK_NAME hook: $HOOK"
  done
  exit 0
fi

if ! command -v lark-cli >/dev/null 2>&1; then
  die "未找到 lark-cli，请确认其已加入 PATH" || { [ "$BACKUP_MODE" = "soft" ] || exit 1; }
fi

read_backup_token() {
  TOKEN=""
  [ -f "$TOKEN_FILE" ] || return 0
  while IFS= read -r line; do
    line="${line%$'\r'}"
    case "$line" in
      \#*|"") continue ;;
    esac
    key="${line%%|*}"
    if [ "$key" = "BACKUP_BUNDLE" ]; then
      rest="${line#*|}"
      TOKEN="${rest%%|*}"
    elif [ "$key" = "BACKUP_FOLDER" ]; then
      rest="${line#*|}"
      SAVED_FOLDER_TOKEN="${rest%%|*}"
    elif [ "$key" = "BACKUP_WIKI" ]; then
      rest="${line#*|}"
      SAVED_WIKI_TOKEN="${rest%%|*}"
    fi
  done < "$TOKEN_FILE"
}

save_backup_token() {
  local new_token="$1" new_folder="${2:-}" new_wiki="${3:-}" tmp="$TOKEN_FILE.tmp" found_bundle=0 found_folder=0 found_wiki=0
  : > "$tmp"
  if [ -f "$TOKEN_FILE" ]; then
    while IFS= read -r line; do
      line="${line%$'\r'}"
      key="${line%%|*}"
      if [ "$key" = "BACKUP_BUNDLE" ]; then
        printf 'BACKUP_BUNDLE|%s|NONE\n' "$new_token"
        found_bundle=1
      elif [ "$key" = "BACKUP_FOLDER" ] && [ -n "$new_folder" ]; then
        printf 'BACKUP_FOLDER|%s|NONE\n' "$new_folder"
        found_folder=1
      elif [ "$key" = "BACKUP_WIKI" ] && [ -n "$new_wiki" ]; then
        printf 'BACKUP_WIKI|%s|NONE\n' "$new_wiki"
        found_wiki=1
      else
        printf '%s\n' "$line"
      fi
    done < "$TOKEN_FILE" >> "$tmp"
  fi
  if [ "$found_bundle" = 0 ]; then
    printf 'BACKUP_BUNDLE|%s|NONE\n' "$new_token" >> "$tmp"
  fi
  if [ -n "$new_folder" ] && [ "$found_folder" = 0 ]; then
    printf 'BACKUP_FOLDER|%s|NONE\n' "$new_folder" >> "$tmp"
  fi
  if [ -n "$new_wiki" ] && [ "$found_wiki" = 0 ]; then
    printf 'BACKUP_WIKI|%s|NONE\n' "$new_wiki" >> "$tmp"
  fi
  mv "$tmp" "$TOKEN_FILE"
}

build_bundle() {
  if ! git rev-parse --verify HEAD >/dev/null 2>&1; then
    say "仓库尚无提交，跳过备份"
    exit 0
  fi
  mkdir -p "$BACKUP_DIR"
  BUNDLE="$BACKUP_DIR/$NAME"
  say "构建 bundle: $BUNDLE"
  if ! out="$(git bundle create "$BUNDLE" --all HEAD 2>&1)"; then
    say "$out"
    die "git bundle 创建失败" || return 1
  fi
  if ! out="$(git bundle verify "$BUNDLE" 2>&1)"; then
    say "$out"
    die "git bundle 校验失败" || return 1
  fi
  SIZE="$(du -h "$BUNDLE" | cut -f1)"
  say "bundle 校验通过，大小 $SIZE"
}

upload_bundle() {
  local token="$1" out
  say "上传 bundle 到飞书云盘（同名覆盖）"
  out="$(cd "$BACKUP_DIR" && lark-cli drive +upload --file "./$NAME" --file-token "$token" --as user --format json 2>&1)"
  if ! printf '%s\n' "$out" | "$PY" "$LARK_JSON" ok; then
    say "lark-cli 输出:"
    say "$out"
    die "飞书上传失败" || return 1
  fi
  returned="$(printf '%s\n' "$out" | "$PY" "$LARK_JSON" token)" || returned=""
  if [ -z "$returned" ] || [ "$returned" != "$token" ]; then
    say "lark-cli 输出:"
    say "$out"
    die "上传返回 file_token 与登记不一致" || return 1
  fi
}

run_init() {
  if [ -n "$FOLDER_TOKEN" ] && [ -n "$WIKI_TOKEN" ]; then
    die "--folder-token 与 --wiki-token 不能同时使用" || return 1
  fi
  read_backup_token
  if [ -z "$FOLDER_TOKEN" ] && [ -n "$SAVED_FOLDER_TOKEN" ]; then
    FOLDER_TOKEN="$SAVED_FOLDER_TOKEN"
  fi
  if [ -z "$WIKI_TOKEN" ] && [ -n "$SAVED_WIKI_TOKEN" ]; then
    WIKI_TOKEN="$SAVED_WIKI_TOKEN"
  fi
  if [ -n "$TOKEN" ]; then
    say "BACKUP_BUNDLE token 已登记，按普通模式同名覆盖"
    build_bundle || return 1
    upload_bundle "$TOKEN" || return 1
    return 0
  fi
  build_bundle || return 1
  local out token
  say "首次上传 bundle 到飞书云盘并登记 token"
  if [ -n "$FOLDER_TOKEN" ]; then
    out="$(cd "$BACKUP_DIR" && lark-cli drive +upload --file "./$NAME" --folder-token "$FOLDER_TOKEN" --as user --format json 2>&1)"
  elif [ -n "$WIKI_TOKEN" ]; then
    out="$(cd "$BACKUP_DIR" && lark-cli drive +upload --file "./$NAME" --wiki-token "$WIKI_TOKEN" --as user --format json 2>&1)"
  else
    out="$(cd "$BACKUP_DIR" && lark-cli drive +upload --file "./$NAME" --as user --format json 2>&1)"
  fi
  if ! printf '%s\n' "$out" | "$PY" "$LARK_JSON" ok; then
    say "lark-cli 输出:"
    say "$out"
    die "首次上传失败" || return 1
  fi
  if ! token="$(printf '%s\n' "$out" | "$PY" "$LARK_JSON" token)"; then
    say "lark-cli 输出:"
    say "$out"
    die "未能从上传结果解析 file_token" || return 1
  fi
  save_backup_token "$token" "$FOLDER_TOKEN" "$WIKI_TOKEN"
  TOKEN="$token"
  say "已登记 BACKUP_BUNDLE token"
  upload_bundle "$TOKEN" || return 1
}

read_backup_token

if [ "$DRY" = 1 ]; then
  if [ "$BACKUP_MODE" = "skip" ]; then
    say "KB_BACKUP_MODE=skip：跳过 dry-run 备份构建"
    exit 0
  fi
  build_bundle || soft_fail
  if [ -n "$TOKEN" ]; then
    say "dry-run：将同名覆盖飞书云盘节点（token 已登记）"
  else
    say "dry-run：token 未登记，首次上传请先运行 --init"
  fi
  exit 0
fi

if [ "$BACKUP_MODE" = "skip" ] && [ "$INIT" = 0 ]; then
  say "KB_BACKUP_MODE=skip：跳过仓库备份"
  exit 0
fi

if [ "$INIT" = 1 ]; then
  run_init || soft_fail
else
  if [ -z "$TOKEN" ]; then
    die "未找到 BACKUP_BUNDLE token；请先运行 bash tools/backup_commit.sh --init" || soft_fail
  fi
  build_bundle || soft_fail
  upload_bundle "$TOKEN" || soft_fail
fi

HEAD="$(git rev-parse --short HEAD)"
say "仓库备份完成: HEAD=$HEAD file=$NAME"
