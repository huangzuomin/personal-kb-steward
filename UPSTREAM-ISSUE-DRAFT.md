# seed-card 质量与 index/log 路径外泄 —— 真库分批验证发现

> 代码基线：`f05e7d1`（PR #15 合并后 main）
> 验证环境：真实知识库 1890 篇（raw 132 / quicknote 219），GLM-5.3-Flash
> 统计快照：**47 张 seed-card + 27 篇 source-note**（分批跑到 raw 27/132 时）
> 复核脚本：`scripts/eval_seeds.py`、`scripts/analyze_plan.py`

## 先说结论

`source-note` 层**质量可靠，可以放心用**（12 篇抽样全部准确，无占位/兜底内容）。
问题集中在 **seed-card 层**，共 7 项，按严重度排列。

---

## 1. 🔴 「关键信号」100% 是机械截断，无任何信息量

实测 **96/96 条**关键信号（47 张卡）都是源文件头部 240 字符的硬截断 —— 无一例外。

根因链：

```
skills/mindseed-grow/renderer.py:51   item["signals"]
  ← skills/mindseed-grow/executor.py:56  f"{n['title']}：{n.get('summary','')}"
    ← core/markdown.py:16  note_summary() = re.sub(r"\s+"," ",note.body)[:240] + "..."
```

对日报型笔记，文件头永远是模板样板，于是每张卡的关键信号长得一模一样：

```
- 2022 年 10月 19日 星期三：# 2022 年 10月 19日 星期三 # 晨间日记 --- ## 每日例程
  - [x] 10 - 19 整理笔记 ✅ 2022-10-21 - [x] 10 - 19 Steem 写作 ✅ ...
```

**建议**：`note_summary()` 用于「卡片内展示」时应改为 LLM/启发式抽取的关键句，
而不是 `text[:240]`；至少应对 frontmatter 之后的**正文首个非列表段落**取值。

---

## 2. 🔴 空内容照样出卡，且标 `confidence: high`

「晨间日记例行打卡」的核心议题原文：

> [LLM语义聚类] 这批日记仅包含每日例程（整理笔记、Steem写作、阅读、得到课程、Anki复习）
> 的打卡记录，**无额外实质内容**，构成统一的日常习惯追踪主题。

仍然生成了 seed-card，`confidence: high`、`review_required: false`。

**模型知道这是空的，还是照样发货。** 根因在
`skills/mindseed-grow/executor.py:40`：

```python
review = confidence == "low"
```

复核标记只与聚类置信度挂钩，与「内容是否含信息量」无关。

**建议**：对 LLM 自述「无实质内容 / 无额外内容」的聚类，不生成卡片，
或强制 `review_required=True` + `status: manual_review`。

---

## 3. 🔴 无跨批次去重，同主题反复出卡

每轮聚类只看本批输入，不与已落盘的 seed 比对，导致：

| 主题 | 卡片数 |
| --- | --- |
| 晨间日记 / 每日例程 | **4**（晨间日记例行打卡、晨间日记固定例程打卡、晨间日记与每日例程打卡、晨间日记例程与空记录碎片） |
| 空投 / 加密交互 | **3**（加密空投与测试网交互攻略、加密空投与链上交互机会追踪、加密货币空投交互机会追踪） |
| 温州开埠 | 2 |
| 温州网络公益 / 网上问政 | 2 |
| 单位党务学习与工会事务 | 2 |
| DIY 装机 | 2 |

另有 **22/78 篇来源被 2 张以上卡同时引用（28%）**。

样本从 17 张涨到 47 张时，重复与碎片化都在**变差**：

| 指标 | 17 张时 | 47 张时 |
| --- | --- | --- |
| 单来源成卡 | 4（24%） | **16（34%）** |
| 来源被复用 | 7/34（21%） | **22/78（28%）** |

**建议**：生成前对已有 seed 的 title/terms 做一次相似度比对（或用 object_id 去重），
命中则合并到既有卡而不是新建。

---

## 4. 🟠 `manual_review_on_unresolved_link` 在 mindseed-grow 未生效

`quality_gate.manual_review_on_unresolved_link: true`，但 seed-card 的
`review_required` 恒等于 `confidence == "low"`（`executor.py:40`），
`pending_links` 非空也不触发复核。实测 **47/47 张 `review_required: false`**，
其中 15 张 `confidence: medium`、32 张 `high`。

另外 `pending_links = cluster.get("terms", [])[:3]` —— 装的是**聚类 terms 不是链接**，
却被渲染进「## 待创建链接」小节，且用 `bullet()` 输出为纯文本而非 wikilink。
小节名有误导性。

---

## 5. 🟠 apply 会写到 `write.*` 配置的目录之外

配置 `write.*` 全部指向 `_kb-steward/*`，但一次 apply 后库根多出三处：

