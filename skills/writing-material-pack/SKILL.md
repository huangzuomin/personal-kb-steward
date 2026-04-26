---
name: writing_material_pack
description: 将证据、案例、观点、风险和缺口组织成写作前材料包，但不生成正式文章。
---

# Skill：writing-material-pack

## 定位

写作前结构化。将 evidence-pack、topic-card、gap-report、claim-check 整理成“可以开始写”的材料包。

本 Skill 不负责写正式文章，不负责生成完整成稿。

## 触发

- 用户指定选题并要求“打包素材”“准备写作”
- evidence-pack 已经达到 `compiled` 或接近完成
- topic-card 推荐等级为 A 或 B

## 输入

- `wiki/topics/*.md`
- `wiki/evidence/*.md`
- `wiki/gaps/*.md`
- `wiki/claim-checks/*.md`
- 用户指定选题

## 输出

位置：

```text
wiki/material-packs/
```

文件命名：

```text
YYYY-MM-DD-material-选题.md
```

页面类型：

```text
material-pack
```

## Material Pack 元数据

```yaml
---
title:
type: material-pack
status: growing
stage: assembling
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

`status` 只能使用全局生命周期状态。写作准备流程态写入 `stage`：

```text
assembling
draft_ready
insufficient
```

本 Skill 默认只能创建：

```text
assembling
insufficient
```

只有证据、案例、反方、缺口和结构均满足标准时，才允许 `status: compiled`、`stage: draft_ready`。

## 正文结构

```markdown
# 写作材料包：选题

## 选题

## 核心张力

## 可用事实

## 可用案例

## 可用数据

## 时间线

## 关键人物/机构

## 正反观点

## 风险与缺口

## 可选结构

## 不建议写法

## 写作前检查清单
```

## 方法

1. 先复用或调用 evidence-pack，不直接从 raw 拼材料。
2. 对材料分层：事实、解释、观点、故事、数据、疑问。
3. 形成 2-3 个可选写作角度。
4. 标注每个角度需要的关键证据。
5. 明确哪些内容不能写，因为证据不足。
6. 将未解决缺口交给 `knowledge-gap-finder`。

## 质量标准

- 不得只有来源列表。
- 至少 5 条证据。
- 至少 1 个案例。
- 至少 1 个反方或风险。
- 必须列出缺口。
- 必须有“不建议写法”。
- 不写正式文章段落。

## 失败处理

- 证据不足：`status: manual_review`，`stage: insufficient`。
- 缺反方：标记 `review_required: true`。
- 选题不清：退回 topic-insight-miner。
- claim 未校验：建议调用 claim-evidence-checker。

## 禁止事项

- 不写成稿。
- 不生成标题党。
- 不把素材包当结论页。
- 不隐藏证据缺口。
