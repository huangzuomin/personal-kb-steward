---
name: topic_insight_miner
description: 从知识库中发现值得写、值得研究或值得立项的选题，而不是按词频机械生成主题。
---

# Skill：topic-insight-miner

## 定位

选题洞察。它从已有 seed、topic、source、work-memory 中发现“值得写”的问题，而不是统计高频词。

本 Skill 只生成选题卡，不生成正式文章，不生成材料包。

## 触发

- 用户问“有什么值得写”
- 用户要求挖掘选题、洞察、题目、写作方向
- 某个主题已有多个 seed 或来源
- 发现资料充足但尚未表达的张力

## 输入

- `wiki/seeds/*.md`
- `wiki/topics/*.md`
- `wiki/sources/*.md`
- `wiki/work-memory/*.md`
- 用户指定主题或问题

## 输出

位置：

```text
wiki/topics/
```

文件命名：

```text
YYYY-MM-DD-topic-核心问题.md
```

页面类型：

```text
topic-card
```

## Topic Card 元数据

```yaml
---
title:
type: topic-card
status: growing
stage: candidate
created:
updated:
sources:
related:
tags:
score:
confidence:
review_required:
---
```

`status` 只能使用全局生命周期状态。选题流程态写入 `stage`：

```text
candidate
promising
ready_for_evidence
rejected
```

本 Skill 默认只能创建：

```text
candidate
promising
```

不得直接创建 `stage: ready_for_evidence`，除非证据数量、张力和边界都已满足。来源不足时使用 `status: manual_review`、`stage: candidate`。

## 正文结构

```markdown
# 选题卡：标题

## 一句话选题

## 选题张力

## 为什么值得写

## 知识库证据

## 可用角度

## 目标读者/使用场景

## 反方与风险

## 缺口

## 推荐等级

## 下一步
```

## 信号

- 多个来源指向同一张力或问题
- 资料充足但尚未形成表达
- 中外实践存在差异
- 用户项目与公共议题发生交叉
- 有冲突、有反直觉、有未被解释的现象
- 存在可验证的案例和证据链

## 方法

1. 先从 seed/topic/source 网络中找问题，不从高频词直接生成标题。
2. 识别“主题 + 张力 + 证据 + 读者价值”。
3. 过滤过宽主题，如“AI”“媒体”“写作”。
4. 优先生成问题式选题，例如“地方媒体 AI 转型为什么更难？”。
5. 给出 A/B/C 推荐等级：
   - A：证据充分、张力明确、可进入证据包
   - B：有潜力但缺关键证据
   - C：只是线索，需继续积累

## 查重规则

可能重复：

- 一句话选题高度相似
- 核心张力相同
- sources 高度重合
- 目标读者和使用场景相同

重复时更新已有 topic-card 的“新增证据”和“推荐等级”，不新建。

## 质量标准

- 至少 3 个具体来源，少于 3 个则 `manual_review`。
- 选题必须包含明确张力。
- 必须有可验证证据，不允许只凭直觉。
- 不得只生成宽泛主题名。
- 必须列出风险或反方。

## 失败处理

- 主题过宽：生成拆题建议，不生成正式 topic-card。
- 来源不足：`status: manual_review`，`stage: candidate`。
- 没有张力：降级为 seed 或建议继续积累。

## 禁止事项

- 不写正式文章。
- 不生成标题党。
- 不把趋势词包装成选题。
- 不跳过证据包直接进入材料包。
