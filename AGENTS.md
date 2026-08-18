<!-- TRELLIS:START -->
# Trellis Instructions

These instructions are for AI assistants working in this project.

This project is managed by Trellis. The working knowledge you need lives under `.trellis/`:

- `.trellis/workflow.md` — development phases, when to create tasks, skill routing
- `.trellis/spec/` — package- and layer-scoped coding guidelines (read before writing code in a given layer)
- `.trellis/workspace/` — per-developer journals and session traces
- `.trellis/tasks/` — active and archived tasks (PRDs, research, jsonl context)

If a Trellis command is available on your platform (e.g. `/trellis:finish-work`, `/trellis:continue`), prefer it over manual steps. Not every platform exposes every command.

If you're using Codex or another agent-capable tool, additional project-scoped helpers may live in:
- `.agents/skills/` — reusable Trellis skills
- `.codex/agents/` — optional custom subagents

Managed by Trellis. Edits outside this block are preserved; edits inside may be overwritten by a future `trellis update`.

<!-- TRELLIS:END -->



AGENTS.md — SOP 知识库工作区指南
本文件在进入本工作区时自动载入，是本仓库的"操作地图"：结构、真相源、工作流与禁忌。 最后核实：2026-08-18（GitHub Actions 校验、构建、bot 上传飞书全链路通过）。

一、仓库定位：源 vs 临时区
位置	角色	git
本仓库（D:\Program Files\worksc\SOPworksc\SOP-SEC-2026-001）	真相源：md 源、生成器、REGISTRY	✅ 跟踪（私有 GitHub remote + 飞书 bundle 双备份）
C:\Users\11058\AppData\Local\Temp\sop-exports\	临时产物区：docx 预览迭代、publish\ 可重建发布快照、backup\ 可重建仓库 bundle（上传 token 见仓库根 .publish-tokens，不入库）	❌ 无 .git，也不是任何仓库的工作树
单向流水线：git 源 md → 生成器 → docx → %TEMP%\sop-exports\publish\（发布文件）→ 上传飞书云盘（文件挂载）。GitHub 私有 remote 负责代码/历史同步，Actions 负责 push 后自动校验与构建。

二、仓库结构
sops/ — md 源文件 + REGISTRY.md（编号唯一权威，见 §三）
output/sop-system-20260812/stage3/ — docx 生成工具链：
sop_to_docx_stdlib.py <input.md> <output.docx>（纯 stdlib，主生成器）
sop_to_docx.py（依赖版，功能同前）
check_docs.py（健康检查：front matter 完整性 + REGISTRY 发布契约一致性）
registry_lib.py（REGISTRY 表解析与契约校验共享库）
registry_manifest.py（从 REGISTRY 生成 publish.sh 发布清单）
docx_template.b64（docx 模板）
publish.sh（发布管线：构建-校验-发布-报告，--dry-run；清单由 REGISTRY 自动生成，上传 token 见 .publish-tokens，不入库）
backup_commit.sh（git 仓库备份：post-commit/pre-push hook 生成完整 git bundle 并同名覆盖上传飞书；GitHub 与飞书 bundle 均须成功，hook 失败会让 git 命令显式失败；支持 --install/--init/--dry-run）
cleanup_90_md.py（90 目录清理：列出并删除散装 md，先 --dry-run 审计，再 --yes 执行）
.gitignore 关键规则：
*.docx 绝不入库——本机有文件监视器会损坏 .docx，这是初始化提交就写明的纪律
output/**/stage2/、output/**/restructured.html 为可复现中间产物，不入库
.workbuddy/ 工具元数据不入库
三、文档治理（sops/REGISTRY.md 为唯一权威）
编号规则：SOP-<域名>-<年>-<序号>（序号按"域名+年"各自递增，不足 3 位前补零；跨年不沿用旧序号）。登记后不回收、不重用（作废仅改状态为 Retired）
doc_type（2026-08-14 起登记）：policy 方针 / standard 标准 / procedure 程序 / guideline 指南 / reference 参考说明；参考类（如系统说明）归入 07-参考与说明 目录
IMS 层级：L1 方针 / L2 跨部门程序 / L3 作业指导书+记录
域名代码：INFRA / SEC / APP / DESK / DR / GEN，各绑定默认关联标准（SEC→ISO/IEC 27001，APP/DESK→ISO/IEC 20000-1，其余→ISO 9001）
目标目录：飞书 Wiki「企业IT-SOP知识库」的 00-总纲与索引 … 07-参考与说明，与线上落位一一对应
发布契约（2026-08-17 起）：publish.sh 的构建/发布清单由 REGISTRY「已分配编号」表自动生成，不再维护脚本内 manifest；docx 输出名 = 源文件 basename 的 .md 换成 .docx，Retired 不发布，缺 token 即失败
md front matter schema（新格式，faa3c44 起连坐升级）：document_id / title / category / doc_type / version / status / author / approver（旧字段 doc_number / domain / owner 已废弃，勿再用）
四、知识库承载模式（2026-08-14 起 = 文件挂载）
每文档一个飞书节点：·成品（docx 文件，点击即在线预览/可下载，无导入导出损耗）。md 源不再单独上传，源码随仓库 bundle 备份（见 §五）。更新走同名覆盖（file token 不变，节点不失效）。上传 token 见仓库根 .publish-tokens（gitignore 忽略，不入库）；8/13 曾使用临时区 *_create.json 预签名凭证，当前 publish.sh 不再依赖该路径。GitHub remote：https://github.com/wsolarq11/SOP-SEC-2026-001.git（私有，master）；.github/workflows/publish.yml 在 push 后自动跑 check_docs.py + docx 构建，并还原 PUBLISH_TOKENS_B64 secret；LARK_APP_ID/LARK_APP_SECRET 已配置为 GitHub secrets，CI 以 bot 身份自动上传；应用 cli_aaf1518a8c789bd5 已对现有 docx 成品文件获得 full_access 协作者权限。仓库备份登记 BACKUP_BUNDLE|<bundle file_token>|NONE、BACKUP_FOLDER|<90 目录 folder_token>|NONE、BACKUP_WIKI|<90 目录 wiki node_token>|NONE，由 backup_commit.sh 读写。GitHub 与飞书 bundle 为主副双备份，两者都必须成功；post-commit/pre-push hook 失败会让 git commit/push 显式失败。

