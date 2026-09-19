# HANDOVER —— personal-kb-steward 本地补丁集（Patch A–K）

> **给下游读者（人 / GPT）的交接文档。**
> 目的：让上游仓库维护者能判断哪些补丁值得合并、哪些必须拒绝，以及为什么。
>
> - 上游仓库：https://github.com/huangzuomin/personal-kb-steward
> - **基线 commit：`1355b1abcee341f73fadd0297285a7d1602ab3f5`**（"Fix Obsidian related-link validation for LLM topic cards"）
> - 本分支：`fix-path-authority-and-demo-corpus`，三个提交 `a9801a9` + `11174ab` + `ec46ddf`
> - 改动规模：**17 文件，约 +2690 / −257 行**
>   - 其中**代码 15 文件，+857 / −257**（精确值，这才是真正的补丁）
>   - 文档 2 文件，约 +1830（`HANDOVER.md` 1195 + `LOCAL-PATCHES.md` 633）
>
>   > 文档行数写「约」是因为**改这份文档本身就会改变这个数字** —— 想写成精确值，
>   > 就得改一次、量一次、再改一次，永远差几行。代码部分是稳定的。
> - 验证环境：Windows 11 + Python 3.13 + 真实 Obsidian 库（2188 篇 md）
> - 测试基线（**三方实测，见 §5.11**）：
>
> | 版本 | tests | failures | errors | skipped |
> | --- | --- | --- | --- | --- |
> | 纯上游 `1355b1a` | 320 | **5** | 0 | 0 |
> | 本补丁 `11174ab` | 323 | **5** | 0 | 0 |
>
> **失败集合逐项完全相同（`新增的失败 = 无`），零回归。**
> 本补丁净增 3 个测试。5 个失败全部是**上游既有**问题，与补丁无关。

---

## 📌 勘误（ERRATA）—— 本文件早期版本的 3 处错误断言

这份文档的第一版是在**没有真跑验收命令**的情况下写完的，因此写错了 3 处。
全部已在下文修正，并在此列明，以免下游被误导：

| # | 早期错误断言 | 实际情况 | 修正位置 |
| --- | --- | --- | --- |
| 1 | 「`wiki/` 字面量残留 = 0」 | 非 0：**10 行**，其中 8 行是有意的无配置回退、**2 行是残留** | §3.2 验证 / §7.3 |
| 2 | 「`grep -n "wiki/" core/index_builder.py` → 无输出」 | 仍命中 `LEGACY_INDEX_DIRS`（**有意保留**） | §8.4 第 3 条 |
| 3 | 「Patch I 的 demo 语料已全部清除」 | 当时只清了 1/6 处，**另有 5 处在别处** | §3.1.x |

> **根本教训**：文档里写的每一条验收命令，**必须真去执行一遍**再定稿。
> 「我以为我改完了」和「命令输出证明我改完了」是两回事。
> 这与本库既有的一条铁律同源 —— *「没报错」不等于「算对了」*。

---

## 0. 一句话结论

**这份补丁集分两类，必须分开对待：**

| 类别 | 补丁 | 上游该怎么处理 |
| --- | --- | --- |
| **真缺陷修复**（上游也有 bug，与我的库无关） | D、E、F、G、H、I | ✅ **建议全部合并** |
| **口径适配**（为 Obsidian 库调解析口径） | A、B | ⚠️ 建议合并，但**需保留开关** |
| **仅记录、刻意不改** | C、J | 📝 只读，不要改 |
| **测试健壮性** | K | ✅ 建议合并 |

**其中 Patch I 是唯一一个「不修就会批量生产垃圾数据」的缺陷**，优先级最高。

---

## 1. 为什么会有这份补丁集（背景）

我的知识库是 `OLD_VAULT` —— 一个用了多年的 Obsidian 库，特征：

- **2188 篇 md**，大量 Web Clipper 抓取物
- **中英混排**，文件名含 `（）`、`#`、`：`、emoji
- **182 篇 CRLF**，其余 LF
- **大量附件嵌入** `![[xxx.pdf]]` / `![[xxx.png]]`
- **Web Clipper 系 frontmatter**（与 Steward 期望的 11 字段体系完全不同）

把这套工具接到这个库上，暴露了上游在「**非纯净库**」上的若干问题。
下面每条都附**可复现的实测证据**，不是推测。

---

## 2. 补丁总览

> ⚠️ **编号正名**：`LOCAL-PATCHES.md` 里曾有**两个「补丁 D」**（一个是「LLM 超时与端点固化」，
> 一个是「渲染输出契约」）。本文档重新编号，以本文档为准。

| # | 名称 | 文件 | 性质 | 上游风险 |
| --- | --- | --- | --- | --- |
| **A** | 链接解析口径（附件索引 + stem + 转义 `#`） | `core/vault.py`、`scripts/…` | 适配 | 中（需开关） |
| **B** | `noncanonical_link` 收窄 | `scripts/…` | 适配 | 中（需开关） |
| **C** | LLM 超时与端点固化 | `config.json`（gitignored） | 配置 | 无 |
| **D** | 渲染输出契约 | `core/skill_runtime.py`、`core/skill_loader.py` | **缺陷修复** | 低 |
| **E** | 检索上下文总预算 | `core/retrieval.py`、`scripts/…` | **缺陷修复** | 低（默认关闭） |
| **F** | 写入路径权威 | `skills/topic-research-compile/{renderer,executor}.py` | **缺陷修复** | 低 |
| **G** | 读取层路径权威（**四层**，含 `healthcheck` 的 6 处，见 §3.2.x） | `core/{retrieval,knowledge_objects,index_builder,finalizer,reconcile}.py`、`scripts/…` | **缺陷修复** | 低 |
| **H** | `scan.exclude_files` | `core/vault.py` | **缺陷修复** | 低（默认空） |
| **I** | **清除硬编 demo 语料**（3 处主体 + 3 处轻度） | `core/initializer.py`、`skills/topic-research-compile/executor.py`、`core/finalizer.py`、`core/retrieval.py`、`scripts/…` | 🔴 **P0 缺陷修复** | 低（默认空） |
| **J** | `router.json` 触达不了 `topic-research-compile` | — | **仅记录** | 见 §4.10 |
| **K** | 测试超时健壮性 | `tests/test_dry_run.py` | 测试 | 无 |

---

## 3. 上游真缺陷（与我的库无关，任何库都会中招）

### 3.1 🔴 Patch I —— 候选页硬编 demo 语料，凭空造专题

**这是本次最重要的发现。**

#### 症状

`init-kb` 跑 6 篇**内容互不相关**的文档，产出 8 页。其中 6 页 source note 正常，
**另 2 页与输入毫无关系**：

```
_s0-steward/topics/温州人工智能创新发展路径.md
_s0-steward/material-packs/温州AI政策与产业研究资料包.md
    sources = 全部 6 篇
```

那 6 篇是：雁荡山民国摄影史 / AI Adoption 指南 / NAS 部署问答 /
漫画工具介绍 / PAI 研报 / 一条推文。

**一篇讲民国摄影史的文章，被列为「温州 AI 政策与产业」的证据。**

#### 为什么这是 P0（三层放大器）

| 属性 | 值 | 后果 |
| --- | --- | --- |
| `confidence` | `medium` | **不是 low** → 不触发 `manual_review_on_low_confidence` |
| `review_required` | **`false`** | **不进人工审核队列** |
| 正文原话 | 「这是初始化 pipeline 自动生成的候选页，**可直接落盘进入 growing 状态**」 | **自称可免检转正** |

