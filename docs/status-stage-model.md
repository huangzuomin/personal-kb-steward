# Status And Stage Model

## Demo baseline 新产物合同

2026-09-21 迭代中新生成的 source/seed 使用类型配对约束：

| type | 正常候选 | 上下文不足或需审核 |
| --- | --- | --- |
| seed-card | status=seed, stage=candidate | status=manual_review, stage=needs_context |
| source-note | status=growing, stage=compiling | status=manual_review, stage=needs_context |

这些配对由 `core/schemas/` 的类型 schema 校验。旧 producer 的 growing/seed 与 compiled/compiled 只在新产物适配边界归一化，不构成存量迁移。本轮不执行下文历史迁移建议。

schema 合法、引用匹配或 coverage=full 均不表示事实已获独立核实。其他类型仍沿用其现有合同，新增类型后单独补充。

Phase 3 将状态模型拆成两个字段：

- `status`：知识对象生命周期。
- `stage`：具体 Skill 或产品流程中的阶段。

## status

`status` 只能使用：

```text
raw
seed
growing
compiled
linked
stale
conflict
archived
manual_review
```

## stage

`stage` 用来表示流程态，例如：

```text
candidate
promising
collecting
assembling
draft
checking
weak
unsupported
insufficient
open
active
waiting
blocked
done
```

## 示例

选题卡：

```yaml
type: topic-card
status: growing
stage: promising
```

观点校验：

```yaml
type: claim-check
status: manual_review
stage: unsupported
```

工作记忆：

```yaml
type: work-memory
status: growing
stage: active
```

## 迁移规则

历史页面如果出现：

```yaml
status: candidate
status: promising
status: draft
status: checking
```

应迁移为：

```yaml
status: growing
stage: candidate
```

或按具体语义使用 `manual_review`、`compiled`、`conflict` 等生命周期状态。

当前 lint 会把这类历史页面列入 `stage_migrations`，不再计入非法 `status_issues`。


## Runtime 约束

- 判断流程态必须读取 `stage`，不能把 `active`、`candidate` 等流程值当作 `status`。
- `status` 与 `stage` 可以在个别词值上重合，但代码必须按字段语义判断，不能混用。
- lint 中的低置信度活跃页规则使用 `confidence: low + stage: active`。
