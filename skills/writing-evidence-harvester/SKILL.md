---
name: writing_evidence_harvester
description: 围绕具体选题抽取事实、案例、数据、人物、时间线、反方观点和可引用证据。
---

# Skill：writing-evidence-harvester

## 定位

证据采集。围绕一个具体选题，把知识库中的来源拆成可审计、可引用、可复用的证据条目。

本 Skill 不负责组织完整写作结构，不负责写正式文章。

## 触发

- 用户指定选题并要求找证据、素材、案例、数据
- topic-card 的 `stage` 达到 `promising`
- material-pack 需要补充证据

## 输入

- 具体选题
- `wiki/topics/*.md`
- `wiki/seeds/*.md`
- `wiki/sources/*.md`
- `raw/*.md`

## 输出

位置：

```text
wiki/evidence/
```

文件命名：

```text
YYYY-MM-DD-evidence-选题.md
```

页面类型：

```text
evidence-pack
```

## Evidence Pack 元数据

```yaml
---
title:
type: evidence-pack
status: growing
stage: collecting
created:
updated:
sources:
related:
topic:
tags:
confidence:
review_required:
---
```

`status` 只能使用全局生命周期状态。证据采集流程态写入 `stage`：

```text
collecting
compiled
insufficient
conflict
```

本 Skill 默认只能创建：

```text
collecting
insufficient
```

只有证据条目足够、来源可解析、冲突已标注时，才允许 `status: compiled`、`stage: compiled`。

## 正文结构

```markdown
# 证据包：选题

## 选题边界

## 来源范围

## 事实

## 案例

## 数据

## 人物/机构

## 时间线

## 反方观点

## 可引用片段候选

## 证据强度

## 来源限制

## 待补缺口
```

## 方法

1. 先确认选题边界，过宽则拆成子问题。
2. 按来源逐篇抽取证据，不跨来源混写。
3. 每条证据标注：来源、类型、内容、可信度、可用场景。
4. 区分事实、观点、解释、推断。
5. 把证据不足项交给 `knowledge-gap-finder`。

## 证据条目格式

```markdown
- 类型：
- 证据：
- 来源：
- 可支持的论点：
- 可信度：
- 限制：
```

## 质量标准

- 不能只有来源列表。
- 每条证据都要有具体来源。
- 至少包含事实、案例或数据中的两类。
- 引述候选必须短，并指向来源。
- 不得把来源摘要当成证据。

## 失败处理

- 选题过宽：退回 topic-insight-miner 拆题。
- 证据不足：`status: manual_review`，`stage: insufficient`。
- 来源冲突：`status: conflict`，保留冲突。

## 禁止事项

- 不写成材料包。
- 不写成正式段落。
- 不省略来源限制。
- 不把模型总结伪装成证据。