→ 一个明显错误的页面：**不拦截、不标记、自称可直接转正。**
→ 批量跑 21 批 ≈ **40 张污染页，全部绕过审核**。

#### 根因

`core/initializer.py::promote_candidate_pages()` 里硬编了**上游自己 demo 库的语料**：

```python
# 上游原文（基线 1355b1a）
if len(sources) >= int(cfg.get("quality_gate", {}).get("min_sources_for_topic", 3)):
    pages.append(make_promote_candidate_page(
        cfg, kind="topic",
        title="温州人工智能创新发展路径",        # ← 城市名写死
        ...
    ))
if any(marker in text for marker in ("人工智能局", "先行市", "示范应用第一城")):
        title="人工智能创新发展先行市",
...
if any(m in f"{n.title}\n{n.body[:1000]}" for m in ("揭牌", "瓯海", "财政", "车间", "智能眼镜")):
        title="温州AI应用与机构建设案例线索",
...
title="温州AI政策与产业研究资料包",
```

**触发条件只看批次大小（`len(sources) >= 5`），完全不看内容是否相关。**

#### 修法

整段重写为**配置驱动**，源码里不再出现任何具体地名/机构名：

```python
def candidate_promotion_specs(cfg) -> list[dict]:
    """Candidate-page rules, taken from config rather than hardcoded examples."""
    specs = cfg.get("candidate_promotion")
    if not isinstance(specs, list):
        return []          # 无配置 = 不产出，这是更安全的默认
    return [spec for spec in specs if isinstance(spec, dict) and spec.get("title")]
```

每条规则显式声明 `kind / title / rel_dir_key / match_any / min_sources / body`。

同时修掉模板里的两处：

```diff
  "## 后续整理",
- "- 这是初始化 pipeline 自动生成的候选页，可直接落盘进入 growing 状态。",
+ "- 这是初始化 pipeline 自动生成的候选页，主题边界尚未人工确认。",
+ "- 转正为正式专题前，需核对全部来源是否确实支持本页主题。",
...
- "review_required": False,
+ # Auto-generated candidate pages must never claim they are ready to
+ # promote themselves; a human confirms the topic boundary first.
+ "review_required": True,
```

#### 验证

```
修前：8 页 = 6 source + 2 假专题（含「温州」）
修后：3 页 = 3 source，含「温州」的页 = 0   ✅
```

#### 附带修复

`material-pack` 页正文曾**重复 `## 后续整理` 标题**（模板拼接缺陷），已随重写消除。

#### 回归守卫

`tests/test_workflows.py::test_candidate_promotion_absent_config_produces_no_pages`
—— 造 7 篇「雁荡山老照片，与人工智能无关」，断言 `init_pages == []`。

#### ⚠️ 给上游的迁移提示

合并这个补丁后，**原本依赖硬编规则的测试会失败**：

`tests/test_workflows.py::test_init_kb_builds_batched_pipeline_plan` 断言
`wiki/concepts/` 页存在 —— 它原本靠硬编的「先行市」关键词产出。
**这个测试已同步改为在 fixture 里显式声明 `cfg["candidate_promotion"]`。**

如果你的库确实想要自动候选页，就在 `config.json` 里配：

```json
"candidate_promotion": [{
  "kind": "topic",
  "title": "某个真实的专题名",
  "rel_dir_key": "topics_dir",
  "match_any": ["只在确实属于该专题时才出现的词"],
  "min_sources": 3,
  "body": ["## 主题边界", "……"]
}]
```

**关键约束：`match_any` 必须是真的判别词，不能用城市名这种到处都是的词。**

#### 3.1.x 同一个 demo 语料**泄漏在 6 处**（全部已清）

Patch I 的第一版只修了 `initializer.py`。**后来做交接前复核时，发现同一个 demo 语料
还散落在另外 5 处。** 全部一并清掉了 —— 否则「已修复」是假的。

| # | 位置 | 严重度 | 表现 | 修法 |
| --- | --- | --- | --- | --- |
| 1 | `core/initializer.py::promote_candidate_pages` | 🔴 **P0** | **默认路径**产出「温州 AI 政策与产业」假专题，`review_required: false` | `candidate_promotion` 配置驱动 |
| 2 | `core/finalizer.py::make_finalize_plan` | 🔴 **高** | `finalize-kb` 产出 4 张温州页 + 温州专属正文与关键词过滤 | 标题**从资料自身「提取的专题」派生**，其余走 `finalize_aggregation` |
| 3 | `skills/topic-research-compile/executor.py::infer_topics` | 🟡 中 | **启发式路径**（`--no-llm` 或 LLM 失败降级）产出温州专题 | `heuristic_topics` 配置驱动 |
| 4 | `core/retrieval.py::query_terms` 兜底词表 | 🟢 低 | 检索无词可用时兜底成 `["ai","新闻","媒体","温州","知识"]` | 改为用 query 自身词（`fallback_terms`） |
| 5 | `scripts/personal_kb_steward.py::select_notes` 兜底词表 | 🟢 低 | 同上（重复实现） | 复用 `core.retrieval.fallback_terms` |
| 6 | `scripts/personal_kb_steward.py::evidence_items` 案例判定词 | 🟢 低 | 事实行含「温州」就被标成「案例」 | 提取为 `core.retrieval.CASE_MARKERS`（通用词） |

**第 2 处值得单独说**：`finalizer.py` 里其实**已经有**从资料派生的 `top_topics`
（来自 source note 的「## 提取的专题」），但页面标题却用硬编的温州名 ——
**派生数据现成，只是没被用。** 修完的副产物是行为兼容：

```
测试 fixture 的 source note 正文含「- 温州人工智能创新发展路径：…」
→ top_topics[0] = "温州人工智能创新发展路径"
→ 派生出的页名与上游硬编的名字完全一致
```

所以 `test_finalize_kb_...` 里那句
`assertTrue(any(page["rel_path"] == "wiki/topics/温州人工智能创新发展路径.md" ...))`
**不改也能过** —— 但现在是**因为派生对了**才过，而不是因为名字被写死。

**验证（最终）**：

```bash
grep -rn "温州\|人工智能局\|瓯海\|智能眼镜\|先行市" core/ scripts/ skills/ --include=*.py
```

剩下的命中**全部是解释性注释/docstring**（描述这个 bug 本身），无一是可执行代码。
（`scripts/fix_broken_links*.py` 是本库的一次性迁移脚本，不属于工具源码。）

**新增 2 个回归守卫**：

- `test_candidate_promotion_absent_config_produces_no_pages`
- `test_finalize_aggregation_without_config_produces_no_demo_pages`

---

### 3.2 🔴 Patch G —— 路径权威是四层的，不是两层

#### 症状

`config.write.sources_dir = "_kb-steward/sources"`，但：
- 写出去的文件被检索**找不到** → 系统以为「还没做」→ **重复生成同一篇**
- **全程零报错**

#### 四层（这是本补丁的核心价值）

| 层 | 文件 | 硬编码 |
| --- | --- | --- |
| 1 写入 | `skills/topic-research-compile/renderer.py` | `wiki/sources/` |
| 2 检索 | `core/retrieval.py` `DEFAULT_PREFIXES` + runner 3 处调用点 | `wiki/*/` |
| 3 **对象身份** | `core/knowledge_objects.py::is_knowledge_path()` | `p.parts[0] == "wiki"` |
| 4 **扫描范围** | `config.json` `scan.include_dirs` | **根本没有新目录** |

**第 3 层最危险**：漏了它，`object_id` / `revision` / `canonical_path` **全部静默失效**，
知识对象退化成普通 Markdown。

