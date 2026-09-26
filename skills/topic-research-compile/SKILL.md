---
name: topic_research_compile
description: 将长资料沉淀为带原始快照和证据的 source-note；已保存的合格来源再由独立类型化编排生成 concept、case、topic 候选。
---

# Skill：topic-research-compile

## 定位

专题资料的来源沉淀。将长文、报告和完整案例先编译为可核验的 `source-note`，保留原始字节 hash、覆盖状态、逐字证据和待研究的 topic hints。

本 Skill 负责处理 `raw/` 中的长资料。它比 `mindseed-grow` 更适合长文、PDF 转文本、研究报告、完整案例集。单篇来源须先成为合格的 `source-note`，再由下游类型化编排按契约处理。

## 触发

- 用户指定一个专题进行调研沉淀
- `raw/` 中存在长文、报告或多来源资料
- `raw/` 中存在需要完整读取和证据保留的资料
- 需要在已保存的来源卡基础上继续做类型化概念、案例或专题发现

## 输入

- `raw/*.md`（来源编译的实际输入）
- 已通过 plan/review/apply 保存的 `wiki/sources/*.md`（下游类型化发现的输入）
- `card_pipeline.topic_questions` 中明确配置的研究问题（专题阶段必需）

## 输出

来源编译器直接产出：

```text
wiki/sources/
```

每个成功来源输入最多形成一个 `source-note`，其中保留 `card_state`、原始来源链接、证据单元、覆盖状态和 `topic_hints`。`partial`、`zero`、`blocked`、`error` 等输入结果会按真实状态记录，不伪装成完整来源卡。

保存并确认合格的 source-note 由独立的类型化编排（`init-kb` 的累计阶段或 `finalize-kb`）继续生成候选，目标目录可能为：

```text
wiki/concepts/
wiki/cases/
wiki/topics/
```

类型化阶段一次分别运行 concept、case、topic 生成器。concept/case 可以由单一合格来源支撑，但必须通过各自证据契约；完整 topic 需要明确研究问题、足够的不同且可用来源和可编译判断。source-note 中的 topic hint 只是待研究提案，不会自动升级为 topic。

## 来源与双链边界

来源编译器只把经过路径校验的实际原始来源写成双链：

- source-note 的实际来源：`[[raw/xxx.md]]`
- 类型化页面的已确认关联对象：`[[wiki/sources/xxx.md]]`、`[[wiki/concepts/xxx.md]]`、`[[wiki/cases/xxx.md]]` 或 `[[wiki/topics/xxx.md]]`

模型文本不能制造双链。只有索引中确认存在的路径才可进入 `related` 双链；未确认的目标留在 `pending_links` 或“待创建链接”中，使用裸文本路径。

以下形式不能作为生成链接：

```markdown
raw/温州新闻网AI战略研究.md
topics/地方媒体AI战略...
concepts/多做少说策略
```

已确认实际存在的路径才写成：

```markdown
[[raw/温州新闻网AI战略研究.md]]
[[wiki/topics/2026-04-25-地方媒体AI战略的多做少说困境.md]]
[[wiki/concepts/多做少说策略.md]]
```

如果目标页面尚不存在，保留裸文本路径，例如 `待创建：concepts/灯塔计划`，不要伪造 `[[...]]`。

## 当前卡片状态与元数据

新 producer 使用 `status` 表示生命周期、`stage` 表示当前流程；不能把流程值写入 `status`，也不能把 `compiled`/`linked` 当作本轮自动成功。当前 canonical schema 的合法配对为：

| type | 正常候选 | 来源不足或需审核 |
| --- | --- | --- |
| `source-note` | `status: growing` + `stage: compiling` | `status: manual_review` + `stage: needs_context` |
| `seed-card` | `status: seed` + `stage: candidate` | `status: manual_review` + `stage: needs_context` |
| `concept-page` | `status: growing` + `stage: draft` | `status: manual_review` + `stage: needs_context` |
| `case-story` | `status: growing` + `stage: draft` | `status: manual_review` + `stage: needs_context` |
| `topic-page` | `status: growing` + `stage: assembling` | `status: manual_review` + `stage: insufficient` |

所有候选仍需人工审核；schema 合法、引用匹配或 `coverage: full` 都不等于事实已独立核实。完整字段以 `core/schemas/` 下对应 schema 为准。

## 下游 topic-page 正文参考

以下结构只适用于满足来源和问题门槛、并进入类型化 topic 候选的页面；source executor 本身只输出 `source-note`，不会按此模板直接生成专题页。

