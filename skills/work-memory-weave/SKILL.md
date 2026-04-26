---
name: work_memory_weave
description: 将会议、项目、周报、随手记和决策记录编织成结构化工作记忆、决策记录和时间线。
---

# Skill：work-memory-weave

## 定位

工作记忆编织。将会议、项目推进、周报、课程安排、待办和复盘记录整理为可查询、可追踪、可复盘的工作记忆。

本 Skill 不负责整理一般资料，不负责生成研究专题页，不负责写项目总结文章。

## 触发

- 用户要求整理会议、周报、项目、复盘、待办、时间线
- `quicknote/`、`inbox/` 中出现工作记录
- 文件中出现 `#项目`、`#会议`、`#复盘`、`#待办`、`#decision`
- 用户明确指定某个工作记录文件

## 输入

默认输入：

- `quicknote/*.md`
- `inbox/*.md`
- `wiki/work-memory/*.md`

受限输入：

- `raw/*.md` 仅在用户指定，且内容明确是会议纪要、项目记录或复盘材料时处理

参考目录：

- `wiki/projects/`
- `wiki/work-memory/`
- `wiki/project-reviews/`
- `wiki/seeds/`

## 输出

位置：

```text
wiki/work-memory/
```

文件命名：

```text
YYYY-MM-DD-项目或事项.md
```

页面类型：

```text
work-memory
decision-record
project-timeline
```

## Work Memory 元数据

```yaml
---
title:
type: work-memory
status: growing
stage: active
created:
updated:
sources:
related:
project:
people:
tags:
confidence:
review_required:
---
```

`status` 只能使用全局生命周期状态。工作流状态写入 `stage`：

```text
active
waiting
blocked
done
```

本 Skill 默认只能创建：

```text
active
waiting
```

不得把事项直接标记为 `stage: done`，除非来源中明确写明已完成。无法判断时使用 `status: manual_review`。

## 正文结构

```markdown
# 工作记忆：标题

## 来源文件

## 项目/事项

## 时间线

## 关键决策

## 行动项

## 人物/组织

## 风险与阻塞

## 下次回看

## 人工复核项
```

## 方法

1. 判断输入是否属于工作过程记录，不要把普通资料误归入 work-memory。
2. 抽取时间、项目、人物、行动、决策、阻塞、结果。
3. 区分事实记录、待办、推断和建议。
4. 对决策生成 `decision-record`：背景、选项、选择、理由、影响、风险。
5. 对行动项标注状态：todo、doing、waiting、blocked、done。
6. 检查是否已有同项目 work-memory，若有则追加更新记录，不重复建页。

## 查重规则

可能重复：

- 项目名相同
- 时间范围重叠
- 来源来自同一会议或同一周报
- 行动项高度重合

重复时追加：

```markdown
## 更新记录 YYYY-MM-DD

新增来源：
新增行动项：
新增决策：
状态变化：
人工确认：
```

## 质量标准

- 必须有具体来源。
- 决策必须能追溯到原文或用户明确输入。
- 行动项不能凭空创建。
- 不确定的人物、时间、项目名进入人工复核。
- 普通资料不得误入 `work-memory`。

## 失败处理

- 无法判断是否为工作记录：`manual_review`。
- 缺时间但有明确事项：允许创建，但标记 `review_required: true`。
- 来源过长且多主题：建议拆分或交给 `topic-research-compile`。

## 禁止事项

- 不修改原始会议纪要。
- 不虚构行动项。
- 不把用户没有确认的建议标记为决策。
- 不把研究资料整理成工作记忆。
