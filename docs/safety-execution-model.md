# Safety Execution Model

Phase 2 引入安全执行模型，让所有用户任务默认先生成 plan，再由用户显式 `--apply` 执行。

## 执行链

```text
scan -> route -> plan -> dry-run -> manual review queue -> apply -> report/log/state
```

## 命令

```powershell
python scripts\personal_kb_steward.py plan "发现选题"
python scripts\personal_kb_steward.py task "发现选题"
python scripts\personal_kb_steward.py task --apply "发现选题"
python scripts\personal_kb_steward.py run
python scripts\personal_kb_steward.py run --apply
python scripts\personal_kb_steward.py review
```

## 默认行为

- `plan` 只写 `.openclaw/plans/*.json`。
- `task` 默认只生成 dry-run plan。
- `run` 默认只生成每日 dry-run plan。
- `task --apply` 和 `run --apply` 才会写知识库派生页面、日志、报告和 state。

## 人工确认队列

人工确认队列路径：

```text
.openclaw/manual-review/queue.jsonl
```

当前进入队列的典型事项：

- raw 文件将被默认整理入口碰到。
- lint 发现断链、来源、状态等健康风险。
- 后续 Phase 会加入重复合并、重命名、删除、结论改写等高风险动作。

## 当前限制

现有运行时仍是单 `primary_skill` 执行模型；完整 pipeline 编排、可预览 diff、逐项 approve/reject 会在后续阶段继续实现。

## 状态模型

Phase 3 后，`status` 只表示知识生命周期：

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

具体流程态统一写入 `stage`，例如 `candidate`、`promising`、`draft`、`checking`、`weak`、`unsupported`、`insufficient`、`open`、`active`。
