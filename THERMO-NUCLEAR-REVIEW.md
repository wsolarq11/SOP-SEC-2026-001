# 全仓 Thermo-Nuclear 代码质量评审

> 范围：整个 `SOP-SEC-2026-001` 工作区（仓库）的工具链与管线代码，即
> `tools/**/*.py`、`tools/*.sh`、`.github/workflows/*.yml` 及其集成，
> 按 `thermo-nuclear-code-quality-review` 的从严标准审查。
> 基线：仅评审，未改动任何代码（本文件为唯一产物）。

## 总体结论

这是一个**整体健康、刻意保持单调**的工具链：几乎每个模块都被解耦成小型的纯函数，无 `any`/强转滥用，文件行数全部远低于 1000 行，测试充分且确定。未发现高严重度的结构倒退。

但存在**一类反复出现的真实问题：多个"规范契约"在 Python 与 shell 之间被重复实现，且语义已开始分叉（canonical-helper fragmentation）**。这正是 thermo-nuclear 审查最应该抓住的结构性机会——删除这些重复，而不是把同一份复杂度再挪一处。按优先级排序如下。

---

## 1. 「.publish-tokens」文件契约在 5 处被重复实现（高优先级 / 规范助手碎片化）

`tools/.publish-tokens`（`<key>|<flag>|<token>` 行格式）是整个发布链的单一契约，但被**读了 5 遍、写了 4 遍**，各自语义微妙不同：

- `tools/token_bootstrap.py` `_read_tokens()`（line 111）与 `tools/line_report.py` `_read_tokens()`（line 86）**逐字节相同**（按 `|` 切、取 `fields[2]`），是纯复制粘贴。
- `tools/token_bootstrap.py` `_update_tokens()`（line 159）是唯一的 Python 写端，会**丢弃注释并重排**，与读端语义不完全一致。
- `tools/cleanup_90_md.py` `read_target_tokens()`（line 57）只解析 `BACKUP_WIKI`/`BACKUP_FOLDER` 前缀键，是第三种语义。
- `tools/publish.sh`（line 101 与 **134–138 重复两遍**同一段 `while IFS='|' read ... DOCTOK`）是第四种。
- `tools/backup_commit.sh` `read_token_line()`/`append_token_line()`/`save_backup_token()`（line 140/165/180）是第五种，且带去重/回写逻辑。

**为什么这是结构问题而非洁癖**：这是单一文件的单一格式，被五处各自“小改一下”，每次新增一个读者都要重新踩一遍格式边界；任何一处改了格式（例如某字段加转义、改成 JSON）都会在其余四处静默漂移。这是明摆着的 code-judo 删除对象。

**建议**（Python 侧先统一，shell 侧收敛为一个共享库）：
1. 在 `registry_lib.py`（或新建 `tokens.py`）放一个 `read_publish_tokens(path) -> Record[str,str]` 与 `write_publish_token(path, key, token)`，让 `token_bootstrap._read_tokens`、`line_report._read_tokens`、`cleanup_90_md` 全部复用，删掉两处 `_read_tokens`。
2. shell 侧把 `publish.sh` 两次读 token 的块收敛为一次，并与 `backup_commit.sh` 共用同一条解析约定（二者目前对 `BACKUP_*` 行的处理细节都有差异）。

---

## 2. `publish.sh`：TARGET 过滤条件复制 4 次 + 同段 token 读取重复（spaghetti-condition 增长）

`tools/publish.sh` 中，同一个目标过滤条件

```
[ "$TARGET" != "ALL" ] && [ "$mdrel" != "$TARGET" ] && [ "$docxname" != "$TARGET" ]
```

在 line 118 / 148 / 169 / 211 出现 **4 次**；同时 `IFS='|' read -r mdrel docxname` 解构在 line 114 / 147 / 168 / 210 各重复一次；`.publish-tokens` 读取块在 line 101 与 134–138 重复两次。

**这是教科书式的「重复条件暗示缺失助手」**：四个独立循环里反复内联同一判断。它们不是"碰巧相似"，而是同一目标的过滤语义散落四处，下次改过滤规则（例如支持 `--target` 前缀匹配）必须同步改 4 处。

