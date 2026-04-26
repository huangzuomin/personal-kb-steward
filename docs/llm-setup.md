# LLM 接入配置指南 (LLM Setup Guide)

Personal KB Steward 核心依赖大语言模型 (LLM) 进行高质量的语义聚类、工作记忆提取和知识缺口分析。为了达到最佳效果，你需要配置一个可用的 LLM API 密钥。

## 1. 配置文件

系统通过根目录的 `.env` 文件读取 LLM 配置。如果根目录下没有该文件，请复制 `.env.example` 进行修改：

```powershell
cp .env.example .env
```

## 2. 参数说明

在 `.env` 文件中，你需要关注以下几个环境变量：

```ini
# API 供应商的基础 URL，通常是兼容 OpenAI 格式的接口
OPENAI_BASE_URL="https://api.deepseek.com/v1"

# 你的 API 密钥
OPENAI_API_KEY="sk-你的真实密钥"

# 使用的模型名称
# 推荐使用深度思考/长上下文模型，如 deepseek-chat 或 gpt-4o
LLM_MODEL="deepseek-chat"

# 调试模式（可选）
# 设置为 1 可以在控制台看到详细的 prompt 和 token 消耗
DEBUG_LLM=0
```

## 3. 推荐模型

对于个人知识库的整理，我们**强烈推荐**使用具备强大中文理解与逻辑梳理能力的模型，以下是经过验证的选型：

1. **DeepSeek-V3 / R1 (推荐)**：成本极低且逻辑能力极强，非常适合大量碎片的聚类。
2. **Claude 3.5 Sonnet**：在知识点提炼和文章大纲排布上表现最为出色。
3. **GPT-4o**：通用能力强，速度快。

*(注：系统底层使用 OpenAI SDK 兼容协议，任何支持 `base_url` 覆盖的厂商均可直接接入。)*

## 4. 离线/本地模型支持

如果你极其在意隐私，不希望个人笔记上传云端，可以将 `OPENAI_BASE_URL` 指向本地运行的推理服务（如 Ollama, vLLM, LM Studio）：

```ini
# 例如 Ollama 的本地兼容接口
OPENAI_BASE_URL="http://127.0.0.1:11434/v1"
OPENAI_API_KEY="ollama"
LLM_MODEL="qwen2.5:14b"
```

> **注意**：本地模型建议至少使用 14B 以上参数级别（如 Qwen2.5 14B），否则在执行复杂的 `writing-material-pack` 逻辑时，可能无法按严格的 JSON 格式输出或发生幻觉。

## 5. 测试连接

配置好 `.env` 后，建议使用命令行进行一次计划生成测试（带 `--llm` 标志，确保调用真实接口）：

```powershell
python scripts\personal_kb_steward.py plan --llm "整理知识库"
```

如果没有报错且成功输出了计划，说明你的 LLM 接入已大功告成！
