
# Project Spec：personal-kb-steward

（OpenClaw 子智能体 · 个人知识库运营系统）

---

## 一、项目定位（Positioning）

构建一个 OpenClaw 子智能体 `personal-kb-steward`，用于**运维已有个人知识库**，并将其从“存储系统”升级为“知识生产系统”。

该子智能体不负责采集入口、不负责最终写作成稿，而是负责：

👉 **知识的生长、沉淀、连接、运维、调用准备与选题洞察**

---

## 二、核心目标（Objectives）

1. 让碎片信息持续生长为结构化知识资产
2. 让专题调研形成长期复利
3. 为写作提供高质量素材与证据链
4. 维持知识库长期健康（不腐烂、不混乱）
5. 构建可查询的个人工作记忆系统
6. 从知识库中自动发现可写选题

---

## 三、明确边界（Non-Goals）

本项目**不实现**：

* ❌ 信息采集入口（WebClip / 微信等）
* ❌ 正式文章生成
* ❌ UI系统
* ❌ 向量数据库（MVP阶段）
* ❌ 多人协同
* ❌ 全自动重构知识库

---

## 四、系统架构（Architecture）

基于三层结构：

```text
知识输入层（已有） → 知识运维层（本项目） → 知识生产层（辅助）
```

本项目覆盖：

```text
运维层 + 部分生产能力
```

---

## 五、Skill体系设计（核心）

本子智能体由**三层 Skill 体系组成**：

---

# 1. 基础运维层（必须实现 · MVP）

### 1.1 `mindseed-grow`

碎片信息生长

作用：
将 quicknote / inbox 中的碎片转化为“知识种子”

输出：

* seed card
* 关联链接建议
* 生长状态标记

状态模型：

```text
seed → growing → compiled → linked → archived
```

关键原则：

* 不强行升格为知识
* 先成为“种子”，再判断是否成长

---

### 1.2 `work-memory-weave`

工作记忆编织

作用：
将会议、周报、项目记录转化为结构化工作记忆

输出：

* project page
* people page
* decision record
* timeline

核心价值：
👉 替代“靠脑子记项目”的低效模式

---

### 1.3 `kb-lint-healthcheck`

知识库健康检查

作用：
防止知识库腐烂

检查项：

```text
孤立页面
重复页面
无来源结论
inbox堆积
过期内容
断链
状态异常
```

输出：

* lint report
* 自动修复低风险问题
* 高风险问题进入人工确认

---

# 2. 知识沉淀层（第二阶段）

### 2.1 `topic-research-compile`

专题调研沉淀

作用：
维护长期专题资产

输出：

* topic page
* source page
* concept page
* 证据链

核心能力：
👉 调研复利（不是每次重来）

---

# 3. 知识生产层（第三阶段）

---

### 3.1 `topic-insight-miner`

选题洞察（新增重点）

作用：
从知识库中发现“值得写的选题”

识别信号：

```text
高频问题
新出现趋势
多项目交叉矛盾
知识冲突
证据充足但未表达主题
空白领域
```

输出：

```markdown
# 选题卡

## 一句话选题
## 为什么值得写
## 知识库证据
## 可用角度
## 风险与缺口
## 推荐等级
```

---

### 3.2 `writing-evidence-harvester`

素材提取

作用：
围绕选题抽取：

```text
事实
案例
数据
故事
人物
时间线
```

---

### 3.3 `writing-material-pack`

素材组织

作用：
将素材整理成写作前结构

输出：

```text
事实 + 观点 + 时间线 + 案例 + 风险 + 写作结构
```

---

### 3.4 `knowledge-gap-finder`

知识缺口识别

作用：
识别当前选题缺什么：

```text
缺数据
缺案例
缺反方
缺政策依据
缺时间线
```

---

### 3.5 `claim-evidence-checker`

观点证据校验

作用：
防止“凭感觉写”

---

### 3.6 `case-story-bank-builder`

案例库建设

作用：
沉淀可复用故事资产

---

### 3.7 `project-review-synthesizer`

项目复盘提炼

作用：
提炼经验与方法论

---

## 六、Skill优先级（非常关键）

### MVP（第一阶段）

```text
mindseed-grow
work-memory-weave
kb-lint-healthcheck
```

👉 目标：让知识库“活起来”

---

### 第二阶段

```text
topic-research-compile
topic-insight-miner
knowledge-gap-finder
```

👉 目标：让知识库“会思考”

---

### 第三阶段

```text
writing-evidence-harvester
writing-material-pack
claim-evidence-checker
```

👉 目标：让知识库“能生产”

---

## 七、Agent运行机制（Runtime）

---

### 1. 子智能体角色定义

```text
你是 personal-kb-steward。

职责：
运维个人知识库，使其持续生长、沉淀、连接，并服务于调研与写作。

禁止：
直接写正式文章
无来源生成结论
破坏原始材料
```

---

### 2. 路由机制（Router）

输入 → 分类 → 调用 Skill

```text
碎片输入 → mindseed-grow
会议/项目 → work-memory-weave
检查请求 → kb-lint-healthcheck
专题资料 → topic-research-compile
选题请求 → topic-insight-miner
写作准备 → evidence-harvester → material-pack
```

---

### 3. 定时调度（Schedule）

每日：

```text
mindseed-grow
work-memory-weave
```

每周：

```text
topic-research-compile
kb-lint-healthcheck
```

按需：

```text
topic-insight-miner
writing-evidence-harvester
```

---

## 八、知识状态模型（Critical）

所有知识对象必须包含：

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

👉 这是“知识是否在生长”的核心机制

---

## 九、元数据规范（Metadata）

所有页面必须：

```yaml
---
title:
type:
status:
created:
updated:
source:
related:
tags:
confidence:
---
```

---

## 十、日志系统（Log System）

所有操作必须写入：

```markdown
## 时间

Skill:
输入:
新建:
更新:
问题:
人工确认:
```

---

## 十一、输出报告（Reports）

路径：

```text
outputs/kb-steward-YYYYMMDD.md
```

内容：

```text
处理数量
新增知识
更新知识
问题
风险
建议
```

---

## 十二、工程实现要求（For Codex）

---

### 必须实现：

1. 目录扫描
2. 文件变更检测
3. Skill调用机制
4. Router逻辑
5. Markdown生成
6. YAML写入
7. log记录
8. report生成
9. config支持路径配置

---

### 可延后：

* 向量搜索
* embedding
* UI

---

## 十三、Definition of Done

系统完成标准：

1. 能创建并运行子智能体
2. 能加载Skill体系
3. 能自动路由任务
4. 能处理已有知识库
5. 能生成结构化知识
6. 能生成选题卡
7. 能输出素材包
8. 能做健康检查
9. 不破坏原数据
10. 可持续运行（定时）