**建议**：
- 抽 `is_target() { [ "$TARGET" = "ALL" ] || [ "$mdrel" = "$TARGET" ] || [ "$docxname" = "$TARGET" ]; }`，循环体内只调它。
- 把 manifest 解构抽成一次解析（如 `parse_manifest` 数组换成强类型行），让 4 个循环只 `for entry`，避免重复的 `IFS= read`。
- `.publish-tokens` 读取抽成一个 `load_doctoken()` 函数，bootstrap 后 `unset DOCTOK; load_doctoken` 复用，而非粘贴两遍。

---

## 3. `publish_log.append_publish` 的布尔 flag 累积（可控流 flag 味道）

`tools/publish_log.py` `append_publish()`（line 117）签名是
`append_publish(log, source, file_token, result, update_registry, persist, repo_summary, repo_history)`——
一个函数通过 4~5 个布尔开关同时承担多种正交职责（写主日志 / 写持久日志 / 写 token-free 仓库摘要 / 回写 registry）。`publish.sh` 一处调用即传 `--update-registry --persist --repo-summary` 三开关。

这不是什么大衰败，但属于「一个功能叠多个 boolean flag」的可读性膨胀：调用者难以只根据签名判断“这次到底写哪几份”。属 thermo 审查会点名的**一次性布尔/flag 把控制流弄复杂**。

**建议**：把这 4 个正交副作用拆成显式小函数（`write_durable(record)`、`write_repo_summary(record)`、`update_registry_last_published(entry,date)`），`append_publish` 只写主日志并返回 `record`，由调用者（CLI 与 `publish.sh`）自行组合——让"到底写哪几份"在调用肉眼可见。

---

## 4. `registry_lib` 里回归的 markdown 解析路径（dead/legacy 漂移）

`tools/registry_lib.py` 仍保留完整 Markdown 版 REGISTRY.md 解析器：`_default_registry_path()`（line 155）在缺 `registry.json` 时回退 `REGISTRY.md`，`parse_registry()`（line 162）对非 `.json` 显式路径走 `_parse_registry_markdown()`（line 266）+ `HEADER_ALIASES`（line 59）。但 AGENTS.md / 仓库文档已将 `sops/registry.json` 宣称为**唯一机器事实源**，`REGISTRY.md` 只是生成视图。按「registry.json 是唯一事实源」的既有口径，这套 md 解析器已成为 **dead/legacy 代码**——它仍在被所有 `parse_registry()` 调用方（check/render/manifest/line/fact/token_bootstrap）静态链接，但只在异常回归场景（缺 json 或显式传 md 路径）才会命中。

**建议（两项之一，需真实验收）**：
- 若确认仓库已无需从 `REGISTRY.md` 反解（registry.json 永久在），删除 `_parse_registry_markdown`、`_process_markdown_*`、`_markdown_header`、`_append_markdown_entry`、`HEADER_ALIASES` 与 `_default_registry_path` 的 md 回退，让 `parse_registry()` 只认 `.json`——直接删掉一整块按 API 层冗余。
- 若这是有意的向后兼容（供老 commit 恢复），则在 `parse_registry` 文档注释里明示「md 路径仅供历史恢复，非当前事实源」，避免它在当前管线被误当成 equal 分支。

同时 `docxgen/constants.py` `FM_LABELS` 仍含 `review_due`/`last_reviewed`/`doc_number` 等已废弃字段映射（AGENTS.md 已废弃 `doc_number/domain/owner`），当前 registry schema 不再生成这些值，属少量的死映射，建议顺手清理或标注。

---

## 5. `proxy_core._exchange_request` 里硬编码的 CORS 特例（feature 逻辑泄漏进通用代理）

`tools/feishu_preview_proxy/proxy_core.py` `_exchange_request()`（line 207）对
`host == "internal-api-lark-api.feishu.cn"` 这一个字符串字面量做 CORS 注入，而其它走默认直通。`routes` 本就是数据驱动，唯独这条规则被一个魔法字符串嵌在通用代理的请求/响应交换路径正中。

**这是 thermo 最典型的「特例分支bolted到通用flow」**：将来要加第二个需要 CORS 的 host，就得在 `_exchange_request` 里再塞一个 `if`。

