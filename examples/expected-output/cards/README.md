# 参考卡（Reference Cards）

> 从 `examples/mini-vault/` 生成的**人工示范卡片**，用于回答一个问题：
> **这条流水线"产出正确"的时候，产出到底应该长什么样？**

## 一、这是什么

10 张卡片，覆盖 5 种类型，**全部来自 `examples/mini-vault/` 这一个夹具库**，不含任何外部或私人内容。

```
cards/
├── seeds/      ×3   （含 1 张负例基线）
├── concepts/   ×2
├── cases/      ×1
├── sources/    ×3   （含 1 张"拒绝摘要"的编码损坏卡）
└── topics/     ×1
```

它们**不是**运行产物——是人工写的**目标态**。用途有三：

1. **验收基线**：`plan` 出来的卡片应该达到这个形状。
2. **讨论载体**：把「卡片该写什么」从抽象争论变成可逐行对照的具体文本。
3. **回归测试**（可选）：其中若干张可直接转成断言，见第五节。

## 二、怎么复现与对比

```powershell
python scripts\init_config.py --kb examples\mini-vault
python scripts\personal_kb_steward.py plan "整理知识库"
python scripts\personal_kb_steward.py plan "发现选题"
python scripts\personal_kb_steward.py plan "准备写作素材：地方媒体AI转型"
```

把 `.openclaw/plans/` 里的产出与 `cards/` 下的对应文件并排看。**重点不是字数或措辞，而是下面三件事：**

| 看什么 | 错误的形态 | 正确的形态 |
| --- | --- | --- |
| 卡的单位 | 一次聚类 / 一段原文 | **一个念头 / 一个概念 / 一个机制** |
| 链接 | `related: []` 恒空 | 指向**真实存在**的卡；不存在的进「待创建链接」 |
| 判据 | 覆盖了几篇源文件 | **能否被独立引用** |

## 三、五条基线主张

### 1. 模板骨架不用改，要改的是往里填什么

`skills/mindseed-grow/renderer.py` 输出的骨架（`核心议题 / 来源文件 / 关键信号 / 可生长方向 / 相关链接 / 待创建链接 / 人工复核项`）**本身是好的**。
`seeds/` 下的三张参考卡**逐字沿用了这个骨架**。

问题不在骨架，在于填充策略：

| 骨架小节 | 当前填充 | 应该填充 |
| --- | --- | --- |
| `## 核心议题` | 聚类理由（`seed_quality.py:71`：`cluster.get('reasoning')`） | **念头本身**（半成品状态也要写出来） |
| `## 可生长方向` | 两句写死的模板文案（`seed_quality.py:73`） | **每卡 3–5 条，逐卡不同，且必须含反例方向** |
| `## 相关链接` | `related` 硬编码 `[]`（`seed_quality.py:74`） | 指向真实存在的卡 |

→ 对照：`seeds/组织能力-而非工具.md` 的 `## 可生长方向` 有 5 条，其中 2 条是**反例/证伪方向**
（「有没有机构只需要工具？」「什么现象能说明能力已内化？」）。这是写死的模板永远给不出的。

### 2. seed 卡允许「单源」，也允许「不生长」

- `seeds/知识库的价值在可复用性.md` **只有 1 个来源**——念头本来就是零星的。
  当前 `min_sources` 默认 2 会把这类卡判成 `needs_context`，**方向反了**：1 源卡恰恰最像「一个念头」。
- `seeds/猫砂盆种大蒜-一个不应被聚类的生活念头.md` 是一张**负例基线**。
  它带 `#seed` 标签，但与库内任何 AI / 媒体内容**毫无语义关联**。
  **它存在的意义是被拒绝**：如果流水线把它并进「地方媒体 AI 转型」，那就是过聚类。
  这张卡同时说明：**`related: []` 有时是正确答案，不是缺陷。**

### 3. 概念卡的价值在「边界」，不在「定义」

