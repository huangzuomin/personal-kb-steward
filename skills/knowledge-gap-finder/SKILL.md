---
name: knowledge_gap_finder
description: 识别某个主题或写作材料包还缺少哪些数据、案例、反方、政策依据、时间线和一手来源。
---

# Skill：knowledge-gap-finder

## 定位

知识缺口识别。防止“材料看起来很多，但关键证据缺失”。

本 Skill 不补资料、不生成结论，只指出当前主题要继续推进还缺什么。

## 触发

- 用户问“还缺什么”
- evidence-pack 或 material-pack 标记为 `insufficient`
- claim-check 出现 weak、unsupported、conflict
- topic-card 准备升级前需要评估证据完整性

## 输入

- `wiki/topics/*.md`
- `wiki/evidence/*.md`
- `wiki/material-packs/*.md`
- `wiki/claim-checks/*.md`
- 用户指定主题

## 输出

位置：

```text
wiki/gaps/
```

文件命名：

```text
YYYY-MM-DD-gap-主题.md
```

页面类型：

```text
gap-report
```

## Gap Report 元数据

```yaml
---
title:
type: gap-report
status: growing
stage: open
created:
updated:
sources:
related:
topic:
tags:
priority:
confidence:
review_required:
---
```

`status` 只能使用全局生命周期状态。缺口处理流程态写入 `stage`：

```text
open
partially_resolved
resolved
```

本 Skill 默认只能创建：

```text
open
```

不得直接创建 `stage: resolved`。无法判断时使用 `status: manual_review`、`stage: open`。

## 正文结构

```markdown
# 知识缺口报告：主题

## 当前主题

## 已有证据

## 缺口清单

## 优先级

## 不补会造成的风险

## 推荐补充路径

## 可交给哪个 Skill

## 人工复核项
```

## 缺口类型

- 缺数据
- 缺案例
- 缺反方
- 缺政策/制度依据
- 缺时间线
- 缺一手来源
- 缺中国语境或本地语境
- 缺可验证引用
- 缺用户自身项目经验

## 方法

1. 对照选题或材料包的核心论断。
2. 检查每个论断是否有事实、案例、数据、反方。
3. 判断缺口对写作或研究的影响。
4. 给出补充路径，而不是泛泛说“多找资料”。
5. 标注可交给哪个后续 Skill。

## 质量标准

- 每个缺口必须对应具体风险。
- 每个缺口必须有优先级。
- 不得泛泛写“需要更多资料”。
- 不得凭空要求无关材料。

## 失败处理

- 主题不清：要求先生成 topic-card。
- 材料包为空：退回 evidence-harvester。
- 缺口无法判断：`manual_review`。

## 禁止事项

- 不替用户搜索外部资料，除非用户要求。
- 不把缺口补成结论。
- 不生成正式写作结构。