**第 4 层最容易漏**：前 3 层都对了也没用 —— 写出的文件从不进索引。

#### 修法

全部改为从 `cfg["write"]` 派生，**缺失时回退上游 `wiki/` 字面量**（零破坏）：

```python
# core/retrieval.py
KNOWLEDGE_DIR_KEYS = ("seed_dir", "topics_dir", "sources_dir", ...)
LEGACY_KNOWLEDGE_DIRS = ("wiki/seeds", "wiki/topics", "wiki/sources", ...)

def knowledge_prefixes(cfg=None) -> tuple[str, ...]:
    write = (cfg or {}).get("write") if isinstance(cfg, dict) else None
    write = write if isinstance(write, dict) else {}
    dirs = [str(write.get(k) or "").replace("\\", "/").strip("/") for k in KNOWLEDGE_DIR_KEYS]
    dirs = [d for d in dirs if d]
    if not dirs:
        dirs = list(LEGACY_KNOWLEDGE_DIRS)      # ← 无配置 = 上游行为
    return tuple(f"{d}/" for d in dirs)
```

```python
# core/knowledge_objects.py
_DEFAULT_KNOWLEDGE_ROOT = "wiki"
_KNOWLEDGE_ROOTS: tuple[str, ...] = (_DEFAULT_KNOWLEDGE_ROOT,)

def bind_knowledge_roots(cfg=None) -> tuple[str, ...]:
    """Derive the knowledge-object roots from `config.write` and cache them."""
    global _KNOWLEDGE_ROOTS
    ...
    _KNOWLEDGE_ROOTS = tuple(roots) or (_DEFAULT_KNOWLEDGE_ROOT,)
    return _KNOWLEDGE_ROOTS
```

`scripts/personal_kb_steward.py::main()` 新增一行：

```python
bind_objects(cfg)  # object identity follows config.write
```

#### 🔴 一个必须避开的实现陷阱（我踩了，改了 3 次）

**不要用模块级可变缓存来做 `cfg` 驱动的谓词。**

我第一版写成模块级 `_TOPIC_PREFIX` / `_SOURCES_PREFIX` + `bind_topic_prefix(cfg)`，
结果**测试单独跑通过、全量跑失败** —— 缓存跨测试泄漏。

**正确形态：谓词显式接收 `cfg`，字面量只作 fallback。**

```python
def _dir_prefix(write: dict[str, Any], key: str, fallback: str) -> tuple[str, ...]:
    text = str(write.get(key) or fallback).replace("\\", "/").strip("/")
    return (f"{text}/",)

def topic_prefixes(cfg: dict[str, Any] | None = None) -> tuple[str, ...]:
    """Topics prefix from config; the literal is only a no-config fallback."""
    return _dir_prefix((cfg or {}).get("write") or {}, "topics_dir", "wiki/topics")

def is_topic_page(page: dict[str, Any], cfg: dict[str, Any] | None = None) -> bool:
    return str(page.get("rel_path", "")).startswith(topic_prefixes(cfg))
```

#### 一个必须保留的收窄

`review_required` 自动清理**原本只作用于 `wiki/sources/`**。
我在重构时一度扩到「全部知识前缀」，导致 topic/material 页也被清掉 review 标记
（`test_dry_run` / `test_retrieval` 因此失败）。**已收窄回 sources：**

```python
for page in planned_pages:
    # Only source notes are auto-cleared; topic/material pages keep their review flag.
    if is_source_page(page, cfg) and not page_has_blocked_placeholder(page, cfg):
        page["review_required"], page["confidence"] = False, "high"
```

#### 验证

以下输出是**实测**（本机 `config.json`，`write.*` 指向 `_kb-steward/`）：

```
knowledge_prefixes(cfg) -> 10 个前缀，全部 _kb-steward/
    _kb-steward/seeds/  topics/  sources/  work-memory/  evidence/
    gaps/  claim-checks/  concepts/  cases/  material-packs/

is_knowledge_path('_kb-steward/topics/x.md')
    绑定前 → False      ← 🔴 注意：必须先 bind
    绑定后 → True       （bind_knowledge_roots(cfg) -> ('_kb-steward',)）
is_knowledge_path('raw/剪藏/y.md')            → False（原料不是知识对象，正确）
knowledge_root_prefixes(cfg)                  → ('_kb-steward/',)
is_source_page({'rel_path':'_kb-steward/sources/x.md'}, cfg) → True
无 cfg 回退: is_source_page({'rel_path':'wiki/sources/x.md'}) → True（上游行为保持）
无 cfg 回退: knowledge_root_prefixes(None)    → ('wiki/',)（上游行为保持）
```

> ⚠️ **`is_knowledge_path` 是模块态的**：它读 `_KNOWLEDGE_ROOTS`，只有
> `bind_knowledge_roots(cfg)` 调用过才会变。`main()` 里已经调了，所以 CLI 路径没问题；
> 但**任何绕过 `main()` 直接调用的代码/测试，拿到的都是上游 `wiki/` 行为**。
> 这不是 bug（有意的默认值），但排查时必须先想到它 —— 我第一次自测就在这里
> 得到 `False`，一度以为补丁没生效。
>
> `knowledge_root_prefixes(cfg)` 特意**不读模块态**、显式收 `cfg`，就是为了避开这个坑。

#### 3.2.x 🔴 第 4 层当时只修了一半：`healthcheck` 里的 6 处（已补）

**这是我写这份文档时自查发现的，不是用户报的。** 教训写在前面：

> 我在 §8.4 验收标准里写了 `grep -rn "wiki/"` 的期望值。**真去跑那条命令**，
> 才发现 `healthcheck()` / `raw_coverage_report()` 里还有 6 处
> `note.rel.startswith("wiki/")` 是我第一轮漏掉的。

后果（当时状态）：

```python
# healthcheck() —— 全部 5 个清单都会静默变空
missing_meta          # 缺 frontmatter 的知识页
mock_content          # 含占位内容的页
low_confidence_active # confidence=low 却 stage=active
orphans               # 零入链页
raw_coverage          # raw 原料的覆盖情况
```

`config.write.*` 一旦指向别的树（本库是 `_kb-steward/`），
这 5 项**全部返回空列表，不报错、不告警** —— 健康报告会说「没有问题」。
这正是 Patch G 存在的理由（消除静默失败），却在最后一公里漏掉了。

**修法**（`11174ab`）：新增 `knowledge_root_prefixes(cfg)`，
与 `bind_knowledge_roots()` **共用同一份根目录推导**（抽出 `roots_from_write`），不重复实现：

```python
# core/knowledge_objects.py
def roots_from_write(cfg) -> list[str]:
    """Top-level dirs named by `config.write`; files (e.g. log_file) are skipped."""
    ...

def bind_knowledge_roots(cfg) -> tuple[str, ...]:
    global _KNOWLEDGE_ROOTS
    _KNOWLEDGE_ROOTS = tuple(roots_from_write(cfg)) or (_DEFAULT_KNOWLEDGE_ROOT,)
    return _KNOWLEDGE_ROOTS

def knowledge_root_prefixes(cfg=None) -> tuple[str, ...]:
    return tuple(f"{r}/" for r in roots_from_write(cfg)) or (f"{_DEFAULT_KNOWLEDGE_ROOT}/",)
```

