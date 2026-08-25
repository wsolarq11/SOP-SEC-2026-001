# SOP 编号总登记表

> `sops/registry.json` 是 git 跟踪的**机器唯一编号权威**；本表由 `registry_render.py` 生成，仅作人工审计视图。新增文档时，按「域名 + 年」分配下一个 3 位序号并登记 `registry.json`，防止重复与遗漏。
> 编号规则：`SOP-<域名>-<年>-<序号>`（序号按 域名+年 各自递增）。
> 2026-08-13 起：每条文档登记「层级」与「关联标准」，使编号体系与 ISO 9001 / ISO/IEC 27001 / ISO/IEC 20000-1 三套标准绑定。
> 2026-08-13 起：每条文档登记「目标目录」（飞书 Wiki 知识库「企业IT-SOP知识库」内的一级目录），与线上落位一一对应。
> 2026-08-14 起：知识库承载模式 = **文件挂载**（非在线文档导入）。每文档一个 `·成品` 节点（docx 文件，点击即在线预览/可下载，无导入导出损耗）。更新走同名覆盖（file token 不变，节点不失效）。
> 2026-08-14 起：每条文档登记「文档类型」（doc_type：policy 方针 / standard 标准 / procedure 程序 / guideline 指南 / reference 参考说明），区分强制规范与描述性文档；参考类（如系统说明）归入 `07-参考与说明` 目录，与规范类分离。
> 2026-08-18 起：md 源不再单独上传到飞书；源码由 GitHub 私有 remote 与 `%TEMP%\sop-exports\backup\` git bundle 备份（见 AGENTS §四/§五）。内容目录只放 docx 成品，registry.json/REGISTRY.md 仍为索引，留在 00。
> 2026-08-18 起：front matter schema 收敛——level / review_due / last_reviewed / related_standards 不再写入 front matter；「层级」与「关联标准」以 `sops/registry.json` 为唯一权威（生成器与发布契约均不消费上述字段，仅注册表承载索引语义）。

## 文档类型：doc_type
| 类型 | 规范性 | 语义 | 示例 |
| --- | --- | --- | --- |
| policy | 强制 | 方针 / 定位总纲（what & why） | （待建） |
| standard | 强制 | 具体可测要求（how much / which） | 表格排版规范 |
| procedure | 强制 | 逐步操作指令（exactly how） | 各 SOP 文档 |
| guideline | 非强制 | 建议 / 最佳实践（should / consider） | （待建） |
| reference | 非规范 | 解释性 / 描述性（系统说明、手册、FAQ） | 系统说明、合规与标准定位 |

## 层级说明：IMS 三级文件
| 层级 | 含义 | 本库对应 |
| --- | --- | --- |
| L1 | 方针 / 定位总纲 | （待建） |
| L2 | 跨部门程序 | （待建） |
| L3 | 作业指导书 SOP + 记录 | 各 SOP 文档 |

## 域名代码表
| 域名代码 | 分类 | 默认关联标准 |
| --- | --- | --- |
| INFRA | 基础设施 | ISO 9001 |
| SEC | 信息安全 | ISO/IEC 27001 |
| APP | 应用与系统 | ISO/IEC 20000-1（第二阶段） |
| DESK | 终端与桌面 | ISO/IEC 20000-1（第二阶段） |
| DR | 数据容灾 | ISO 9001 |
| GEN | 通用 | ISO 9001 / 27001 / 20000（总纲） |

## 目标目录
| 一级目录 | 域名 | 内容 |
| --- | --- | --- |
| 00-总纲与索引 | GEN（总纲） | registry.json/REGISTRY.md 索引 |
| 01-SEC-信息安全 | SEC | 安全域 SOP（账号权限、合规审计、安全事件等） |
| 02-APP-应用系统 | APP | 应用系统 SOP（部署、发布、变更、监控） |
| 03-DESK-桌面终端 | DESK | 终端 / 桌面 / 服务台 SOP |
| 04-INFRA-基础设施 | INFRA | 服务器 / 网络 / 存储 / 云平台 SOP |
| 05-DR-灾难恢复 | DR | 备份 / 容灾 / 演练 SOP |
| 06-GEN-通用 | GEN | 跨域基础规范（standard / guideline）|
| 07-参考与说明 | 跨域 | 描述性文档（reference）：系统说明、使用指南、FAQ |

## 发布契约

- `sops/registry.json` 是 publish.sh 构建/发布清单的**唯一机器来源**；新增或停用文档只改 `registry.json` 与源文件，再运行 `python tools/kb.py registry-render --write` 同步本表。
- docx 输出名 = 源文件列 basename 的 `.md` 换成 `.docx`（REGISTRY.md / registry.json 不生成/上传 docx，输出为 `NONE`；md 源不再单独上传，源码随 GitHub remote 与 git bundle 备份）。
- 状态为 `Retired` 的文档不进入构建/发布清单；`Draft` 状态禁止发布；其余条目必须源文件存在，且 front matter 的 `document_id / title / category / doc_type / version / status` 与 `registry.json` 一致。
- 每个 docx 清单条目必须提供 docx 上传 token（`.publish-tokens`），缺失即发布失败；`--dry-run` 同样检查 token 完备性。

<!-- generated from sops/registry.json; do not edit by hand -->
## 已分配编号
| 文档号 | 标题 | 层级 | 类型 | 域名 | 版本 | 关联标准 | 编制人 | 状态 | 源文件 | 目标目录 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SOP-GEN-2026-001 | 合规与标准定位 | — | reference | GEN | 1.0 | ISO 9001 / 27001 / 20000 | 待定 | Draft | sops/SOP-GEN-2026-001-合规与标准定位.md | 07-参考与说明 |
| SOP-GEN-2026-002 | 表格排版规范 | L2 | standard | GEN | 1.1 | 通用（不绑定单一标准） | 段天俊 | Draft | sops/SOP-GEN-2026-002-表格排版规范.md | 06-GEN-通用 |
| SOP-SEC-2026-001 | 安防平台人员变动信息处理标准作业程序书 | L3 | procedure | SEC | 1.1 | ISO/IEC 27001（人力资源安全 / offboarding） | 段天俊 | Draft | sops/SOP-SEC-2026-001.md | 01-SEC-信息安全 |
| SOP-DESK-2026-001 | 员工电脑配给与收回资料汇编 | — | reference | DESK | 3.0 | ISO/IEC 20000-1（人力资源安全 / 配给与收回） | 段天俊 | Draft | sops/SOP-DESK-2026-001.md | 03-DESK-桌面终端 |
| SOP-DESK-2026-002 | 员工电脑配给与收回 · 支撑资料清单 | — | reference | DESK | 2.0 | ISO/IEC 20000-1（人力资源安全 / 配给与收回） | 段天俊 | Draft | sops/SOP-DESK-2026-002.md | 03-DESK-桌面终端 |
| SOP-DESK-2026-003 | 员工电脑配给与收回 · 源文件清单 | — | reference | DESK | 1.0 | ISO/IEC 20000-1（人力资源安全 / 配给与收回） | 段天俊 | Retired | sops/SOP-DESK-2026-003.md | 03-DESK-桌面终端 |
| SOP-DESK-2026-004 | 员工电脑配给与收回 · 相关表单明细 | — | reference | DESK | 1.0 | ISO/IEC 20000-1（人力资源安全 / 配给与收回） | 段天俊 | Retired | sops/SOP-DESK-2026-004.md | 03-DESK-桌面终端 |
| REF-GEN-2026-001 | SOP与规范库 · 系统说明 | — | reference | GEN | 1.3 | — | 段天俊 | Draft | SOP-通用-系统说明.md | 07-参考与说明 |

## 分配规则
- 新增时：取目标域名 + 当前年，查 sops/registry.json 该「域名+年」最大序号 +1，不足 3 位前补零。
- 例：下一个信息安全类（SEC）2026 年文档 = `SOP-SEC-2026-002`。
- 年份跨年不沿用旧年序号：2027 年首条 = `SOP-SEC-2027-001`。
- 文档号一经分配**不回收、不重用**（即便作废，仅将状态改为 Retired）。
- 「关联标准」按上方域名默认关联标准填写；跨域文档（如总纲）可多选。
