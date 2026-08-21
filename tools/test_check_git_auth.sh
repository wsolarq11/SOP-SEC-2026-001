#!/usr/bin/env bash
# =============================================================
# check_git_auth.sh 回归测试
#
# 用临时 HOME / GIT_CONFIG_GLOBAL 验证守卫能拦截：
#   1. global url.*.insteadOf 内嵌 GitHub token
#   2. http.https://github.com/.extraheader
#   3. ~/.git-credentials 残留 GitHub 凭据
# 最后用当前真实 gh 登录态跑一次干净检查。
# =============================================================
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -W)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd -W)"
SCRIPT="$SCRIPT_DIR/check_git_auth.sh"
TMP="$(mktemp -d)"
HOME_TMP="$TMP/home"
GLOBAL_TMP="$TMP/global"
mkdir -p "$HOME_TMP"
: > "$GLOBAL_TMP"

cleanup() {
  rm -rf "$TMP"
}
trap cleanup EXIT

export HOME="$HOME_TMP"
export GIT_CONFIG_GLOBAL="$GLOBAL_TMP"

fail_test() {
  echo "❌ $*" >&2
  exit 1
}

expect_fail() {
  local desc="$1"; shift
  "$@" >/dev/null 2>&1
  local code=$?
  if [ "$code" = 0 ]; then
    fail_test "守卫未拦截: $desc"
  fi
  echo "✅ 守卫拦截: $desc"
}

git config --global "url.https://user:ghp_bad@github.com/.insteadof" "https://github.com/"
expect_fail "insteadOf 内嵌 token" bash "$SCRIPT"
git config --global --unset-all "url.https://user:ghp_bad@github.com/.insteadof"

git config --global "http.https://github.com/.extraheader" "AUTHORIZATION: basic dGVzdA=="
expect_fail "extraheader" bash "$SCRIPT"
git config --global --unset-all "http.https://github.com/.extraheader"

printf 'https://wsolarq11:ghp_bad@github.com\n' > "$HOME/.git-credentials"
expect_fail "~/.git-credentials 残留" bash "$SCRIPT"
rm -f "$HOME/.git-credentials"

bash "$SCRIPT" >/dev/null 2>&1 || fail_test "干净状态未通过"

echo "✅ 全部通过：check_git_auth.sh 可拦截旧凭据，干净状态放行"
