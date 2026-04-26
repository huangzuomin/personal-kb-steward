---
name: project_review_synthesizer
description: 从项目复盘和工作记录中提炼经验、方法论、决策模式和下次可复用的行动原则。
---

# Skill：project-review-synthesizer

## 定位

项目复盘提炼。将 work-memory、decision-record、timeline 和用户复盘记录沉淀为可复用的方法论资产。

本 Skill 不负责写宣传稿、总结稿或正式汇报稿。

## 触发

- 用户要求复盘项目
- 某个项目结束或阶段结束
- work-memory 中存在多个决策和行动项
- 用户要求提炼经验、教训、方法论

## 输入

- `wiki/work-memory/*.md`
- `wiki/project-reviews/*.md`
- `quicknote/*.md`
- `inbox/*.md`
- 用户指定项目材料

## 输出

位置：

```text
wiki/project-reviews/
```

文件命名：

```text
YYYY-MM-DD-review-项目名.md
```

页面类型：

```text
project-review
```

## Project Review 元数据

```yaml
---
title:
type: project-review
status: growing
stage: draft
created:
updated:
sources:
related:
project:
people:
tags:
confidence:
review_required:
---
```

`status` 只能使用全局生命周期状态。复盘流程态写入 `stage`：

```text
draft
validated
actionable
```

本 Skill 默认只能创建：

```text
draft
```

不得直接创建 `stage: validated` 或 `stage: actionable`，除非用户确认。

## 正文结构

```markdown
# 项目复盘：标题

## 项目背景

## 目标

## 关键过程

## 决策节点

## 做对了什么

## 出了什么问题

## 可复用方法

## 下次检查清单

## 仍需确认
```

## 方法

1. 汇总项目来源，不凭记忆复盘。
2. 抽取目标、行动、结果、决策、阻塞。
3. 区分“这次有效”和“普遍有效”。
4. 将经验改写成可行动原则。
5. 保留未确认假设。

## 质量标准

- 必须基于项目事实。
- 方法论必须可行动。
- 必须保留失败和风险。
- 不得写空泛鸡汤。

## 失败处理

- 来源不足：`manual_review`。
- 项目边界不清：要求先整理 work-memory。
- 结果未知：只生成阶段复盘。

## 禁止事项

- 不写正式汇报稿。
- 不夸大成果。
- 不把个人猜测写成经验。
- 不删除原始工作记录。
