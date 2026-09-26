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

## 生成器入口（M2）

案例卡的自动生成走 `core.case_generation.generate_cases`：

```python
from core.case_generation import generate_cases
result = generate_cases(notes, cfg, *, known_paths=None,
                        analysis_mode="llm", call_provider=None, now=None)
```

- 输入 note 与 source 生产线一致（rel/title/body/metadata/source_text/source_sha256
  完整原始快照 + 原始字节 hash）；`metadata.upstream_analysis` 可附上游登记的
  `source_kind`/`limitations`/`speakers`（allow-list、限量，模型不可删除）。
- 返回 `{state, reason, items, pages, claims, analysis, issues}`；
  `pages[].content` 的 frontmatter 已持久化 `card_state`（claims 可经
  `core.claims.validate_claims` 对同一原始快照严格重载）。
- 结果陈述（数字或定性观察）、可复用机制、机制推断、适用条件的权威文字一律是
  所引编译判断的原句（单一权威文本）：机制来源陈述用 fact 判断
  （`reusable_mechanism_claim`），机制推断必须绑 kind=inference 判断
  （`mechanism_inference_claim`），条件逐项给 claim 引用。引用不合法即整条丢弃并记
  诊断，不为填空编造机制；模型给的平行展示文本与判断原文不一致时被忽略。
  `uncertainties` 是待研究问题（页面标注"模型整理，非来源事实"）。
  来源断言一律 `source_asserted: true`，不代表独立验证。
- `card_level` 区分 project / mechanism；同一故事+同一判断集在两个层级重复登记时，
  第二张强制 `manual_review/needs_context`。查重为证据并集式合并，不丢证据。
- 单一来源可以成卡：没有跨来源数量配额；证据不足 → stub，不编造。

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
