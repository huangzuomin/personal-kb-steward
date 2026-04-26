# MVP Runtime

Phase 5 重写 MVP 三个 Skill 的运行时边界：

- `mindseed-grow`
- `work-memory-weave`
- `kb-lint-healthcheck`

## mindseed-grow

默认输入：

```text
quicknote/
inbox/
```

`raw/` 仅在以下条件满足时进入：

- 文件长度不超过 `scan.raw_seed_max_chars`
- 或包含 `scan.seed_markers` 中任一标记：`#seed`、`#随手记`、`#待生长`

其余 raw 文件会被跳过，并进入 plan/manual review 提示，不直接生成 seed。

重复策略：

- 已存在同标题 `seed-card` 时，跳过新建。
- 后续阶段再实现追加更新与合并。

## work-memory-weave

默认只处理：

```text
quicknote/
inbox/
```

输出 `work-memory`，并包含：

- 来源文件
- 项目/事项
- 时间线
- 关键决策
- 行动项
- 人物/组织
- 风险与阻塞
- 下次回看
- 人工复核项

缺日期或缺行动项时，页面标记为：

```yaml
status: manual_review
stage: needs_context
```

## kb-lint-healthcheck

新增：

- `health_score`
- `risk_buckets.P0/P1/P2/P3`
- `noncanonical_links`
- `stage_migrations`

风险含义：

- P0：破坏性风险
- P1：可信度风险，如断链、来源问题
- P2：结构风险，如非规范双链、状态迁移、缺元数据
- P3：维护风险，如孤立页、积压、占位内容

lint 仍然只读；修复动作进入后续 plan/apply 或人工确认流程。
