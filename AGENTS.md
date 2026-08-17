# AGENTS.md — SOP 知识库工作区指南

> 本文件在进入本工作区时自动载入，是本仓库的"操作地图"：结构、真相源、工作流与禁忌。
> 最后核实：2026-08-14（全部事实经文件系统与 git 历史逐一验证）。

## 一、仓库定位：源 vs 临时区

| 位置 | 角色 | git |
| --- | --- | --- |
| 本仓库（`D:\Program Files\worksc\SOPworksc\SOP-SEC-2026-001`） | **真相源**：md 源、生成器、REGISTRY | ✅ 跟踪（无 remote，纯本地） |
| `C:\Users\11058\AppData\Local\Temp\sop-exports\` | **临时产物区**：docx 预览迭代、`publish\` 可重建发布快照（上传 token 见仓库根 `.publish-tokens`，不入库） | ❌ 无 .git，也不是任何仓库的工作树 |

单向流水线：**git 源 md → 生成器 → docx → `%TEMP%\sop-exports\publish\`（发布文件）→ 上传飞书云盘（文件挂载）**。

## 二、仓库结构

- `sops/` — md 源文件 + `REGISTRY.md`（编号唯一权威，见 §三）
- `output/sop-system-20260812/stage3/` — docx 生成工具链：
  - `sop_to_docx_stdlib.py <input.md> <output.docx>`（纯 stdlib，主生成器）
  - `sop_to_docx.py`（依赖版，功能同前）
  - `check_docs.py`（健康检查：front matter 完整性校验）
  - `docx_template.b64`（docx 模板）
  - `publish.sh`（发布管线：构建-校验-发布-报告，`--dry-run`；上传 token 见 `.publish-tokens`，不入库）
- `.gitignore` 关键规则：
  - `*.docx` **绝不入库**——本机有文件监视器会损坏 .docx，这是初始化提交就写明的纪律
  - `output/**/stage2/`、`output/**/restructured.html` 为可复现中间产物，不入库
  - `.workbuddy/` 工具元数据不入库

## 三、文档治理（`sops/REGISTRY.md` 为唯一权威）

- 编号规则：`SOP-<域名>-<年>-<序号>`（序号按"域名+年"各自递增，不足 3 位前补零；跨年不沿用旧序号）。登记后**不回收、不重用**（作废仅改状态为 Retired）
- doc_type（2026-08-14 起登记）：`policy` 方针 / `standard` 标准 / `procedure` 程序 / `guideline` 指南 / `reference` 参考说明；参考类（如系统说明）归入 `07-参考与说明` 目录
- IMS 层级：L1 方针 / L2 跨部门程序 / L3 作业指导书+记录
- 域名代码：INFRA / SEC / APP / DESK / DR / GEN，各绑定默认关联标准（SEC→ISO/IEC 27001，APP/DESK→ISO/IEC 20000-1，其余→ISO 9001）
- 目标目录：飞书 Wiki「企业IT-SOP知识库」的 `00-总纲与索引` … `07-参考与说明`，与线上落位一一对应
- md front matter schema（新格式，faa3c44 起连坐升级）：`document_id / title / category / doc_type / version / status / author / approver`（旧字段 `doc_number / domain / owner` 已废弃，勿再用）

## 四、知识库承载模式（2026-08-14 起 = 文件挂载）

每文档两个飞书节点：`·成品`（docx 文件，点击即在线预览/可下载，无导入导出损耗）+ `·源文件`（md 文件，下载即 git 源）。更新走**同名覆盖**（file token 不变，节点不失效）。上传 token 见仓库根 `.publish-tokens`（gitignore 忽略，不入库）；8/13 曾使用临时区 `*_create.json` 预签名凭证，当前 publish.sh 不再依赖该路径。

## 五、%TEMP%\sop-exports 的真相与纪律

- **为什么放 %TEMP%**：本机文件监视器会把写进工作区/个人目录的 .docx 替换成损坏桩（.gitignore 注释为据；实测工作区及上级目录零 docx，docx 只存在于 %TEMP%）。docx 生成与发布文件全放这里，**用完即弃**
- **`publish\` 是可重建快照，不是镜像**：临时区可能随时被清空，publish.sh 通过 `mkdir -p` 自动重建；发布前必须从 git 源重新构建，勿复用旧快照
- **临时区路径由 publish.sh 管理**：当前默认 `C:/Users/11058/AppData/Local/Temp/sop-exports/publish`，可用 `PUB` 环境变量覆盖；换账号/机器时不要假设该目录或旧文件仍存在
- **清掉 %TEMP% 的后果**：docx 可由生成器重建、md 可从 git 恢复——唯一例外见 §六

## 六、未决事项（2026-08-14 已清零）

- ~~系统说明源文件工作树已删除~~ → **已解决**：实测根目录 `SOP-通用-系统说明.md` 仍被 git 跟踪且内容完好（`git log` 无删除提交），REGISTRY 登记有效，无需恢复或注销。

## 七、标准工作流

1. 编辑/新建 md 源（放 `sops/`；系统说明类归 `07-参考与说明`），同步登记 `REGISTRY.md`（编号、类型、层级、域名、目标目录）
2. 跑 `check_docs.py` 健康检查（front matter 完整性）
3. 生成 docx：`python output/sop-system-20260812/stage3/sop_to_docx_stdlib.py <input.md> <output.docx>`，输出到 `%TEMP%\sop-exports\publish\`（同名覆盖）
4. git 提交 md 源与生成器改动（docx 一律不入库）
5. 上传飞书：成品 docx + 源文件 md 同名覆盖对应节点

## 八、禁忌

- 禁止把 .docx 写入工作区任何位置（会被监视器损坏）
- 禁止 git 跟踪 `%TEMP%\sop-exports`
- 禁止绕过 REGISTRY 分配编号
- 生成器排版基准（103c977）：正文宋体+Times New Roman+深灰 3F3F3F，标题黑体去蓝——改生成器时不得破坏
