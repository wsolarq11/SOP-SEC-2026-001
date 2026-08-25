#!/usr/bin/env bash
# =============================================================
# 发布管线（Docs-as-Code 四步法：构建-校验-发布-报告）
# git md 源 → 生成 docx → 同步 publish → 同名覆盖上传飞书（幂等）
#
# 发布契约：sops/registry.json「已分配编号」数据是清单唯一机器来源。
#   - docx 输出名 = 源文件 basename 的 .md 换成 .docx
#   - Retired 文档不进入清单；Draft 文档跳过并提示
#   - 只有 Approved 文档进入发布清单；无 Approved 时明确提示，不阻断
#   - REGISTRY.md / registry.json 不生成 docx（输出为 NONE），源码随仓库 bundle 备份
#   - 发布只上传 docx；md 不再单独上传
#   - 每个 docx 条目必须提供 docx 上传 token，缺失即失败
#
# 用法:
#   bash publish.sh            # 全量构建+校验+上传
#   bash publish.sh --dry-run  # 仅构建+校验+token 完备性检查，不上传
#   bash publish.sh <md路径>   # 只发布指定文档（相对仓库根，如 sops/SOP-SEC-2026-001.md）
#
# 原则: 单一入口 / dry-run / 幂等同名覆盖 / 失败即报错可重跑
# 注意: 上传 file_token 已移出本脚本 → $ROOT/.publish-tokens（gitignore 忽略，不入库）
#       飞书节点重建后 file_token 会变，需更新 .publish-tokens
# =============================================================
set -u
export PYTHONIOENCODING="${PYTHONIOENCODING:-utf-8}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if command -v cygpath >/dev/null 2>&1; then
  SCRIPT_DIR="$(cd "$SCRIPT_DIR" && cygpath -w "$PWD")"
fi
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
if command -v cygpath >/dev/null 2>&1; then
  ROOT="$(cd "$ROOT" && cygpath -w "$PWD")"
fi
if [ -n "${PY:-}" ]; then
  :
else
  PY="python"
fi
TOOLS="$ROOT/tools"
CONV="$TOOLS/sop_to_docx_stdlib.py"
CHECK="$TOOLS/check_docs.py"
SECRETS="$TOOLS/check_secrets.py"
MANIFEST_GEN="$TOOLS/registry_manifest.py"
LARK_JSON="$TOOLS/lark_json.py"
if [ -z "${PUB:-}" ]; then
  _TEMP="${TEMP:-${TMP:-/tmp}}"
  PUB="${_TEMP//\\//}/sop-exports/publish"
fi
AS="${AS:-user}"

DRY=0
[[ "${1:-}" == "--dry-run" ]] && DRY=1 && shift
TARGET="${1:-ALL}"

mkdir -p "$PUB"

echo "== [1/4] 健康检查 + 敏感信息扫描 =="
"$PY" "$CHECK" "$ROOT/sops" || { echo "健康检查失败，中止"; exit 1; }
"$PY" "$SECRETS" --all || { echo "敏感信息扫描失败，禁止发布"; exit 1; }

echo "== [2/4] 从 registry.json 生成发布清单 =="
MANIFEST=()
while IFS= read -r line; do
  [ -z "$line" ] && continue
  MANIFEST+=("$line")
done < <(PYTHONIOENCODING=utf-8 "$PY" "$MANIFEST_GEN" | tr -d "\r") || { echo "registry manifest 生成失败，中止"; exit 1; }
if [ "${#MANIFEST[@]}" -eq 0 ]; then
  echo "❌ registry.json 未生成任何发布条目，中止"
  exit 1
fi
printf '  %s
' "${MANIFEST[@]}"

HAS_DOCX=0
for entry in "${MANIFEST[@]}"; do
  IFS='|' read -r _mdrel docxname <<< "$entry"
  if [ "$docxname" != "NONE" ]; then
    HAS_DOCX=1
  fi
done
if [ "$HAS_DOCX" = "0" ]; then
  echo "当前没有 Approved 文档，无可发布条目"
  echo "统一语义：Draft 不发布，Approved 才发布，Retired 注销"
  exit 0
fi

# 读取上传 token（gitignore 忽略，不入库）
declare -A DOCTOK
if [ ! -f "$ROOT/.publish-tokens" ]; then
  echo "❌ 缺少 $ROOT/.publish-tokens（上传 token 映射），无法发布"
  exit 1
fi
while IFS='|' read -r mdrel mdtok docxtok; do
  [ -z "$mdrel" ] && continue
  DOCTOK["$mdrel"]="$docxtok"
done < <(tr -d "\r" < "$ROOT/.publish-tokens")

