#!/usr/bin/env bash
# =============================================================
# check_git_auth.sh 回归测试
#
# 用临时 HOME / GIT_CONFIG_GLOBAL 验证守卫能拦截：
#   1. global url.*.insteadOf 内嵌 GitHub token
#   2. http.https://github.com/.extraheader
#   3. ~/.git-credentials 残留 GitHub 凭据
# 最后用 fake gh 模拟登录态，验证干净状态放行，不依赖本机 gh 配置。
# =============================================================
set -u

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
. "$SCRIPT_DIR/lib.sh"
SCRIPT="$SCRIPT_DIR/check_git_auth.sh"
TMP="$(mktemp -d)"
HOME_TMP="$TMP/home"
GLOBAL_TMP="$TMP/global"
FAKE_BIN="$TMP/bin"
mkdir -p "$HOME_TMP" "$FAKE_BIN"
: > "$GLOBAL_TMP"
REPO_TMP="$TMP/repo"
git init -q "$REPO_TMP"

cat > "$FAKE_BIN/gh" <<'EOF'
#!/usr/bin/env bash
if [ "${1:-}" = "auth" ] && [ "${2:-}" = "status" ]; then
  exit 0
fi
if [ "${1:-}" = "auth" ] && [ "${2:-}" = "git-credential" ] && [ "${3:-}" = "get" ]; then
  printf 'protocol=https\nhost=github.com\nusername=fake\npassword=fake-token\n\n'
  exit 0
fi
if [ "${1:-}" = "auth" ] && [ "${2:-}" = "setup-git" ]; then
  exit 0
fi
exit 127
EOF
chmod +x "$FAKE_BIN/gh"

cleanup() {
  rm -rf "$TMP"
}
trap cleanup EXIT

# CI checkout 会在真实仓库写入 local extraheader，测试必须隔离本地 git 配置。
export HOME="$HOME_TMP"
export GIT_CONFIG_GLOBAL="$GLOBAL_TMP"
export GIT_CONFIG_NOSYSTEM=1
export GIT_DIR="$REPO_TMP/.git"
export GIT_WORK_TREE="$REPO_TMP"
export PATH="$FAKE_BIN:$PATH"

fail_test() {
  echo "FAIL: $*" >&2
  exit 1
}

expect_fail() {
  local desc="$1"; shift
  "$@" >/dev/null 2>&1
  local code=$?
  if [ "$code" = 0 ]; then
    fail_test "守卫未拦截: $desc"
  fi
  echo "OK: 守卫拦截: $desc"
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

echo "OK: check_git_auth.sh 可拦截旧凭据，干净状态放行"
