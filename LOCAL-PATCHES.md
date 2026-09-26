# 本地补丁说明（相对于上游 main）

> ⚠️ **本文档是逐补丁流水账，头部信息已过期。**
> **要了解现状、要合并上游，请先读 `HANDOVER.md`** —— 那是权威入口，
> 含正确的基线 commit、补丁总览、测试基线、合并指引，以及测试过程踩的坑。
>
> 本文档保留的价值是**历史记录**（含每次同步上游的过程），但注意：
> - 头部写的基线 `65741ae` 与测试数 `234 passed` **已过期**
> - 文档里有**两个「补丁 D」**（编号冲突），`HANDOVER.md` 已重新编号

> 上游：https://github.com/huangzuomin/personal-kb-steward
> 本文件记录**本机对工具源码的改动**，`git pull` 前请先看这里。

## 为什么要打补丁

上游把「链接解析」的目标限定为 **只索引 `.md`**，且用 `Path(...).stem` 剥扩展名。
在 OLD_VAULT 这类 Obsidian 库里，这两点导致**大量假断链**：

| 现象 | 真实原因 |
| --- | --- |
| `![[报告.pdf]]`、`![[图片.png]]` 全部报断链 | 附件未被索引（只收 `.md`） |
| `[[方案（3.0）]]` 永远解析不到 | `Path.stem` 把 `（3.0）` 当扩展名剥掉 |
| `[[\#我平常都看什麼書]]` 报断链 | 正则把 `\#` 当锚点截断（本库 `\#` 是文件名的一部分） |
| `[[PDF] xxx](https://…)` 报断链 | 正则误吞 Markdown 链接文本 |

**首次 `lint`：60 条"断链" → 其中 52 条是上述假阳性。** 修完工具后真实断链只剩 8 条。

## 改动清单

### `core/vault.py`（+85 行）

1. **`VaultIndex` 新增 `by_attachment` 字段** —— 附件索引（小写 basename → 相对路径列表）。
2. **新增 `build_attachment_index(root)`** —— 扫描全库非 `.md` 文件。
   与 `include_dirs` 无关，因为 Obsidian 的链接解析是**全库按名**的。
3. **新增 `extract_wikilinks(text)`** —— 替代原 `re.findall(r"\[\[([^\]|#]+)")`：
   - `\#` 不截断，事后还原为 `#`
   - 跳过含换行的与以 `[` 开头的（Markdown 链接文本）
4. **新增 `wiki_stem(target)`** —— 只在**真的以 `.md` 结尾**时才剥。
5. **新增 `resolve_link(index, target)`** —— 解析顺序：
   相对路径 → 文件名 stem → **附件名** → 标题。

### `scripts/personal_kb_steward.py`（净 -1 行）

1. 删除本地的三个 helper，改为**从 `core.vault` 导入**（保持文件 < 1700 行，
   这是 `tests/test_runtime_boundaries.py` 的架构约束）。
2. **`noncanonical_link` 判定收窄**（新增 `is_noncanonical_strict`）：
   只有「**显式写了路径或扩展名**、但解析结果与之不符」才报警。
   裸 stem（`[[AI和媒体]]`）是 Obsidian 惯例，**不再刷屏**。

## 效果

| 指标 | 修补前 | 修补后 |
| --- | --- | --- |
| `lint` 报的断链 | 60 | **0**（还需修 8 条数据，见下） |
| `noncanonical_link` | 1933 | **0** |
| 风险总数 | 2129 | 136 |
| 知识库文件改动 | — | **0**（纯工具侧修复） |

> 剩下的 8 条是真数据问题（插件幻影、MuseScore 残渣、模板占位），
> 已在知识库侧单独修完，最终全库活跃区断链 **0**。

## 测试状态

```
3 failed, 234 passed, 75 subtests passed
```

3 个失败**全部是 Windows 环境限制，与补丁无关**（已用 `git stash` 对照验证，
补丁前后完全一致）：

- `test_shallow_clone_does_not_silently_shrink_pr_range` —— `git clone file://` 在 Windows 下失败
- `test_symlink_escape_rejected` —— 需要创建目录符号链接（需开发者模式/管理员）
- `test_links_do_not_export_external_notes_or_redirect_cache` —— 派生索引跨盘行为

**补丁曾引入 1 个新失败**（`test_runner_is_smaller_after_phase_14`，文件超 1700 行），
已通过把 helper 下沉到 `core/vault.py` 解决，现为 1694 行。

## 同步上游时的注意点

```bash
cd tools/personal-kb-steward
git stash                    # 先存本地补丁
git pull origin main
git stash pop                # 大概率冲突：core/vault.py 与 scripts/personal_kb_steward.py
```

**冲突解决要点**：上游若未修附件索引，务必保留本地的 `by_attachment` 与
`wiki_stem` 逻辑；否则 52 条假断链会立刻回来。

---

## 补丁 D：LLM 超时与端点固化（2026-09-19）

### 背景

接入 GLM Coding Plan 后 `task --llm` 首跑直接 `TimeoutError`。
二分实测证明**不是端点问题，是超时不够**：

| payload 字符数 | 结果 | 耗时 |
| --- | --- | --- |
| 13,504 | ✅ | 57.2 s |
| 27,009 | ✅ | 48.3 s |
| 40,000 | ✅（超时放宽 240 s） | 63.5 s |
| 40,514 | ❌ 超时 | >100 s |
| 54,019（真实 payload） | ❌ 超时 | >200 s |

真实 `discover_topics` payload = 8 篇 × 6000 字符 = **54k 字符**，稳定越过默认 60 s。

### 改动

`config.json` 的 `llm` 段：

```diff
-  "base_url": "https://api.openai.com/v1",
-  "model": "",
-  "timeout_seconds": 60
+  "base_url": "https://open.bigmodel.cn/api/coding/paas/v4",
+  "model": "GLM-5.3-Flash",
+  "timeout_seconds": 300
```

`config.json` 是 `.gitignore` 内的本地文件，**不影响上游同步**。

### 环境变量名陷阱（上游文档错误）

> 官方/上游文档写 `LLM_MODEL`，**代码读的是 `OPENAI_MODEL`**。

`call_chat_completion()` 只认 `OPENAI_BASE_URL` / `OPENAI_MODEL` / `OPENAI_API_KEY`，
`LLM_MODEL` 这个名字在代码里不存在。按文档配会抛 `Missing LLM model`。

### 端点选择

`core/llm.py` 裸 POST 到 `{base_url}/chat/completions`，因此只能用
**OpenAI Chat Completion 协议**端点 `.../api/coding/paas/v4`。
`.../api/anthropic`（Messages 协议）和 `.../api/v1`（Response 协议）路径都不匹配。

---

## 🔴 上游缺陷（未修，仅记录）：LLM 产出与 planned_pages 不连通

**现象**：`task --llm` 显示 `LLM runtime：provider，items=6，ok=True`，
LLM 返回 6 张高质量选题卡；但 `planned_pages` 仍是模板文，两者交集 **0**。

**根因**：两条独立代码路径，从未对接。

| 路径 | 产出 | 去向 |
| --- | --- | --- |
| `core/skill_runtime.py::run_skill_runtime()` | 真 LLM 结果 | **仅**写入 plan 的 `llm_runtime.items` / `previews`（展示用） |
| `scripts/…::mvp_executor_plan()` | 决定 `planned_pages` | 调 `skills/<name>/executor.py::execute()` |

而 `skills/topic-insight-miner/executor.py` 是**纯 Python 硬编码模板**，
**不读 LLM、不读 `use_llm`**（只有 `raw-ingest-router` 和 `topic-research-compile`
两个 executor 读了 `use_llm`）。

**结论**：`--llm` 的真实语义是「额外跑一次 LLM 给你看看」，
不是「用 LLM 生成落盘内容」。**开不开 `--llm`，落盘页面完全一致。**

**未修原因**：修复后 `apply-plan` 会真的写库，需用户先确认写入目标与字段体系。

### 若将来要修（方案 1）

在 `make_execution_plan()` 中，当 `llm_result["ok"]` 为真时，
直接用 `llm_result["items"]` 构造 `planned_pages`，跳过 executor 模板路径。

两个必须一并处理的点：

1. LLM 返回的 `path` 带 `wiki/` 前缀，**必须映射到 `cfg["write"]` 里的 `_kb-steward/`**，
   否则会把上游的幻影 `wiki/` 目录树重新造进知识库；
2. 需重新串接 `validate_markdown()` / `origin` / `manual_review` 三个字段。