**建议**：把「需要 CORS 的 host 集合」做成配置数据（如 `Config["cors_hosts"]: set[str]`，默认含该 host），`_exchange_request` 只要 `if host in config["cors_hosts"]`——把特例逻辑从代码里的魔法字面量转移到数据，整个 if 从"为什么是它"变成"配置说了算"。改动极小、行为不变、可测试。

---

## 6. `feishu_mitm_proxy` 的 `__all__` 复export facade（thin wrapper 味道，轻度）

`tools/feishu_preview_proxy/feishu_mitm_proxy.py` 是 CLI 入口，却通过 `__all__` 把 `proxy_core`/`proxy_http`/`proxy_certs` 的几乎**全部**符号再导出一遍（line 42–66），只为让 `test_pipeline.py` 里 `import feishu_mitm_proxy as feishu_proxy` 只引一个模块。而包本身 `docxgen/__init__.py` 是空的，这个 façade 既不是包入口，也没增加任何语义，纯粹是"为测试少写一行 import"的中间层。

**建议**：
- 要么让 `feishu_mitm_proxy` 只保留真正的 CLI 主入口（`main`/`argv`），测试改为 `from proxy_core import ...`、`from proxy_http import ...`，删掉 `__all__` 这层 re-export（删除 indirection）；
- 要么若想保留"一个 import 拿全套"的便利，就把 `proxy_core` 等真正放进包，并让 `feishu_mitm_proxy` 成为合理的包级 API（放进 `__init__.py` 而不是装作 CLI 文件的 `__all__`）。

属轻量、可选，但符合"删掉不产生清晰的抽象"的准则。

---

## 7. shell 路径归一化样板在 5 个脚本里逐字重复

`normalize_path()`（`cygpath -w`）+ `SCRIPT_DIR/ROOT` 推导块，在 `tools/publish.sh`（27–33）、`tools/ship.sh`（23–30）、`tools/backup_commit.sh`（29–41）、`tools/check_git_auth.sh`（21–33）、`tools/test_check_git_auth.sh`（13–25）几乎逐字重复。

**建议**：抽一个 `tools/lib.sh`（含 `normalize_path`、`resolve_root`、`default_pub`、`trim_cr`），5 个脚本 `source "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/lib.sh"`。这是 shell 版的「复用 canonical helper」——和 §1 同类，只是跨文件级。

---

## 低优先级观察（供参考，不建议专门处理）

- `check_docs._check_git_diff`（line 229）对每个文档各单独执行一次 `git diff --quiet HEAD -- <rel>`；在一大批 md 下会产生同数量 git 子进程。可用单次 `git status --porcelain` 集合替换为一次调用。小性能/健壮性优化。
- `line_report._summary` 的 `"production_lines": 1` 是硬编码常量（line 158），一旦以后多管线就不再成立。可接受；标注即可。
- `publish.sh` line 218 的 `lark-cli ... || true` 吞掉失败后靠后续输出解析来判断成败——是本脚本设计，行为正确（token 一致性校验），无需改。

---

## 结论（Approval bar 对照）

按 thermo 的审批门槛逐项自查：

| 门槛 | 结果 |
|------|------|
| 文件被推过 1000 行 | **未触发**——最大文件 `test_pipeline.py`（661 行），全部 <1000 |
| 结构回归 / spaghetti 增长 | **未发现**；唯一的分支增长是 `publish.sh` 的 TARGET 条件复制（§2）与 `append_publish` 的 flag 累积（§3），都是可收敛的局部点 |
| 无谓抽象/wrapper | **轻触发**——`feishu_mitm_proxy.__all__` re-export（§6）为轻度 |
| 边界/类型泄漏 | **仅一处**——proxy 特写 host 魔法字面量（§5） |
| 乱加分支到无关流 | **未发现** |
| 重复 helper / 错层逻辑 | **是（主要问题）**——`.publish-tokens` 契约 5 处实现（§1）、docx 名 3 处（§1 / 附）、`_entry` 查注册项 2 处、bash 归一化 5 处（§7） |
| 未清理的 legacy dead 代码 | **是**——markdown registry 解析回退路径（§4） |
| 明显错过的 code-judo 简化 | 有：收敛上述 canonical 契约即可删掉一整类重复 |