定义到处都能查到。一张概念卡独有的贡献是**它不是什么**。
`concepts/演示层困境.md` 逐条排除了 4 个易混概念（试点失败 / 技术不成熟 / 采纳率低 / 缺预算），
并给出**一条可检验的判据**：「这条 AI 流程替代了哪个岗位的哪个具体动作？」

> ⚠️ 仓库目前**没有** `concept-page` 的模板或骨架（见第四节），本 PR 提出一个，供讨论。

### 4. 案例卡按「可复用机制」切，不按项目切

`cases/Patch-本地新闻通讯的AI自动化.md` 的标题是**张力**，不是**成功**。
案例卡天然只记录成功路径，因此最容易退化成成功学。写明「可复用点」与「边界（什么时候不适用）」是唯一的解药。

### 5. 来源卡的第一职责是评估来源，不是转述来源

`sources/` 下三张卡演示了三种来源病理，且**处理方式各不相同**：

| 卡 | 来源病理 | 正确产出 |
| --- | --- | --- |
| `source-patch-ai-newsletter` | 自述为课堂占位材料，无出处 | 正常摘要 + **显著的质量标记**，标注不可引用 |
| `source-local-news-ai-risk` | 三段并列，无论证、无出处 | 摘要 + 指出「这是风险清单而非分析」 |
| `source-industry-report` | **编码损坏，内容不可恢复** | **拒绝摘要**，转 `manual_review` / `stage: insufficient` |

最后一张是关键：当来源不可读时，**最诚实也最有价值的产出是「我读不了，原因如下」**。
如果流水线对它产出了一段通顺的中文摘要，那是在**对不可读内容编造内容**——这是最严重的一类缺陷。

## 四、骨架来源（哪些沿用，哪些新提）

| 类型 | 骨架来源 | 本 PR 的角色 |
| --- | --- | --- |
| `seed-card` | `skills/mindseed-grow/renderer.py` + `schema.json` | **沿用**，只改填充语义 |
| `source-note` | `core/templates/source_note.j2` | **沿用** |
| `topic-page` | `skills/topic-research-compile/SKILL.md:127-154` | **沿用** |
| `concept-page` | **无** | **新提出**（一句话定义 / 展开 / 边界 / 判据 / 关系 / 出处） |
| `case-story` | **无** | **新提出**（背景 / 做法 / 结果 / 核心张力 / 可复用点 / 边界 / 出处） |

## 五、可直接转成回归断言的三条

1. **不过聚类**：`raw/random_idea.md` 与 `quicknote/001-ai-newsroom.md` 的产出
   **必须落在不同的 seed 卡中**。
2. **不编造**：`raw/industry_report.md` 的产出必须为 `manual_review`，
   **且摘要中不得出现除 `Zettelkasten` / `AI Agent` / `40%` 之外的实质内容**。
3. **不伪造链接**：任何卡片正文与 frontmatter 中出现的 wikilink，其目标必须真实存在
   （含附件口径：解析目标 = 所有 `.md` 的 stem ∪ 全库所有文件的 basename）；
   不存在的目标必须写成纯文本 `待创建：<类型>/<名称>`（依据 `SKILL.md:78`）。

## 六、顺带发现的四个缺陷（均可复现）

### 1. 🔴 `examples/mini-vault/raw/industry_report.md` 编码已损坏

- 255 字节，其中 `EF BF BD`（UTF-8 编码的 **U+FFFD 替换字符**）出现 **35 次**。
- 含义：原文曾用**错误编码解码**过一次，无法映射的字节被替换；此后又存为 UTF-8 ⇒ **中文内容不可逆丢失**。
- 文件中另混入一段 **UTF-16BE** 片段，可辨认的 ASCII 仅剩 `Zettelkasten` / `AI Agent` / `40%`。
- **建议**：修复该夹具，或**保留它作为编码鲁棒性用例**，并在 `examples/expected-output/README.md`
  中明确声明「本文件故意损坏，预期产出为 `manual_review`」。

