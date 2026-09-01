# Session Log 2026-09-01（四维审计 + CI 发布剪除）

> 本次工作分三阶段：①对全仓「代码 + 文档语义」按 简洁/透明/可复现/边界清晰 四维审计并整改文档漂移；②按用户目标「发布/备份不依赖 CI、结果立刻知道」剪除 CI 发布、收敛边界到本机；③与用户确认最终边界：裸 push 只备份、发布保持显式。

- Session: 2026-09-01 (CST)
- Repository: SOP-SEC-2026-001（wsolarq11/SOP-SEC-2026-001，public，master）
- 提交（两批，均已推送 origin/master）：
  - `c18d105` docs: 全仓四维审计报告与文档口径对齐
  - `40aaffe` ci: 剪除 CI 发布，发布/备份收敛到本机

---

## 阶段一：全仓四维审计（简洁 / 透明 / 可复现 / 边界清晰）

### Scope
- 审计：代码 `tools/**/*.py`、`tools/*.sh`、`.github/workflows/*.yml`；文档 `AGENTS.md`、`docs/*.md`、`sops/*.md`、`sop/*.md`、`sessionlogs/*`。

### 结论
- 代码层四维均达标（上轮 thermo 重构已收敛 canonical helper，文件 <1000 行、纯小函数、无 any/float 滥用）。
- 文档层主要问题为**数据漂移**：`ship` 未同步入操作地图、AGENTS.md「最后核实」日期过期、硬编码计数过期、活跃条目表遗漏。

### Fixes（文档层）
1. `AGENTS.md`：头部「最后核实 → 2026-09-01」并补 `ship`；§二 命令清单补 `ship/build/stage/manifest`，结构补 `ship.sh`/`publish_tokens.py`/`lib.sh`；§六 日期更新并明确 ship 入口；§七 补一键发布 ship。
2. `docs/项目事实与产线总览.md`：§2 依赖补 `publish_tokens.py`/`lib.sh`/`ship.sh`；§3 活跃表补 `SOP-DESK-2026-003` 并同步最近发布为 2026-08-31；§5.3 补 ship。
3. `docs/产线化规划与评估.md`：测试数 →「以 `kb.py test` 输出为准（38）」、登记数 7→8、去旧硬编码。
4. `docs/产线词表.md`：验收补 ship 一键入口。
5. 新增 `docs/审计-简洁透明可复现边界清晰.md`：四维审计报告（结论 + 依据 + 整改清单）。

---

## 阶段二：CI 发布剪除（用户确认「发布/备份不依赖 CI、要立刻知道结果」）

### 事实基线（gh 查证）
- `publish.yml`（SOP Publish Pipeline）历次 push 全 **failure**：根因 CI 还原的 `PUBLISH_TOKENS_B64` 缺 `SOP-DESK-2026-003` token，在 token 完备性校验中断，**从未真正发布成功**。
- `test.yml`（Toolchain Tests）历次全绿。
- 线上 docx 全部由**本机 `ship`/`publish`** 发布；`publish-history.jsonl` 无 CI 发布记录。

### 落地
1. 删除 `.github/workflows/publish.yml`：CI 不再真发布；只留 `test.yml`（`kb.py test`+`line`）作只读校验门。
2. 删除 3 个失效 GitHub secrets：`PUBLISH_TOKENS_B64`/`LARK_APP_ID`/`LARK_APP_SECRET`（repo 现无 secret）。
3. 移除 `token_bootstrap.py` 死代码 `--sync-secret`（`_repo_name`/`_sync_ci_secret`/`import base64`），更新 `kb.py` 用法。
4. 文档口径同步：`AGENTS.md`（§二/§四/§六/§七）、`docs/产线化规划与评估.md`、`docs/项目事实与产线总览.md`、`docs/审计-…md` §5、本日志。

### 新边界
| 动作 | 归属 |
|---|---|
| docx 发布 + 发布事实回写 | 本机 `ship` / `publish`（唯一） |
| 飞书 bundle 备份 | 本机 pre-push / post-commit hook |
| 回归/校验门 | CI `test.yml`（只读，不发布） |
| GitHub secrets | 无 |

---

## 阶段三：最终边界确认（用户拍板）

- 用户确认「发布不依赖 CI、结果立刻可复现」方向，并拍板：**裸 `git push` 只做飞书 bundle 备份，docx 发布保持显式（`ship`/`publish`），不把发布串进 push hook**——选最稳形态。
- 本轮**不改任何代码 / hook**，维持现有边界。

### 最终「远近全同步」边界
| 端 | 内容 | 触发 |
|---|---|---|
| GitHub（远端源码） | commit + push | 本机 `git push` |
| 飞书 backup（近端） | bundle 完整快照 | 本机 pre-push / post-commit hook |
| 飞书 docx（近端） | 文档成品发布 | 本机显式 `ship`/`publish` |
| CI 校验 | `test.yml` 只读回归门 | push 后自动，不发布 |

想一键全同步走 `kb.py ship`（发布+bundle+push 一体，失败即停），而非裸 push 串发布。

---

## Verification
- `python tools/kb.py check`：OK（8 文档 front matter / registry 契约一致）。
- `python tools/kb.py test`：38 tests OK（含 docx 生成、secret 扫描、git auth 守卫）。
- `python tools/kb.py publish --dry-run`：10 项 0 失败。
- delivery gate：PASS。
- 提交 `c18d105`、`40aaffe` 已推送，工作树清洁，`HEAD == origin/master`；远程 workflow 仅 `test.yml`；远程 secrets 为空。

## Notes
- 阶段一只改文档（.md），未改代码与 `sops/registry.json`/`.publish-tokens`。
- 阶段二改了 `tools/token_bootstrap.py`、`tools/kb.py`、删 `.github/workflows/publish.yml` 及 GitHub secrets，代码测试零回归。
- 阶段三未改 hook 语义，发布始终显式。