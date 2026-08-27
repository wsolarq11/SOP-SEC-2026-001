# SOP 编号总登记表

> `sops/registry.json` 是 git 跟踪的**机器唯一编号权威**；本表由 `registry_render.py` 生成，仅作人工审计视图。新增文档时，按「域名 + 年」分配下一个 3 位序号并登记 `registry.json`，防止重复与遗漏。
> 编号规则：`SOP-<域名>-<年>-<序号>`（序号按 域名+年 各自递增）。
> 2026-08-13 起：每条文档登记「目标目录」（飞书 Wiki 知识库「企业IT-SOP知识库」内的一级目录），与线上落位一一对应。
> 2026-08-14 起：知识库承载模式 = **文件挂载**（非在线文档导入）。每文档一个 `·成品` 节点（docx 文件，点击即在线预览/可下载，无导入导出损耗）。更新走同名覆盖（file token 不变，节点不失效）。
> 2026-08-14 起：每条文档登记「文档类型」（doc_type：policy 方针 / standard 标准 / procedure 程序 / guideline 指南 / reference 参考说明），区分强制规范与描述性文档；参考类（如系统说明）归入 `07-参考与说明` 目录，与规范类分离。
> 2026-08-18 起：md 源不再单独上传到飞书；源码由 GitHub public remote 与 `%TEMP%\sop-exports\backup\` git bundle 备份（见 AGENTS §四/§五）。内容目录只放 docx 成品，registry.json/REGISTRY.md 仍为索引，留在 00。
> 2026-08-18 起：front matter schema 收敛——level / review_due / last_reviewed 不再写入 front matter；本库不再登记 IMS 层级（L1/L2/L3），文档性质由 `doc_type` 区分。

## 文档类型：doc_type
| 类型 | 规范性 | 语义 | 示例 |
| --- | --- | --- | --- |
| policy | 强制 | 方针 / 定位总纲（what & why） | （待建） |
| standard | 强制 | 具体可测要求（how much / which） | 表格排版规范 |
| procedure | 强制 | 逐步操作指令（exactly how） | 各 SOP 文档 |
| guideline | 非强制 | 建议 / 最佳实践（should / consider） | （待建） |
| reference | 非规范 | 解释性 / 描述性（系统说明、手册、FAQ） | 系统说明、合规与标准定位 |

## 域名代码表
| 域名代码 | 分类 |
| --- | --- |
| INFRA | 基础设施 |
| SEC | 信息安全 |
| APP | 应用与系统 |
| DESK | 终端与桌面 |
| DR | 数据容灾 |
| GEN | 通用 |

## 目标目录
| 一级目录 | 域名 | 内容 |
| --- | --- | --- |
| 00-总纲与索引 | GEN（总纲） | registry.json/REGISTRY.md 索引 |
| 01-SEC-信息安全 | SEC | 安全域 SOP（账号权限、合规审计、安全事件等） |
| 02-APP-应用系统 | APP | 应用系统 SOP（部署、发布、变更、监控） |
| 03-DESK-桌面终端 | DESK | 终端 / 桌面 / 服务台 SOP |
| 04-INFRA-基础设施 | INFRA | 服务器 / 网络 / 存储 / 云平台 SOP |
| 05-DR-灾难恢复 | DR | 备份 / 容灾 / 演练 SOP |
| 06-GEN-通用 | GEN | 跨域基础规范与流程（standard / guideline / procedure） |
| 07-参考与说明 | 跨域 | 描述性文档（reference）：系统说明、使用指南、FAQ |

## 发布契约

- `sops/registry.json` 是 publish.sh 构建/发布清单的**唯一机器来源**；新增或停用文档只改 `registry.json` 与源文件，再运行 `python tools/kb.py registry-render --write` 同步本表。
- docx 输出名 = 源文件列 basename 的 `.md` 换成 `.docx`（REGISTRY.md / registry.json 不生成/上传 docx，输出为 `NONE`；md 源不再单独上传，源码随 GitHub remote 与 git bundle 备份）。
- 停用文档直接从 `registry.json` 删除，历史编号保留在 git 历史；`Draft`/`Approved` 文档进入清单，`Draft` 发布不代表已签批；其余条目必须源文件存在，且 front matter 的 `document_id / title / category / doc_type / version / status` 与 `registry.json` 一致。
- 每个 docx 清单条目必须提供 docx 上传 token（`.publish-tokens`），缺失即发布失败；`--dry-run` 同样检查 token 完备性。

<!-- generated from sops/registry.json; do not edit by hand -->
## 已分配编号
| 文档号 | 标题 | 类型 | 域名 | 版本 | 编制人 | 状态 | 源文件 | 目标目录 | 需求来源 | 签批人 | 生效日期 | 评审人 | 评审时间 | 签批时间 | 最近发布 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SOP-GEN-2026-001 | 合规与标准定位 | reference | GEN | 1.2 | 段天俊 | Draft | sops/SOP-GEN-2026-001-合规与标准定位.md | 07-参考与说明 | 历史存量（知识库初始化） | 待定 | 待定 |  |  |  |  |
| SOP-GEN-2026-002 | 表格排版规范 | standard | GEN | 1.2 | 段天俊 | Draft | sops/SOP-GEN-2026-002-表格排版规范.md | 06-GEN-通用 | 历史存量（2026-08 表格规范收敛） | 待定 | 待定 |  |  |  |  |
| SOP-SEC-2026-001 | 安防平台人员变动信息处理标准作业程序书 | procedure | SEC | 1.2 | 段天俊 | Draft | sops/SOP-SEC-2026-001.md | 01-SEC-信息安全 | 历史存量（安防平台作业程序） | 待定 | 待定 |  |  |  |  |
| SOP-DESK-2026-001 | 员工电脑配给与收回作业程序 | procedure | DESK | 3.3 | 段天俊 | Draft | sops/SOP-DESK-2026-001.md | 03-DESK-桌面终端 | 历史存量（员工电脑作业程序） | 待定 | 待定 |  |  |  |  |
| SOP-DESK-2026-002 | 员工电脑配给与收回 · 支撑资料清单 | reference | DESK | 2.4 | 段天俊 | Draft | sops/SOP-DESK-2026-002.md | 03-DESK-桌面终端 | 历史存量（员工电脑支撑清单） | 待定 | 待定 |  |  |  |  |
| SOP-GEN-2026-003 | SOP与规范库 · 系统说明 | reference | GEN | 2.1 | 段天俊 | Draft | sops/SOP-通用-系统说明.md | 07-参考与说明 | 2026-08 系统说明统一迁移 | 待定 | 待定 |  |  |  |  |
| SOP-GEN-2026-004 | AI 会话知识库维护流程 | procedure | GEN | 1.0 | 段天俊 | Draft | .sop/AI会话知识库维护流程.md | 06-GEN-通用 | 2026-08-26 会话维护流程归位决策 | 待定 | 待定 |  |  |  | 2026-08-27 |

## 分配规则
- 新增时：取目标域名 + 当前年，查 sops/registry.json 该「域名+年」最大序号 +1，不足 3 位前补零；如历史编号已删除，以 git 历史判断不回收。
- 例：下一个信息安全类（SEC）2026 年文档 = `SOP-SEC-2026-002`。
- 年份跨年不沿用旧年序号：2027 年首条 = `SOP-SEC-2027-001`。
- 文档号一经分配**不回收、不重用**；停用后从 registry 删除，历史编号保留在 git 历史。
- 「类型」按 doc_type 填写：policy / standard / procedure / guideline / reference。
