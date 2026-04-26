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
3. **🎯 选题与素材提炼 (`topic-insight-miner` / `writing-material-pack`)**：根据你指定的选题，自动遍历知识库寻找支撑证据、数据、案例，甚至自动帮你指出“知识缺口”与“反方观点缺失”。
4. **🏥 知识库健康诊断 (`kb-lint-healthcheck`)**：自动扫描坏链、孤儿页面、缺乏双链的目录，并评估风险等级。

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
2. **安装依赖**（如果你的 Python 环境未包含）：
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
复制 `.env` 示例并填写（默认推荐 DeepSeek-V3/R1 兼容接口）：

```powershell
cp .env.example .env
# 编辑 .env 文件，填入你的 API 密钥
```
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
