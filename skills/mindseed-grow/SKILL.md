---
name: mindseed_grow
description: 将 quicknote、inbox 以及用户指定 raw 中的碎片转化为可追溯、可生长的 seed card，避免把原始资料误升格为结论。
---

# Skill：mindseed-grow

## 定位

碎片信息生长。将临时记录、剪藏、想法、问题、案例片段和短材料整理成“知识种子”，为后续专题、概念、证据包、写作材料包和工作记忆提供生长入口。

本 Skill 不负责生成正式概念页、专题页、证据包、材料包或结论页。

核心原则：**碎片先变 seed，不直接变结论**。

## 触发

- 用户要求整理 `quicknote/`、`inbox/`
- 用户明确指定某个 `raw/` 文件进行 seed 提取
- 文件中出现 `#seed`、`#随手记`、`#待生长`
- 多条碎片围绕同一问题反复出现

## 输入

默认输入：

- `quicknote/*.md`
- `inbox/*.md`

受限输入：

- `raw/*.md` 仅在用户指定、文件较短、或含 seed 标记时处理

参考目录：

- `wiki/seeds/`
- `wiki/topics/`
- `wiki/concepts/`
- `wiki/projects/`
- `wiki/work-memory/`

## 输出

位置：

```text
wiki/seeds/
```

文件命名：

```text
YYYY-MM-DD-核心议题.md
```

页面类型：

```text
seed-card
```

## Seed Card 元数据

所有 seed card 必须包含：

```yaml
---
title:
type: seed-card
status: seed
stage: seed
created:
updated:
sources:
related:
tags:
confidence:
review_required:
---
```

`status` 使用全局生命周期状态。seed 的流程态写入 `stage`，默认与 `status` 一致：

```text
seed
growing
merged
compiled
archived
manual_review
```

本 Skill 默认只能创建：

```text
seed
manual_review
```

不得直接创建 `compiled` 状态。

## 正文结构

```markdown
# 知识种子：标题

## 核心议题

这条碎片真正指向的问题是什么。

## 来源文件

- quicknote/xxx.md
- inbox/xxx.md

## 关键信号

- 具体信号一
- 具体信号二

## 可生长方向

- 可能进入的专题：
- 可能形成的概念：
- 可能关联的项目：
- 可能转化的写作选题：

## 相关链接

- [[已有专题]]
- [[已有概念]]
- [[已有项目]]

## 质量状态

- confidence:
- status:
- review_required:

## 人工复核项

- 哪些关联不确定
- 哪些判断缺少来源
- 是否需要合并到已有 seed
```

## 方法

1. 建立来源索引，确保每个来源路径真实存在。
2. 判断碎片类型：事实、案例、观点、问题、项目记录、写作素材、工具资料。
3. 对同主题碎片做轻量聚类，优先生成“主题型 seed”，避免一篇原文一张低价值卡。
4. 每张 seed 只表达一个核心问题或主题。
5. 用具体来源列表写入 `sources`，不得写 `raw/` 这种粗路径。
6. 检查 `wiki/seeds/` 中是否已有近似 seed。
7. 若已有近似 seed，追加来源和更新记录，不新建重复页。
8. 不下最终结论，只写“可能生长为”的方向。

## raw 输入限制

`raw/` 默认不批量进入本 Skill。

允许处理：

- 用户明确指定的 `raw/*.md`
- 文件较短，且明显是摘录、灵感、问题或案例片段
- 文件中含 `#seed`、`#待生长`、`#随手记`

应跳过：

- 长文
- PDF 转文本
- 完整调研报告
- 会议纪要
- 多主题资料合集

跳过时建议交给：

```text
topic-research-compile
work-memory-weave
```

## 查重规则

如果满足任一条件，视为可能重复：

- 标题高度相似
- 核心议题高度相似
- 来源指向同一项目或同一专题
- 关联概念重合度较高

重复时，不新建页面，而是在已有 seed 中追加：

```markdown
## 更新记录 YYYY-MM-DD

新增来源：
- xxx

新增信号：
- xxx

是否建议升级：
- 是 / 否

人工确认：
- xxx
```

## 质量标准

- 至少 1 个真实来源。
- 来源路径必须具体到文件。
- 相关链接必须可解析，或标记为待确认。
- 不得复制大段原文。
- 不得把模型推测写成事实。
- 不得将原始资料直接升格为结论。
- 如果来源不足、主题不清、链接不确定，`status: manual_review`。

## 失败处理

- 无法判断主题：生成 `manual_review` seed。
- 来源链接无法解析：不生成正式 seed，写入健康报告或运行报告。
- 内容重复：链接到已有 seed，并追加来源。
- 输入为空：跳过并写入 log。
- raw 文件过长且无明确 seed 标记：跳过，建议交给 `topic-research-compile`。

## 禁止事项

- 不删除原始文件。
- 不改写 `quicknote/`、`inbox/`、`raw/` 原文。
- 不创建正式 concept page。
- 不创建正式 topic page。
- 不生成写作素材包。
- 不把一句灵感包装成成熟判断。
- 不贪心。宁可少建高质量 seed，也不要批量制造低价值卡片。