| 路径 | 代码位置 | 可配置 |
| --- | --- | --- |
| `index.md` | `core/index_builder.py:170` `root / "index.md"` | ❌ 硬编码 |
| `logs/<YYYY>/…md` | `core/log_manager.py:22` `index.root / "logs" / yyyy` | ❌ 硬编码 |
| `log.md` | `config.write.log_file`（默认 `"log.md"`） | ✅ |

这与 PR #15 修掉的「四层路径权限」是同一类问题，只是发生在 **index/log 层**。
对已有自建根目录结构（PARA/PARO）的库，`index.md` 和 `logs/` 是意外的顶层侵入；
`index.md` 标题还是英文 `Personal Knowledge Base`。

**建议**：`index.md` 与 `logs/` 也应从 `config.write` 取（例如 `index_file`、`logs_dir`），
未配置时再回落到库根。

> 补充：`index.md` 其实有护栏（`index_builder.py:177`：库根 index.md 若属用户所有则改写
> `.openclaw/generated-index.md`）。但**原本不存在 index.md 的库会被判为「非用户所有」而直接写库根**，
> 所以护栏挡不住首次写入。

---

## 6. 🟠 含需审核页面的计划无法被应用

`apply-plan` 遇到 `page_requires_manual_review(page) is True` 的页面直接
`raise SystemExit`（`scripts/personal_kb_steward.py:1267`）。

- `allow_reviewed` 是 `command_apply_plan()` 的内部参数，**没有 CLI 开关**
- 拦截条件是**页面自身属性**，不是审核队列状态 ⇒ `review approve` 也解不开
- `init-kb --apply` 遇之直接 `return 1`（`personal_kb_steward.py:1166-1168`），
  **整批丢弃**

实测被拦的「Twitter账号封禁与申诉」是 1 个来源、落地率 6% 的弱页 —— **护栏判断是对的**，
但代价是同批另外 7 个正常页面一起被丢掉。

**建议**：加 `--allow-reviewed` CLI 开关；或让 `init-kb --apply` 跳过被拦页面、
应用其余页面，而不是整批放弃。

---

## 7. 🟡 单来源也生成 seed-card

实测 **16/47 张卡（34%）只有 1 个来源**。`quality_gate.min_sources_for_topic: 3`
只约束 topic 页，不约束 seed-card。粒度偏碎，且下游 topic 聚合时这些卡贡献不了证据。

**建议**：seed-card 也应有最小来源数（或至少标 `status: manual_review`）。

---

## 附带确认（非缺陷，供参考）

- **`plan --llm` 在未初始化的库上产出 0 页**，并写入 high-risk 人工项
  `wrong_entry_for_initialization：organize_kb 不能用于 raw 全量初始化；请改用 init-kb 分批 pipeline。`
  —— 这是护栏生效，但 README 建议的验证命令
  `plan --llm "发现选题 AI 与媒体"` 在这种库上什么都不会产出，文档需注明前置条件。
- **dry-run 并非完全只读**：会往 `.openclaw/manual-review/queue.jsonl` 追加记录。
- **apply-plan 失败可能是部分写入**：重跑时输出「跳过已存在页面：N」兜住，
  不会重复覆盖 ⇒ 失败后原样重跑是安全的。

---

## 复现方式

```powershell
# 分批初始化（dry-run 不推进 processed index，必须 apply 后才会取下一批）
python scripts\personal_kb_steward.py init-kb --batch-size 3
python scripts\personal_kb_steward.py apply-plan <plan>
```

跑几批后，直接看 `_kb-steward/seeds/*.md`：

- 每条「## 关键信号」是否以 `...` 收尾 ⇒ 问题 1
- 是否存在「核心议题自述无实质内容」却已落盘的卡 ⇒ 问题 2
- 标题是否出现同主题多张 ⇒ 问题 3
- `review_required` 是否全为 `false` ⇒ 问题 4
- 库根是否出现 `index.md` / `logs/` ⇒ 问题 5

> 文中引用的 `scripts/eval_seeds.py`、`scripts/analyze_plan.py` 是**本地复核脚本**，
> 不在本仓库内；判定方法已写在最后一节，需要的话我可以整理成 PR 附上去。

## 判定「有没有编造」的方法（推荐给上游做回归测试）

只比对「核心议题 vs 自己的来源」的绝对重合度**不可靠** —— CJK bigram 含跨词边界噪声
（如「网交」「互与」「在空」源文本来就没有），连接词还会稀释。
正确做法是**带对照组**：

```
命中率(核心议题 → 自己的来源)  vs  命中率(核心议题 → 随机 N 篇同类文件)
只有前者显著高于后者，才算真落地
```

本库实测 **47 张卡**：

- **42 张 1.7x–51.7x（真落地）** ⇒ LLM 不编造，这一层是可信的
- **5 张 0.94x–1.11x（与随机无异 = 空卡）**：4 张是「晨间日记 / 每日例程」类，
  加 1 张「Twitter账号解封申诉」

两种口径的结论天差地别，而这 5 张正好是真正的缺陷所在。