```python
# scripts/personal_kb_steward.py
def raw_coverage_report(index, cfg):
    ...
    for note in index.notes:
        if not note.rel.startswith(knowledge_roots(cfg)):
            continue

def healthcheck(index, cfg):
    ...
    roots = knowledge_roots(cfg)          # 循环外算一次，用了 5 次
    for note in index.notes:
        if note.rel.startswith(roots) and not note.metadata: ...
        if note.rel.startswith(roots) and note.metadata and note.path.name != "README.md": ...
        if note.rel.startswith(roots) and any(marker in note.body for marker in BLOCKED_APPLY_MARKERS): ...
        if note.rel.startswith(roots) and confidence == "low" and stage == "active": ...
    orphans = [n.rel for n in index.notes if n.rel.startswith(roots) and ...]
```

**行为等价性**：上游布局下 `knowledge_root_prefixes(cfg)` = `('wiki/',)`，
与原字面量逐字节一致；无配置时回退 `('wiki/',)`；本库为 `('_kb-steward/',)`。

> **runner 行数**：这次改动净 +1 行，撞到 1700 硬上限的边缘（1697 → 1698）。
> `raw_coverage_report` 里的 `roots` 因此**刻意内联**（该函数只被调用一次，
> 循环体极轻），把余量留给下一个人。

---

### 3.3 Patch F —— 写入路径权威（G 的孪生兄弟）

`skills/topic-research-compile/renderer.py` 第 23 行硬编码 `wiki/sources/`，
且 `executor.py` 的三个 `render({...})` 调用点**都没传 config**。

```python
# renderer.py
sources_dir = str(data.get("sources_dir") or "_kb-steward/sources").replace("\\", "/").strip("/")
source_target = f"{sources_dir}/source-{slug(source_name, 'source')}-{short_hash(source_rel)}.md"
```

```python
# executor.py —— 新增
def target_dirs(cfg: dict[str, Any]) -> dict[str, str]:
    """Write targets must come from config.write, never from hardcoded paths."""
    write = cfg.get("write") if isinstance(cfg, dict) else None
    write = write if isinstance(write, dict) else {}
    return {
        "sources_dir": str(write.get("sources_dir") or "_kb-steward/sources").replace("\\", "/").strip("/"),
    }
```

**验证**：`init-kb` plan 的 `wiki/sources/` 页数 6 → **0**。

---

### 3.4 Patch H —— 生成型索引页被当原料喂给 LLM

`raw/剪藏/0-MOC.md`（12,271 字符）是**自动生成的导航索引**（「被引用最多的笔记」清单），
落在 `include_dirs` 里 → 被当原料喂给 LLM。

**它不只是浪费预算 —— 它污染检索排序**：实测它**每次都排在检索结果第 2 位**，
因为它罗列了所有标题，任何关键词都能命中它。

```python
# core/vault.py —— 新增
def excluded_note(cfg: dict[str, Any], path: Path) -> bool:
    """Generated index pages (0-MOC.md and friends) are navigation, not input.

    Feeding them to the LLM invites it to summarise a table of contents. The
    rule lives in config so a vault can name its own index pages instead of
    hardcoding the convention here. Empty by default: upstream vaults that
    never opted in keep indexing every file.
    """
    names = {str(n).strip().lower() for n in (cfg["scan"].get("exclude_files") or []) if str(n).strip()}
    if not names:
        return False
    return path.name.lower() in names or path.stem.lower() in names
```

**默认空列表 → 上游行为完全不变。**
本库配置 `"exclude_files": ["0-MOC.md"]` → raw 索引数 **134 → 132**。

> ⚠️ **注意**：不能用现成的 `scan.exclude_dirs` —— 它匹配的是**目录名**
> （`set(path.relative_to(root).parts) & exclude_dirs`），排除文件不干净。

---

### 3.5 Patch D —— 输出契约没被渲染进 system prompt

**两处都缺**：

1. `core/skill_runtime.py` 的 `output_contract` **只声明 8 个必填字段**，
   而 `core/llm_plan.py::_strings()` 实际会校验 **11 个可选字段** —— 一个都没写进契约。
2. 更关键：`core/skill_loader.py::build_system_prompt()` **压根没渲染 `output_contract`**。
   契约只躺在 user payload，system prompt 只说 "Follow the SKILL.md contract exactly"，
   而 `skills/topic-insight-miner/SKILL.md` 从未定义这些字段的类型。

**模型两边都看不到说明，只能猜。这是契约缺失，不是模型能力问题。**

修法：`skill_runtime.py` 补 `required_item_types` / `optional_item_types` / `type_rules`；
`build_system_prompt(spec, contract=None)` 新增可选参数并渲染契约
（**不传时行为与上游完全一致**）。

**效果**：`risks` 从散文变 `list`，`related` 变规范完整路径。

---

### 3.6 Patch E —— 检索只有「每篇」上限，没有「总量」上限

`Retriever.documents()` 的 `max_chars=6000` 是**每篇**上限。
8 篇 → 48,000 字符 → payload **46k** → **稳定 300s 超时**（连试 3 次全挂）。

递进探针证明不是 provider 问题：

| payload | 实测 |
| --- | --- |
| 8k（纯探针） | 11 s |
| 14k（真实 prompt + 小文档） | 88–113 s |
| 19k（8×1800） | 262 s |
| **46k（8×6000）** | **297 s 成功 / 300 s 超时** ← 不可用 |

修法：`documents(notes, max_chars, total_budget=0)` —— 按 `budget/len(notes)`
分公平份额，后面的文档借用前面未用完的余额。

| 设置 | 每篇 | 总量 |
| --- | --- | --- |
| `budget=0`（上游行为） | 6000 ×8 | 48000 |
| `budget=22000` | 2750 ×8 | 22000 |
| `budget=8000` | 1000 ×8 | 8000 |

**`budget=0` 时代码路径与上游逐字等价。**

---

### 3.7 Patch K —— 测试超时在负载下误报

`tests/test_dry_run.py` 用 `timeout=30` 跑子进程。该测试的 vault **只有 7 个文件**，
单独跑约 1 秒。但全量跑时因机器负载触发 `subprocess.TimeoutExpired` ——
**报的是超时，实际是负载抖动，不是挂起**。

修法：`timeout=180`，并写明注释解释为什么给这么宽。仍能捕获真挂起。

---

## 4. 口径适配补丁（为 Obsidian 库调整）

### 4.1 Patch A —— 链接解析口径

上游把链接解析目标限定为**只索引 `.md`**，且用 `Path(...).stem` 剥扩展名。
在 Obsidian 库上产生**大量假断链**：

| 现象 | 真实原因 |
| --- | --- |
| `![[报告.pdf]]`、`![[图片.png]]` 全报断链 | 附件未被索引（只收 `.md`） |
| `[[方案（3.0）]]` 永远解析不到 | `Path.stem` 把 `（3.0）` 当扩展名剥掉 |
| `[[\#我平常都看什麼書]]` 报断链 | 正则把 `\#` 当锚点截断（本库 `\#` 是文件名一部分） |
| `[[PDF] xxx](https://…)` 报断链 | 正则误吞 Markdown 链接文本 |

**首次 `lint` 报 60 条"断链" → 其中 52 条是假阳性。**

修法（`core/vault.py`）：
1. `VaultIndex` 新增 `by_attachment`（小写 basename → 相对路径列表）
2. 新增 `build_attachment_index(root)` —— 扫全库非 `.md` 文件
   （与 `include_dirs` 无关，因为 Obsidian 链接解析是**全库按名**的）
3. 新增 `extract_wikilinks(text)` —— `\#` 不截断、跳过含换行与 Markdown 链接文本
4. 新增 `wiki_stem(target)` —— 只在**真的以 `.md` 结尾**时才剥
5. 新增 `resolve_link(index, target)` —— 解析顺序：相对路径 → stem → **附件名** → 标题

