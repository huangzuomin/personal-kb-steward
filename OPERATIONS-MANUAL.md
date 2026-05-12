# 个人知识库管家 · 操作手册

> 版本：2026-04-28 | 适用：personal-kb-steward v2 | 知识库路径：`C:\Users\zooma\.qclaw\workspace\wiki`

---

## 一、架构概览

```
用户（自然语言）
    │
    ▼
┌─────────────────────────────┐
│      5 大产品入口             │
│  整理 / 选题 / 素材 / 记忆 / 体检 │
└──────────┬──────────────────┘
           │ 路由
           ▼
┌─────────────────────────────────────────────┐
│           12 个 Skill（内部执行单元）            │
│  mindseed-grow     raw-ingest-router          │
│  topic-insight-miner   topic-research-compile│
│  writing-evidence-harvester                   │
│  knowledge-gap-finder                         │
│  writing-material-pack                        │
│  work-memory-weave    project-review-synthesizer
│  claim-evidence-checker  case-story-bank-builder
│  kb-lint-healthcheck                           │
└─────────────────────────────────────────────┘
           │
           ▼  dry-run（默认）  /  --apply（显式授权）
┌─────────────────────────────────────────────┐
│           知识库写入层                         │
│  wiki/seeds/      wiki/topics/               │
│  wiki/sources/    wiki/concepts/              │
│  wiki/evidence/   wiki/material-packs/        │
│  wiki/work-memory/  outputs/                   │
│  .openclaw/manual-review/queue.jsonl          │
└─────────────────────────────────────────────┘
```

**安全模型**：默认 dry-run plan，不写入知识库。`--apply` 显式授权才能写入。

---

## 二、5 大产品入口（用户对话层）

所有用户入口均收敛为以下 5 个场景。对管家说话时无需指定具体 Skill，路由层会自动匹配。

### 入口 1：整理知识库
**场景**：你往 `quicknote/` 或 `inbox/` 里塞了很多碎片，想让管家整理。

**触发说法**：
```
整理知识库
整理碎片
清理 inbox
把随手记整理一下
这些想法太散了，帮我理一理
生长 seed
```

**内部链路**：`mindseed-grow` → 可选触发 `kb-lint-healthcheck`

**典型流程**：
1. 扫描 `quicknote/` 和 `inbox/`
2. 识别碎片类型（事实、案例、观点、问题、项目记录、写作素材）
3. 同主题碎片聚类，生成主题型 seed card
4. 查重：已有近似 seed → 追加来源；无重复 → 新建
5. 输出到 `wiki/seeds/YYYY-MM-DD-核心议题.md`
6. 高风险项进入人工确认队列

**输出示例**：
```yaml
# wiki/seeds/2026-04-28-地方媒体AI转型难在哪.md
title: 地方媒体AI转型难在哪
type: seed-card
status: seed
stage: seed
sources: [inbox/2026-04-27-media-ai.md, quicknote/2026-04-26-thoughts.md]
confidence: medium
review_required: true
```

---

### 入口 2：发现选题
**场景**：你积累了一些材料，想知道有没有值得写的题目。

**触发说法**：
```
发现选题
有什么值得写
找选题
挖掘选题
帮我看看最近有什么可以写的方向
这个月积累了不少，整理一下思路
```

**内部链路**：`topic-insight-miner` → 可选触发 `knowledge-gap-finder`

**典型流程**：
1. 扫描 `wiki/seeds/`、`wiki/topics/`、`wiki/sources/`、`wiki/work-memory/`
2. 从"主题 + 张力 + 证据 + 读者价值"四维找问题，不做词频统计
3. 生成 2-3 个候选选题，标注 A/B/C 推荐等级
4. 来源不足 3 个 → 标记 `manual_review`

**输出示例**：
```yaml
# wiki/topics/2026-04-28-topic-地方媒体AI转型为什么更难.md
title: 地方媒体AI转型为什么更难
type: topic-card
status: growing
stage: candidate
score: B
confidence: medium
review_required: true
```

**选题质量信号**：
- 多个来源指向同一张力或问题
- 资料充足但尚未形成表达
- 中外实践存在差异
- 有冲突、有反直觉、有未被解释的现象

---

### 入口 3：准备写作素材
**场景**：你确定了写什么，需要把相关材料打包。

**触发说法**：
```
准备写作素材：XXX
生成材料包：XXX
帮我找素材：XXX
围绕 XXX 准备写作
帮我组稿
围绕"地方媒体AI转型"生成材料包
```

