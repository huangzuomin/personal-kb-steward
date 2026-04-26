# Processed Index

Phase 6 引入幂等处理索引：

```text
.openclaw/processed-index.json
```

## 目的

避免重复运行时无限生成新页面。索引按：

```text
source file -> skill -> source sha256 -> outputs
```

记录已处理状态。

## 行为

- dry-run 会读取 processed index，用于估算还有多少未处理输入。
- `--apply` 成功后才写入 processed index。
- 如果 source 的 sha256 没变，同一个 skill 会跳过。
- 如果 source 内容变化，sha256 改变，会重新进入候选输入。

## 当前覆盖

MVP 阶段覆盖：

- `mindseed-grow`
- `work-memory-weave`

后续阶段可扩展到 topic、evidence、material 等 query 型任务。

## 查看

```powershell
python scripts\personal_kb_steward.py processed
```

## 索引示例

```json
{
  "processed": {
    "quicknote/2026-04-15.md": {
      "title": "2026-04-15",
      "current_sha256": "...",
      "skills": {
        "mindseed-grow": {
          "sha256": "...",
          "processed_at": "2026-04-26T02:00:00",
          "outputs": ["wiki/seeds/example.md"],
          "operation_status": "created"
        }
      }
    }
  }
}
```
