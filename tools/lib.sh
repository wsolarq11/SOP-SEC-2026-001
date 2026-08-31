#!/usr/bin/env bash
# =============================================================
# lib.sh — 各工具脚本共享的路径与环境初始化
#
# 用法（在被调用脚本顶部）：
#   SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
#   . "$SCRIPT_DIR/lib.sh"
#
# lib.sh 会基于调用链设置规范化的 SCRIPT_DIR 与 ROOT（仓库根），
# 并把 Windows cygpath 归一化的逻辑收敛到这一处。
# =============================================================
set -u

normalize_path() {
  local p="$1"
  if command -v cygpath >/dev/null 2>&1; then
    cygpath -w "$p"
  else
    printf '%s\n' "$p"
  fi
}

setup_paths() {
  # BASH_SOURCE[1] 是被调用方脚本（本文件为 source 目标）
  local caller="${BASH_SOURCE[1]}"
  SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$caller")" && pwd)"
  SCRIPT_DIR="$(normalize_path "$SCRIPT_DIR")"
  ROOT="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)"
  ROOT="$(normalize_path "$ROOT")"
}

default_pub() {
  # 返回默认发布目录；未设置 PUB 时基于 %TEMP% 推导
  local _temp="${TEMP:-${TMP:-/tmp}}"
  printf '%s\n' "${PUB:-${_temp//\\//}/sop-exports/publish}"
}

setup_paths