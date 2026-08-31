# Session Log 2026-08-31 (thermo-nuclear review + 落地)

> 本次工作：对全仓工具链做 thermo-nuclear 代码质量评审并产报告；随后依用户"一并处理"指示逐项落地重构；清洁目录、记录本次会话并 push。

- Session: 2026-08-31 (CST)
- Repository: SOP-SEC-2026-001
- Branch: master
- HEAD（review 前）: 0896a7a

## Scope

- 全仓评审（`tools/**/*.py`、`*.sh`、`.github/workflows/*.yml` 与集成），按
  `thermo-nuclear-code-quality-review` 从严标准，
  产出 `THERMO-NUCLEAR-REVIEW.md`（按优先级排序发现 + 具体整改）。
- 逐项落地 §1–§7 的建议（见下），行为保持不变。
- 清洁 git/目录（移除 `py_compile` 生成的忽略 `__pycache__`），写会话记录并 push。

## Completed

- 新增 `tools/publish_tokens.py`：`.publish-tokens` 唯一 reader/writer
  `read_publish_tokens`/`write_publish_token`（封装 BACKUP_* 键字段1、文档键字段2 的位置差异），
  消除 `token_bootstrap._read_tokens` 与 `line_report._read_tokens` 的逐字节重复、
  `cleanup_90_md.read_target_tokens` 的第三套实现。
- `registry_lib` 新增 `docx_output_name`（docx 名唯一规范）与 `entry_by_source`（按 source 查注册项），
  收敛 `registry_lib._register_source` / `registry_manifest._docx_name` / `token_bootstrap._docx_output_name`，
  及 `publish_log._entry_for_source` / `token_bootstrap._entry`。
- `publish.sh`：抽 `is_target()`（原 4 处重复 TARGET 过滤收敛），`.publish-tokens` 读取收敛为 `load_doctoken()`
  （初始与 bootstrap 后共用，删除重复块）。
- `publish_log.append_publish`：拆出显式子操作 `build_record` / `write_record` / `persist_record` /
  `write_repo_summary` / `update_last_published`；签名与 CLI/`publish.sh` 调用不变。
- `proxy_core`：CORS 注入由硬编码 host 字面量改为数据驱动 `Config["cors_hosts"]`。
- `feishu_mitm_proxy`：删除 `__all__` 冗余 re-export，仅留 CLI 所需 import；`test_pipeline` 改直接
  `from proxy_core` / `from proxy_certs`。
- 新增 `tools/lib.sh`（`normalize_path` / `setup_paths` / `default_pub`），
  `ship.sh` / `publish.sh` / `backup_commit.sh` / `check_git_auth.sh` / `test_check_git_auth.sh`
  五处路径样板各收敛为 `SCRIPT_DIR=…; . "$SCRIPT_DIR/lib.sh"`。
- legacy markdown registry 解析器判定为有意向后兼容，保留并在 `parse_registry` docstring 标注。
- 评审报告追加《实施记录》并重新过交付门（PASS）。

## Verification

- `python -m py_compile`（10 个改动 py）：通过。
- `bash -n`（6 个改动 sh / lib.sh）：通过。
- `python tools/kb.py test`：38 项通过 + `test_check_secrets` + `test_check_git_auth.sh`（覆盖 lib.sh 源码链路）全绿。
- `python tools/kb.py check`：8 文档 front matter / registry 契约一致。
- `bash tools/publish.sh --dry-run`：manifest 生成、token 完备、docx 构建 10 项全部通过（未上传）。
- `git diff --stat`：14 改 + 3 新增，净删约 250 行（删除复杂度多于新增）。
- 工作树清洁后提交并 push；飞书 bundle 备份由 pre-push hook 完成。

## Notes

- 改动只涉及工具链/审查产物，未改任何 `sops/*.md` 源、`registry.json`、`.publish-tokens`。
- `.trellis/scripts/` 仍按既有口径豁免；本次未纳入审计（基线既定）。