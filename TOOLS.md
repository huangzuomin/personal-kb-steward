# TOOLS.md

## 知识库路径

```text
C:\path\to\your\workspace\wiki
```

## 重要目录

- `quicknote/`：临时碎片、随手记。
- `inbox/`：待处理输入。
- `raw/`：原始资料，原则上只读。
- `wiki/seeds/`：种子卡。
- `wiki/sources/`：来源页。
- `wiki/concepts/`：概念页。
- `wiki/topics/`：专题页与选题卡。
- `wiki/evidence/`：证据包。
- `wiki/material-packs/`：写作材料包。
- `wiki/work-memory/`：工作记忆。
- `outputs/`：运行报告。
- `log.md`：操作日志。

## 本地 CLI

在本工作区运行：

```powershell
python scripts\personal_kb_steward.py status
python scripts\personal_kb_steward.py lint
python scripts\personal_kb_steward.py run
python scripts\personal_kb_steward.py run --apply
python scripts\personal_kb_steward.py plan "发现选题"
python scripts\personal_kb_steward.py task "整理知识库"
python scripts\personal_kb_steward.py task --apply "整理知识库"
python scripts\personal_kb_steward.py task "发现选题"
python scripts\personal_kb_steward.py task "准备写作素材：地方媒体AI转型"
python scripts\personal_kb_steward.py task "沉淀工作记忆"
python scripts\personal_kb_steward.py task "检查知识库健康"
python scripts\personal_kb_steward.py review
python scripts\personal_kb_steward.py processed
```

CLI 默认只生成 dry-run plan。只有显式添加 `--apply` 才允许写入派生页面、报告、日志和运行状态。任何模式都不允许覆盖原始资料。

## 安全执行模型

```text
scan -> route -> plan -> dry-run -> manual review queue -> apply -> report/log/state
```

- `plan`：只生成执行计划，不写知识库。
- `task`：默认等同 dry-run plan。
- `task --apply`：按入口的 primary skill 执行写入。
- `run`：默认只生成每日计划。
- `run --apply`：执行每日整理。
- `review`：查看 `.openclaw/manual-review/queue.jsonl` 中的人工确认项。
- `processed`：查看 `.openclaw/processed-index.json` 中的已处理索引。

## 产品入口

用户入口收敛为：

- `整理知识库`：处理 quicknote/inbox，生成 seed，并提示健康风险。
- `发现选题`：从已有知识网络生成候选 topic-card。
- `准备写作素材`：生成 evidence pack、gap report、material pack。
- `沉淀工作记忆`：整理会议、项目、周报和复盘。
- `检查知识库健康`：检查断链、来源、状态、重复和积压。

内部 Skill 编排见 `workflows.json`，自然语言路由见 `router.json`。

## 质量检查重点

- 双链是否能解析到真实文件。
- 双链是否使用知识库相对路径，例如 `wiki/topics/xxx.md`。
- 待创建页面是否放在“待创建链接”，而不是伪造 `[[...]]`。
- `sources` 是否是具体来源文件。
- `status` 是否只使用知识生命周期状态。
- `stage` 是否承载候选、草稿、校验、证据强弱等流程态。
- `mindseed-grow` 是否跳过未指定、未标记、过长的 `raw/`。
- 健康检查是否输出 `health_score` 与 P0/P1/P2/P3 风险分级。
- 是否存在无来源结论。
- 是否存在占位文字。
- 主题页是否有 3 个以上来源。
- 材料包是否有事实、案例、时间线、反方和缺口。