---

## 2026-09-19 同步上游 d4853bc 后的补丁清单

上游 `d4853bc`（*Fix LLM topic writeback into reviewed plans*）已修复
「LLM 产出不进 planned_pages」这个缺陷，并新增 `core/llm_plan.py` + 4 个回归测试。

**因此我原先自己写的 LLM 桥接补丁已弃用**（`core/llm_pages.py` 已删除），
改用上游实现。上游那版更稳：程序掌管落盘位置与生命周期，模型只供内容与引用。

### 仍然保留的补丁（上游未包含）

| 补丁 | 文件 | 位置 | 为什么还要 |
| --- | --- | --- | --- |
| A 附件索引进解析目标 | `core/vault.py` | `build_attachment_index()` + `resolve_link()` 附件分支 | 上游 `build_index()` 仍是 `extensions = {".md"}`，37 个 `.pdf/.png/.jpg/.mp4` 附件嵌入全被误报断链 |
| B `wiki_stem` | `core/vault.py` | 同名函数 | 上游仍用 `Path(...).stem`，会把 `方案（3.0）` 截成 `方案（3` |
| C `extract_wikilinks` | `core/vault.py` | 同名函数 | 上游仍是 `re.findall(r"\[\[([^\]|#]+)", text)`——在 `#` 处截断、且误吞 Markdown 链接文本 |
| E `noncanonical_link` 豁免 | `scripts/personal_kb_steward.py` | `is_noncanonical_strict()` | 上游仍无豁免，会把 1933 条裸 stem 链接全报成非规范 |

`core/vault.py` 的改动是**纯增**：只替换 1 行（`build_index` 的 return，为带上 `by_attachment`），
其余 82 行全是新增函数。上游自 `65741ae` 起未改动 `vault.py`，所以可安全整体覆盖。

### 验证

| 指标 | 值 |
| --- | --- |
| 断链 | **0** |
| 非规范双链 | **0**（原 1933） |
| 风险桶 | P0=0 / P1=100 / P2=1 / P3=1 |
| runner 行数 | **1699**（上限 1700） |
| 测试 | `4 failed, 238 passed`（纯上游为 `3 failed, 239 passed`；多出的 1 个是 flaky） |

### 同步操作注意

**不要在本机用 `git stash`。** 它会被 SIGTERM 打断并连带删除 `.git/refs/`，
导致 git 报 `not a repository`。改用：

```bash
cp core/vault.py /tmp/keep_vault.py          # 手工备份要保留的文件
git checkout -- core/vault.py                # 还原到上游
# ...同步...
cp /tmp/keep_vault.py core/vault.py          # 再放回来
```

若已中招，恢复 refs：
```bash
mkdir -p .git/refs/heads .git/refs/tags
printf '<sha>\n' > .git/refs/heads/main      # sha 取自 .git/ORIG_HEAD
rm -f .git/AUTO_MERGE
```

---

## 2026-09-19 二次同步：上游 PR #14（`1355b1a`）

**上游动了 3 个文件：`core/validator.py`、`core/skill_runtime.py`、`tests/test_llm_runtime.py`。**
**没有碰 `core/vault.py`，也没有碰 `scripts/personal_kb_steward.py`。**

→ 声明的四条补丁 **全部零冲突**，`git merge --ff-only origin/main` 干净快进。
→ runner 行数仍 **1699**（< 1700 上限）。
→ 断链 **0** / 非规范 **0** 的效果不变。

### 上游这次修的是什么（与我们的补丁同族，但方向不同）

我们修的是「**裸 stem 是 Obsidian 惯例，不该判为 noncanonical**」（豁免误报）。
上游修的是「**`[[X]]` 应当能解析到本次提供的文档**」（补全解析能力）。

两者都在治「**链接识别口径**」这一个病根，只是从两侧下手，**不冲突**。

上游新增 `core/validator.py`：
- `_link_target()` —— 剥 `[[ ]]`、切 `|` 别名、切 `#` 锚点、`\` → `/`
- `_known_link_index()` —— 别名集 = `路径 ∪ 去.md ∪ 文件名 ∪ stem ∪ title`（含 casefold）
- `resolve_known_link()` —— **唯一命中才认**，多命中/零命中都返回 `None`
- `canonicalize_related_links()` —— 可解析的就地改写成完整相对路径

### 复检记录

| 检查项 | 结果 |
| --- | --- |
| 五种链接形态 | 三种合法形态全部解析成功；不存在/散文句子正确拦下 |
| 上一轮 13 条 issue 重放 | **0 issues** ✅ |
| ff-merge 冲突 | 无 |
| runner 行数 | 1699 ✅ |
| 库体改动 | 无（2184 md，`_kb-steward/` 0 文件，`--apply` 未执行）|

---

## 2026-09-19 本地新增补丁 D：渲染输出契约（2 文件）

**性质：本地新增，未提上游。向后兼容。**

### 为什么需要

模型把 `risks` 写成散文段落（`str` 而非 `list[str]`），报错
`LLM 选题 risks 必须是字符串列表`。查下来发现**两处都缺**：

1. `core/skill_runtime.py` 的 `output_contract` **只声明了 8 个必填字段**，
   而 `core/llm_plan.py::_strings()` 实际会校验 **11 个可选字段**的形态 —— 一个都没写进契约。
2. 更关键：`core/skill_loader.py::build_system_prompt()` **压根没渲染 `output_contract`**。
   契约只躺在 user payload，system prompt 只说 "Follow the SKILL.md contract exactly"，
   而 `skills/topic-insight-miner/SKILL.md` 从未定义这些字段的类型。

模型两边都看不到说明，只能猜。**这是契约缺失，不是模型能力问题。**

### 改动

| 文件 | 内容 |
| --- | --- |
| `core/skill_runtime.py` | 新增 `required_item_types`（8 个必填字段类型）、`optional_item_types`（11 个可选字段类型）、`type_rules`（数组必须返回 JSON 数组） |
| `core/skill_loader.py` | `build_system_prompt(spec, contract=None)` 新增可选参数并渲染契约；**不传时行为与上游完全一致** |

### 效果（实测，连续两次）

| ok | writeback_used | writeback_pages | issues |
| --- | --- | --- | --- |
| True | True | 5 | 0 |
| True | True | 5 | 0 |

`risks` → `list`；`related` → 规范完整路径；散文 related 消失。

⚠️ **注意：这是「8 篇 ×1800 字符」下的结果。原始 46k payload 仍会超时（未修）。**

### 单测

`3 failed, 238 passed, 4 skipped, 75 subtests passed`
3 个失败**已在纯上游 `1355b1a` 上复现**，与本补丁无关。

---

## 2026-09-19 本地新增补丁 E：检索上下文总预算（2 文件）

**性质：本地新增，未提上游。默认关闭（`max_total_source_chars: 0`），开了才生效。**

### 为什么需要

`Retriever.documents()` 只有「**每篇**上限」（`max_chars=6000`），**没有「总量」上限**。
8 篇 → 正文 48000 字符 → payload **46k** → **稳定 300s 超时**（实测连试 3 次全挂）。

递进探针证明不是 provider 问题：8k→11s、14k→88-113s、46k→297s/超时。

### 改动

| 文件 | 内容 |
| --- | --- |
| `core/retrieval.py` | `documents(notes, max_chars, total_budget=0)`：按 `budget/len(notes)` 分公平份额，后面的文档借用前面未用完的余额 |
| `scripts/personal_kb_steward.py` | `llm_documents(...)` 同步；调用点读 `scan.max_total_source_chars` |

**配置**：`scan.max_total_source_chars`（默认 `0` = 保持上游行为）。本地设 `22000`。

### 分配精度（已验）

| 设置 | 每篇 | 总量 |
| --- | --- | --- |
| `budget=0`（上游行为） | 6000 ×8 | 48000 |
| `budget=22000` | 2750 ×8 | 22000 |
| `budget=8000` | 1000 ×8 | 8000 |

**`budget=0` 时代码路径与上游逐字等价**，不会静默改变已有行为。

### 效果

```
payload 46k → 22k
ok=True | writeback_used=True | writeback_pages=6 | issues=[] | planned_pages=6
```

**6 个页面，全部落在 `_kb-steward/topics/`。**

### 单测
`3 failed, 238 passed, 4 skipped, 75 subtests passed` —— 与改动前完全一致，零回归。

---

## Patch F —— 写入路径权威（第 8 处）

**症状**：`config.write.sources_dir = "_kb-steward/sources"`，但 `init-kb` 的 plan 里
`planned_pages[*].rel_path` 全是 `wiki/sources/source-….md`。这个目录在库里根本不存在，
一旦 `--apply` 就会**凭空新建一个 `wiki/` 树**，正是用户明确要求消除的「幽灵目录」。

**根因**：`skills/topic-research-compile/renderer.py` 第 23 行硬编码了目录名，
而 `render()` 是被 `executor.py` 调用的——**渲染器自己不去读配置，调用方也没把配置传进去**。
这是本库第 8 次踩同一类坑：*声明式配置存在，但被硬编码字符串绕过。*

| 文件 | 改动 |
| --- | --- |
| `skills/topic-research-compile/renderer.py` | 目录改读 `data.get("sources_dir")`，兜底 `_kb-steward/sources`（不再出现 `wiki/`） |
| `skills/topic-research-compile/executor.py` | 新增 `target_dirs(cfg)` 只从 `cfg["write"]` 取目录；三处 `render({...})`（heuristic / llm / fallback 分支）全部传入 `sources_dir` |

### 验证

```
修复前：planned_pages 中 `wiki/sources/*` 计数 = 6
修复后：_kb-steward/sources 3 + _kb-steward/seeds 5 + _kb-steward/topics 1
        `wiki/` 前缀页面数 = 0