五、%TEMP%\sop-exports 的真相与纪律
为什么放 %TEMP%：本机文件监视器会把写进工作区/个人目录的 .docx 替换成损坏桩（.gitignore 注释为据；实测工作区及上级目录零 docx，docx 只存在于 %TEMP%）。docx 生成与发布文件全放这里，用完即弃
publish\ 是可重建快照，不是镜像：临时区可能随时被清空，publish.sh 通过 mkdir -p 自动重建；发布前必须从 git 源重新构建，勿复用旧快照
临时区路径由 publish.sh 管理：当前默认 C:/Users/11058/AppData/Local/Temp/sop-exports/publish，可用 PUB 环境变量覆盖；换账号/机器时不要假设该目录或旧文件仍存在
backup\ 是可重建仓库 bundle 暂存区：post-commit/pre-push hook 每次提交和推送前重建并同名覆盖上传到飞书 90 目录（BACKUP_WIKI Wiki 节点），上传失败则 commit/push 显式失败；默认 C:/Users/11058/AppData/Local/Temp/sop-exports/backup，可用 BACKUP_DIR 覆盖
清掉 %TEMP% 的后果：docx 可由生成器重建、md 可从 git 恢复——唯一例外见 §六
六、未决事项（2026-08-14 已清零）
系统说明源文件工作树已删除 → 已解决：实测根目录 SOP-通用-系统说明.md 仍被 git 跟踪且内容完好（git log 无删除提交），REGISTRY 登记有效，无需恢复或注销。
七、标准工作流
仓库备份初始化（一次性）：bash output/sop-system-20260812/stage3/backup_commit.sh --install，再 bash output/sop-system-20260812/stage3/backup_commit.sh --init --wiki-token <90目录wiki node_token>

编辑/新建 md 源（放 sops/；系统说明类归 07-参考与说明），同步登记 REGISTRY.md（编号、类型、层级、域名、目标目录；发布清单会自动包含该条目）
跑 check_docs.py 健康检查（front matter 完整性 + REGISTRY 契约一致性）
构建验证：bash output/sop-system-20260812/stage3/publish.sh --dry-run，输出到 %TEMP%\sop-exports\publish\（docx 不入库）
git 提交 md 源与生成器改动（docx 一律不入库；post-commit hook 必须完成飞书 bundle 上传，失败时 git commit 显式报错）
git push origin master：pre-push hook 先强制飞书 bundle 上传成功再推送 GitHub；GitHub Actions 随后自动跑健康检查、docx 构建，并以 bot 身份自动上传飞书
本地上传飞书兜底：bash output/sop-system-20260812/stage3/publish.sh（仅成品 docx 同名覆盖对应节点；md 不再单独上传）
一次性清理 90 目录旧 md：python output/sop-system-20260812/stage3/cleanup_90_md.py --dry-run 审计后，再 --yes 执行删除
八、禁忌
禁止把 .docx 写入工作区任何位置（会被监视器损坏）
禁止 git 跟踪 %TEMP%\sop-exports
禁止绕过 REGISTRY 分配编号
禁止把 .bundle 或备份日志放进工作区（bundle 写到 %TEMP%\sop-exports\backup，日志在 .git\backup-commit.log）
禁止把 GitHub token、Feishu appSecret、.publish-tokens 写进仓库文件；CI 凭据只放 GitHub secrets，本机凭据只放仓库外受控文件
90 目录旧 md 只能通过 cleanup_90_md.py 的 --yes 删除；执行前必须先 --dry-run 看清单
生成器排版基准（103c977）：正文宋体+Times New Roman+深灰 3F3F3F，标题黑体去蓝——改生成器时不得破坏
