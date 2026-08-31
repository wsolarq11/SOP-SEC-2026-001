#!/usr/bin/env bash
# =============================================================
# ship — 一键总控：同步 + 校验 + 测试 + 发布 + git 提交推送
#
# 牵一发而动全身：任意一步失败立刻整体停止（set -euo pipefail）。
# 幂等：发布为同名覆盖，token 不变；git 仅在内容变更时提交。
#
# 用法:
#   bash ship.sh               # 完整管线（含真实发布 + git push）
#   bash ship.sh --dry-run     # 只校验，不发布、不 push
#   bash ship.sh --bootstrap   # 发布前自动对缺 token 文档首次上传登记
#
# 顺序:
#   1 registry-render --write  同步 front matter / REGISTRY
#   2 kb.py check              健康契约（失败即停）
#   3 kb.py test               测试套件（失败即停）
#   4 kb.py publish            构建 + 上传飞书（同 publish.sh，失败即停）
#   5 git add/commit/push      提交并推送源文件与 registry
# =============================================================
set -euo pipefail
export PYTHONIOENCODING="${PYTHONIOENCODING:-utf-8}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if command -v cygpath >/dev/null 2>&1; then
  SCRIPT_DIR="$(cd "$SCRIPT_DIR" && cygpath -w "$PWD")"
fi
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
if command -v cygpath >/dev/null 2>&1; then
  ROOT="$(cd "$ROOT" && cygpath -w "$PWD")"
fi
PY="${PY:-python}"

DRY=0
BOOTSTRAP=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY=1 ;;
    --bootstrap) BOOTSTRAP=1 ;;
    *) echo "未知参数: $arg" >&2; exit 2 ;;
  esac
done

cd "$ROOT"

echo "== [1/5] 同步 front matter / REGISTRY =="
"$PY" tools/kb.py registry-render --write

echo "== [2/5] 健康检查 =="
"$PY" tools/kb.py check

echo "== [3/5] 测试套件 =="
if ! "$PY" tools/kb.py test; then
  echo "测试失败，中止 ship" >&2
  exit 1
fi

echo "== [4/5] 发布（构建 + 上传飞书）=="
if [ "$DRY" = "1" ]; then
  if ! "$PY" tools/kb.py publish --dry-run; then
    echo "发布校验失败，中止 ship（未实际推送/上传）" >&2
    exit 1
  fi
  echo "== [dry-run] 全部校验通过，未上传、未推送 =="
  exit 0
fi

BOOT_ARGS=()
[ "$BOOTSTRAP" = "1" ] && BOOT_ARGS=(--bootstrap)
if ! "$PY" tools/kb.py publish "${BOOT_ARGS[@]}"; then
  echo "发布失败，中止 ship，未推 git" >&2
  exit 1
fi

echo "== [5/5] git 提交并推送 =="
git add -A
if git diff --cached --quiet; then
  echo "无改动可提交，跳过 commit/push"
else
  MSG="${SHIP_MSG:-docs: 同步发布（ship）}"
  if ! git commit -m "$MSG"; then
    echo "git commit 失败，中止" >&2
    exit 1
  fi
  if ! git push; then
    echo "git push 失败（hooks/网络），请检查后重跑" >&2
    exit 1
  fi
fi

echo "== ship: 全部完成 =="