```

单测 `3 failed, 238 passed, 4 skipped, 75 subtests passed` —— 与 Patch E 后完全一致。

### 遗留

其余同族硬编码仍在（本次未动，因为不属于「写入目标」而是「读取检索」）：
`core/retrieval.py::DEFAULT_PREFIXES`、`core/index_builder.py:85`、`core/finalizer.py`、
以及 `scripts/personal_kb_steward.py` 的 `select_notes/query_results` 默认前缀与 328/379/381 行的
`retriever.select(..., prefixes=("wiki/…"))`。

**这些会让检索「查不到刚写出来的东西」**：文件写在 `_kb-steward/`，检索却在 `wiki/` 里找。
因为 `_kb-steward/` 当前是空的，症状尚未暴露；**在首次 `--apply` 之后必须立刻修**，
否则「写完 → 检索 → 发现没命中 → 重复写」的循环会静默发生。

---

## Patch G —— 读取层路径权威（Patch F 的孪生兄弟）

**Patch F 只修了「写」，没修「读」。这一半更危险。**

### 症状

写完的东西，工具自己找不到：

| 环节 | 修前行为 |
| --- | --- |
| `init-kb` 写入 | `_kb-steward/sources/*.md`（Patch F 已修） |
| 检索 | 在 `wiki/seeds/`、`wiki/topics/`… 里找 ← **找错树** |
| 对象识别 | `is_knowledge_path()` 硬编码 `parts[0] == "wiki"` → `_kb-steward/` 页面**不被当作知识对象** |
| 扫描范围 | `config.json` 的 `include_dirs` **根本没有 `_kb-steward`** ← 最致命 |

**后果**：写完 → 下次跑检索不到 → 以为没做 → **重复生成同一篇**。
全程零报错，只是安静地重复劳动、污染库。

### 第 4 层问题：扫描范围（最深的一层）

`config.json` 的 `scan.include_dirs` 原本是：
```json
["4-项目","2-领域","3-资源","5-归档","1-每日记录","raw","quicknote"]
```
**没有 `_kb-steward`。** 所以即使前 3 层都修对，写进去的文件也**永远进不了索引**。
已补 `_kb-steward`。

### 改动

| 文件 | 内容 |
| --- | --- |
| `core/retrieval.py` | 新增 `knowledge_prefixes(cfg)` / `retrieval_prefixes(cfg)` / `knowledge_prefixes_with_inputs(cfg)`，全部从 `config.write.*` 取；`Retriever.select(prefixes=None)` 默认走配置。新增 `bind_topic_prefix()` / `topic_prefixes()` / `is_topic_page()` |
| `core/knowledge_objects.py` | 新增 `bind_knowledge_roots(cfg)` / `knowledge_root()`；`is_knowledge_path()` 改为匹配配置里的知识根，**默认仍是 `wiki`**（不配置即保持上游行为） |
| `core/reconcile.py` | 错误文案不再写死 `wiki/` |
| `core/index_builder.py` | 新增 `indexed_dirs(cfg)`；README 生成、核心入口、活跃专题全部按配置解析 |
| `core/finalizer.py` | 新增 `write_dirs(cfg)`；4 个聚合页目标 + 全部 `related` 链接按配置解析 |
| `scripts/personal_kb_steward.py` | `select_notes` / `query_results` 默认前缀走配置；3 处 `retriever.select(..., prefixes=(...))` 改为配置驱动；`page_has_blocked_placeholder` 的 topics 判定走配置 |
| `config.json` | `scan.include_dirs` 补 `_kb-steward` |

### 防回归测试

`tests/test_source_traceability.py::test_query_results_recall_follows_config_write_dirs`
—— 把 `write.sources_dir` 指到 `_kb-steward/sources`，断言检索**能命中**该目录，
且显式传 `prefixes=("wiki/sources/",)` 时**不会**命中（显式参数仍然权威）。

### 验证

```
knowledge_prefixes(cfg) → 10 个 _kb-steward/ 前缀
is_knowledge_path('_kb-steward/topics/x.md') → True   （⚠️ 需先 bind_knowledge_roots(cfg)）
is_knowledge_path('raw/剪藏/y.md')           → False（原料不是知识对象，正确）
init-kb plan → _kb-steward/sources 3 + seeds 4 + topics 1，wiki/ 幽灵页 = 0
runner 行数 1698（< 1700）✅
```

> ⚠️ **此处原文写的是「`wiki/` 残留 = 0」—— 那是错的，已更正。**
> 实测 `grep -rn '"wiki/' core/ scripts/ skills/ --include=*.py` 有 **10 行**：
> 8 行是有意的无配置回退常量（`FINALIZE_DIR_FALLBACK` / `LEGACY_INDEX_DIRS` /
> `DEFAULT_PREFIXES` / `LEGACY_KNOWLEDGE_DIRS` / `_dir_prefix()` fallback），
> **2 行是真正的残留**（`core/validator.py:70`、`scripts/personal_kb_steward.py:411`，
> 属「source too broad」措辞，见 `HANDOVER.md §7.3`）。
> 详细清单与逐行判定见 `HANDOVER.md §8.4` 第 3 条。

### 🔴 一个必须记住的教训

**`knowledge_objects.is_knowledge_path()` 原本把 `wiki/` 写死在对象身份层。**
这意味着换布局不只是「找不到文件」，而是**对象身份整个失效**——
`object_id`、`revision`、`canonical_path` 全部不生效，知识对象退化成普通 Markdown。
改布局时这一层最容易漏，因为它不在「写入」也不在「检索」的直觉范围内。

---

## Patch H —— 排除生成型索引页（`scan.exclude_files`）

**问题**：`raw/剪藏/0-MOC.md`（12,271 字符）是自动生成的**导航索引**（「被引用最多的笔记」清单），
却因为落在 `include_dirs` 里，被当作原料喂给了 LLM。

实测证据：用 6 篇探针做检索时，`0-MOC.md` **每次都排在第 2 位**——
因为它罗列了所有标题，任何关键词都能命中它。这意味着它不只是浪费预算，
还会**污染检索排序**。

**修法**：`core/vault.py` 新增 `excluded_note()`，读 `scan.exclude_files` 配置：

```python
def excluded_note(cfg, path) -> bool:
    names = {str(n).strip().lower() for n in (cfg["scan"].get("exclude_files") or []) if str(n).strip()}
    if not names:
        return False
    return path.name.lower() in names or path.stem.lower() in names
```

**默认空列表** → 上游 vault 不配置时行为完全不变（零破坏）。

**本库配置**：`"exclude_files": ["0-MOC.md"]`

**验证**：
```
raw 索引数  134 → 132     （两个 0-MOC.md 被排除）
索引里残留 0-MOC.md = 0
```

---

## Patch I —— 候选页从配置驱动（清除硬编 demo 语料）🔴 P0

**这是 S0 校准批抓出的最严重缺陷。**

### 缺陷表现

S0 跑 6 篇探针（雁荡山民国摄影史、AI Adoption 指南、NAS 部署问答、漫画工具、PAI 研报、推文线程），
产出 8 页。其中 **6 页 source note 正常，但另外 2 页完全无关**：

```
_s0-steward/topics/温州人工智能创新发展路径.md
_s0-steward/material-packs/温州AI政策与产业研究资料包.md
    sources = 全部 6 篇（含雁荡山老照片、NAS 部署问答）
```

**一篇讲民国摄影史的文章，被列为「温州 AI 政策与产业」的证据。**

### 为什么是最高风险

| 属性 | 值 | 问题 |
| --- | --- | --- |
| `confidence` | `medium` | 不是 low，不触发质量门 |
| `review_required` | **`false`** | **不进人工审核队列** |
| 正文原话 | 「这是初始化 pipeline 自动生成的候选页，**可直接落盘进入 growing 状态**」 | 自称可免检转正 |

→ 一个明显错误的页面：**不拦截、不标记、自称可直接转正。**
→ 若 S1 开跑，每批多产 1–2 张，21 批 ≈ 40 张污染页，全部绕过审核。

### 根因

`core/initializer.py::promote_candidate_pages()` 里硬编了**上一个 vault 的 demo 语料**：
城市名（温州）、机构（人工智能局）、地名（瓯海）、产业（智能眼镜）全部写死在代码里。
触发条件只看 `len(sources) >= min_evidence_items_for_material_pack`（默认 5），
**完全不看 sources 与主题是否相关**。

### 修法

整段重写为**配置驱动**，代码里不再出现任何具体地名/机构名：

```python
def candidate_promotion_specs(cfg) -> list[dict]:
    specs = cfg.get("candidate_promotion")
    if not isinstance(specs, list):
        return []          # 无配置 = 不产出，这是更安全的默认
    return [s for s in specs if isinstance(s, dict) and s.get("title")]
```

每个规则显式声明 `kind / title / rel_dir_key / match_any / min_sources / body`。
**没有配置就不产出任何候选页。**

同时修掉模板里的自我转正声明与 `review_required`：

```python
"## 后续整理",
"- 这是初始化 pipeline 自动生成的候选页，主题边界尚未人工确认。",   # 原：可直接落盘进入 growing 状态
"- 转正为正式专题前，需核对全部来源是否确实支持本页主题。",
...
"review_required": True,   # 原：False —— 自动生成页必须人工确认主题边界
```

### 验证（沙箱重跑，batch-size 3）

```
修前：8 页 = 6 source + 2 假专题（温州…）
修后：3 页 = 3 source，含「温州」的页 = 0  ✅
耗时：5m08s → 2m27s（批次减半）
```

### 新增回归守卫

`tests/test_workflows.py::test_candidate_promotion_absent_config_produces_no_pages`
—— 造 7 篇「雁荡山老照片，与人工智能无关」，断言 `init_pages == []`。
**这个测试就是防「温州」复活。**

### 附带修复

`material-pack` 页正文曾**重复 `## 后续整理` 标题**（模板拼接缺陷），已随重写消除。

---

## Patch J —— `task` 命令无法触达 `topic-research-compile`

**问题**：`router.json` 6 条路由中，**没有任何一条指向 `topic-research-compile`**。

用户从 CLI 说「整理 raw 长文」→ 永远落到 `organize_kb` → `mindseed-grow`（种子卡）。
实测：`task --llm "PAI合成媒体框架研报"` →
`primary_skill=mindseed-grow`、喂入 `quicknote/2022-08-24~30` 日记、`planned_pages=0`、白跑 3m11s。

**结论**：`topic-research-compile` **只能由 `init-kb` 内部代码路径触发**，用户无法主动调用。

**这是设计层面的缺口，不是 bug** —— 修它要动 `router.json` 的语义（加一条路由），
会影响所有上游用户的 `task` 行为。**当前选择：不修，但在文档里写明。**
S0/S1 必须走 `init-kb`。

### 🔴 但这次"白跑"捞到了高价值情报

LLM 面对不匹配素材时，在 `Manual Review` 主动写：

> 「任务主题 PAI 合成媒体框架与本文档内容不匹配，请确认输入文件是否提供正确」

**它不硬编专题。** 这是 S0 第 2 问的独立佐证 —— 而且是在**最恶劣的输入条件下**得到的。

---

## Patch K —— 测试超时在负载下误报

`tests/test_dry_run.py` 用 30s 超时跑子进程。该测试的 vault 只有 7 个文件，
单独跑约 1 秒。但全量跑时因机器负载触发 `subprocess.TimeoutExpired` ——
**报的是超时，实际是负载抖动，不是挂起**。

修法：超时提到 180s，并写明注释解释为什么给这么宽。仍然能捕获真挂起。


---

## Patch I 扩展 —— demo 语料泄漏在 6 处（2026-09-19 交接前复核）

写 `HANDOVER.md` 时做「断言复核」，发现 **Patch I 第一版只修了 1/6**。
同一个 demo 语料（温州 / 人工智能局 / 瓯海 / 智能眼镜 / 先行市）还散落在另外 5 处。

| # | 位置 | 严重度 | 修法 |
| --- | --- | --- | --- |
| 1 | `core/initializer.py::promote_candidate_pages` | 🔴 P0 | `candidate_promotion` 配置驱动 |
| 2 | `core/finalizer.py::make_finalize_plan` | 🔴 高 | 标题从「提取的专题」派生；其余走 `finalize_aggregation` |
| 3 | `skills/topic-research-compile/executor.py::infer_topics` | 🟡 中 | `heuristic_topics` 配置驱动 |
| 4 | `core/retrieval.py::query_terms` 兜底词表 | 🟢 低 | 新增 `fallback_terms()`，用 query 自身词 |
| 5 | `scripts/…::select_notes` 兜底词表 | 🟢 低 | 复用 `core.retrieval.fallback_terms` |
| 6 | `scripts/…::evidence_items` 案例判定词 | 🟢 低 | 提取为 `core.retrieval.CASE_MARKERS`（通用词） |

### 🔴 第 2 处的教训：派生数据现成，只是没被用

`finalizer.py` 里**已经有** `top_topics`（来自 source note 的「## 提取的专题」），
但 4 个页面标题却用硬编温州名。**改用它之后行为完全兼容** ——
测试 fixture 的 source note 正文恰好含「温州人工智能创新发展路径」，
派生结果与硬编名字逐字相同，所以那条断言不改也能过。

> **教训：修「硬编」时先看旁边有没有现成的派生数据。**
> 有的话，改用它往往零行为变更。

### 🔴 附带踩的坑：runner 又超 1700 行

加 `CASE_MARKERS` + 兜底改动后 runner 变成 **1705 行**，超上限。
按既有教训（新逻辑放 `core/`）把 `CASE_MARKERS` 与 `fallback_terms`
下沉到 `core/retrieval.py` → **1697 行**。

### 新增回归守卫

- `test_candidate_promotion_absent_config_produces_no_pages`（initializer）
- `test_finalize_aggregation_without_config_produces_no_demo_pages`（finalizer）

### 最终状态（**已按三方实测更正，见 `HANDOVER.md §5.11`**）

```
── 测试 ──
纯上游 1355b1a      320 tests / 5 failed / 0 errors / 0 skipped
本补丁              323 tests / 5 failed / 0 errors / 0 skipped
失败集合            与纯上游逐项相同 → 新增的失败 = 无 → 零回归
                    （本补丁净增 3 个测试）
runner 行数         1698（< 1700 硬上限；纯上游也是 1698）

── 硬编语料 ──
core/ scripts/ skills/ 内    只剩解释性注释
另外                         上游自带的 scripts/fix_broken_links{,_v2}.py
                             里硬编了具体库的文件名（上游 4e9dfa0 引入，
                             不在调用链上，本补丁未动）

── 路径字面量 ──
"wiki/" 共 10 行：8 行有意的无配置回退 + 2 行已知残留（§7.3）
```

> ⚠️ **本块原文写的是 `tests=323 failures=3 errors=0 skipped=4` 与 `runner 1697` —— 已更正。**
>
> 两个更正都源于**同一件事**：这些数字是在**没跑验收命令**的情况下凭印象写的。
> - `failures=3 / skipped=4` 是在**符号链接不可用**的环境下测的：
>   `test_review_guards` 与 `test_derived_index` 各有一个测试此时 `skipTest`。
>   符号链接可用时它们会真跑，于是变成 `5 failed / 0 skipped`。
>   ⇒ **判断回归只能比「失败集合」，不能比「失败个数」。**
> - `runner 1697` 是 `a9801a9` 时的值；`11174ab` 补完 healthcheck 后是 **1698**。
>
> 教训见 `HANDOVER.md` 顶部的 **勘误（ERRATA）**。

## 2026-09-21 完整迭代版本部署记录

本次部署包含已验收的完整迭代应用树，以及工作记忆、写作材料包、说话人归属三处修复；不是只拷贝相对黑盒基线的7个文件。活配置、凭据、运行状态、原始知识库和存量卡片保持原样。实际部署结果、备份位置与部署后测试以同目录 `部署验收记录-2026-09-21.md` 为准；详细证据保存在工作区 `iteration-artifacts/2026-09-21-deployment/`。

## 2026-09-21 B07 修复：模型漏返回契约元数据不再丢弃整条候选（未部署）

**问题**：`core/json_contract.py` 的 `REQUIRED_ITEM_KEYS` 把 `confidence`、`review_required` 与
`title`/`summary`/`sources` 等**内容字段**同等对待，缺失即记为 issue → `skill_runtime` 置
`ok=False`、`previews=[]` → 下游 **0 个可审页面**。

真实后果（T1 隔离真跑实测）：同一任务、同一材料、同一代码，
首次 `items=1 → planned_pages=0`（`items[0] missing keys: confidence, review_required`），
重试 `items=2 → planned_pages=2`。内容完整正确、来源可追溯的候选，仅因两个**非内容字段**被全盘丢弃；
且退出码仍是 0，CLI 摘要行只写 `ok=False`，极易被误读为"跑完了"。

**改动（仅迭代区 `core/`，未同步到部署目录）**：

| 文件 | 改动 |
|---|---|
| `core/json_contract.py` | 新增 `CONTRACT_DEFAULT_KEYS = {"confidence": "low", "review_required": True}` 与 `apply_contract_defaults(data)`：只补**契约元数据**，绝不编造内容字段；补了 `confidence` 就强制 `review_required=True`；空串按缺失处理；返回可读 notes 使降级可见 |
| `core/skill_runtime.py` | 在 `validate_contract` 前调用 `apply_contract_defaults`，结果以新键 `contract_notes` 随 `llm_runtime` 落盘（不进 `issues`，不影响 `ok`）；LLM 异常早退分支同样补 `contract_notes: []` |
| `core/executor_adapters.py` | CLI 摘要下新增一行「契约降级提示：…」，仅提示、不改退出码 |
| `tests/test_contract_defaults.py` | 新增 7 项定向测试（合成样本，不含真实个人笔记内容） |

**为什么默认成 low / True 而不是保留原值**：`validator.validate_skill_items` 有
「confidence == low 必须 review_required」的约束；且 low + 强制复核是最保守取向，
不把模型猜测写成事实。内容字段缺失**仍然报错**（有测试覆盖）。

**验证**（`iteration-artifacts/2026-09-21-live-realgate/`）：
- A/B 回放（同一份真实被丢弃响应，无新模型调用）：旧代码 `ok=False / 0 页` → 新代码 `ok=True / 1 页`，
  页上 `confidence=low`、`review_required=True`，并留下契约降级提示。见 `evidence/b07-replay-ab.json`。
- 定向 + 相关套件 65 项通过；完整回归见 `evidence/B07-full-suite.log`。

### 部署记录（2026-09-22 08:06，已部署)

**方式：5 文件定点补丁，不是整树同步。** 与 2026-09-21 三处修复那轮必须整树同步的原因不同——
那次 7 个修复文件中有 4 个在部署副本里不存在；本轮被改的 3 个 `.py` 在生产里都已存在，
可逐文件替换 + 哈希核验。同步范围 = 上表 4 项 + 新增 `tests/test_contract_defaults.py`。

| 门禁 | 结果 |
|---|---|
| 全量备份 | 1125 个文件（`iteration-artifacts/2026-09-21-live-realgate/evidence/deploy-B07-20260922-0806/backup-20260922-0806`） |
| 5 个文件哈希 | 5/5 一致 |
| 部署侧独有资产 486 项 | 变更 0、丢失 0 |
| `git status` 删除行 | 0 |
| `validate_config.py` | 退出 0 |
| CLI 冒烟 `--help` | 正常 |
| 部署后定向回归（8 个相关测试文件） | **123 passed in 156.78s** |
| 部署后全量回归（排除 `test_ci_committed_diff.py`） | **993 passed / 89 subtests / 8 failed in 350.77s** |
| **相对部署前的新增失败** | **0**（失败集合与部署前逐条相同） |
| 知识库 | 今日被修改/新建文件 0，`_kb-steward/` 仍 349 个文件 |

**8 个失败与本修复无关**：均为符号链接权限类测试（`test_symlink_escape_rejected`、
`test_true_symlink_guard_evidence_or_explicit_unverified` 等），靠「本机无建符号链接权限」触发守卫；
2026-09-21 基线里它们是被 skip 的 9 项，现已能建符号链接 → 断言反转为 failed。
**已于 2026-09-22 在未经本修改的部署代码上复跑，8 项 2.05 秒内全部复现**，确认为环境漂移。

**未闭环**：`tests/test_ci_committed_diff.py`（18 项）在本机不稳定，前 17 项通过、
最后一项 `test_shallow_clone_does_not_silently_shrink_pr_range` 原地不动；
已在**未改动的部署代码**上复现同样现象 → 环境问题（本机单次 git 调用约 1.2–1.6 秒）。

详见 `D:/OLD_VAULT-整理后-20260919/iteration-artifacts/2026-09-21-live-realgate/B07-回归验证结论.md`
与同目录 `evidence/deploy-B07-20260922-0806/`。部署侧验收记录：
`tools/personal-kb-steward/部署验收记录-B07-2026-09-22.md`。

**回滚**：从 `backup-20260922-0806` 按文件还原上述 5 项即可；**不要用 `/MIR` 整体镜像**
（会抹掉部署后新产生的数据）。

---

## 2026-09-22 B02 修复：标题不再被盲切成半句/半词（未部署）

**现象**：seed 卡标题出现半句甚至半词，例如

- `在 AI 绘图工具快速迭代的环境下，如何既保持技能不快速过时、又不让重新学习的成`
- `半年未使用 Stable Diffusion，技术演进已使既有经验被淘汰，Com`
- `笔记中并存两条水墨风格提示词，均以极简禅意自然景观为主题：一条用日出金光渲染巨石`

**根因**：`core/atomic_seed.py:289`

```python
title = _single_line_text(raw.get("title"), 60) or statement[:40]
```

`_single_line_text` 是**校验**函数（空 / 超 60 字 / 含换行即返回 `None`），一旦模型没给 `title`
或给了超长的，就退化成 `statement[:40]` —— **盲切 40 字**。`Com` 是英文单词被切成半截。

**改动**（仅迭代区 `core/`，尚未同步到部署目录）：

| 文件 | 改动 |
|---|---|
| `core/atomic_seed.py` | 新增 `_short_title(text, limit)`：取预算内**最靠后的**子句/句末边界收短；去掉悬空标点；绝不切断英文单词（回退到词边界）；**只在真的硬切时才加省略号**，并为此预留一格 |
| `core/atomic_seed.py:289` | 模型未给 `title` → `_short_title(statement, 40)`；模型给了但超长/含换行 → `_short_title(supplied, 60)`（**收短保留，不再整条丢弃**） |
| `core/atomic_seed.py`（`_preview_item`） | 同样的盲切 `unit["quote"][:40]` 换成 `_short_title(unit["quote"], 40)` |
| `tests/test_short_title.py` | 新增 11 项定向测试（合成样本，不含真实个人笔记） |

**为什么按「位置最靠后」而不是「标点强度」选边界**：先按强度试过，结果在第 3 例上**变差**——
它在第一个逗号（14 字）就收尾，丢掉了「均以极简禅意自然景观为主题」这个要点。
改成取预算内最靠后的边界后：

| | 旧（盲切 40 字） | 新 |
|---|---|---|
| 1 | …又不让重新学习的**成** | …如何既保持技能不快速过时（30 字） |
| 2 | …被淘汰，**Com** | …技术演进已使既有经验被淘汰（36 字） |
| 3 | …一条用日出金光渲染巨石 | …均以极简禅意自然景观为主题（28 字） |

**开发过程中被测试抓到的一个真 bug**：硬切时加了省略号却没给它预留位置，
导致标题 61 字超出 60 上限。已修（硬切改用 `limit - 1` 的预算）。

### 部署记录（2026-09-22 08:50，已部署）

`deploy_patch.py B02 core/atomic_seed.py tests/test_short_title.py LOCAL-PATCHES.md` → verdict PASS。

| 门禁 | 结果 |
|---|---|
| 全量备份 | 1128 个文件（`evidence/deploy-B02-20260922-0850/backup-20260922-0850`） |
| 3 个文件哈希 | 3/3 一致 |
| 部署侧独有资产 488 项 | 变更 0、丢失 0 |
| `validate_config.py` / `--help` | 退出 0 |
| 部署后定向门禁（`test_short_title` + `test_atomic_seed` + B07 那 8 个相关文件） | **158 passed in 131.46s** |
| 部署后全量回归（排除 `test_ci_committed_diff.py`） | **1004 passed / 89 subtests / 8 failed in 329.50s** |
| **相对部署前的新增失败** | **0**（失败集合与已知 8 项逐条相同） |
| 知识库 | 今日被修改/新建文件 0，`_kb-steward/` 仍 349 |

部署侧验收记录：`tools/personal-kb-steward/部署验收记录-B02-2026-09-22.md`。
回滚：从 `backup-20260922-0850` 按文件还原，并删除新增的 `tests/test_short_title.py`；
**不要用 `/MIR` 整体镜像**。

---

## 2026-09-22 B08 修复：人工拒绝不再阻塞整轮记账 + 中文查询切词 + 检索范围可配置（已部署）

一次补丁打包三处修复，共同指向同一个症状：**管家「看起来跑通了，实际什么都没长出来」**。

### A. 拒绝任一页 → 整轮不记账 → 无限重复（P0）

**现象**：page-scoped plan 里只要有一页被人工拒绝，整轮 `processed_index_advanced=False`，
`is_processed()` 永为 `False` → 下一轮**原样重选同一批源文件**，无限重复。
唯一绕法是「整轮全批准」，等于被迫写下自己不认可的页。

**根因**：`core/apply_execution.py` 的保守分支要求 `set(parent_catalog) ⊆ facts`
—— plan 里**每一页**的产物都要有事实。被拒页**按设计没有产物** → 判据不成立 →
`processed_completion_operations` 返回 `[]` → `scripts/personal_kb_steward.py`
判定 `processed_index_advanced=False`。**「人工拒绝」这个决定根本没被记进账。**

**修法**（3 文件）：

| 文件 | 改动 |
|---|---|
| `core/apply_execution.py` | ① `auth` 增加 `rejected_targets` 透传；② `processed_completion_operations` 新增 `selected_targets` / `rejected_targets` 关键字参数，保守分支判据由 `set(parent_catalog)` 改为 `selected or set(parent_catalog)`；③ 被拒页的源以**空 outputs** 记入完成操作 → 记成 `skipped`（终态）；④ 新增 `record_apply_completion(..., writer=...)`，把收尾逻辑搬出 runner |
| `core/state.py` | `update_processed_index` 改为**按源文件**（而非按操作）判定 `operation_status`：`needs_review` > `created`（有产物）> `skipped`（无产物） |
| `scripts/personal_kb_steward.py` | `:37` 导入 `record_apply_completion`；调用点改为 `record_apply_completion(..., writer=update_processed_index)`；manifest 加 `rejected_targets` 字段 |

**为什么要走 writer 注入**：`test_claim_evidence.py` / `test_synthesis.py` 用
`patch.object(steward, "update_processed_index", side_effect=OSError(...))` 注入写失败。
若在 `core/` 里直接 `from .state import update_processed_index` 再调用，
**patch 会静默失效而测试仍然 PASS**。改用本仓库既有的 writer 注入惯例
（同 `apply_subset_with_writer(..., writer=command_apply_plan)`），core 收 `writer` 关键字参数。

### B. 中文查询恒 0 命中

**现象**：任何长中文短语检索都命中不到内容。

**根因**：`core/retrieval.py` 的 `query_terms()` 用 `[\u4e00-\u9fff]+`
把**连续中文整段当成一个 term（不分词）**，而计分是**字面子串**匹配
（`matched = sum(t in hay for t in terms)`）→ 长中文短语几乎不可能命中。
只有查询里恰好含短英文词（`ai` / `python`）时才碰巧命中 —— **这是巧合，不是设计。**

**修法**：长中文段（> 3 字）切 **3 字窗口**（`CJK_WINDOW = 3`，
宽度**对齐索引侧 FTS5 trigram 分词器**）；≤ 3 字保持原样；
额度跨子句**轮转**（`TERM_BUDGET = 16`），避免第一个长词吃掉全部额度。

### C. 检索范围硬编码（配置改不了）

**现象**：本库检索覆盖率仅 **636/2176 = 29.2%**；
`4-项目/`、`3-资源/`、`2-领域/`、`5-归档/`、`1-每日记录/` **全部 0%**。

**根因**：`core/retrieval.py` 的 `INPUT_DIRS = ("raw","quicknote","inbox")`
是**模块级常量**，配置改不了。

**修法**：新增 `retrieval_input_dirs(cfg)` 读 `scan.retrieval_include_dirs`
（默认仍是历史三个，**行为不变**）；`retrieval_prefixes` 改用它。
`config.example.json` 补上该项示例值。

**🔴 不要与 `core/layout.py` 的同名 `INPUT_DIRS` 合并**：那个是**安全集合**
（知识输出不得与输入目录重叠，`knowledge_dirs()` 拿它做校验），
这个是**检索范围**。同值只是巧合，合并会把写库护栏一起放宽。

### 验证（离线复算 + 真实库对照）

**A**：用真实 run `20260922-082521-975114`（plan 3 页、批 2 拒 1、`generation_receipts` 缺失）离线复算 ——
修复前返回 `[]`，修复后覆盖 **3/3 源**；被拒页源 `1-每日记录/1-My Diary.md` 记 `skipped`（outputs=[]）、
批准页源记 `created`；索引 350 → 353；下一轮 `unprocessed_notes` 为空。
**生产 `processed-index.json` sha256 与 mtime 未变，backups 无新增，知识库零改动。**
单变量对照：只把判据改回 `set(parent_catalog)` → 必须失败 2 项（第 3 项「全拒绝」两次都通过，是**防过度记账的护栏**）。

**B**（真实库对照）：

| 查询 | 旧命中 | 新命中 |
|---|---|---|
| `温州文化辅助指南` | 0 | 8 |
| `全球人工智能与媒体融合平台概览` | 0 | 12 |
| `单位党务学习与工会事务记录` | 3 | 12 |
| `知识管理`（短，回归对照） | 6 | 6 |
| `温州`（短，回归对照） | 12 | 12 |

性能 0.40–0.75 秒/查询（2176 篇），terms 最多 16 个，不构成瓶颈。

**C**：覆盖率 **636/2176 = 29.2% → 1875/2176 = 86.2%**（仅剩 `5-归档/` 301 篇未纳入）。

### 新增测试

- `tests/test_rejected_page_accounting.py`（3 项，新建）：部分批准推进索引并记录拒绝 / 对照（不给 `rejected_targets` 则被拒源不记账）/ 全拒绝不伪造完成。
- `tests/test_retrieval.py`（+5 项，共 18 项）：长中文切窗、长中文可达、旧整串口径对照、检索范围可配置且默认不变、扩展范围可达主题目录（内建对照）。

### 门禁

| | 结果 |
|---|---|
| 定向 | 134 passed / 0 failed |
| 全量 | 6 failed / 1014 passed |
| **新增失败** | **0**（6 项为本机 Windows 目录符号链接行为漂移，在**未改动的生产代码**上逐条同样复现） |

### 部署记录（2026-09-22 11:52，已部署）

```
deploy_patch.py B08 core/apply_execution.py core/state.py core/retrieval.py \
    scripts/personal_kb_steward.py tests/test_rejected_page_accounting.py \
    tests/test_retrieval.py config.example.json LOCAL-PATCHES.md
```

→ verdict **PASS**。

| 门禁 | 结果 |
|---|---|
| 全量备份 | 1139 个文件（`evidence/deploy-B08-20260922-1152/backup-20260922-1152`） |
| 8 个文件哈希 | **8/8 一致**（`hash_mismatches: []`） |
| 部署侧独有资产 497 项 | **变更 0、丢失 0** |
| `git status` 删除行 | **0**（变更 129 → 131、未跟踪 82 → 83） |
| `validate_config.py` / `--help` | 退出 0 |
| 部署后定向（6 个测试文件） | **1 failed / 76 passed / 26 subtests** |
| 部署后全量（排除 `test_ci_committed_diff.py`） | **5 failed / 1015 passed / 89 subtests in 405.06s** |
| **相对部署前的新增失败** | **0** |
| 知识库 | B08 部署时 `config.json` 未变；随后 13:11 已开启 B 档；`processed-index.json` 未变；`_kb-steward/` 零改动 |

**对照实验（关键证据）**：从**部署前代码**（本次备份目录，已核对 4 个核心文件哈希 = 部署前值）跑
同一组 5 项 symlink 测试 → **5 failed in 2.60s**，失败集合与部署后**逐条相同**
→ 证明这 5 项是**本机 Windows 目录符号链接行为漂移**，与 B08 无关。

另：迭代区基线曾记 6 项，本次生产侧为 5 项，少的是
`test_public_baseline_runner_c3.py::test_main_refuses_symlink_artifact_root`；
单独复跑 **1 passed in 0.37s** → 是**负载/时序 flaky**，不是被修好，也不构成新增失败。

部署侧验收记录：`tools/personal-kb-steward/部署验收记录-B08-2026-09-22.md`。
回滚：从 `backup-20260922-1152` 按文件还原 7 项，并**删除新增的** `tests/test_rejected_page_accounting.py`；
**不要用 `/MIR` 整体镜像**。

**后续状态**：
1. **③ 已开启（2026-09-22 13:11）** —— 生产 `config.json` 写入 B 档
   `["raw","quicknote","inbox","1-每日记录","2-领域","3-资源","4-项目"]`，`5-归档/` 不纳入；覆盖率 29.2% → 86.2%。
2. **④ 凭据副本清理 + 库根加 `.gitignore`** —— 实测 `.env` 共 8 份，破坏性操作，待确认。
3. **⑤ 第三轮** —— 已于 15:45 销账收口（见下 §B09-前置），死循环已打破。

---

## 2026-09-22 B09 修复：写作入口也吃 `scan.retrieval_include_dirs`（已部署）

### 问题

`prepare_writing`（`scripts/personal_kb_steward.py:351/425/427`）走
`core/retrieval.py knowledge_prefixes_with_inputs()`，它把输入目录**写死成 `raw/`**：

```python
return (knowledge or knowledge_prefixes(cfg)) + ("raw/",)
```

同文件里的 `retrieval_prefixes()` 已经读了 `scan.retrieval_include_dirs`，**只有这条没读**。
→ 生产开启 B 档后，其他入口都能吃到 `2-领域/`，**写作入口完全吃不到，配置层面无解**。

实测：写作入口可及 **419/2178 = 19.2%**，主题目录可及 **0 篇**。

### 修复

`core/retrieval.py`：

```python
scope = ((cfg or {}).get("scan") or {}).get("retrieval_include_dirs")
inputs = ("raw/",) if scope is None else tuple(f"{d}/" for d in retrieval_input_dirs(cfg))
return (knowledge if knowledge is not None else knowledge_prefixes(cfg)) + inputs
```

**取舍：未配置时行为完全不变（仍是 `raw/`），只有显式配置才放宽** —— 老库零惊喜。

⚠️ 与 B08 同一条纪律：这里放宽的是**检索范围**，`core/layout.py` 的 `INPUT_DIRS`
（「知识输出不得与输入目录重叠」的**安全集合**）**没动**。两者同名同值纯属巧合，不可合并。

### 验证（先离线，后部署）

`iteration-artifacts/2026-09-21-live-realgate/verify_writing_scope_fix.py` → **VERDICT PASS**

| | 修复前 | 修复后 |
|---|---|---|
| 写作入口可及 | 419/2178 = 19.2% | **1877/2178 = 86.2%** |
| 主题目录可及 | **0** | **1236** |

判据：**只增不减** + 主题目录 0 → 正数。

### 部署记录（2026-09-22 17:28，已部署）

```
deploy_patch.py B09 core/retrieval.py tests/test_retrieval.py
```

| 门禁 | 结果 |
|---|---|
| 2 个文件哈希 | **2/2 一致** |
| 全量备份 | 1148 个文件（**已排除 `.env`**，沿用 B08 治本） |
| 独有资产 507 项 | **变更 0、丢失 0** |
| `git status` 删除行 | **0** |
| 定向 `test_retrieval.py` | 18 passed, 1 skipped |
| 写作链路定向（7 文件） | **91 passed, 1 skipped, 20 subtests** |
| 全量（排除 `test_ci_committed_diff.py`） | **1012 passed, 9 skipped, 89 subtests，0 failed**（117.50s） |
| CLI `--help` / `validate_config.py` | 退出 0 |

**verdict PASS**。部署侧验收记录：`tools/personal-kb-steward/部署验收记录-B09-2026-09-22.md`。

### 部署后生产实测（只读）

| 入口 | 修复前主题目录命中 | 修复后 |
|---|---|---|
| B 写作素材·AI和媒体 | 0/8 | **5/8** |
| C 选题·AI和媒体 | 0/8 | **7/8** |
| D 写作素材·发现雁荡 | 0/8 | **7/8** |
| E 写作素材·园博园 | 0/8 | **8/8**（全在 `4-项目/园博园`，0 重复） |

### B09-前置：销账收口（2026-09-22 15:45）🔴 含一条重要更正

第三轮 dry-run（run `20260922-140953-607400`）4 页来源与上一轮完全重复。
**我原先的假设「4 条全 reject 就能销账」是错的**：

`core/apply_execution.py:153-165` 在 `if not selected:`（无 approved 页）时**提前返回、
完全不记账**，manifest 只写 `status="rejected"` 而**退出码仍是 0**。
这是**有意设计**，护栏测试 `test_all_pages_rejected_does_not_fabricate_completion`
（防误操作整轮拒绝把一批源永久销账）。

**正确做法：一轮里至少要 approve 一页。**
本次：逐条比对源 `1-每日记录/一周计划.md` 后 `approve 9ca5971e`，其余 3 条 reject
→ 记账 **350 → 353**（1 `created` + 2 `skipped`），知识库只新增 1 页（渲染 6 个 `## `，正常）。
离线复算：入口 A 命中从「主题目录 1/5、含 3 篇重复」→「**4/5、重复 0/5**」，死循环确认打破。

**记账索引两个易错点**：
- 真身 `.openclaw/processed-index.json`（**不是** `.openclaw/state/processed-index.json`）
- `operation_status` 在 `processed[源路径]["skills"][skill]` 层，**不在顶层**
  （顶层只有 `title` / `current_sha256` / `skills`）

---

## 2026-09-22 B10 修复：启发式产出误触发敏感检查 → `init-kb` 整批中止（已部署）

### 问题

```
python scripts/personal_kb_steward.py init-kb --batch-size 3 --no-llm
→ SensitiveContentError: 敏感内容检查阻断：opaque_machine_line
   栈顶 skills/topic-research-compile/executor.py:350 assert_safe_content(data)
```

`assert_safe_content(note)`（原始输入）**先过了**，炸的是 `analyze_note()` 的**产物** ——
命中串是启发式**构造**出来的，不是原文照抄。`diagnose_safety_block.py` 逐篇复算：
**14 篇 raw 命中**，位于 `data.topics[0].title` 与 `data.key_facts[N]`。

**两处都是误报**：

1. `infer_topics` 回退分支 `re.sub(r"\s+", "", title)` 删掉标题所有空格 →
   `AmazonJustKilled50,000HumanVoices`：无空格 + 大小写 + 数字 + 逗号，正中 `suspicious_machine_line`（12 篇）。
2. `sentence_chunks` 对 `.`/`!`/`?` **无条件断句**，把 markdown 图片链接切碎：
   `!` 被单独切出后 `[](https://substackcdn.` 不再以 `![` 开头、绕过噪音过滤；
   残留片段里百分号编码把 `://` 变成 `%3A%2F%2F`，**藏掉了 URL 豁免用的 `/`**，读起来像裸 token。

**不是真凭据** → 不改写原文、不换 provider；修的是「启发式不该产出机器样 token」。

### 修复（4 个文件）

- `core/source_analysis.py`：`_is_noise` 增加 `suspicious_machine_line` 判定；
  `infer_topics` 回退分支保留单空格；新增 `_SENTENCE_BOUNDARY`，**ASCII 句末符仅在
  后接空白或文末时断句**（CJK 句末符始终断句）。
- `core/content_safety.py`：`SensitiveContentError` 增加 `reason` 属性（**只带规则码，
  不带命中值**），供调用方区分「真凭据」与「高误报启发式」。
- `skills/topic-research-compile/executor.py`：3 处 `except SensitiveContentError` 按
  `_HARD_SAFETY_REASONS` 分流 —— 真凭据 **仍然 `raise`**（安全事件，不降级）；
  只有 `opaque_machine_line` 记 `blocked` 并 `continue`（不写页面、不计 processed、
  在 `input_outcomes` 可见）。
- `tests/test_content_safety_false_positives.py`（新增，14 个用例）。

⚠️ **安全强度未被削弱**：既有契约测试 `test_secret_in_unused_response_field_is_blocked`
（真凭据出现在产出里必须中止）**原样通过**。

### 离线复算（真实 132 篇 raw，先离线后部署）

| 指标 | 修复前 | 修复后 |
|---|---|---|
| 敏感命中 | **14 篇** | **0 篇** |
| `bare_token` 形态单元（触发拦截那类） | 133 | **0** |
| 垃圾形态单元（bare_token + urlish） | 237 | **147**（−38%） |
| 真散文单元 | 524 | **593**（+69） |

### 🔴 撤回过一个更「大」的修法（有实测依据，记下来防重犯）

曾把**换行也作为切句边界**（能多救回「标题后被粘走的第一句」）。**已撤回**：

- 换行成边界后，长 JSON / 百分号编码碎片按长度抢进 `extract_info_units` 的 top-6，
  **反而挤掉散文** → prose 只 +13，而最终方案 +69；
- 更关键：它会让部分输入从「无页面」变成「启发式页面」，而**任何非 LLM 源页面在 apply
  时都会被 `page_has_blocked_placeholder` 拒绝并 `SystemExit` 中断整轮 apply**。

**纪律：不为了一个漂亮的局部指标去改会波及 apply 语义的东西。**

### 部署记录（2026-09-22 19:37，已部署）

```
deploy_patch.py B10 core/source_analysis.py core/content_safety.py \
    skills/topic-research-compile/executor.py tests/test_content_safety_false_positives.py
```

| 门禁 | 结果 |
|---|---|
| 4 个文件哈希 | **4/4 一致** |
| 全量备份 | 1173 个文件（**已排除 `.env`**） |
| 独有资产 532 项 | **变更 0、丢失 0** |
| `git status` 删除行 | **0** |
| 生产定向（6 文件） | **138 passed, 5 subtests** |
| 全量（排除 `test_ci_committed_diff.py`） | **1030 passed, 89 subtests，5 failed**（352s） |
| 那 5 项 failed | **与部署前基线逐项相同**（Windows 符号链接需管理员权限；已在未改动的生产代码上对照复跑） |
| CLI `--help` / `validate_config.py` | exit 0 |

**verdict PASS**。部署侧验收记录：`部署验收记录-B10-2026-09-22.md`。

### 部署后生产实测：阻塞解除

```
init-kb --batch-size 3 --no-llm  →  exit 0；计划 67 页；人工确认队列 22 项
```

### 两条相邻发现（**预存**，本轮未动，需单独排期）

1. **`page_has_blocked_placeholder` 因单个非 LLM 页面中断整轮 apply**
   （`scripts/personal_kb_steward.py:1238-1241,1271-1272`：`mode != "llm"` 即判占位 →
   `SystemExit`）。后果：**LLM 批次里只要一篇 provider 失败回退启发式，整轮 apply 被拒**。
   直接影响无人值守批量跑的稳定性。
2. **换行不是切句边界** → 「标题后的第一句」仍被整块丢弃。已用
   `test_heading_prefixed_prose_line_is_dropped_known_limitation` 把该局限钉住。

---

## 2026-09-22 B11 新增：`initialize.seed_stage` 开关（先只跑源卡，已部署）

### 背景（不是 bug，是按用户决定新增的**范围开关**）

用户 2026-09-22 的决定：**先只跑 raw 源卡，不产种子卡**。理由：`mindseed-grow`
当前定位错位（issue #26 —— 做成了「主题聚合卡」而非「单条发芽」），其测试产出的
147 张种子卡刚被归档，不该在定位修好前继续量产。

但一次 `init-kb --batch-size 3` 的实测构成是：

| 技能 | 页数 |
|---|---|
| `topic-research-compile`（源卡） | 3 |
| `mindseed-grow`（种子卡） | **64** |

64 张种子卡全部来自 `quicknote/*`（`quicknote/2022-08-25.md` 一篇就产 32 张），
quicknote 积压 218 篇 → 预计约 1300 张。而 `mindseed-grow` **在构建 plan 时就调用模型**。

### 为什么不能用「取巧」的办法（四个方案逐一否掉）

| 方案 | 为什么不行 |
|---|---|
| 生成后在 `review` 阶段 reject 种子页 | `mindseed-grow` **构建 plan 时就调模型**，reject 只拦落盘，**省不下 64 次/轮模型调用** |
| 临时把 `quicknote` 移出 `scan.include_dirs` | 会让索引缺 quicknote，而 **apply 时会用该索引重写 `_kb-steward/index.md`** → 索引条目丢失，是**写坏库**的风险 |
| 改 `workflows.json` 的 `init_kb.pipeline` | 无效：pipeline 在 `core/initializer.py` **硬编码**（`pipeline_declared`），不是从 workflows.json 读的 |
| 加 CLI 参数 | `scripts/personal_kb_steward.py` 已 **1698/1700 行**（硬上限），加不了 |

→ 唯一干净的做法：**在 `core/initializer.py` 加一个默认不改行为的配置开关**。

### 修复（2 个文件）

`core/initializer.py`（`make_initialization_plan`）：

```python
seed_stage_enabled = bool((cfg.get("initialize") or {}).get("seed_stage", True))
...
quick_unprocessed = (
    [note for note in quick_candidates if id(note) in seed_to_generate]
    if seed_stage_enabled else []
)
```

以及 seed 阶段 `else` 分支的**诚实记账**：

```python
"outcome": "no_inputs",
# `reason` 不能在「阶段被关掉但 quicknote 输入仍在」时说 no_inputs —— 那是假话。
"reason": "no_inputs" if seed_stage_enabled else "seed_stage_disabled",
"reason_detail": (... "配置 initialize.seed_stage=false：本轮只沉淀源卡，未调用 seed updater"
                    "（quicknote/inbox 输入仍在，未被消费）。"),
"seed_stage_enabled": seed_stage_enabled,
```

**设计取舍（与 B09 同一条纪律）：不配置时行为逐字不变。**
`outcome` 保留 `"no_inputs"`，**不引入新枚举值**，避免任何枚举消费者改变含义；
真相由 `reason` / `reason_detail` / `seed_stage_enabled` 三个字段承载。

`tests/test_seed_stage_switch.py`（新增，3 个用例）：

1. 未配置 → 种子阶段照常产出（`provider.calls` 非空）；
2. 关闭 → **零种子页面 + 零模型调用**（`provider.calls == []`）；
3. 关闭 → **raw 源卡不受影响**（source 阶段 `outcome=ok`，源卡仍在 planned_pages）。

### 部署记录（2026-09-22 20:40，已部署）

```
deploy_patch.py B11 core/initializer.py tests/test_seed_stage_switch.py
```

| 门禁 | 结果 |
|---|---|
| 2 个文件哈希 | **2/2 一致** |
| 全量备份 | 1176 个文件（**已排除 `.env`**） |
| 独有资产 534 项 | **变更 0、丢失 0** |
| `git status` 删除行 | **0** |
| 迭代区全量（排除 `test_ci_committed_diff.py`） | **1033 passed, 89 subtests，5 failed**（+3 新用例；5 项仍为 Windows 符号链接环境问题，与基线逐项相同） |
| 生产定向（3 文件） | **43 passed** |

**verdict PASS**。部署侧验收记录：`部署验收记录-B11-2026-09-22.md`。

### 配置变更（可一行回退）

`config.json` 新增（**已先备份**到
`iteration-artifacts/2026-09-21-live-realgate/evidence/config-backup/`）：

```json
{
  "initialize": {
    "seed_stage": false
  },
  ...
}
```

- **回退 = 删掉这三行**（或把 `false` 改 `true`）。
- `scripts/validate_config.py` 改后仍 **配置校验通过**。
- `config.json` 本身**不含密钥值**（只有 `api_key_env: OPENAI_API_KEY` 这个变量名）。

### 未做 / 待确认

- 本轮**未改** `core/layout.py` 的 `INPUT_DIRS`（安全集合），未改检索范围。
- 关闭种子是**临时范围决定**，不是对 `mindseed-grow` 的否定；issue #26 修好后
  把 `seed_stage` 改回 `true` 即可恢复。
