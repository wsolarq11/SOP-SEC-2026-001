#!/usr/bin/env bash
# =============================================================
# 发布管线（Docs-as-Code 四步法：构建-校验-发布-报告）
# git md 源 → 生成 docx → 同步 publish → 同名覆盖上传飞书（幂等）
#
# 发布契约：REGISTRY.md「已分配编号」表是清单唯一来源。
#   - docx 输出名 = 源文件 basename 的 .md 换成 .docx
#   - Retired 文档不进入清单
#   - REGISTRY.md 不生成 docx（输出为 NONE），源码随仓库 bundle 备份
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

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -W)"
ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd -W)"
if [ -n "${PY:-}" ]; then
  :
elif [ -x "C:/Users/11058/.workbuddy/binaries/python/versions/3.13.12/python.exe" ]; then
  PY="C:/Users/11058/.workbuddy/binaries/python/versions/3.13.12/python.exe"
else
  PY="python"
fi
STAGE="$ROOT/output/sop-system-20260812/stage3"
CONV="$STAGE/sop_to_docx_stdlib.py"
CHECK="$STAGE/check_docs.py"
MANIFEST_GEN="$STAGE/registry_manifest.py"
PUB="${PUB:-C:/Users/11058/AppData/Local/Temp/sop-exports/publish}"
AS="${AS:-user}"

DRY=0
[[ "${1:-}" == "--dry-run" ]] && DRY=1 && shift
TARGET="${1:-ALL}"

mkdir -p "$PUB"

echo "== [1/4] 健康检查（check_docs + REGISTRY 契约）=="
"$PY" "$CHECK" "$ROOT/sops" || { echo "健康检查失败，中止"; exit 1; }

echo "== [2/4] 从 REGISTRY 生成发布清单 =="
MANIFEST=()
while IFS= read -r line; do
  [ -z "$line" ] && continue
  MANIFEST+=("$line")
done < <(PYTHONIOENCODING=utf-8 "$PY" "$MANIFEST_GEN" | tr -d "\r") || { echo "REGISTRY manifest 生成失败，中止"; exit 1; }
if [ "${#MANIFEST[@]}" -eq 0 ]; then
  echo "❌ REGISTRY 未生成任何发布条目，中止"
  exit 1
fi
printf '  %s
' "${MANIFEST[@]}"

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
    if lark-cli drive +upload --file "./$docxname" --file-token "${DOCTOK[$mdrel]}" --as "$AS" --format json 2>/dev/null | grep -q '"ok": true'; then
      echo "  ✅ docx 上传: $docxname"
    else
      echo "  ❌ docx 上传失败: $docxname"; FAIL=$((FAIL+1))
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
