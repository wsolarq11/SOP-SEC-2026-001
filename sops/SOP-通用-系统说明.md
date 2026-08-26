---
document_id: SOP-GEN-2026-003
title: SOP与规范库 · 系统说明
category: GEN
doc_type: reference
version: 2.0
status: Draft
author: 段天俊
approver: 待定
effective_date: 待定
---

# SOP与规范库 · 系统说明

> 本说明解释知识库怎么组织、编号、登记和发布。日常维护只改 `sops/` 下的 md 与 `sops/registry.json`。

## 一、知识库结构

- `sops/*.md`：文档源文件，由 git 跟踪。
- `sops/registry.json`：文档登记的唯一机器来源。
- `sops/REGISTRY.md`：由 registry 自动生成的登记表，人工只读。
- `tools/`：检查、生成、发布工具。
- docx 成品不入库，发布时临时生成。

## 二、文档编号

- 统一格式：`SOP-<域名>-<年>-<序号>`。
- 域名：`INFRA / SEC / APP / DESK / DR / GEN`。
- 序号：按“域名 + 年”从 001 开始递增，不复用、不回收。
- 所有文档统一使用 `SOP-` 前缀，不再使用 `REF-`。
- 文档号写在 front matter 和 registry；文件名不必等于文档号，docx 输出名跟随源文件名。

## 三、文档类型

| 类型 | 含义 |
| --- | --- |
| policy | 方针 / 定位总纲 |
| standard | 具体、可检查的规范要求 |
| procedure | 逐步执行的作业程序 |
| guideline | 建议 / 最佳实践 |
| reference | 说明、资料清单、参考信息 |

本库不登记 L1/L2/L3 层级，不把文档与外部标准条款做映射；文档性质由 `doc_type` 区分。

## 四、目标目录

| 目录 | 内容 |
| --- | --- |
| 00-总纲与索引 | 索引与系统说明 |
| 01-SEC-信息安全 | 信息安全文档 |
| 02-APP-应用系统 | 应用系统文档 |
| 03-DESK-桌面终端 | 终端、桌面、服务台文档 |
| 04-INFRA-基础设施 | 基础设施文档 |
| 05-DR-灾难恢复 | 备份、容灾、演练文档 |
| 06-GEN-通用 | 跨域规范 |
| 07-参考与说明 | 跨域参考说明 |

业务域配套资料清单（如 DESK 的支撑资料清单）可留在对应业务目录，便于与主程序一起查看。

## 五、登记与维护

新增文档：

1. 在 `sops/` 下新建 md。
2. 在 `sops/registry.json` 增加一条记录，字段为 `document_id / title / doc_type / domain / version / author / status / source / target_dir`。
3. 运行 `python tools/kb.py registry-render --write` 更新登记表。
4. 运行 `python tools/kb.py check` 和 `python tools/kb.py publish --dry-run` 验证。

修改文档：

1. 修改 md，并同步更新 front matter 与版本修订记录。
2. 同步更新 registry 中的 `version`。
3. 重新生成登记表并验证。

停用文档：从 `sops/registry.json` 删除该条记录；文档号继续保留在 git 历史中，不回收、不重用。

## 六、签批信息

- `author`（编制人）、`approver`（批准人）、`effective_date`（生效日期）全部由人工维护。
- 工具链不自动填写、不自动推导签批状态。
- `Draft` 文档可以发布，但 `Draft` 不代表已签批。
- 真实签批后，人工更新 front matter、registry 和审批信息表。

## 七、发布

- 运行 `python tools/kb.py publish --dry-run` 验证，或运行 `python tools/kb.py publish` 发布。
- 发布清单只包含 `Draft` / `Approved` 文档。
- 发布时从 git 源重新生成 docx，再同名覆盖上传飞书。
- md 源不单独上传，源码由 GitHub remote 与 git bundle 备份。

## 版本修订记录

| 版本 | 日期 | 说明 |
| --- | --- | --- |
| 2.0 | 2026-08-26 | 统一文档号为 SOP- 前缀；明确不登记 L1/L2/L3、签批全手工、停用文档从 registry 删除 |
| 1.5 | 2026-08-26 | 发布语义调整为 Draft/Approved 可发布，Draft 发布不代表已签批 |
| 1.4 | 2026-08-25 | 源文件统一移入 sops/，删除口语化 AI 使用说明，命名规则改为以 front matter 与 registry 为准 |
| 1.3 | 2026-08-21 | registry.json 唯一权威、REGISTRY.md 生成视图；md 不再单独上传飞书 |
| 1.2 | 2026-08-13 | 命名规范改为 ISO 语义式：SOP-<域名>-<年>-<序号>，新增域名代码表与 REGISTRY 编号索引 |
| 1.1 | 2026-08-12 | 分类体系调整为面向企业 IT：基础设施/信息安全/应用系统/终端桌面/数据容灾/通用 |
| 1.0 | 2026-08-12 | 初始化知识库与系统说明 |
