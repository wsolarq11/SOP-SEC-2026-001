# 会话日志基线

> 2026-08-27 更新后的现状入口。历史日志保留在 `sessionlogs/`，但现状以本文件为准。

## 仓库现状

- 源与发布：GitHub public 与飞书 bundle 双备份；Actions 校验、构建、发布已恢复。
- 治理：`sops/registry.json` 是唯一编号权威；Draft/Approved 均可发布，Draft 不代表已签批。
- 源目录：`sops/` 为正式知识库源；`.sop/` 为会话/治理类 SOP；`sessionlogs/` 只存历史归档。
- 已登记文档：SOP-GEN-2026-001/002/003/004、SOP-SEC-2026-001、SOP-DESK-2026-001/002，均为 Draft。
- 项目主线：`docs/项目事实与产线总览.md` 统一承载事实模型、数据形态、依赖方向与已通线路；工具链、CI、hooks 按依赖方向串入同一条文档产线。

## 已完成

- 2026-08-26 工具链按 AGENTS 全修：代理模块拆分，registry、发布、校验、敏感扫描、备份脚本重构；测试 24 passed，`check`、渲染、secrets、dry-run 等当时通过。
- 会话维护流程已归位 `.sop/AI会话知识库维护流程.md`，并登记为 SOP-GEN-2026-004。
- 2026-08-27 归一化自检：`check`、`registry-render --check`、`manifest` 均通过；`test` 34 passed；历史会话目录统一为 `sessionlogs/`；产线统一路线闭环并按依赖方向串入非文档资产。
- 2026-08-27 事实收口：`registry.json` 为唯一事实源，`registry-render --write` 单向生成 front matter/REGISTRY.md；发布事实写入 `sops/publish-history.jsonl` 安全摘要并由 CI 提交回 master；`check`、`test` 36 passed、`publish --dry-run` 通过；会话日志见 `sessionlogs/2026-08-27-165200-sessionlog.md`。

## 未收口

- `.trellis/scripts/` 未纳入工具链审计，多个文件超过 500 行；作为上游模板运行时豁免，已在总览与 AGENTS 说明。
- Trellis workspace journal 未记录，`00-bootstrap-guidelines` 仍在 `in_progress`。
- 工作区仍有未提交的产线工具链与文档改动，git 提交/推送作为部署动作待用户确认。