# token 完备性是发布契约的一部分；dry-run 也检查，避免临发布才发现缺映射
echo
echo "== token 完备性检查 =="
FAIL=0
for entry in "${MANIFEST[@]}"; do
  IFS='|' read -r mdrel docxname <<< "$entry"
  if [ "$TARGET" != "ALL" ] && [ "$mdrel" != "$TARGET" ] && [ "$docxname" != "$TARGET" ]; then
    continue
  fi
  if [ "$docxname" != "NONE" ] && { [ -z "${DOCTOK[$mdrel]:-}" ] || [ "${DOCTOK[$mdrel]}" = "NONE" ]; }; then
    echo "  ❌ 缺少 docx 上传 token: $mdrel"
    FAIL=$((FAIL+1))
  fi
done
if [ "$FAIL" -gt 0 ]; then
  echo "  token 缺失 $FAIL 项，请补充 .publish-tokens 后重跑"
  exit 1
else
  echo "  ✅ 全部清单条目均有上传 token"
fi

echo
echo "== [3/4] 构建 docx 到 publish =="
OK=0
declare -A BUILT_OK
for entry in "${MANIFEST[@]}"; do
  IFS='|' read -r mdrel docxname <<< "$entry"
  if [ "$TARGET" != "ALL" ] && [ "$mdrel" != "$TARGET" ] && [ "$docxname" != "$TARGET" ]; then
    continue
  fi
  echo "--- $mdrel ---"
  if [ "$docxname" = "NONE" ]; then
    echo "  ✅ 仅仓库源码（不生成/上传 docx）"
    BUILT_OK["$mdrel"]=1
    OK=$((OK+1))
    continue
  fi
  if [ ! -f "$ROOT/$mdrel" ]; then
    echo "  ❌ md 源缺失: $mdrel"; FAIL=$((FAIL+1)); continue
  fi
  if ! "$PY" "$CONV" "$ROOT/$mdrel" "$PUB/$docxname" >/dev/null 2>&1; then
    echo "  ❌ docx 生成失败: $docxname"; FAIL=$((FAIL+1)); continue
  fi
  echo "  ✅ docx 生成: $docxname"
  BUILT_OK["$mdrel"]=1
  OK=$((OK+1))
done

if [ "$FAIL" -gt 0 ]; then
  echo "构建/校验失败 $FAIL 项，中止，未上传"
  exit 1
fi

if [ "$DRY" = "1" ]; then
  echo
  echo "== [dry-run] 构建完成，跳过上传（--dry-run）=="
  echo "通过: $OK | 失败: $FAIL"
  [ "$FAIL" -gt 0 ] && exit 1
  exit 0
fi

echo
echo "== [4/4] 同名覆盖上传飞书（幂等，token 不变）=="
cd "$PUB"  # lark-cli --file 要求 cwd 相对路径
for entry in "${MANIFEST[@]}"; do
  IFS='|' read -r mdrel docxname <<< "$entry"
  if [ "$TARGET" != "ALL" ] && [ "$mdrel" != "$TARGET" ] && [ "$docxname" != "$TARGET" ]; then
    continue
  fi
  if [ "${BUILT_OK[$mdrel]:-}" != "1" ]; then
    continue
  fi
  if [ "$docxname" != "NONE" ] && [ -n "${DOCTOK[$mdrel]:-}" ] && [ "${DOCTOK[$mdrel]}" != "NONE" ]; then
    UPLOAD_OUTPUT="$(lark-cli drive +upload --file "./$docxname" --file-token "${DOCTOK[$mdrel]}" --as "$AS" --format json 2>&1 || true)"
    if printf '%s\n' "$UPLOAD_OUTPUT" | "$PY" "$LARK_JSON" ok; then
      RETURNED_TOKEN="$(printf '%s\n' "$UPLOAD_OUTPUT" | "$PY" "$LARK_JSON" token)" || RETURNED_TOKEN=""
      RETURNED_TOKEN="${RETURNED_TOKEN%$'\r'}"
      if [ "$RETURNED_TOKEN" = "${DOCTOK[$mdrel]}" ]; then
        echo "  ✅ docx 上传: $docxname"
      else
        echo "  ❌ docx 上传后 file_token 不一致: $docxname"
        printf '%s\n' "$UPLOAD_OUTPUT" | "$PY" "$LARK_JSON" message || true
        FAIL=$((FAIL+1))
      fi
    else
      echo "  ❌ docx 上传失败: $docxname"
      printf '%s\n' "$UPLOAD_OUTPUT" | "$PY" "$LARK_JSON" message || true
      FAIL=$((FAIL+1))
    fi
  fi
done

echo
echo "== [4/4] 完成 =="
if [ "$FAIL" = "0" ]; then
  echo "✅ 全部发布成功（$OK 项）"
else
  echo "⚠️ $FAIL 项失败，请检查后重跑（幂等，安全重试）"
  exit 1
fi