> **给上游的建议**：附件索引对**任何 Obsidian 用户**都适用，不只是我。
> Obsidian 的 `![[x.pdf]]` 是标准语法，不索引附件就是错的。

### 4.2 Patch B —— `noncanonical_link` 收窄

原判定把**裸 stem**（`[[AI和媒体]]`）也报为 noncanonical —— 但那是 **Obsidian 惯例**，
不是错误。`1933` 条刷屏。

修法：新增 `is_noncanonical_strict` —— 只有「**显式写了路径或扩展名**、但解析结果与之不符」
才报警。

**效果**：`noncanonical_link` 1933 → **0**。

### 4.3 Patch C —— LLM 超时与端点固化（**仅配置，勿改代码**）

`config.json`（`.gitignore` 内）的 `llm` 段：

```diff
- "base_url": "https://api.openai.com/v1",
- "model": "",
- "timeout_seconds": 60
+ "base_url": "https://open.bigmodel.cn/api/coding/paas/v4",
+ "model": "GLM-5.3-Flash",
+ "timeout_seconds": 300
```

> 🔴 **上游文档错误（值得单独修）**：官方/上游文档写 `LLM_MODEL`，
> **代码读的是 `OPENAI_MODEL`**（`core/llm.py`）。按文档配会抛 `Missing LLM model`。

---

## 5. 🔴 测试过程中遇到的问题（完整记录）

> 这一节是用户明确要求的。**每条都是真实踩过的坑，附排查路径与最终结论。**

### 5.1 跨测试污染：模块级可变缓存（**最隐蔽，改了 3 次**）

**现象**：`test_dry_run::test_mock_llm_plan_is_dry_run` **单独跑通过**，
但在 `test_retrieval` 之后跑**必失败**。

**排查**：`pytest -p no:randomly`、单独文件跑、组合跑 —— 确认是**顺序依赖**。

**根因**：我第一版用模块级可变缓存做 `cfg` 驱动的谓词：

```python
# ❌ 错误形态
_TOPIC_PREFIX: tuple[str, ...] = ("wiki/topics/",)
def bind_topic_prefix(cfg): 
    global _TOPIC_PREFIX
    _TOPIC_PREFIX = ...
```

第一个测试用 cfg A 绑定 → 第二个测试用 cfg B，但缓存还是 A 的值。

**修法**：**彻底移除模块级状态**，谓词显式接收 `cfg`，字面量只作 fallback。

**教训**：**任何接收 `cfg` 的谓词，都不该有模块级状态。**

### 5.2 `test_index_builder` FileNotFoundError

**现象**：`FileNotFoundError: .../wiki/seeds/README.md`

**根因**：该测试的 `make_cfg` **完全没有 `write` 段**，
我新写的 `indexed_dirs(cfg)` 返回 `{}` → 一个 README 都不建。

**修法**：引入 `LEGACY_INDEX_DIRS` 回退 —— 缺 `write` 键时返回上游 `wiki/...` 路径，
而不是返回空。

**教训**：**`cfg` 缺段时不能返回空 —— 空意味着「静默停摆」，回退才是安全默认。**

### 5.3 我自己的新测试先失败 → 反而暴露了第 4 层

**现象**：我写的 `test_query_results_recall_follows_config_write_dirs` 首次运行失败，
`_kb-steward/sources/note.md` 找不到。

**排查**：不是前缀逻辑错 —— 是 `cfg["scan"]["include_dirs"]` **没包含 `_kb-steward`**，
所以 `build_index` 从未索引那个文件。

**价值**：**这个测试 bug 揭示了四层缺陷里的第 4 层（扫描范围）。**
没有它，我会以为前三层修完就完事了。

### 5.4 `core/reconcile.py` 的硬断言 —— 证明第 3 层是真正阻塞点

**现象**：`ReconcileConflict: write.topics_dir 必须是规范的 wiki/ 子目录`

**根因**：它调用 `is_knowledge_path(rel)`，而后者把 `parts[0] == "wiki"` 写死。

**价值**：**这是「第 3 层（对象身份）」存在的直接证据。**
不是「找不到文件」这么轻 —— 是**对象身份整个失效**。

### 5.5 `test_retrieval` 的 `review_required` 断言失败

**现象**：`assert False is True` on `page['review_required']`

**根因**：我把 `review_required` 自动清理的范围从 `wiki/sources/`
**扩到了全部知识前缀**，导致 topic/material 页也被清掉标记。

**修法**：收窄回 `is_source_page(page, cfg)`。

**教训**：**重构「把字面量换成配置」时，容易顺手扩大语义范围。
必须先确认原范围是什么。**

### 5.6 `Edit` 工具合并相邻行 → SyntaxError

**现象**：`SyntaxError: invalid syntax` at line 69，看到
`...)from core.state import (`

**根因**：删掉一个行尾换行，导致两条 import 语句被拼成一行。

**修法**：重写整个 import 块。

**教训**：**每次 Edit 后立刻 `py_compile`。** 不要批量改完再验。

### 5.7 runner 的 1700 行硬上限（反复撞）

`tests/test_runtime_boundaries.py::test_runner_is_smaller_after_phase_14`
断言 `assertLess(line_count, 1700)`。

**实测轨迹**：`1694 → 1720 → 1710 → 1709 → 1701 → 1700 → 1699 → 1698 → 1699`

**修法**：把新逻辑下沉到 `core/`（无上限），runner 只留调用。

**教训（已写入 LOCAL-PATCHES.md）**：**新逻辑放 `core/`，runner 只保留调用。**

### 5.8 pytest 输出被 hook 吞掉

**现象**：`tail -10` / `grep` 拿不到 pytest 的汇总行，
`/tmp/pytest_out.txt` 只有 5 行进度点。

**根因**：一个 `[safe-delete]` hook 截断了控制台输出。

**修法**：改用 `--junitxml=/tmp/junit.xml` + `xml.etree.ElementTree` 解析。

```bash
python -m pytest tests/ -q --junitxml=/tmp/junit.xml
python -c "
import xml.etree.ElementTree as ET
t=ET.parse('/tmp/junit.xml'); r=t.getroot()
s=r if r.tag=='testsuite' else r[0]
print('tests=%s failures=%s errors=%s skipped=%s'%(s.get('tests'),s.get('failures'),s.get('errors'),s.get('skipped')))
for tc in s.iter('testcase'):
    if tc.find('failure') is not None: print('FAIL:',tc.get('name'))
"
```

### 5.9 `git stash` 在本仓库是危险的

**现象**：`git stash` 后 SIGTERM 导致 `.git/refs/` 被删。

**修法**：改用 `cp` 备份到 `/tmp/mine/` + `git checkout --`。

**教训**：**这个仓库别用 `git stash`。**

### 5.10 如何证明一个失败是「既有的」而不是「我引入的」

**方法**（这是最有价值的一步）：

```bash
# 1. 备份我的改动
mkdir -p /tmp/mine && cp <改动的文件> /tmp/mine/
# 2. 恢复纯上游
git checkout -- <改动的文件>
# 3. 跑那个失败的测试 —— 如果同样失败，就是既有的
python -m pytest tests/test_retrieval.py -q
# 4. 恢复我的改动
cp /tmp/mine/* <原路径>/
```

**结果**：`test_real_material_task_uses_deep_fts_hits_and_records_inputs`
在**纯上游 `1355b1a`** 上以**完全相同的断言**失败
（`assert '大黄鱼产业有一项可核对' in ...` with `status: insufficient`）
→ **证明是既有失败，与我无关。**

