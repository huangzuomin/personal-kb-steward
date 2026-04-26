# Status And Stage Model

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