```markdown
# 专题：标题

## 主题边界

## 双链索引

- 来源：
- 已有种子：
- 相关专题：
- 概念页：
- 来源笔记：
- 待创建链接：

## 来源地图

## 已知事实

## 核心概念

## 案例与证据链

## 分歧与冲突

## 缺口

## 下一步
```

## 方法

1. 建立来源清单，按一手资料、二手资料、用户笔记、搜索结果分级，并保存原始字节 hash。
2. 建立全库文件索引，解析已有 seed、topic、concept、case、source-note；确认路径后才写入链接。
3. 为关键来源生成或更新 `source-note`，保留证据单元、覆盖状态和待研究的 `topic_hints`。
4. 将来源页写入 plan，经过 review 后由 `apply-plan` 或 `review apply-approved` 写入；失败、部分完成和零结果保留真实输入状态。
5. 仅对已保存且合格的 source-note 运行独立类型化发现：concept/case 逐类满足证据契约，topic 只在有明确问题和足够不同来源时生成。
6. 对已确认存在的对象维护 `related` 双链；未确认的对象留在 `pending_links` 或裸文本路径，不让模型文本直接造链。
7. 分开标注事实、观点、解释、假设、冲突、覆盖和证据匹配；引用匹配不等于事实已核实。
8. 将已确认的证据结构交给 `writing-evidence-harvester` 继续细化。

## 双链规则

来源编译和类型化发现分开处理：

- `source-note` 只链接已经索引确认的实际 raw/source 路径。
- concept、case、topic 页只链接实际参与其证据契约的 source-note、seed 或其他类型化页面。
- topic hint 是提案，不能因为标题相似就反向链接或创建 topic page。
- 核心判断在证据字段中保留来源、原文片段和匹配位置；正文双链用于导航，不替代证据字段。

双链路径必须真实可解析。不能解析的链接不得写成 `[[...]]`，只能放入“待创建链接”或 `pending_links`。

## 查重规则

如果已有 topic page 满足以下任一条件，优先更新而非新建：

- 主题边界高度重合
- sources 重合度高
- concepts 重合度高
- 已有 topic page 是同一问题的上位或下位主题

## 质量标准

- 每个成功 source-note 都要保留原始 hash、实际来源、证据单元和覆盖状态；`partial`、`zero`、`blocked`、`error` 不得伪装成成功。
- concept/case 的每个候选判断都要通过对应 schema 的证据契约；单一来源可以支持它们，但不能跳过证据校验。
- 完整 topic 必须有明确配置的问题、足够的不同且可用来源（默认门槛以配置为准）和可编译判断；source-note 的 hint 或单篇摘要不满足条件。
- 核心判断的证据要保存具体来源和原文片段；导航双链必须可解析，不能用路径字符串冒充证据。
- 冲突资料不能被抹平；来源不足、关联不确定或需要人工判断时使用 canonical 的 `manual_review`/对应 stage。
- 低可信来源只能作为线索，不能作为结论依据。
- 不得把长文直接摘要成 topic page 后宣布完成，也不得把 schema 合法或 `coverage: full` 当作事实已核实。

## 失败处理

- 来源编译不足：保留对应输入的 `partial`、`zero`、`blocked` 或 `error` 结果；需要人工补充时使用 `manual_review` + `needs_context` 的 source-note。
- concept/case 证据不足：保留候选为 `manual_review` + `needs_context`，不伪造完整判断。
- 未配置 `card_pipeline.topic_questions` 时 topic 阶段是 `disabled/not_configured`，不调用 provider，也不产生 topic 页；已配置明确问题但没有相关合格来源时保留 `zero/no_relevant_sources`；有来源但证据范围不足以形成 full topic 时，才使用 `manual_review` + `insufficient`，不把 hint 或单篇来源升级为完整 topic。
- 来源冲突写入证据和冲突区；`conflict` 是历史/全局状态，不能替代当前类型 schema 的合法 status/stage 配对。
- 双链无法解析：列入待创建或待修复链接，不生成不存在的 `[[...]]`；不要用 `compiled`/`linked` 掩盖失败。
- 任何计划写入都先经过 review；人工拒绝、应用失败和原始 hash 变化必须保留可追踪状态，不靠原样重跑覆盖。

## 禁止事项

- 不覆盖原始 raw。
- 不生成正式文章。
- 不把单篇资料包装成成熟专题。
- 不隐藏证据冲突。
- 不生成孤立页面。
- 不把裸路径当作知识链接。
- 不创建指向不存在页面的假双链。
