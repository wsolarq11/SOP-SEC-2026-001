---
document_id: REF-GEN-2026-001
title: SOP与规范库 · 系统说明
category: GEN
doc_type: reference
version: 1.5
status: Draft
author: 段天俊
approver: 待定
effective_date: 待定
---

# SOP与规范库 · 系统说明

> 本知识库用于沉淀团队的企业 IT SOP、操作规范、步骤与流程，可按需导出为 .docx 文档。

## 一、企业 IT 分类体系
- 基础设施（INFRA）：服务器与操作系统、网络、存储、虚拟化/云平台底座、机房/IDC
- 信息安全（SEC）：账号与权限(IAM)、合规与审计、漏洞与威胁管理、安全事件应急响应
- 应用与系统（APP）：业务系统部署、发布与变更、配置管理、监控与可用性
- 终端与桌面（DESK）：员工设备(PC/手机)、办公软件、IT 服务台/工单
- 数据容灾（DR）：数据库运维、备份策略、容灾演练、数据合规
- 通用（GEN）：跨域基础规范、文档与命名规范、流程与角色定义

## 二、ISO 语义式编号与命名规范
每条 SOP 分配一个受控文档号，格式：
`SOP-<域名>-<年>-<序号>`
- 域名：见下方域名代码表（INFRA / SEC / APP / DESK / DR / GEN）
- 年：文档建立年份（如 2026）
- 序号：3 位，按「域名 + 年」各自递增（如 SEC-2026 第一条为 001）

源文件统一放在 `sops/`；文档号、标题、分类、类型、版本与状态以 front matter 和 `sops/registry.json` 为准，不要求文件名等于文档号。docx 输出名与源文件 basename 一致。

### 域名代码表
| 域名代码 | 分类 |
| --- | --- |
| INFRA | 基础设施 |
| SEC | 信息安全 |
| APP | 应用与系统 |
| DESK | 终端与桌面 |
| DR | 数据容灾 |
| GEN | 通用 |

> 编号由 git 跟踪的 `sops/registry.json` 统一分配与记录；`sops/REGISTRY.md` 是自动生成的审计视图。版本真相源在 git（提交历史 / 标签），不把版本号写入文档号。

## 三、固定结构条目模板
每条 SOP 统一包含以下字段（front-matter + 正文）：
- 文档编号（document_id）/ 标题 / 分类（category）/ 文档类型（doc_type）/ 版本 / 状态 / 编制人（author）/ 批准人（approver）
- 适用场景：什么时候该用这份 SOP
- 前置条件：开始前需准备好的事项（含配置参数）
- 操作步骤：编号清单，逐步可执行
- 注意事项 / 常见坑（含异常处理）
- 关联资料

## 四、如何新增 / 更新
- 新增：把规范文本整理后放入 `sops/`，在 `sops/registry.json` 登记文档号，运行 `python tools/kb.py registry-render --write` 后提交 git；发布见“五、如何发布文档”。
- 更新：修改源文档并升版本，同步 `sops/registry.json` 与版本修订记录，提交 git，再按“五、如何发布文档”发布。

## 五、如何发布文档
运行 `python tools/kb.py publish --dry-run` 验证，或运行 `python tools/kb.py publish` 发布 `Draft`/`Approved` 文档。发布管线从 git 源重新生成 docx 到 `%TEMP%\sop-exports\publish\`，再以成品 docx 同名覆盖上传飞书；md 源不单独上传，源码由 GitHub 私有 remote 与 git bundle 备份。`Draft` 发布不代表已签批，`approver` / `effective_date` 在真实签批后填写。

## 版本修订记录
| 版本 | 日期 | 说明 |
| --- | --- | --- |
| 1.0 | 2026-08-12 | 初始化知识库与系统说明 |
| 1.1 | 2026-08-12 | 分类体系调整为面向企业 IT：基础设施/信息安全/应用系统/终端桌面/数据容灾/通用 |
| 1.2 | 2026-08-13 | 命名规范改为 ISO 语义式：SOP-<域名>-<年>-<序号>，新增域名代码表与 REGISTRY 编号索引 |
| 1.3 | 2026-08-21 | registry.json 唯一权威、REGISTRY.md 生成视图；md 不再单独上传飞书 |
| 1.4 | 2026-08-25 | 源文件统一移入 sops/，删除口语化 AI 使用说明，命名规则改为以 front matter 与 registry 为准 |
| 1.5 | 2026-08-26 | 发布语义调整为 Draft/Approved 可发布，Draft 发布不代表已签批 |
