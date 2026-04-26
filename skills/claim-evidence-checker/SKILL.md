---
name: claim_evidence_checker
description: 校验观点和论断是否有证据支持，标记强支持、弱支持、冲突和无来源。
---

# Skill：claim-evidence-checker

## 定位

观点证据校验。防止凭感觉写作，防止知识库被无来源结论污染。

本 Skill 不负责生成新观点，只负责检查已有论断的证据状态。

## 触发

- 用户要求核查观点、论断、提纲
- material-pack 准备进入写作前
- topic-page 中出现强判断
- evidence-pack 中存在冲突材料

## 输入

- 用户输入的一组 claims
- `wiki/topics/*.md`
- `wiki/material-packs/*.md`
- `wiki/evidence/*.md`
- `wiki/sources/*.md`

## 输出

位置：

```text
wiki/claim-checks/
```

文件命名：

```text
YYYY-MM-DD-claim-check-主题.md
```

页面类型：

```text
claim-check
```

## Claim Check 元数据

```yaml
---
title:
type: claim-check
status: growing
stage: checking
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

`status` 只能使用全局生命周期状态。证据校验流程态写入 `stage`：

```text
checking
verified
weak
unsupported
conflict
```

本 Skill 默认只能创建：

```text
checking
weak
unsupported
conflict
```

不得直接创建 `stage: verified`，除非每条核心论断都有强证据。无来源论断使用 `status: manual_review`、`stage: unsupported`。

## 正文结构

```markdown
# 观点证据校验：主题

## 校验对象

## 论断清单

## 支持证据

## 反向证据

## 证据等级

## 是否可写入正式稿

## 需要补充的证据

## 人工复核项
```

## 证据等级

```text
strong：多个可靠来源直接支持
medium：单一可靠来源直接支持
weak：只有间接线索
unsupported：无来源
conflict：来源之间冲突
```

## 方法

1. 将输入拆成可校验的独立论断。
2. 为每条论断寻找支持来源和反向来源。
3. 判断证据是直接支持、间接支持还是无关。
4. 标注能否写入正式稿。
5. 对 weak、unsupported、conflict 生成补证建议。

## 质量标准

- 不能把 weak 写成 strong。
- unsupported 必须进入人工复核。
- conflict 必须保留冲突，不强行调和。
- 每条论断必须单独评级。

## 失败处理

- 输入不是论断：要求改写成可校验句。
- 来源不足：标记 `stage: unsupported`，必要时 `status: manual_review`。
- 论断过大：拆成多个小论断。

## 禁止事项

- 不替用户美化论断。
- 不用模型常识代替来源。
- 不隐藏反向证据。
- 不把“可写”当成“已经证明”。