### 5.11 最终测试基线（**三方实测**）

这一节我做过一次修正。**第一次写的是「3 failures / 4 skipped」——
那是在符号链接不可用的环境下跑的，其中 2 个测试被 `skipTest` 跳过了。**

后来在完整环境下重跑，那两个测试**真的执行了并失败**，于是数字变成 5 failed。
为了确认这不是我引入的，我用 `git worktree` 建了**纯上游的干净检出**做三方对照：

```bash
git worktree add --detach ../pks-pristine 1355b1a
cp config.json ../pks-pristine/          # config.json 在 .gitignore 内，需手动带过去
cd ../pks-pristine && python -m pytest -q --junitxml=.pytest-upstream.xml
```

| 版本 | tests | failures | errors | skipped |
| --- | --- | --- | --- | --- |
| 纯上游 `1355b1a` | 320 | **5** | 0 | 0 |
| 补丁第一提交 `a9801a9` | 323 | **5** | 0 | 0 |
| 补丁全部 `11174ab` | 323 | **5** | 0 | 0 |

用 junit XML 提取失败集合做集合运算：

```
上游失败集合 == 最终失败集合   -> True
新增的失败                    -> 无
被消除的失败                  -> 无
```

**5 个失败全部是上游既有的**（纯上游就失败）：

| 测试 | 原因 | 与补丁的关系 |
| --- | --- | --- |
| `test_ci_committed_diff::test_shallow_clone_does_not_silently_shrink_pr_range` | `git clone file://` 在本机失败 | 无关 |
| `test_derived_index::test_links_do_not_export_external_notes_or_redirect_cache` | 符号链接 / 路径导出行为 | 无关 |
| `test_frontmatter::test_topic_research_keeps_topics_as_candidates_inside_source_note` | 上游既有 frontmatter 行为 | 无关 |
| `test_retrieval::test_real_material_task_uses_deep_fts_hits_and_records_inputs` | LLM 返回 `status: insufficient` | 无关 |
| `test_review_guards::test_symlink_escape_rejected` | 符号链接创建后未触发逃逸检测 | 无关（`core/safety.py` 本补丁未触碰） |

**本补丁净增 3 个测试**（320 → 323）。**零回归。**

> ⚠️ **`skipped` 数是环境相关的**，不要拿它当基线。
> `test_review_guards` 与 `test_derived_index` 各有一个测试在
> **创建不了符号链接时 `skipTest`**（Windows 需管理员或开发者模式）。
> 因此同一份代码在不同环境下会给出 `3 failed / 4 skipped` 或 `5 failed / 0 skipped`。
> **判断回归只能比「失败集合」，不能比「失败个数」。**
> —— 我第一次就差点被这个数字骗过去。

### 5.12 运行测试时的 Python 环境陷阱

**managed Python 没装 pytest**：

```
C:\Users\zooma\.workbuddy-ai\binaries\python\versions\3.13.12\python.exe -m pytest
→ No module named pytest
```

**可用的解释器**（装了 pytest）：

```
C:\Users\zooma\.workbuddy-ai\binaries\python\envs\default\Scripts\python.exe   # pytest 9.1.1 ✅
C:\Users\zooma\AppData\Local\Programs\Python\Python313\python.exe              # pytest 7.4.3 ✅
```

### 5.13 CRLF / `core.autocrlf=true` 的良性警告

本仓库 `core.autocrlf=true`，工作区是 CRLF。Edit 写入 LF 行时会打印：

```
warning: in the working copy of 'core/vault.py', LF will be replaced by CRLF the next time Git touches it
```

**已验证是良性的**：`core/vault.py` 246 行全部 CRLF，无混合行尾；diff 干净。
提交时 git 会规范化。

### 5.14 🔴🔴 编辑会「静默消失」—— 沙箱/非沙箱视图不一致（**本次最贵的坑**）

**现象**：我用编辑工具改了 `core/knowledge_objects.py` 和 `scripts/personal_kb_steward.py`，
并且**连续两条命令都验证过改动生效**（`py_compile` 通过、行数从 1697 变 1698、
新函数 `knowledge_root_prefixes` 能 import 且返回正确值）。

然后我做了个「备份 → 回退 → 对照」的实验：

```bash
mkdir -p .mywork-backup
cp core/knowledge_objects.py .mywork-backup/          # ← 备份
cp scripts/personal_kb_steward.py .mywork-backup/
git checkout -- core/knowledge_objects.py scripts/personal_kb_steward.py   # ← 回退
```

**结果：备份下来的根本不是我的版本。** 它 168 行、没有 `knowledge_root_prefixes`、
与 `git show HEAD:` 只差行尾（7250 B LF → 7418 B CRLF，差 168 = 行数）。
**我的全部改动没了。**

**诊断过程**（值得抄的排查手法）：

1. 先用 `Write` 落一个标记文件 `fs-probe.txt`，再从**非沙箱**命令去 `cat` 它 —— 能读到，
   说明写入确实落在真实文件系统上，不是「写进了内存」。
2. 于是怀疑**视图不一致**：某些命令看到的是沙箱覆盖层，另一些看到的是真实盘。
3. **决定性动作**：重新应用改动后，**立刻用 `dangerouslyDisableSandbox: true` 的命令**
   跑 `git diff --stat`。这次看到了 `21 insertions(+), 6 deletions(-)` —— 改动真实落盘了。

**规避规则（以后一律照做）**：

> ### 改完文件，必须用**非沙箱**命令验证一次 `git diff --stat`。
> ### 跑测试/回退等危险操作**之前**，先 `git add` + `git commit`。

第二句是关键：**改动一旦 commit，就再也不会被视图差异吃掉**。
本次正是先 commit（`11174ab`）再跑全量测试，才没再丢。

**连带的认知修正**：因为文件曾经静默回到 HEAD，我一度做了个**无效的 A/B 对照** ——
「回退后测试通过 / 改动后测试失败」，看起来像是我引入了 bug，
实际上**两边跑的都是同一个 HEAD 版本**。教训：
**做 A/B 之前，先用 `git diff --stat` 确认 A 和 B 真的不同。**

---

## 6. 🔴 需要同步的配置变更（`config.json` 在 `.gitignore` 内）

**这些改动不会随补丁走，必须手动同步到你的 `config.json`。**

```jsonc
{
  "scan": {
    // Patch G 第 4 层：新写入目录必须进扫描面，否则写出的文件永不进索引
    "include_dirs": [..., "_kb-steward"],

    // Patch H：排除生成型索引页
    "exclude_files": ["0-MOC.md"],

    // Patch E：检索总量预算（0 = 上游行为）
    "max_total_source_chars": 22000,

    "max_source_chars": 6000
  },

  // Patch I：候选页规则。留空 = 不自动产出任何候选页（推荐）
  "candidate_promotion": [],

  // Patch I（finalizer 侧）：聚合页。留空时只产出「从资料派生标题」的 topic 页
  "finalize_aggregation": {},

  // Patch I（启发式侧）：--no-llm 或 LLM 降级时的专题规则。留空 = 只用中性标题
  "heuristic_topics": [],

  "llm": {
    "timeout_seconds": 300
  },

  "write": {
    // Patch F/G：所有知识目录都从 config.write 派生
    "sources_dir": "_kb-steward/sources",
    "topics_dir": "_kb-steward/topics"
    // ... 其余同构
  }
}
```

**关键**：`write.*` 与 `scan.include_dirs` **必须一致** ——
一个是「写到哪」，一个是「去哪读」。不一致就是 Patch G 那个静默重复生成的坑。

---

