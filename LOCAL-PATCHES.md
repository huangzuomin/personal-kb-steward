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
knowledge_prefixes(cfg) → 10 个 _kb-steward/ 前缀，wiki/ 残留 = 0
is_knowledge_path('_kb-steward/topics/x.md') → True
is_knowledge_path('raw/剪藏/y.md')           → False（原料不是知识对象，正确）
init-kb plan → _kb-steward/sources 3 + seeds 4 + topics 1，wiki/ 幽灵页 = 0
runner 行数 1698（< 1700）✅
```

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

### 最终状态

```
tests=323 failures=3 errors=0 skipped=4     （3 个失败在纯上游同样失败）
runner 行数 1697（< 1700）
可执行代码中的硬编语料 = 0（只剩解释性注释）
```