### 2. 🔴 `schema.json` 从未被任何代码读取

```bash
$ grep -rln "schema.json" core/ scripts/
（无输出）
$ grep -i jsonschema requirements.txt
（无输出）
```

仓库里 5 个 skill 各有一份 `schema.json`（`mindseed-grow`、`topic-insight-miner`、
`writing-evidence-harvester`、`writing-material-pack`、`official-material-handoff`），
但**没有任何代码引用它们**，`jsonschema` 也不在依赖里 ⇒ **schema 是纯文档，不产生任何约束**。

**后果是可观测的**：`skills/mindseed-grow/renderer.py:13-14` 把 LLM 返回的
`item['status']` / `item['stage']` **原样写进 frontmatter**，不做校验。

### 3. 🔴 真实产物 30% 超出自己的 schema

在 `mindseed-grow/schema.json` 中：`status ∈ {seed, manual_review}`、`stage ∈ {seed, needs_context}`。

对某真实知识库的 148 张 seed 卡统计：

| 字段 | 取值 | 数量 | 是否合规 |
| --- | --- | --- | --- |
| `stage` | `needs_context` | 57 | ✅ |
| `stage` | `seed` | 47 | ✅ |
| `stage` | **`candidate`** | **43** | ❌ 超出 enum |
| `stage` | **`compiled`** | **1** | ❌ 超出 enum |
| `status` | `seed` | 90 | ✅ |
| `status` | `manual_review` | 57 | ✅ |
| `status` | **`compiled`** | **1** | ❌ 超出 enum |

⇒ **44 / 148（30%）的 `stage` 取值超出 schema 声明的 enum，且没有任何环节报错。**

### 4. ⚠️ `stage` 存在两套互相冲突的词汇表

| 来源 | `stage` 的合法取值 |
| --- | --- |
| `skills/mindseed-grow/schema.json` | `seed`、`needs_context` |
| `docs/status-stage-model.md` | `candidate`、`promising`、`collecting`、`draft`、`checking`、`weak`、`active`、`done` … |

两个列表**没有交集**。而 `docs/status-stage-model.md:85-87` 的迁移规则又要求
`status: candidate` → `status: growing` + **`stage: candidate`**，
即把 `candidate` 当作合法 stage —— 与 schema 直接矛盾。

**另**：`skills/topic-research-compile/` **没有 `schema.json`**，而其余 4 个 skill 都有 ⇒ 校验能力不对称。

> 本 PR 的参考卡按**各自 skill 的 schema** 取值（seed 用 `stage: seed`）。
> 这不代表 schema 是对的——只是为了让基线可校验。**两套词汇表需要先合并，再谈强制。**

## 七、局限（诚实说明）

1. **深度受夹具限制。** 夹具本身是 60–70 字的一句话材料，因此参考卡不可能很厚。
   本 PR 的目标是**结构与语义**，不是信息量。
2. **夹具自述为占位材料。** `patch-ai-newsletter.md` 与 `local-news-ai-risk.md` 都写明
   「真实使用时应替换为可追溯来源」。参考卡保留了这个事实并显式标注，
   **没有假装素材比实际更厚**——这一点本身也是基线的一部分。
3. **`concept-page` / `case-story` 的骨架是本 PR 提出的**，不是仓库既有约定，需要维护者裁定。
4. **未做跨卡去重。** `Patch` 案例卡与「规模化与社区连接的张力」概念卡刻意有重叠内容，
   用于演示「同一材料按不同粒度切」；真实场景需要判定谁吸收谁。
5. **链接密度未校准。** 夹具库太小（10 个源文件），链接网络无法反映真实库的密度。

## 八、验证

- 全部 wikilink 指向真实存在的目标（`mini-vault` 内文件或本目录内卡片）；
  不存在的目标一律写成纯文本 `待创建：<类型>/<名称>`，符合 `SKILL.md:78`。
- 未包含任何外部、私人或凭据类内容——全部文本可追溯到 `examples/mini-vault/`。
