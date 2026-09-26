# Product Entries

Phase 1 将用户可见入口从 11 个 Skill 收敛为 5 个高频任务。

## 入口

| Entry | 用户说法 | Primary Skill | 内部 Pipeline |
|---|---|---|---|
| `organize_kb` | 整理知识库 | `mindseed-grow` | `mindseed-grow` -> `kb-lint-healthcheck` |
| `discover_topics` | 发现选题 | `topic-insight-miner` | `topic-insight-miner` -> `knowledge-gap-finder` |
| `prepare_writing` | 准备写作素材 | `writing-material-pack` | `writing-evidence-harvester` -> `knowledge-gap-finder` -> `writing-material-pack` |
| `weave_work_memory` | 沉淀工作记忆 | `work-memory-weave` | `work-memory-weave` -> `project-review-synthesizer` |
| `healthcheck` | 检查知识库健康 | `kb-lint-healthcheck` | `kb-lint-healthcheck` |

## 当前兼容策略

现有 `scripts/personal_kb_steward.py task` 仍然是单 Skill 执行模型。自然语言先命中产品入口，再执行该入口的 `primary_skill`。

当前 `task` 和 `run` 先保存 dry-run plan；无人工审核项时用 `apply-plan`，有审核项时先 `review approve`，再用 `review apply-approved --run-id` 写入。`init-kb` 和 `finalize-kb` 的 `--apply` 也遵守这条 review queue 边界，不是绕过审核的唯一写入条件。

## 边界

- 不把 11 个 Skill 作为普通用户入口。
- 不在 Phase 1 引入多 Skill 批量写入。
- 不修改 `raw/`、`quicknote/`、`inbox/`。
- 不修复历史断链，历史修复进入后续 plan/apply 流程。
