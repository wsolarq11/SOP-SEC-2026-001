# Session Log 2026-08-31

> 本次工作记录：003 收尾（人名/版本修订清空、栏目重排）、ship 一键发布管线落地、Windows 本机 Steamcommunity_302 官方升级与 github 冲通、全量发布并 push。

- Session: 2026-08-31 (CST)
- Repository: SOP-SEC-2026-001
- Branch: master
- HEAD（上一提交）: 5c5c0a0
- Goal: 收尾 DOC 内容与元数据口径、把「同步+测试+发布+push」串成单一入口，并修复本机 github/302 网络链路使 push/发布全自动。

## Scope

- `sops/SOP-DESK-2026-003-新员工电脑配给验收清单.md` 及 `sops/registry.json`：003 栏目与人名字段、版本修订记录口径
- `sops/*.md`（8 个文档）+ registry：author/approver 清空、effective_date 待定删除、version 统一 1.0、修订记录清成「表头 + 一行空行」
- `tools/ship.sh` + `tools/kb.py`：新增 `kb.py ship` 一键管线（同步→校验→测试→发布→commit/push，失败即停）
- `tools/token_bootstrap.py`：Windows 下 lark-cli 为 `.cmd` shim，加 `cmd /c` 兼容，003 首次上传成功
- `tools/docxgen/*`：支持 `<!-- docx-hide: 目标 -->` 隐藏章节/文档信息；front-matter 行的整行隐形
- `tools/test_pipeline.py`：新增 docx-hide 与 requirement_ref 隐藏行回归测试
- 本机 Windows 环境：Steamcommunity_302 AMD64_V14.0.02 → 官方 V15.0.3 升级；github 规则、hosts、443 后端监听、开机/登录自启

## Completed

- 003 第 1/5/N 章节重命名为 `2 标配软件 / 3 邮箱配置 / 4 打印连接 / 5 账密与登记 / 6 按需配给 / 7 验收确认`，序号随章节重排。
- 秘书：003 正文按用户原文调优（win11/存量 win10、腾讯会议安装目录删除、笔记本管理制度阅签等）。
- `docx` 层按用户要求隐藏 填写说明/文档信息/附页相关依据/版本修订记录；md 源完整保留，仅用 `<!-- docx-hide -->` 控制生成。
- 全部 8 个文档 `author`、`approver` 清空，`effective_date` 待定删除；`version` 统一 `1.0`；修订记录保留表头 + 一行空行，历史改由人工维护（git 历史保留）。
- 新增 `kb.py ship [--dry-run] [--bootstrap]`：串起 `registry-render --write → check → test → publish → git commit/push`，`set -euo pipefail` 失败即停、幂等。
- 修复 `token_bootstrap.py` Windows shim 问题：`_command()` 在 Windows 走 `cmd /c lark-cli`，`_run_cli` 与 `_upload_new` 均复用；003 首次上传成功并登记 token。
- 生成 home：官方 sha256 一致的 `Steamcommunity_302_15.0.3_Windows_x64.zip` 下载并解压到 `D:\Program Files\Steamcommunity_302_15`；旧版整目录备份到 `%TEMP%\s302-upgrade\backup-AMD64_V14.0.02`。
- V15 github 规则已启用、hosts 全量写入、443 后端监听、`startOnDaemonLaunch=True`；登录触发计划任务 `Steamcommunity302 V15`。
- 全量真发布：8 份 docx 同名覆盖上传飞书全成功；`git commit 5c5c0a0` 并 push `master`（615f694→5c5c0a0）。

## Verification

- `python tools/kb.py registry-render --check` / `check`：OK，8 文档 front matter 完整、registry 契约一致
- `python tools/kb.py test`：38 tests passed（含 docx-hide、整行隐藏回归）
- `python tools/kb.py publish --dry-run` / `publish`：通过，10 项全部发布成功
- `python tools/kb.py ship --dry-run`：全链路校验通过，未上传未推送
- `python tools/kb.py ship`：真实发布成功 + 本地 commit `5c5c0a0`；push 因 gh 认证失效+网络不通首轮失败
- 修复本机 302 网络源 + `gh auth login` 后，`git push origin master` 成功（`615f694..5c5c0a0`），工作树清洁
- 302 官方 sha256 校验：`9d2f3726e28bb60b53221cba71866102f490c4cdbd0aa15469511d4d68f6c6cf` 与官方一致

## Notes

- 版本号与修订记录由人工维护，agent 不再直写；git 历史与发布日志保留不动。
- `--docx-hide` 为源 md 侧标记，其余文档未加，仅 003 使用。
- token（`.publish-tokens`、`file_token`）不入库；仓库内 `publish-history.jsonl` 只写安全摘要。
- 本机 302 后端未注册为 Windows 系统服务，开机自启基于「登录触发的计划任务 + startOnDaemonLaunch=true」。