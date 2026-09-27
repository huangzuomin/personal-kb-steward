# LLM 接入配置指南 (LLM Setup Guide)

Personal KB Steward 核心依赖大语言模型 (LLM) 进行高质量的语义聚类、工作记忆提取和知识缺口分析。为了达到最佳效果，你需要配置一个可用的 LLM 后端。

系统支持两种传输后端，通过 `config.json` 的 `llm.backend` 一键切换：

| backend | 机制 | 适用场景 |
| --- | --- | --- |
| `api`（默认） | OpenAI 兼容 `/chat/completions` 直调，单次调用返回 JSON | 成本低、延迟低；受文档截断预算约束 |
| `agent` | 无头 agent CLI（Claude Code 等）只读运行，agent 可 Read 全文、Grep 知识库交叉核验后再输出 JSON | 长文提炼质量、事实核验；token 消耗约为 api 的 5–20 倍 |

两种后端共用同一条确定性链路：dry-run 计划 → 质量门 → review → apply。agent 没有 Write 权限，唯一产出是 stdout 里的 JSON 文本。

## 1. 配置文件

- `config.json` 的 `llm` 段：后端选择与参数（见下）。
- 根目录 `.env`：API 密钥等敏感信息（backend=api 时读取）。仓库不会提交真实密钥。

## 2. backend=api（OpenAI 兼容直调）

`config.json`：

```json
"llm": {
  "backend": "api",
  "provider": "openai-compatible",
  "base_url": "https://api.openai.com/v1",
  "model": "",
  "api_key_env": "OPENAI_API_KEY",
  "temperature": 0.2,
  "timeout_seconds": 300
}
```

`.env` 环境变量（优先级高于 config.json）：

```ini
OPENAI_BASE_URL="https://api.deepseek.com/v1"
OPENAI_API_KEY="sk-你的真实密钥"
OPENAI_MODEL="deepseek-chat"
DEBUG_LLM=0
```

默认 HTTP 超时 300 秒，可在 `llm.timeout_seconds` 调整。超时只表示本次模型调用失败，不会触发知识库写入。

## 3. backend=agent（无头 agent CLI）

`config.json`：

```json
"llm": {
  "backend": "agent",
  "agent": {
    "command": "claude",
    "args": ["-p", "--output-format", "text",
             "--allowedTools", "Read", "--allowedTools", "Grep", "--allowedTools", "Glob",
             "{stdin}"],
    "timeout_seconds": 900
  }
}
```

要点：

- `command`：CLI 名称或绝对路径。Windows 下通过 PATH 解析（支持 `.cmd` shim）；已验证 Claude Code 2.x。
- `args` 模板占位符：`{stdin}` 表示 prompt 经 stdin 传入（默认）；`{cwd}` 展开为知识库根目录；`{prompt_file}` 展开为临时 prompt 文件路径（传入后 prompt 不再走 stdin）。二者不可同时使用。
- 工作目录固定为知识库根，agent 收到的 `documents[].abs_path` 是原文绝对路径——content 被截断时 agent 会 Read 全文，并可用 Grep 核验库内事实。
- 安全边界：`--allowedTools` 只放行 Read/Grep/Glob；headless 模式下未列出的工具（Write/Bash 等）一律拒绝。落盘仍只走 Python 的 apply 链路。
- 其他 CLI 模板示例：
  - Codex：`"command": "codex", "args": ["exec", "--sandbox", "read-only", "{stdin}"]`
  - ZCode CLI：需要支持 stdin 的版本；当前 0.16.x 的 `-p` 只接受位置参数，不适合大 payload，暂不推荐。
- `llm.agent.env`（可选）：为 agent 进程追加环境变量，如 `"env": {"ANTHROPIC_MODEL": "claude-sonnet-4-5"}`。

## 4. 推荐模型

1. **backend=agent**：Claude Sonnet 4.x 级别——全文阅读与交叉核验收益最大。
2. **backend=api**：DeepSeek-V3 / GLM-5.3-Flash——成本低，适合大批量碎片聚类。
3. 本地模型（Ollama / vLLM）：`OPENAI_BASE_URL="http://127.0.0.1:11434/v1"`，建议 14B 以上，否则 JSON 契约易失败。

## 5. 测试连接

```powershell
# 一键探针：向后端发一个 {"ok": true} 往返；切换 backend 后先跑这个
python scripts\personal_kb_steward.py llm-check
python scripts\personal_kb_steward.py llm-check --backend api   # 临时探测另一后端，不改配置

# 真实 dry-run（不带 --apply，不写盘）
python scripts\personal_kb_steward.py plan --llm "发现选题 AI 媒体"
```

检查生成的 plan：`llm_runtime.ok` 应为 true；对"发现选题"，`llm_runtime.writeback_used` 也应为 true，且 `planned_pages` 应直接包含 LLM 选题卡。真实写入仍需后续人工审核与 apply。
