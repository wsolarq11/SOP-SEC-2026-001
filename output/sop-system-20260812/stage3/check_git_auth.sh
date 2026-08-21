#!/usr/bin/env bash
# =============================================================
# GitHub 推送前凭据守卫
#
# 本脚本专门防"旧凭据干扰"：
#   1. 失效 token 被写进 global url.*.insteadOf
#   2. 失效 token 被写进 .git/config http.https://github.com/.extraheader
#   3. 失效 token 被 credential.helper store 写进 ~/.git-credentials
#   4. gh 登录态缺失但 remote 仍指向 GitHub
#
# 用法:
#   bash check_git_auth.sh             # 只检查
#   bash check_git_auth.sh --network   # 检查后执行 git ls-remote 实测
#   bash check_git_auth.sh --fix       # 清理旧凭据后重查
#   bash check_git_auth.sh --network --fix
#
# 原则：只在发现问题时输出被掩码的配置名，绝不打印 token 明文。
# =============================================================
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -W)"
ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd -W)"
GH_HOST="github.com"
FIX=0
NETWORK=0

for arg in "$@"; do
  case "$arg" in
    --fix) FIX=1 ;;
    --network) NETWORK=1 ;;
    *) echo "未知参数: $arg" >&2; exit 2 ;;
  esac
done

mask() {
  sed -E 's#(gh[pousr]_[A-Za-z0-9]+|github_pat_[A-Za-z0-9_]+|x-access-token:[A-Za-z0-9]+)#<MASKED>#g'
}

fail() {
  echo "❌ $*" >&2
  exit 1
}

clean_remote_url() {
  git config --get remote.origin.url 2>/dev/null | sed -E 's#^(https?)://[^/@]+:[^/@]+@#\1://#' || true
}

remove_global_github_insteadof() {
  while IFS= read -r key; do
    [ -n "$key" ] || continue
    git config --global --unset-all "$key" 2>/dev/null || true
    echo "清理 insteadOf: $(printf '%s' "$key" | mask)"
  done < <(git config --get-regexp '^url\..*@github\.com/' 2>/dev/null | awk '{print $1}')
}

remove_github_extraheader() {
  local scope key
  for scope in --system --global --local; do
    while IFS= read -r key; do
      [ -n "$key" ] || continue
      git config "$scope" --unset-all "$key" 2>/dev/null || true
      echo "清理 extraheader: $(printf '%s' "$key" | mask)"
    done < <(git config "$scope" --get-regexp '^http\..*github\.com/\.extraheader' 2>/dev/null | awk '{print $1}')
  done
}

remove_store_helper_and_file() {
  git config --global --unset-all credential.helper store 2>/dev/null || true
  if [ -f "${HOME:-}/.git-credentials" ]; then
    rm -f "${HOME:-}/.git-credentials"
    echo "清理 ~/.git-credentials（避免 credential.helper store 提供旧 token）"
  fi
}

setup_gh_git_credentials() {
  git config --global --unset-all "credential.https://github.com.helper" 2>/dev/null || true
  git config --global --unset-all "credential.https://gist.github.com.helper" 2>/dev/null || true
  gh auth setup-git >/dev/null 2>&1 || true
}

check_gh_login() {
  gh auth status --hostname "$GH_HOST" >/dev/null 2>&1 || fail "gh 未登录 $GH_HOST，请运行 gh auth login"
}

check_no_embedded_remote_token() {
  local url
  url="$(git config --get remote.origin.url 2>/dev/null || true)"
  if printf '%s' "$url" | grep -Eq '://[^/@]+:[^/@]*@'; then
    fail "remote.origin.url 内含 user:token；请使用 gh 凭据。remote=$(printf '%s' "$url" | mask)"
  fi
  if printf '%s' "$url" | grep -Eq 'ghp_|gho_|github_pat_|x-access-token:'; then
    fail "remote.origin.url 检测到 token 明文；remote=$(printf '%s' "$url" | mask)"
  fi
}

check_no_github_insteadof() {
  local bad
  bad="$(git config --get-regexp '^url\..*@github\.com/' 2>/dev/null | head -n 1 || true)"
  [ -z "$bad" ] || fail "存在 github token insteadOf：$(printf '%s' "$bad" | mask)"
}

check_no_github_extraheader() {
  local bad
  bad="$(git config --get-regexp '^http\..*github\.com/\.extraheader' 2>/dev/null | head -n 1 || true)"
  [ -z "$bad" ] || fail "存在 github extraheader：$(printf '%s' "$bad" | mask)"
}

check_no_store_credentials() {
  local store_helpers credfile
  store_helpers="$(git config --get-all credential.helper 2>/dev/null | grep -x 'store' || true)"
  [ -z "$store_helpers" ] || fail "credential.helper store 仍启用；请运行 --fix 清理"
  credfile="${HOME:-}/.git-credentials"
  if [ -f "$credfile" ] && grep -q '@github.com' "$credfile" 2>/dev/null; then
    fail "~/.git-credentials 含 github 凭据；请运行 --fix 清理"
  fi
}

check_gh_credential_works() {
  local out
  out="$(printf 'protocol=https\nhost=github.com\n\n' | gh auth git-credential get 2>&1 || true)"
  printf '%s\n' "$out" | grep -q '^username=' || fail "gh auth git-credential 未返回用户名"
  printf '%s\n' "$out" | grep -q '^password=' || fail "gh auth git-credential 未返回密码"
}

check_network() {
  local remote out
  remote="$(clean_remote_url)"
  [ -n "$remote" ] || fail "未找到 remote.origin.url"
  echo "网络实测: git ls-remote $remote HEAD"
  out="$(git ls-remote "$remote" HEAD 2>&1)" || fail "git ls-remote 失败：$out"
}

if [ "$FIX" = 1 ]; then
  remove_global_github_insteadof
  remove_github_extraheader
  remove_store_helper_and_file
  setup_gh_git_credentials
  # remote 内嵌 token 也在修复范围
  git config remote.origin.url "$(clean_remote_url)" 2>/dev/null || true
fi

check_gh_login
check_no_embedded_remote_token
check_no_github_insteadof
check_no_github_extraheader
check_no_store_credentials
check_gh_credential_works

if [ "$NETWORK" = 1 ]; then
  check_network
fi

echo "✅ GitHub 凭据检查通过（无旧 token 残留）"
