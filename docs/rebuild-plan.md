# personal-kb-steward 重构计划

## 目标

把个人知识库管家从“能生成几张卡片的脚本”重构为一个可持续迭代的 OpenClaw 子智能体。

## 方法论依据

- Zettelkasten：来源笔记、文献笔记、永久笔记分离；原子化；通过链接形成思想网络。
- Evergreen Notes：笔记允许从小开始，但必须持续打磨、链接和提升质量。
- PARA：区分项目、领域、资源、归档，让知识服务实际行动。
- RAG 知识库质量实践：来源可追溯、证据归因、引用可验证，避免幻觉污染。
- Obsidian/Markdown 实践：纯文本、稳定路径、可解析双链、统一 frontmatter。

## 阶段一：基础治理

已实施：

- 重写 `AGENTS.md`、`SOUL.md`、`TOOLS.md`。
- 重写 `config.json`，加入知识对象模型、关系类型、质量门禁。
- 重写 `router.json`，使用中文优先路由。
- 重写 11 个 `SKILL.md`，补充触发、输入、输出、方法、质量标准。
- 重写 `scripts/personal_kb_steward.py`，加入索引、链接解析、质量检查、中文输出。

## 阶段二：质量门禁

已实施：

- `lint` 默认只读，不写入知识库。
- 检查断链、缺元数据、来源过粗、状态异常、占位内容、孤立页。
- 生成内容时使用真实来源文件。
- 报告文件使用时间戳，避免覆盖。

待增强：

- 对派生页自动标记 `manual_review`。
- 支持可审计的修复建议列表。
- 支持对历史低质量产物做隔离建议，而不是直接修改。

## 阶段三：知识生长

已实施：

- `mindseed-grow`：按主题聚合碎片，不再默认一文一卡。
- `topic-insight-miner`：以 seed/source 网络生成选题卡，不再只按词频。
- `writing-evidence-harvester`：抽取证据条目，不只列来源。
- `writing-material-pack`：组织事实、案例、风险、结构和不建议写法。
- `knowledge-gap-finder`、`claim-evidence-checker`、`case-story-bank-builder`、`project-review-synthesizer` 均有基础实现。

待增强：

- 引入更强的语义聚类。
- 为每条证据增加行号或片段定位。
- 区分一手来源、二手来源、用户笔记和搜索结果。
- 构建概念页自动更新机制。

## 阶段四：长期运营

建议节奏：

- 每日：`run`，处理新增 quicknote/inbox/raw。
- 每周：`healthcheck --write`，生成健康报告。
- 写作前：围绕具体选题运行 `writing-material-pack`。
- 月度：人工复核 `manual_review`、合并重复主题、归档过时页面。

## 成功标准

- 原始资料不被破坏。
- 每个派生页面都有具体来源。
- 双链能解析。
- 主题页至少 3 个来源。
- 材料包不再只是来源列表。
- 报告不覆盖历史。
- 不确定内容进入人工复核。