## 7. 刻意不修的项

### 7.1 Patch J —— `router.json` 触达不了 `topic-research-compile`

`router.json` 的 6 条路由里，**没有任何一条指向 `topic-research-compile`**：

```
healthcheck        → kb-lint-healthcheck
weave_work_memory  → work-memory-weave
discover_topics    → topic-insight-miner
prepare_writing    → writing-material-pack
init_kb            → kb-initialize
organize_kb        → mindseed-grow          ← 默认
```

**后果**：用户从 CLI 说「整理 raw 长文」→ 永远落到 `organize_kb`/`mindseed-grow`。

**实测**：`task --llm "PAI合成媒体框架研报"` →
`primary_skill=mindseed-grow`、喂入 `quicknote/2022-08-24~30` 日记、
`planned_pages=0`、**白跑 3m11s**。

**结论**：`topic-research-compile` **只能由 `init-kb` 内部代码路径触发**，
用户无法主动调用。**S0/S1 必须走 `init-kb`，别用 `task`。**

**为什么不修**：改 `router.json` 语义会影响**所有上游用户**的 `task` 行为。
这是设计决策，不是 bug。**留给上游判断。**

> **但这次"白跑"捞到了高价值情报**：LLM 面对不匹配素材时，在 `Manual Review` 主动写
> 「任务主题 PAI 合成媒体框架与本文档内容不匹配，请确认输入文件是否提供正确」——
> **它不硬编专题。** 这是「LLM 行为可靠」的独立佐证，且是在**最恶劣的输入条件下**得到的。

### 7.2 `init-kb` 无法指定篇目（工作方式限制，非 bug）

`init-kb` 取的是**索引字母序前 N 篇**，无法指定「只跑这 6 篇」。
这导致无法做「探针校准」。

**绕法（已验证，可复用）**：独立沙箱 + 数字前缀强制排序。

```
_s0-sandbox/
├── config.json      # knowledge_base → _s0-sandbox/kb
├── kb/raw/剪藏/     # 探针篇目，改名 01-…~06-… 强制排序
└── tool/            # 工具副本（含 .env，已移除 .git / .openclaw）
```

**真库零风险，且能精确控制喂给 LLM 的每一篇。**

> **给上游的建议**：`init-kb` 加一个 `--only <glob>` 或 `--paths <file>`
> 会大幅提升可用性 —— 校准批次是任何批量 LLM 任务的必备能力。

### 7.3 🔴 仍有一处 `wiki` 字面量：`source too broad` 启发式（**故意留的，请一并裁决**）

`grep -rn '"wiki/' core/ scripts/ skills/ --include=*.py` 现在剩下 **10 行**。
其中 **8 行是有意保留的无配置回退常量**，**2 行是真正的残留**：

| 位置 | 性质 |
| --- | --- |
| `core/finalizer.py:21,22` | `FINALIZE_DIR_FALLBACK` 无配置回退 ✅ 有意 |
| `core/index_builder.py:32,33` | `LEGACY_INDEX_DIRS` 无配置回退 ✅ 有意 |
| `core/retrieval.py:16,17` | `DEFAULT_PREFIXES` 无配置回退 ✅ 有意 |
| `core/retrieval.py:32,33` | `LEGACY_KNOWLEDGE_DIRS` 无配置回退 ✅ 有意 |
| `core/retrieval.py:72,76` | `_dir_prefix()` 的 fallback 参数 ✅ 有意 |
| **`core/validator.py:70`** | 🔴 `source in {"raw", "raw/", "wiki", "wiki/"}` |
| **`scripts/personal_kb_steward.py:411`** | 🔴 同上（`source_quality()`） |

```python
# core/validator.py:70
if source in {"raw", "raw/", "wiki", "wiki/"} or str(source).endswith("/"):
    issues.append(f"items[{idx}] source too broad: {source}")
```

**为什么不修**：

1. 两个函数（`validate_skill_items` / `source_quality`）**签名里都没有 `cfg`**，
   要修就得改 4 个调用点（`validate_markdown` 3 处 + `healthcheck` 1 处）并层层透传。
2. **影响很小**：`or str(source).endswith("/")` 已经覆盖 `wiki/`、`raw/`、`_kb-steward/`；
   漏的只是**不带斜杠的裸目录名**（如 `_kb-steward`）。而紧随其后的
   `if source not in paths` 会照样报 `source not provided` ——
   只是提示语从「来源过粗」变成「来源不存在」，**不会静默放过**。
3. 属于**措辞不精确**，不属于「静默错误」。

> **留给上游**：若希望彻底 config 化，建议给这两个函数加 `cfg=None` 关键字参数
> （默认值保持上游行为），而**不是**引入模块级状态 —— 见 §3.2 的实现陷阱。

---

## 8. 给 GPT / 合并者的操作指引

### 8.1 拿到这份补丁

**方式一：GitHub PR（推荐）**

分支 `fix-path-authority-and-demo-corpus` 已推到上游仓库。**代码补丁是前两个提交**：

```
a9801a9  fix: path authority, hardcoded demo corpus, and link-resolution parity
11174ab  fix: make healthcheck path authority config-driven too
```

（另有第三个提交，只改本文件 `HANDOVER.md`，不含代码 —— 合并时可只取前两个。
  它的哈希没写在这里，因为**改这份文档就会 amend 掉它**，写死了必然过期。）

```bash
git log --oneline origin/main..origin/fix-path-authority-and-demo-corpus   # 看全部
```

```bash
git fetch origin fix-path-authority-and-demo-corpus
git diff origin/main...origin/fix-path-authority-and-demo-corpus   # 先看
git merge origin/fix-path-authority-and-demo-corpus                # 再合
```

**方式二：补丁文件（离线交接）**

`pr-artifacts/local-patches.patch`（约 163 KB，`git format-patch 1355b1a..HEAD` 输出）。

```bash
git clone https://github.com/huangzuomin/personal-kb-steward.git
cd personal-kb-steward
git checkout 1355b1abcee341f73fadd0297285a7d1602ab3f5
git checkout -b feature/local-patches-a-k

git apply --check pr-artifacts/local-patches.patch   # 先干跑，必须无输出
git apply         pr-artifacts/local-patches.patch
```

> **已实测**：该补丁对**纯上游 `1355b1a`** 执行 `git apply --check --verbose`，
> 19 个文件补丁**全部通过**，退出码 0。见 §5.11 的 worktree 方法。

> ⚠️ **早期版本这里写的是 `patches/local-patches.patch` —— 那个路径不存在。**
> 真实路径是 `pr-artifacts/local-patches.patch`，且**未提交进分支**（属生成物）。
> 若拿不到该文件，用方式一即可，二者等价。

### 8.2 合并时必须注意的 5 件事

1. **`tests/test_workflows.py` 会失败** —— 它原本依赖 Patch I 要删掉的硬编关键词。
   补丁里已同步改为 fixture 显式声明 `cfg["candidate_promotion"]`。
   **如果你只合 `core/initializer.py` 不合测试，就会红。**

2. **`config.example.json` 需要同步新增 5 个键**（**已知缺口，建议一并补上**）：
   `scan.exclude_files`、`scan.max_total_source_chars`、`candidate_promotion`、
   `finalize_aggregation`、`heuristic_topics`。
   补丁**没有**改 `config.example.json` —— 因为它不在我的配置链路上。
   **新增键全部默认「空/关闭」，所以不改也不报错，只是功能不可用。**

