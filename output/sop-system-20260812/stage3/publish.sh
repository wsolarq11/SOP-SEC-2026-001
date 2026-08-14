#!/usr/bin/env bash
# =============================================================
# 发布管线（Docs-as-Code 四步法：构建-校验-发布-报告）
# git md 源 → 生成 docx → 同步 publish → 同名覆盖上传飞书（幂等）
#
# 用法:
#   bash publish.sh            # 全量构建+校验+上传
#   bash publish.sh --dry-run  # 仅构建+校验，不上传
#   bash publish.sh <md路径>   # 只发布指定文档（相对仓库根，如 sops/SOP-SEC-2026-001.md）
#
# 原则: 单一入口 / dry-run / 幂等同名覆盖 / 失败即报错可重跑
# 注意: 飞书节点重建后 file_token 会变，需更新下方 MANIFEST
# =============================================================
set -u

PY="C:/Users/11058/.workbuddy/binaries/python/versions/3.13.12/python.exe"
ROOT="D:/Program Files/worksc/SOPworksc/SOP-SEC-2026-001"
STAGE="$ROOT/output/sop-system-20260812/stage3"
CONV="$STAGE/sop_to_docx_stdlib.py"
CHECK="$STAGE/check_docs.py"
PUB="C:/Users/11058/AppData/Local/Temp/sop-exports/publish"

DRY=0
[[ "${1:-}" == "--dry-run" ]] && DRY=1 && shift
TARGET="${1:-ALL}"

mkdir -p "$PUB"

# manifest: 本地md相对路径 | docx输出文件名(NONE=不生成docx) | md_file_token | docx_file_token(NONE)
MANIFEST=(
"sops/SOP-SEC-2026-001.md|SOP-SEC-2026-001-v1.0.docx|REDACTED|REDACTED"
"sops/SOP-GEN-2026-002-表格排版规范.md|SOP-GEN-2026-002-表格排版规范.docx|REDACTED|REDACTED"
"sops/SOP-GEN-2026-001-合规与标准定位.md|SOP-GEN-2026-001-合规与标准定位.docx|REDACTED|REDACTED"
"SOP-通用-系统说明.md|SOP-通用-系统说明.docx|REDACTED|REDACTED"
"sops/REGISTRY.md|NONE|REDACTED|NONE"
)

echo "== [1/4] 健康检查（check_docs）=="
"$PY" "$CHECK" "$ROOT/sops" || { echo "健康检查失败，中止"; exit 1; }

echo "== [2/4] 构建 docx + 同步 md 到 publish =="
OK=0; FAIL=0
for entry in "${MANIFEST[@]}"; do
  IFS='|' read -r mdrel docxname mdtok docxtok <<< "$entry"
  # 目标过滤
  if [ "$TARGET" != "ALL" ] && [ "$mdrel" != "$TARGET" ] && [ "$docxname" != "$TARGET" ]; then
    continue
  fi
  echo "--- $mdrel ---"
  # md 同步
  if ! cp "$ROOT/$mdrel" "$PUB/$(basename "$mdrel")" 2>/dev/null; then
    echo "  ❌ md 缺失: $mdrel"; FAIL=$((FAIL+1)); continue
  fi
  # docx 构建
  if [ "$docxname" != "NONE" ]; then
    if ! "$PY" "$CONV" "$ROOT/$mdrel" "$PUB/$docxname" >/dev/null 2>&1; then
      echo "  ❌ docx 生成失败: $docxname"; FAIL=$((FAIL+1)); continue
    fi
    echo "  ✅ docx 生成: $docxname"
  fi
  echo "  ✅ md 同步: $(basename "$mdrel")"
  OK=$((OK+1))
done

if [ "$DRY" = "1" ]; then
  echo
  echo "== [dry-run] 构建完成，跳过上传（--dry-run）=="
  echo "通过: $OK | 失败: $FAIL"
  exit 0
fi

echo
echo "== [3/4] 同名覆盖上传飞书（幂等，token 不变）=="
cd "$PUB"  # lark-cli --file 要求 cwd 相对路径
for entry in "${MANIFEST[@]}"; do
  IFS='|' read -r mdrel docxname mdtok docxtok <<< "$entry"
  if [ "$TARGET" != "ALL" ] && [ "$mdrel" != "$TARGET" ] && [ "$docxname" != "$TARGET" ]; then
    continue
  fi
  # docx
  if [ "$docxtok" != "NONE" ]; then
    if lark-cli drive +upload --file "./$docxname" --file-token "$docxtok" --as user --format json 2>/dev/null | grep -q '"ok": true'; then
      echo "  ✅ docx 上传: $docxname"
    else
      echo "  ❌ docx 上传失败: $docxname"; FAIL=$((FAIL+1))
    fi
  fi
  # md
  mdname="$(basename "$mdrel")"
  if lark-cli drive +upload --file "./$mdname" --file-token "$mdtok" --as user --format json 2>/dev/null | grep -q '"ok": true'; then
    echo "  ✅ md 上传: $mdname"
  else
    echo "  ❌ md 上传失败: $mdname"; FAIL=$((FAIL+1))
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
