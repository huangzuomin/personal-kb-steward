# 个人知识库管家 (Personal Knowledge Steward)

**将你的碎片笔记、专题资料和工作记录，持续转化为可复用的知识生产系统。**

[![Status](https://img.shields.io/badge/Status-Beta-blue.svg)]()
[![Python](https://img.shields.io/badge/Python-3.10+-brightgreen.svg)]()
[![License](https://img.shields.io/badge/License-MIT-green.svg)]()

> **注意：这不是一个网页采集器、也不是一个直接帮你写文章的机器人。**
> 这是一个基于 Zettelkasten 与 PARA 理念的**知识库后台运行器**。它会在不破坏你原始数据的前提下，默默在后台将你的“资料”升华为“知识资产”。

---

## 🌟 核心能力

Personal KB Steward 致力于解决个人知识库常见的“只存不看”、“越攒越乱”的问题。它通过定义明确的工作流，在本地运行：

1. **🌱 碎片生长 (`mindseed-grow`)**：自动发现孤立的、短小的 `quicknote` 或 `inbox` 笔记，通过大语言模型 (LLM) 进行语义聚类，将它们合并为具备上下文的“种子卡片”。
2. **🧠 工作记忆沉淀 (`work-memory-weave`)**：从你的每日会议、流水账中自动提取出可复用的“原则”、“教训”或“长期事实”。
3. **🎯 选题与素材提炼 (`topic-insight-miner` / `writing-evidence-harvester` / `writing-material-pack`)**：根据你指定的选题，自动遍历知识库寻找支撑证据、数据、案例，甚至自动帮你指出“知识缺口”与“反方观点缺失”。
4. **📦 机关材料交接 (`official-material-handoff`)**：把 evidence-pack 与 material-pack 打包为 `official-material-workflow` 可消费的交接包，供下游进行文种判断、成稿和审稿。
5. **🏥 知识库健康诊断 (`kb-lint-healthcheck`)**：自动扫描坏链、孤儿页面、缺乏双链的目录，并评估风险等级。

## 🛡️ 安全承诺：Dry-Run 与 人工确认队列

你的知识库非常重要，我们绝不擅自修改：

- **Dry-Run 优先**：所有的命令默认只生成 `plan`，绝对不会写入知识库。
- **严格隔离**：智能体的产出永远存放在特定的派生目录（如 `wiki/seeds/`, `wiki/topics/`），绝对不会修改或删除你的 `raw/` 原始资料。
- **Manual Review 队列**：当遇到不确定的内容（如证据不足、高风险修改、内容模糊）时，智能体会将其放入 `review queue`，等待你的人工批准 (Approve) 才会执行。

---

## 🚀 快速开始与部署

### 1. 作为 OpenClaw 子智能体导入 (推荐)

如果你正在使用 [OpenClaw](https://docs.openclaw.ai/) 系统，你可以通过以下几步将本管家无缝挂载为你的子智能体：

1. **克隆代码库到工作区**：
   ```bash
   git clone https://github.com/your-username/personal-kb-steward.git ~/.openclaw/workspace-personal-steward
   ```
2. **安装依赖**（如果你的 Python 环境未包含）**：**
   ```bash
   cd ~/.openclaw/workspace-personal-steward
   pip install -r requirements.txt
   ```
3. **配置主控网关**：
   编辑 `~/.openclaw/openclaw.json`，将该路径配置为智能体工作区：
   ```json
   {
     "agents": {
       "defaults": {
         "workspace": "~/.openclaw/workspace-personal-steward"
       }
     }
   }
   ```
   然后运行 `openclaw setup --workspace ~/.openclaw/workspace-personal-steward` 进行初始化。

### 2. 本地独立运行 (独立使用配置)

如果你不使用 OpenClaw 框架，也可以完全独立运行本系统。

**步骤 1: 配置 LLM 密钥**
为了启用高质量的语义分析能力，请配置你的 LLM 密钥。
新建根目录 `.env`（或直接填写 `config.json` 的 `llm` 段），使用 OpenAI-compatible 接口。例如：

```ini
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_API_KEY=你的密钥
OPENAI_MODEL=你的模型名
```

默认模型调用超时为 300 秒，可通过 `llm.timeout_seconds` 调整。
👉 [详细的 LLM 配置指南](docs/llm-setup.md)

### 2. 初始化知识库路径

```powershell
python scripts\init_config.py --kb "C:\path\to\your\markdown\wiki"
python scripts\validate_config.py
```

### 3. 日常使用命令

普通用户只需要向管家下达这 5 种自然语言指令：

- `python scripts\personal_kb_steward.py task "整理知识库"`
- `python scripts\personal_kb_steward.py task "发现选题"`
- `python scripts\personal_kb_steward.py task "准备写作素材：[你的主题]"`
- `python scripts\personal_kb_steward.py task "沉淀工作记忆"`
- `python scripts\personal_kb_steward.py task "检查知识库健康"`

*(提示：加上 `--apply` 才会真正写入知识库，否则只生成 plan 供预览。)*

### 4. 管理人工审核队列

当有不确定的内容时，你可以用 review 命令处理：

```powershell
# 查看待处理项
python scripts\personal_kb_steward.py review list

# 查看单条详情
python scripts\personal_kb_steward.py review show <ID>

# 批准
python scripts\personal_kb_steward.py review approve <ID> --reason "确认无误"
```

---

## 🎓 课堂 / 测试演示

我们准备了一个微型的知识库和一键演示脚本，方便你快速体验全流程，不会影响你真实的知识库数据。

**运行一键演示：**
```powershell
.\demo.ps1
```
演示结束后，脚本会自动生成一个精美的 **HTML 演示报告** (`demo_report.html`) 供你预览效果。

---

## 📚 详细文档

想要深入了解架构和设计理念，请参阅：

- [LLM 接入配置](docs/llm-setup.md) **(新!)**
- [5 个用户自然语言入口](docs/product-entries.md)
- [安全执行模型 (Dry-run / Apply / Review)](docs/safety-execution-model.md)
- [状态流转模型 (Status & Stage)](docs/status-stage-model.md)
- [路径与双链治理红线](docs/path-link-governance.md)
- [幂等追踪 (Processed Index)](docs/processed-index.md)
- [MVP Skill 运行机制](docs/mvp-runtime.md)


---

## 开发与测试

仓库测试应能在 clean clone 环境运行，不依赖本机已有的 `config.json`。

本地验证：

```bash
python -m pip install -r requirements.txt
python -m pytest -q  # 不预先创建本地配置
cp config.example.json config.json
python scripts/validate_config.py
```

GitHub Actions 在 Ubuntu Python 3.11/3.12 和原生 Windows Python 3.12 上验证。先在无 config.json 的 checkout 运行完整测试，再单独校验示例配置。PR 基线变更会触发新验证，并记录实际 checkout 与两侧父提交。


## 稳定知识对象

新知识页在 plan 序列化时由程序分配 `object_id` 与 `revision`，更新保留身份；`canonical_path` 从真实文件路径派生。旧页继续可读，不自动批量迁移。重复 ID 与更新基线冲突会在落盘前阻断。

完整契约、兼容策略和暂不支持的事务能力见 [Stable Knowledge Objects](docs/stable-knowledge-objects.md)。

## 专题增量更新（Reconcile）

通过 `python scripts/reconcile.py "主题名" --source raw/新增资料.md` 为一个主题
生成 `create / update / conflict / noop` 决定和待审核提案。可用 `--target` 指定已有
主题路径或对象 ID；更新只替换 Agent 管理的资料综合区块，不重写手写正文。
新建和更新均沿用 `review approve` / `review apply-approved`；不会直接应用。
来源未变化则不调用模型、不重复生成页面。使用范围与来源发送说明见
[Reconcile Engine](docs/reconcile-engine.md)。


### 判断与原文证据

Reconcile 新提案逐条记录判断及具体原文片段，保存和应用时核对位置与来源版本。
综合正文由这些记录渲染，仍须人工审核；片段匹配不等于事实已证实。
使用 `python scripts/claims.py <主题页路径或对象ID>` 只读查看证据状态。
详见 [Claim + Evidence](docs/claim-evidence.md)。

## 派生索引与全文检索

```bash
python scripts/kb_index.py rebuild
python scripts/kb_index.py search "新闻智能体"
python scripts/kb_index.py search "温州" --kind claim
python scripts/kb_index.py show "wiki/topics/topic-新闻智能体.md"
```

只写可删除重建的 `.kb/index.sqlite`，Markdown 仍是唯一权威来源。
中文短词、类型过滤、判断及证据查询可用；搜索结果标明构建时间和当前文件匹配状态。
查询不会自动重建或调用模型。用法与缓存边界见 [派生索引说明](docs/derived-index.md)。

## 来源影响与待更新清单

```bash
python scripts/kb_index.py rebuild
python scripts/kb_index.py impact "raw/资料.md"
python scripts/kb_index.py stale
```

只从明确的来源/证据关系追踪下游。清单指出哪些判断和主题需复查、先处理哪些上游，
并为可更新主题提供 Reconcile 参数；不自动修改知识页或审核队列。
首次升级须重建缓存。用法和无版本旧笔记的覆盖边界见 [依赖与过时传播](docs/dependency-stale.md)。

## Agent 检索接入

选题和写作材料的 `task/plan` 已使用 FTS 候选、当前文件补查和一层明确来源扩展。
无需新命令；先 `kb_index.py rebuild` 可启用缓存。无缓存时明确回退，不阻塞基本选材。
计划带选材依据与过时提示，待复查材料仍须审核，输入变化会阻断旧提案落盘。
用法与覆盖边界见 [Retrieval 接入](docs/retrieval-integration.md)。

## LLM 选题卡落盘链路

对 `发现选题` 使用 `--llm` 时，校验通过的 `topic-insight-miner` LLM items 会直接转换为 `planned_pages`，不再只是 `llm_runtime` 预览。目标目录始终取 `config.write.topics_dir`，模型返回的 path/filename 不参与写入路径决策；LLM 选题页 v1 一律进入人工审核。模型失败或落盘校验失败时不会静默回退写入硬编码模板页。

其他 LLM Skills 暂时仍保持预览语义，等待各自的受控落盘契约。

## 研究综合写回

```bash
python scripts/synthesize.py "大黄鱼 渠道机会" --topic "大黄鱼产业"
```

从当前资料检索并形成带逐字证据的综合提案，经原 review/apply 审核后更新同一主题，
不把模型预览直接落盘。可用 `--discussion` 提供待核对的讨论要点；讨论本身不是证据。
同一请求和来源未变则跳过；新问题可在同批资料上形成新判断。
用法、上下文限制与安全边界见 [综合写回](docs/synthesis-writeback.md)。

## 可选 Obsidian 小工作区

[小工作区说明](integrations/obsidian/README.md) 提供首页、三视图 Base、报告占位和外层 Agent 对接 Skill。
`python scripts/workspace_report.py` 只读输出已有依赖复查结果，不改知识页或审核队列。
这是隔离验证的试用模板；原生 Obsidian 显示、点击与主机 Skill 触发尚未实测，不是新的运行时或自动安装器。


## 自定义知识目录与历史库接入（PR #15 收口）

`write.*` 决定派生知识的位置；扫描、对象身份、检索和 SQLite 使用同一份目录配置。
配置的知识输出目录会自动加入扫描范围（不是整个上层目录），仍尊重 `scan.exclude_dirs` / `exclude_files`。
不能把 raw 或运行时目录配置成知识输出。默认位置仍是 `wiki/...`，不替用户写死 `_kb-steward/...`。
更新目录配置或排除规则后，请运行 `python scripts/kb_index.py rebuild`，旧缓存不会假装匹配新范围。
独立 `reconcile.py` / `synthesize.py` / `kb_index.py` 与主命令使用同样的对象边界，没有全局绑定顺序。

新增可选配置（`config.example.json` 均为空/关闭；本地 `config.json` 不自动覆盖）：

```json
{
  "scan": {"exclude_files": ["0-MOC.md"], "max_total_source_chars": 22000},
  "link_resolution": {"obsidian_compat": true},
  "candidate_promotion": [],
  "heuristic_topics": [],
  "finalize_aggregation": {}
}
```

`max_total_source_chars` 限制普通 task/plan 单次 LLM 输入的正文字符合计，不含提示词、标题与诊断字段，
不是 token 数或总 HTTP 请求大小。`0` 保持原行为；`init-kb` 逐篇调用仍由 `max_source_chars` 限制每篇。
兼容模式只影响已有笔记的短链接 lint 与附件查询；生成页仍要求完整规范路径，不放宽来源、审核与写入边界。
附件只索引本库路径，不读取正文、不跟随链接，也不把运行时/排除目录里的文件当证据。

未配置候选规则时，初始化不生成跨来源专题；配置规则后，只统计真正命中判别词的来源，
达到数量门槛才生成待审核候选。finalize 的主题标题来自已有 source note 的专题标签，
仅汇总同主题来源；材料、概念、案例仍需显式配置。此版本的自动 topic 聚合仍仅取首个高频标签。
候选与聚合的 plan/Markdown 审核标记一致。finalize 不覆盖非自身生成或正文被人工修改的聚合页，
此时使用 Reconcile 的受控更新；原始资料不迁移、不改状态。

旧 `fix_broken_links*.py` 是带私人路径与猜测关联的一次性脚本，现已退役为无写入提示，不是通用修复入口。
使用 `healthcheck` 查看问题，再准备明确的审核提案。真实模型语义质量、原生 Obsidian 展示效果须在本地另验。

## Seed 质量与索引/日志目录（Issue #16）

`mindseed-grow` 不再把日记头部硬截断当成关键信号：摘取正文原句并带来源，
空内容/单来源与聚类置信度分开处理，seed 候选继续由人审核。主题词不再冒充待建链接。
唯一同名 seed 生成保留原文的更新提案，已消化来源版本不重复建卡；近似标题只提示复核，不自动合并。

索引与日志可配置为 `write.index_file`、`write.index_title`、`write.logs_dir`、`write.log_file`；
未配置仍用原有位置。设置 `_kb-steward/...` 后，重建 SQLite，不会在根目录新建默认索引与日志。
完整示例及现有审核入口见 [Seed 质量与路径说明](docs/seed-quality.md)。

需要审核的初始化批次不是丢弃：计划已保存，`review show` → `review approve` →
`review apply-approved` 后再继续。不要直接修改审核标记，部分执行失败也不能靠原样重跑恢复。
验证 `plan --llm "发现选题 ..."` 前先核对入口和可选来源；它不是 raw 全库初始化命令。
