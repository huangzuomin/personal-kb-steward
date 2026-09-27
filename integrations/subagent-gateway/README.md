# Subagent Gateway（子 agent 网关）

让 personal-kb-steward 的 `llm.backend=agent` 传输层背后接 Muse 的子 agent，
而不是一个 headless CLI（如 `claude -p`）。程序侧**零改动**：复用已测试的
agent 传输（prompt 组装、超时、`assert_safe_content`、JSON 提取）。

## 架构

```text
steward 程序 --subprocess--> shim.py --请求文件--> 队列目录
                                                    |
                                              监督者（Muse）
                                              派生子 agent 应答
                                                    |
shim.py <--响应文件-- 队列目录 <-- 子 agent 写回 JSON
```

- `shim.py`：实现"agent CLI"协议。从 stdin（`{stdin}` 模板）或 prompt 文件
  读入 prompt，写 `requests/<id>.json`，阻塞等待 `responses/<id>.json`，
  把其中的 `response` 字符串原样打到 stdout。超时或响应非法时以非零退出码
  结束 → 程序侧抛 `LLMError`（fail-closed）。
- 监督者是活人侧（Muse）：cron 唤醒后启动程序，轮询 `requests/`，
  每个请求派生一个子 agent，子 agent 按 prompt 要求只输出 JSON 并写回
  `responses/<id>.json`。

## 配置

```json
{
  "llm": {
    "backend": "agent",
    "agent": {
      "command": "python3",
      "args": ["<repo>/integrations/subagent-gateway/shim.py", "{stdin}"],
      "timeout_seconds": 900
    }
  }
}
```

环境变量：

| 变量 | 说明 | 默认 |
|---|---|---|
| `SUBAGENT_GW_QUEUE` | 队列目录（requests/ + responses/） | `<repo>/.openclaw/tmp/subagent-gw` |
| `SUBAGENT_GW_TIMEOUT` | shim 等待响应的秒数，应小于 `timeout_seconds` | `600` |

## 监督者操作流程（cron 场景）

1. `export SUBAGENT_GW_QUEUE=<本轮队列目录>`（每轮用新目录，避免串扰）。
2. 后台启动管家程序（如 `llm-check` / `init-kb --batch-size N`）。
3. 轮询 `<队列>/requests/`：每个新请求派生子 agent，指示它"只读请求文件，
   严格按 prompt 输出 JSON，写 `responses/<同名>.json` 为
   `{"response": "<JSON文本>"}`"。
4. 程序收到全部回包后继续流水线；本轮结束归档队列目录。

注意：没有监督者在跑时不要用这个后端——请求会堆积直到 shim 超时
（程序侧 fail-closed，不会静默跳过）。

## 测试

- `tests/test_subagent_gateway.py`：shim 协议的单元测试（fake 监督者线程），
  不需要 live 子 agent。
- 端到端：`llm-check`（backend=agent）+ 真实监督者派子 agent 应答探针。
  2026-09-27 在 Muse VM 实测通过（24.1s，返回 `{"ok": true}`）。

## 与 api 后端的分工

bulk 批量仍走 api（秒级、便宜）；子 agent 网关用于语义校验层、
抽检审计、高价值小批量——即"慢而准"的顶层。见主文档的质量分级策略。