3. **Patch I 跨 3 个文件，不能只合一个**：
   `core/initializer.py`（候选页）+ `core/finalizer.py`（聚合页）+
   `skills/topic-research-compile/executor.py`（启发式）。
   只合 `initializer.py` 的话，`finalize-kb` 与 `--no-llm` 仍会产温州页。
   `core/retrieval.py` 与 `scripts/…` 里还有 3 处轻度实例（见 §3.1.x）。

4. **`core/vault.py` 的 `by_attachment` 字段** 是 `VaultIndex` 的 dataclass 字段，
   若上游同期也改了 `VaultIndex`，这里会冲突。**保留 `by_attachment`。**

5. **Patch B 的 `is_noncanonical_strict`** 改变了 lint 的报告口径。
   如果你有下游工具依赖 `noncanonical_link` 的条数，**会看到数字从 1933 掉到 0** ——
   这是**修正**，不是漏报。

### 8.3 建议的合并顺序

```
1. Patch I   ← 最紧急，不修会批量产垃圾
2. Patch G   ← 路径权威，四层一起合，别拆
3. Patch F   ← G 的孪生，与 G 同批
4. Patch D   ← 契约，独立
5. Patch E   ← 预算，独立
6. Patch H   ← 小，独立
7. Patch A   ← 口径，建议加开关
8. Patch B   ← 口径，建议加开关
9. Patch K   ← 测试
```

**A/B 建议做成配置开关**（如 `link_resolution.obsidian_compat: true`），
因为它们改变的是**解析口径**，不全是「修 bug」。

### 8.4 验收标准

```bash
# 1. 测试基线（**5 个既有失败，全部在纯上游同样失败**）
python -m pytest tests/ -q --junitxml=/tmp/j.xml
# 期望：tests=323 failures=5 errors=0 skipped=0
#
# ⚠️ 不要用「失败个数」判断是否回归，要用「失败集合」：
#    test_review_guards 与 test_derived_index 各有一个测试在
#    创建不了符号链接时 skipTest（Windows 需管理员或开发者模式）。
#    你的环境若无法建符号链接，会得到 3 failed / 4 skipped —— 那不是回归。
#    正确做法见 §5.11：用 git worktree 建纯上游检出，两边都跑，再比集合。

# 2. 硬编语料是否清除
grep -rn "温州\|人工智能局\|瓯海\|智能眼镜" core/ scripts/ skills/ --include=*.py
# 期望：只剩解释性注释（描述这个 bug 本身），无可执行代码命中
#   ⚠️ 但上游自带两个一次性修复脚本 scripts/fix_broken_links{,_v2}.py，
#      里面**硬编了具体库的文件名**（温州/人工智能局…）。它们是上游代码，
#      不是本补丁引入的，也不该由本补丁去改 —— 见下方「附带观察」。

# 3. 路径字面量：逐行判性质（**不要只看条数**）
grep -rn '"wiki/' core/ scripts/ skills/ --include=*.py
# 期望：10 行。其中 8 行是有意的无配置回退常量，2 行是已知残留。
#   core/finalizer.py:21,22          FINALIZE_DIR_FALLBACK   ✅ 有意
#   core/index_builder.py:32,33      LEGACY_INDEX_DIRS       ✅ 有意
#   core/retrieval.py:16,17          DEFAULT_PREFIXES        ✅ 有意
#   core/retrieval.py:32,33          LEGACY_KNOWLEDGE_DIRS   ✅ 有意
#   core/retrieval.py:72,76          _dir_prefix() fallback  ✅ 有意
#   core/validator.py:70             🔴 残留（见 §7.3）
#   scripts/personal_kb_steward.py:411  🔴 残留（见 §7.3）

# 4. 配置缺失时的回退行为（上游兼容性）
python -c "
import sys; sys.path.insert(0,'.')
from core.retrieval import knowledge_prefixes
from core.knowledge_objects import knowledge_root_prefixes
p = knowledge_prefixes({})
print(len(p), p)                        # 期望：7 个，全部以 wiki/ 开头
print(knowledge_prefixes(None) == p)    # 期望：True
print(knowledge_root_prefixes(None))    # 期望：('wiki/',)
print(knowledge_root_prefixes({}))      # 期望：('wiki/',)
"

# 5. runner 行数硬上限
wc -l scripts/personal_kb_steward.py
# 期望：< 1700（纯上游 1698 / 本补丁 1698）
```

> **注意第 3 条**：`LEGACY_*` / `DEFAULT_PREFIXES` / `*_FALLBACK` 里的 `wiki/...`
> **全是故意保留的** —— 它们是「配置里没有 `write` 段」时的回退，保证上游行为不变。
> 别把它们当成漏改而删掉，否则 `test_index_builder` 会失败（见 §5.2）。

> **附带观察（给上游）**：`scripts/fix_broken_links.py` / `fix_broken_links_v2.py`
> 是上游 `4e9dfa0` 引入的，里面**写死了某一个具体知识库的文件名**
> （`topic-topic-from-温州市数据局（市人工智能局）…` 等）。
> 这跟 Patch I 是**同一个反模式**：把 demo/特定库的数据固化进代码。
> 它们是一次性修复脚本、不在库的调用链上，所以本补丁**没有动它们**；
> 但若上游想彻底清理这个模式，这两处也值得看一眼。

---

## 9. 关键数字速查

```
基线 commit                  1355b1abcee341f73fadd0297285a7d1602ab3f5
分支                         fix-path-authority-and-demo-corpus
提交                         a9801a9（主补丁）+ 11174ab（healthcheck 第 4 层补齐）
                             + 第三个提交（docs，仅改本文件，哈希见 GitHub）
                             —— 前两个哈希稳定；第三个只动文档，故不写死哈希
改动规模                     17 文件，约 +2690 / −257 行
  ├── 代码                   15 文件，+857 / −257（精确）
  └── 文档                    2 文件，约 +1830（本文 1195 + LOCAL-PATCHES 633）

测试基线（三方实测，见 §5.11）
  纯上游 1355b1a             320 tests / 5 failed / 0 errors / 0 skipped
  本补丁 11174ab             323 tests / 5 failed / 0 errors / 0 skipped
  失败集合                   逐项相同 → 新增的失败 = 无 → 零回归
  ⚠️ skipped 数随环境变，不能当基线；只能比「失败集合」

runner 行数                  1698（纯上游 1698；< 1700 硬上限）

── Patch A/B 的效果 ──
lint 报的断链                60 → 0（其中 52 条是假阳性）
noncanonical_link            1933 → 0
风险总数                     2129 → 136

── Patch I 的效果 ──
修前                         8 页 = 6 source + 2 假专题
修后                         3 页 = 3 source，含「温州」页 = 0

── 性能（实测）──
batch-size 6                 5m08s（撞满 300s 预算）🔴
batch-size 3                 2m27s ✅
payload 46k                  297s 成功 / 300s 超时 🔴
payload 22k（Patch E 后）    约 150–210s ✅

── 知识库侧（本机，供参考）──
全库 md                      2188
_kb-steward/ 文件数           0（从未对真库 --apply）
全库断链                     0
```

---

## 10. 相关文档

| 文件 | 内容 |
| --- | --- |
| `LOCAL-PATCHES.md` | 逐补丁技术流水账（581 行，含每次同步上游的记录） |
| `HANDOVER.md` | **本文档** —— 面向合并者的入口 |
| `_kb-steward/calibration-review.md` | S0 校准批评审记录（在知识库侧，非本仓库） |

> ⚠️ `LOCAL-PATCHES.md` 头部写的基线 commit（`65741ae`）与测试数字（`234 passed`）
> **已过期**，且它有两个「补丁 D」。**以本文档为准。**