**总评**：本仓库的"当前实现"处于良好状态——文件小、函数纯、类型边界干净、测试完整且确定。**没有必须立即回滚/rework 的结构性回归**。值得动手的是 §1 与 §7 的 canonical-helper 收敛（把 `.publish-tokens`、docx 名、lookup 统一到一个共享助手，把 5 个 bash 路径样板收进 `lib.sh`），以及 §2 的 `publish.sh` 条件提取——这三处是真正「删除复杂度而非搬运复杂度」的 code-judo，做完后整条管线的读面会显著更利落。§4（legacy md 解析器）需先确认是否有意保留再决定删/标注。

> 本评审仅产出报告，未修改仓库代码。（后续依用户“一并处理”指示已逐项落地，见下方《实施记录》。）
---

## 实施记录（2026-08-31，依用户"一并处理"指示）

评审建议已全部落地，行为保持不变，`kb.py test`（38 项）与 `kb.py check` 全绿，`publish.sh --dry-run` 端到端通过；净删除约 250 行。

| 评审条目 | 实施 |
|------|------|
| §1 `.publish-tokens` 5 处实现 → 收敛 | 新增 `tools/publish_tokens.py`（唯一 reader/writer：`read_publish_tokens` / `write_publish_token`，含 BACKUP_* 键放字段1、文档键放字段2 的位置差异封装）。`token_bootstrap._read_tokens/_update_tokens`、`line_report._read_tokens`、`cleanup_90_md.read_target_tokens` 全部改为调用共享助手；原逐字节重复的读取体已删除（仅留单行委托别名）。docx 名推导统一为 `registry_lib.docx_output_name`（`registry_lib._register_source`、`registry_manifest._docx_name`、`token_bootstrap._docx_output_name` 三处收敛）；"按 source 查注册项"统一为 `registry_lib.entry_by_source`（`publish_log._entry_for_source`、`token_bootstrap._entry` 收敛）。 |
| §2 `publish.sh` 重复条件 | 新增 `is_target()`（4 处重复的 TARGET 过滤条件收敛为一次调用）；`.publish-tokens` 读取收敛为 `load_doctoken()`（初始与 bootstrap 后共用，删除重复块）。 |
| §3 `append_publish` flag 累积 | 拆出显式子操作 `build_record` / `write_record` / `persist_record` / `write_repo_summary` / `update_last_published`；`append_publish` 仅组合它们，签名与 CLI/`publish.sh` 调用不变。 |
| §4 legacy md registry 解析器 | 判定为有意向后兼容（`test_registry_parser_uses_header_order` 在用显式 md 路径），保留功能，仅在 `parse_registry` docstring 标注"md 仅为旧提交/恢复的 back-compat"；未删以免破坏既有测试与恢复链路。 |
| §5 proxy CORS 硬编码 host | 移入配置：`Config["cors_hosts"]`（默认含原 host），`load` 支持配置；`_exchange_request` 由字符串字面量改为 `if host in config["cors_hosts"]`。 |
| §6 `feishu_mitm_proxy.__all__` facade | 删除 `__all__` 与冗余 re-export，仅保留 CLI 所需 import；`test_pipeline.py` 改为直接从 `proxy_core`/`proxy_certs` 引符号。 |
| §7 bash 路径样板 ×5 | 新增 `tools/lib.sh`（`normalize_path`/`setup_paths`/`default_pub` + 自动 source 定位；`setup_paths` 依调用链解析规范化的 SCRIPT_DIR/ROOT）；`ship.sh`/`publish.sh`/`backup_commit.sh`/`check_git_auth.sh`/`test_check_git_auth.sh` 五处各收敛为 `SCRIPT_DIR=...; . "$SCRIPT_DIR/lib.sh"`。 |

### 验证
- `python -m py_compile`（10 个改动的 py）：通过。
- `bash -n`（6 个改动的 sh / lib.sh）：通过。
- `python tools/kb.py test`：38 项通过 + `test_check_secrets.py` + `test_check_git_auth.sh`（覆盖 lib.sh 源码链路）全绿。
- `python tools/kb.py check`：8 文档 front matter / registry 契约一致。
- `bash tools/publish.sh --dry-run`：manifest 生成、token 完备、docx 构建 10 项全通过（未上传）。
- `git diff --stat`：14 改 + 3 新增，净删约 250 行（删除复杂度多于新增）。