**内部链路**：`writing-material-pack` → 可选触发 `writing-evidence-harvester`、`knowledge-gap-finder`

**典型流程**：
1. 以 topic-card 为锚点
2. 复用或新生成 evidence-pack
3. 组织事实、案例、数据、时间线、反方观点
4. 给出 2-3 个可选写作角度
5. 标注"不建议写法"和"证据缺口"
6. 输出到 `wiki/material-packs/`

**材料包必须包含**：
- 可用事实（≥5条）
- 可用案例（≥1个）
- 可用数据
- 时间线
- 正反观点（≥1个反方）
- 风险与缺口
- 不建议写法
- 写作前检查清单

---

### 入口 4：沉淀工作记忆
**场景**：开了会、做了项目、写了周报，想把关键决策和行动项整理出来。

**触发说法**：
```
沉淀工作记忆
整理会议记录
整理周报
整理项目复盘
这些会议纪要帮我理一理
帮我把最近的项目记录整理一下
```

**内部链路**：`work-memory-weave` → 可选触发 `project-review-synthesizer`

**典型流程**：
1. 判断输入是否属于工作过程记录（不是一般资料）
2. 提取时间、项目、人物、行动、决策、阻塞
3. 对决策生成 decision-record（背景/选项/选择/理由/影响/风险）
4. 对行动项标注状态：todo / doing / waiting / blocked / done
5. 同项目已有 work-memory → 追加更新记录

**输出类型**：
- `work-memory`：综合工作记录
- `decision-record`：单次决策（从属于 work-memory）
- `project-timeline`：时间线

**注意**：
- 不虚构行动项和决策，必须来自原文
- 不能把研究资料整理成工作记忆
- 不确定项 → `manual_review`

---

### 入口 5：检查知识库健康
**场景**：你感觉知识库有点乱，想全面体检。

**触发说法**：
```
检查知识库健康
知识库体检
查断链
检查质量
帮我看看有没有重复或断链
健康检查
```

**内部链路**：`kb-lint-healthcheck`（只读）

**检查范围**：quicknote/、inbox/、raw/、wiki/、outputs/

**检查项**：
| 维度 | 检查内容 |
|------|---------|
| 断链 | `[[wikilink]]` 无法解析到真实文件 |
| 重复 | 标题高度相似、核心议题重叠 |
| 来源 | `sources` 为空或只写 `raw/` |
| 元数据 | 缺少 YAML header 或类型不合法 |
| 状态值 | 使用了非生命周期状态词 |
| 积压 | quicknote/inbox 长期未整理 |
| 孤立 | 没有入链的页面 |
| 主题页 | 来源不足 3 个 |
| 材料包 | 缺事实/案例/反方/时间线/缺口 |
| 占位 | 存在"待补充""TODO"等未完成内容 |

**风险分级**：
```
P0 破坏性：原始资料可能被覆盖/删除/不可追溯
P1 可信度：无来源结论、断链、来源不存在
P2 结构：重复页、错误分类、状态异常
P3 维护：积压、孤立页、过期、占位内容
```

**输出**：`outputs/kb-lint-YYYY-MM-DD-HHMMSS.md`

**禁止行为**：
- ❌ 删除原始资料
- ❌ 移动原始资料
- ❌ 自动合并主题页
- ❌ 自动改写 raw/quicknote/inbox

---

## 三、12 个 Skill 详细说明

### 3.1 mindseed-grow
**定位**：碎片 → seed card（不直接变结论）

| 项目 | 说明 |
|------|------|
| 输入 | quicknote/、inbox/；用户指定的 short raw/ |
| 输出 | wiki/seeds/YYYY-MM-DD-核心议题.md |
| 页面类型 | seed-card |
| 默认 status | seed |
| 允许创建的 stage | seed、manual_review |
| 禁止 | 直接创建 compiled；改写原文；批量处理长 raw/ |

**自动跳过**：
- 长文（PDF转文本、完整研报、会议纪要）
- 多主题资料合集
- 未标记、未指定、过长的 raw/

**建议移交**：
- 长文 → `topic-research-compile`
- 会议纪要 → `work-memory-weave`

**查重**：标题/核心议题/来源项目 重合 → 追加到已有 seed，不新建

---

### 3.2 topic-insight-miner
**定位**：从知识网络发现值得写的选题

