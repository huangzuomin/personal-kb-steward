---
name: case_story_bank_builder
description: 从资料中沉淀可复用案例和故事资产，形成可检索、可引用、可复用的案例库。
---

# Skill：case-story-bank-builder

## 定位

案例库建设。将分散在 raw、source、evidence、work-memory 中的案例沉淀为可复用的故事资产。

本 Skill 不负责写故事成稿，只负责建立案例卡。

## 触发

- 用户要求整理案例、故事库、案例库
- evidence-pack 中出现多个具体案例
- material-pack 缺少案例支撑
- 某个案例可反复服务多个选题

## 输入

- `raw/*.md`
- `wiki/evidence/*.md`
- `wiki/sources/*.md`
- `wiki/topics/*.md`
- `wiki/work-memory/*.md`

## 输出

位置：

```text
wiki/cases/
```

文件命名：

```text
YYYY-MM-DD-case-案例名.md
```

页面类型：

```text
case-story
```

## Case Story 元数据

```yaml
---
title:
type: case-story
status: growing
stage: draft
created:
updated:
sources:
related:
people:
organizations:
tags:
confidence:
review_required:
---
```

`status` 只能使用全局生命周期状态。案例流程态写入 `stage`：

```text
draft
usable
needs_context
```

本 Skill 默认只能创建：

```text
draft
needs_context
```

不得直接创建 `stage: usable`，除非背景、行动、结果和来源都完整。

## 正文结构

```markdown
# 案例：标题

## 一句话概括

## 参与者

## 时间地点

## 背景

## 事件经过

## 结果

## 可说明的观点

## 适用主题

## 来源

## 风险与限制

## 人工复核项
```

## 方法

1. 识别具体案例，而不是抽象观点。
2. 区分案例事实和解释。
3. 标注案例适用的主题和论点。
4. 检查案例是否已有卡片。
5. 来源不足时标记 `status: manual_review`、`stage: needs_context`。

## 查重规则

可能重复：

- 参与者相同
- 事件相同
- sources 相同
- 可说明观点相同

重复时更新已有案例卡，不新建。

## 质量标准

- 没有来源不能入库。
- 案例不能只是一句话。
- 必须包含背景、行动、结果中的至少两项。
- 必须写明适用主题和限制。

## 失败处理

- 只有观点没有事件：退回 evidence-harvester。
- 缺背景：`status: manual_review`、`stage: needs_context`。
- 来源冲突：进入人工复核。

## 禁止事项

- 不编故事。
- 不把抽象观点包装成案例。
- 不改写成文学化叙事。
