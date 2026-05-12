---
name: official_material_handoff
description: 将知识库管家的 evidence-pack 与 material-pack 打包成 official-material-workflow 可消费的机关材料交接包。
---

# Skill：official-material-handoff

## 定位

机关材料交接包。把知识库管家已经生成的证据包、材料包、缺口和风险，整理成下游 `official-material-workflow` 可直接消费的输入。

本 Skill 不写正式公文，不判断最终文种，不执行公文审稿门禁。

## 输入

- 用户任务信息
- `evidence-pack.md/json`
- `material-pack.md/json`
- `gap-report.md`（可选）
- `source_refs`

## 输出

位置：

```text
outputs/official-material-handoff/
```

文件命名：

```text
YYYY-MM-DD-handoff-选题.md
YYYY-MM-DD-handoff-选题.json
```

页面类型：

```text
official-material-handoff
```

## Handoff 固定字段

```json
{
  "task": {
    "topic": "",
    "requested_doc_type": "",
    "reader_role": "",
    "purpose": "",
    "deadline": ""
  },
  "material_pack_ref": "",
  "evidence_pack_ref": "",
  "source_refs": [],
  "known_gaps": [],
  "risk_notes": [],
  "recommended_next_step": ""
}
```

## 正文结构

```markdown
# 机关材料交接包：选题

## 任务

## 上游材料

## 来源清单

## 已知缺口

## 风险提示

## 建议下游动作
```

## 质量标准

- 必须包含 material-pack 和 evidence-pack 引用。
- 必须列出 known gaps 和 risk notes，即使为空也要显式说明。
- 不得新增上游没有给出的事实。
- 不得写正式文稿段落。