| 项目 | 说明 |
|------|------|
| 输入 | wiki/seeds/、wiki/topics/、wiki/sources/、wiki/work-memory/ |
| 输出 | wiki/topics/YYYY-MM-DD-topic-核心问题.md |
| 页面类型 | topic-card |
| 默认 status | growing |
| 允许创建的 stage | candidate、promising |
| 最低来源数 | 3 个（不足 → manual_review） |

**推荐等级**：
- A：证据充分、张力明确、可进入证据包
- B：有潜力但缺关键证据
- C：只是线索，需继续积累

---

### 3.3 topic-research-compile
**定位**：长文/多来源 → topic page + source note + concept page

| 项目 | 说明 |
|------|------|
| 输入 | 用户指定主题 + raw/*.md + wiki/seeds/ + wiki/topics/ |
| 输出 | wiki/topics/（topic-page）、wiki/sources/（source-note）、wiki/concepts/（concept-page）、wiki/evidence/（evidence-chain） |
| 适用场景 | 行业报告、长案例、多篇 seed 指向同一研究问题 |
| 页面类型 | topic-page、source-note、concept-page、evidence-chain |

**双链要求**：
- 所有 `[[wikilink]]` 必须可解析
- 使用知识库相对路径（如 `wiki/topics/xxx.md`）

---

### 3.4 writing-evidence-harvester
**定位**：围绕选题抽取可审计的证据条目

| 项目 | 说明 |
|------|------|
| 输入 | 具体选题 + wiki/topics/ + wiki/seeds/ + wiki/sources/ + raw/ |
| 输出 | wiki/evidence/YYYY-MM-DD-evidence-选题.md |
| 页面类型 | evidence-pack |
| 默认 stage | collecting |
| 允许创建的 stage | collecting、insufficient |

**证据条目格式**：
```markdown
- 类型：事实/案例/数据/反方
- 证据：（具体内容）
- 来源：（文件路径）
- 可支持的论点：（这条证据支持什么）
- 可信度：高/中/低
- 限制：（适用边界）
```

**质量门槛**：至少包含事实、案例、数据中的两类

---

### 3.5 knowledge-gap-finder
**定位**：识别"材料很多但关键证据缺失"的问题

| 项目 | 说明 |
|------|------|
| 输入 | wiki/topics/ + wiki/evidence/ + wiki/material-packs/ + wiki/claim-checks/ |
| 输出 | wiki/gaps/YYYY-MM-DD-gap-主题.md |
| 页面类型 | gap-report |
| 默认 stage | open |

**缺口类型**：
- 缺数据 / 缺案例 / 缺反方
- 缺政策/制度依据 / 缺时间线
- 缺一手来源 / 缺中国语境
- 缺可验证引用 / 缺用户自身项目经验

**每个缺口必须包含**：具体风险 + 优先级 + 推荐补充路径

---

### 3.6 writing-material-pack
**定位**：写作前结构化（不是写成稿）

| 项目 | 说明 |
|------|------|
| 输入 | wiki/topics/ + wiki/evidence/ + wiki/gaps/ + wiki/claim-checks/ |
| 输出 | wiki/material-packs/YYYY-MM-DD-material-选题.md |
| 页面类型 | material-pack |
| 默认 stage | assembling |
| 允许创建的 stage | assembling、insufficient |

**升级为 draft_ready 的条件**：
- 证据 ≥ 5 条
- 案例 ≥ 1 个
- 反方 ≥ 1 个
- 缺口已列出
- 结构已给出
- "不建议写法"已标注

---

### 3.7 claim-evidence-checker
**定位**：校验论断是否有证据支持

| 项目 | 说明 |
|------|------|
| 输入 | 用户输入 claims + wiki/topics/ + wiki/material-packs/ + wiki/evidence/ |
| 输出 | claim-check 页面 |
| 支持的校验结果 | strong_support / weak_support / unsupported / conflict |

**使用场景**：
- 材料包准备进入写作前
- topic-page 中出现强判断
- evidence-pack 中存在冲突材料

---

### 3.8 case-story-bank-builder
**定位**：沉淀可复用案例为案例卡

| 项目 | 说明 |
|------|------|
| 输入 | raw/ + wiki/evidence/ + wiki/sources/ + wiki/topics/ + wiki/work-memory/ |
| 输出 | wiki/evidence/ 下的案例卡 |

**案例卡必须包含**：
- 背景（谁/何时/何地/发生了什么）
- 关键决策点
- 结果/影响
- 可复用维度
- 来源

---

### 3.9 work-memory-weave
**定位**：会议/项目/周报 → 结构化工作记忆

| 项目 | 说明 |
|------|------|
| 输入 | quicknote/ + inbox/；用户指定的会议/项目 raw/ |
| 输出 | wiki/work-memory/YYYY-MM-DD-项目或事项.md |
| 页面类型 | work-memory、decision-record、project-timeline |
| 默认 stage | active |
| 允许创建的 stage | active、waiting |

**decision-record 结构**：
- 背景 → 选项 → 选择 → 理由 → 影响 → 风险

**行动项状态**：todo / doing / waiting / blocked / done
（不得凭空创建，必须来自原文）

---

### 3.10 project-review-synthesizer
**定位**：项目复盘 → 方法论资产

| 项目 | 说明 |
|------|------|
| 输入 | wiki/work-memory/ + wiki/project-reviews/ + quicknote/ + inbox/ |
| 输出 | wiki/project-reviews/ |

**提炼内容**：
- 经验（做得好的是什么）
- 教训（什么没达到预期）
- 方法论（下个项目如何复用）
- 决策模式（反复出现的决策逻辑）
- 行动原则（可复用的TODO）

---

### 3.11 raw-ingest-router
**定位**：自动分流 raw/ 目录的新增长文

| 项目 | 说明 |
|------|------|
| 输入 | raw/*.md（新文件） |
| 分流方向 | seed / work_memory / research_report / unclear |
| 触发方式 | 新文件进入 raw/ 时自动调度 |

**分流规则**：
- 短碎片/灵感 → seed（触发 mindseed-grow）
- 会议/项目记录 → work_memory（触发 work-memory-weave）
- 长研报/行业报告 → research_report（触发 topic-research-compile）
- 无法判断 → unclear（进入人工确认）

---

### 3.12 kb-lint-healthcheck
**定位**：只读健康检查，输出分级报告

| 项目 | 说明 |
|------|------|
| 输入 | quicknote/ + inbox/ + raw/ + wiki/ + outputs/ |
| 输出 | outputs/kb-lint-YYYY-MM-DD-HHMMSS.md |
| 页面类型 | lint-report |
| status | compiled 或 manual_review |

**禁止**：
- 删除 / 移动 / 合并 / 重写任何文件
- 把检查报告伪装成内容整理成果

---

## 四、CLI 命令速查

### 4.1 日常使用

```powershell
# 查看知识库状态（文件数、积压情况、上次运行）
python scripts\personal_kb_steward.py status

# 全面健康检查（只读，输出报告）
python scripts\personal_kb_steward.py lint

# 每日整理计划（dry-run）
python scripts\personal_kb_steward.py run

# 执行每日整理（写入知识库）
python scripts\personal_kb_steward.py run --apply

# 针对具体入口生成计划（dry-run）
python scripts\personal_kb_steward.py plan "发现选题"
python scripts\personal_kb_steward.py plan "准备写作素材：地方媒体AI转型"

# 针对具体入口执行（dry-run）
python scripts\personal_kb_steward.py task "整理知识库"
python scripts\personal_kb_steward.py task "发现选题"
python scripts\personal_kb_steward.py task "准备写作素材：地方媒体AI转型"
python scripts\personal_kb_steward.py task "沉淀工作记忆"
python scripts\personal_kb_steward.py task "检查知识库健康"

# 针对具体入口执行（写入知识库）
python scripts\personal_kb_steward.py task --apply "整理知识库"
python scripts\personal_kb_steward.py task --apply "发现选题"
python scripts\personal_kb_steward.py task --apply "准备写作素材：地方媒体AI转型"
```

### 4.2 人工确认队列

```powershell
# 查看待处理项（简洁列表）
python scripts\personal_kb_steward.py review list

# 查看全部待处理项（详细信息）
python scripts\personal_kb_steward.py review

# 查看单条详情
python scripts\personal_kb_steward.py review show <ID>

# 批准执行
python scripts\personal_kb_steward.py review approve <ID> --reason "确认无误"

# 批量批准
python scripts\personal_kb_steward.py review approve --all --reason "全部确认"

# 拒绝并说明原因
python scripts\personal_kb_steward.py review reject <ID> --reason "来源不可信"
```

### 4.3 处理记录

```powershell
# 查看已处理索引
python scripts\personal_kb_steward.py processed
```

---

## 五、人工确认队列（Manual Review Queue）

### 什么会进入队列

以下情况会自动进入 `.openclaw/manual-review/queue.jsonl`，等待人工批准：

| 风险等级 | 场景 |
|---------|------|
| P0 | 原始资料可能被覆盖或删除 |
| P0 | 分类不确定可能导致错误分流 |
| P1 | 来源不足（<3个来源的 topic-card） |
| P1 | 双链无法解析 |
| P1 | 无来源结论 |
| P2 | 状态值不合法 |
| P2 | 重复标题（查重命中） |
| P3 | quicknote/inbox 积压超过 30 天 |

### 处理流程

```
Skill 执行中遇到不确定项
    │
    ▼
写入 .openclaw/manual-review/queue.jsonl
    │
    ▼
用户运行 review 命令
    │
    ├── approve → 执行写入
    └── reject  → 放弃，标记忽略
```

---

## 六、知识库目录结构

```
C:\Users\zooma\.qclaw\workspace\wiki\
│
├── quicknote/          # 随手记、临时碎片（管家可读写）
├── inbox/              # 待处理输入（管家可读写）
├── raw/                # 原始资料（只读，不改不动）
├── wiki/
│   ├── seeds/          # 种子卡（mindseed-grow 输出）
│   ├── sources/         # 来源页（topic-research-compile 输出）
│   ├── concepts/        # 概念页（topic-research-compile 输出）
│   ├── topics/          # 专题页 / 选题卡
│   ├── evidence/        # 证据包
│   ├── gaps/            # 缺口报告
│   ├── material-packs/  # 写作材料包
│   ├── work-memory/     # 工作记忆
│   └── projects/        # 项目复盘
└── outputs/             # 运行报告（lint-report、run-report）
```

**红线**：
- ❌ 不移动/覆盖/删除 `raw/`、`quicknote/`、`inbox/` 原始资料
- ❌ 不在 raw/ 写派生内容

---

## 七、状态与流程模型

### 7.1 status（知识生命周期）

```
raw → seed → growing → compiled → linked → (stale | archived)
                 ↓
           conflict / manual_review
```

| 状态 | 含义 |
|------|------|
| raw | 原始输入 |
| seed | 已提炼为种子 |
| growing | 正在生长/积累 |
| compiled | 整理完成 |
| linked | 已接入知识网络 |
| stale | 过期/失联 |
| conflict | 内容冲突待解决 |
| archived | 已归档 |
| manual_review | 需人工确认 |

### 7.2 stage（流程态）

嵌入各个 Skill 内部的流程状态，用于表达"处理到哪一步"：

**通用**：`open` / `active` / `waiting` / `blocked`

**选题**：`candidate` / `promising` / `ready_for_evidence` / `rejected`

**证据**：`collecting` / `compiled` / `insufficient` / `conflict`

**材料包**：`assembling` / `draft_ready` / `insufficient`

**Seed**：`seed` / `growing` / `merged` / `compiled` / `archived`

**Gap**：`open` / `partially_resolved` / `resolved`

### 7.3 type（页面类型速查）

| type | 生成 Skill | 存放目录 |
|------|-----------|---------|
| seed-card | mindseed-grow | wiki/seeds/ |
| topic-card | topic-insight-miner | wiki/topics/ |
| topic-page | topic-research-compile | wiki/topics/ |
| source-note | topic-research-compile | wiki/sources/ |
| concept-page | topic-research-compile | wiki/concepts/ |
| evidence-pack | writing-evidence-harvester | wiki/evidence/ |
| evidence-chain | topic-research-compile | wiki/evidence/ |
| gap-report | knowledge-gap-finder | wiki/gaps/ |
| material-pack | writing-material-pack | wiki/material-packs/ |
| work-memory | work-memory-weave | wiki/work-memory/ |
| decision-record | work-memory-weave | wiki/work-memory/ |
| project-timeline | work-memory-weave | wiki/work-memory/ |
| project-review | project-review-synthesizer | wiki/projects/ |
| claim-check | claim-evidence-checker | wiki/claim-checks/ |
| lint-report | kb-lint-healthcheck | outputs/ |
| run-report | 各 Skill | outputs/ |

---

## 八、安全红线（必须遵守）

1. **原始资料只读**：`raw/`、`quicknote/`、`inbox/` 不可修改、不可删除
2. **双链必须可解析**：`[[wikilink]]` 在生成前必须确认文件存在
3. **路径规范**：双链用知识库相对路径 `wiki/topics/xxx.md`，不得写 `[[topics/xxx]]`
4. **不存在的页面**：不得伪造双链，应放"待创建链接"裸文本
5. **来源必须具体**：`sources` 不得写 `raw/`，必须精确到文件名
6. **不生成幻觉结论**：没有来源的论断不得写入知识库
7. **不写正式文章**：只做写作前结构化
8. **分类不确定 → manual_review**
9. **证据冲突 → 保留冲突，不掩盖**
10. **健康检查只读**：不自动合并/删除/重命名/改结论

---

## 九、常见场景操作提示词

### 场景 1：刚看完一篇长文章，想提炼
```
把刚下载的《2025年地方媒体转型报告》整理成 topic page
→ 触发 topic-research-compile（识别为长文）

顺手把里面提到的案例整理成案例卡
→ 触发 case-story-bank-builder
```

### 场景 2：quicknote 积压了一堆想法
```
整理知识库
→ 触发 mindseed-grow

发现有什么值得写的方向
→ 再运行 task "发现选题"
```

### 场景 3：确定了写作方向，想快速打包素材
```
围绕"地方媒体AI转型为什么难"生成材料包
→ 触发 writing-material-pack

看看还缺什么证据
→ 触发 knowledge-gap-finder

帮我检查一下核心观点有没有证据支持
→ 触发 claim-evidence-checker
```

### 场景 4：开完一整天会
```
把这些会议记录整理成工作记忆
→ 触发 work-memory-weave

提炼一下这次项目的经验教训
→ 再触发 project-review-synthesizer
```

### 场景 5：感觉知识库很久没整理了
```
检查知识库健康
→ 触发 kb-lint-healthcheck（只读）

根据报告整理一下积压的碎片
→ 触发 mindseed-grow
```

### 场景 6：raw 目录来了一篇新文档
```
raw-ingest-router 自动分流，无需手动处理
→ 新文件自动识别类型并分发到对应 Skill
```

---

## 十、Skill 触发矩阵

| 用户需求 | 触发 Skill | 输出目录 |
|---------|-----------|---------|
| 整理 quicknote/inbox 碎片 | mindseed-grow | wiki/seeds/ |
| 整理 raw/ 长文 | topic-research-compile | wiki/topics/sources/concepts/ |
| 发现值得写的选题 | topic-insight-miner | wiki/topics/ |
| 围绕选题找证据 | writing-evidence-harvester | wiki/evidence/ |
| 看选题还缺什么 | knowledge-gap-finder | wiki/gaps/ |
| 打包写作材料 | writing-material-pack | wiki/material-packs/ |
| 校验论断是否有据 | claim-evidence-checker | wiki/claim-checks/ |
| 沉淀案例故事 | case-story-bank-builder | wiki/evidence/ |
| 整理会议/项目记录 | work-memory-weave | wiki/work-memory/ |
| 提炼项目经验教训 | project-review-synthesizer | wiki/projects/ |
| raw/ 新文件自动分流 | raw-ingest-router | 各 Skill |
| 全面健康检查 | kb-lint-healthcheck | outputs/ |

---

## 附录 A：元数据 YAML 模板

所有生成页面必须包含：

```yaml
---
title:                   # 简短标题
type:                    # 页面类型（见上方 type 表）
status:                  # 知识生命周期状态
stage:                   # 流程态
created:                 # 创建时间 ISO
updated:                 # 更新时间 ISO
sources:                 # 具体来源文件路径列表（不得为 raw/）
related:                 # 相关页面路径列表
tags:                    # 标签
confidence:              # 置信度：high / medium / low
review_required:         # 是否需人工复核
---
```

**注意**：`sources` 必须包含具体文件路径，禁止只写 `raw/`。

---

## 附录 B：双链规范

✅ 正确示例：
```
[[wiki/topics/地方媒体AI转型.md]]
[[wiki/seeds/2026-04-28-转型难点.md]]
```

❌ 错误示例：
```
[[topics/地方媒体AI转型]]      # 缺少 wiki/ 前缀
[[地方媒体AI转型]]              # 缺少路径
[[AI]]                          # 太宽泛
```

待创建页面 → 用裸文本路径，不伪造双链：
```
待创建：wiki/concepts/媒体融合.md
```

---

## 附录 C：Processed Index（幂等追踪）

`.openclaw/processed-index.json` 记录每个文件是否被处理过，防止重复处理。

- 相同来源 + 相同 Skill → 跳过（幂等）
- 同一来源被不同 Skill 处理 → 各自记录
- 用户可以运行 `processed` 命令查看处理历史
