---
name: topic_research_compile
description: 将长期主题资料沉淀为 topic page、source note、concept page 和 evidence chain。
---

# Skill：topic-research-compile

## 定位

专题调研沉淀。将长文、报告、多来源资料和多个 seed card 沉淀为可长期复用的研究资产。

本 Skill 负责处理 `raw/` 中的长资料。它比 `mindseed-grow` 更适合长文、PDF 转文本、研究报告、完整案例集。

## 触发

- 用户指定一个专题进行调研沉淀
- `raw/` 中存在长文、报告或多来源资料
- 多个 seed 已经指向同一研究问题
- 用户要求生成 topic page、source note、concept page

## 输入

- 用户指定主题
- `raw/*.md`
- `wiki/seeds/*.md`
- `wiki/topics/*.md`
- `wiki/evidence/*.md`

## 输出

位置：

```text
wiki/topics/
wiki/sources/
wiki/concepts/
wiki/evidence/
```

页面类型：

```text
topic-page
source-note
concept-page
evidence-chain
```

## 双链要求

专题沉淀不是生成孤立长文。所有产物必须进入 Obsidian 知识网络。

必须双链化的对象：

- 原始来源：`[[raw/xxx.md]]`
- 已有 seed：`[[wiki/seeds/xxx.md]]`
- 已有 topic-card/topic-page：`[[wiki/topics/xxx.md]]`
- 新建 source-note：`[[wiki/sources/xxx.md]]`
- 新建 concept-page：`[[wiki/concepts/xxx.md]]`
- 新建 evidence-chain：`[[wiki/evidence/xxx.md]]`

禁止只写裸路径：

```markdown
raw/温州新闻网AI战略研究.md
topics/地方媒体AI战略...
concepts/多做少说策略
```

必须写成：

```markdown
[[raw/温州新闻网AI战略研究.md]]
[[wiki/topics/2026-04-25-地方媒体AI战略的多做少说困境.md]]
[[wiki/concepts/多做少说策略.md]]
```

如果目标页面尚不存在，不得伪造 `[[...]]`。应写：

```markdown
- 待创建：concepts/灯塔计划
```

并放入“待创建链接”栏目。

## Topic Page 元数据

```yaml
---
title:
type: topic-page
status: growing
stage: compiling
created:
updated:
sources:
related:
concepts:
tags:
confidence:
review_required:
---
```

`status` 只能使用全局生命周期状态。专题沉淀流程态写入 `stage`：

```text
growing
compiled
linked
conflict
archived
manual_review
```

本 Skill 默认只能创建：

```text
growing
manual_review
```

只有在来源充分、证据链清楚、冲突已标注时，才允许标记 `compiled`。

## 正文结构

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

1. 建立来源清单，按一手资料、二手资料、用户笔记、搜索结果分级。
2. 建立全库文件索引，解析已有 seed、topic、concept、source-note。
3. 为关键来源生成或更新 `source-note`。
4. 抽取概念，生成或更新 `concept-page`。
5. 聚合多个来源形成 `topic-page`，不能做单篇摘要。
6. 在正文建立“\u53cc链索引”，把来源、seed、topic、concept、source-note 互相连上。
7. 标注事实、观点、解释、假设、冲突。
8. 将证据链交给 `writing-evidence-harvester` 继续细化。

## 互链规则

生成 topic-page 时：

- 必须链接所有 sources。
- 必须链接参与沉淀的 seed cards。
- 必须链接新建或已有 concept pages。
- 必须链接新建或已有 source notes。
- 必须在每个核心判断后附至少一个来源双链。

生成 source-note 时：

- 必须链接其对应 raw/source。
- 必须反向链接相关 topic-page。
- 必须链接可支持的 concept-page。

生成 concept-page 时：

- 必须链接提出该概念的 sources。
- 必须链接使用该概念的 topic-page。
- 必须列出相近概念和冲突概念。

双链路径必须真实可解析。不能解析的链接不得写成 `[[...]]`，只能放入“待创建链接”。

## 查重规则

如果已有 topic page 满足以下任一条件，优先更新而非新建：

- 主题边界高度重合
- sources 重合度高
- concepts 重合度高
- 已有 topic page 是同一问题的上位或下位主题

## 质量标准

- 专题页至少 3 个具体来源。
- 每个核心判断至少有 1 个来源支持。
- 每个核心判断后的来源必须用 `[[...]]` 双链表示。
- 正文必须包含“\u53cc链索引”。
- `sources` 可保留路径数组，但正文不能只写裸路径。
- 新建 source-note 与 concept-page 必须反向链接 topic-page。
- 冲突资料不能被抹平，必须标注 `conflict`。
- 低可信来源只能作为线索，不能作为结论依据。
- 不得把长文直接摘要成 topic page 后宣布完成。

## 失败处理

- 来源不足：生成 `manual_review` topic stub。
- 来源冲突：标记 `status: conflict` 或列入冲突区。
- 主题过宽：先拆成子专题。
- 双链无法解析：不要生成正式 `compiled/linked` 状态，标记 `manual_review`，并列出待创建或待修复链接。
- 相关 concept/source-note 尚未创建：先创建或列入“待创建链接”，不能伪造双链。

## 禁止事项

- 不覆盖原始 raw。
- 不生成正式文章。
- 不把单篇资料包装成成熟专题。
- 不隐藏证据冲突。
- 不生成孤立页面。
- 不把裸路径当作知识链接。
- 不创建指向不存在页面的假双链。
