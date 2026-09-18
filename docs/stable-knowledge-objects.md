# Stable Knowledge Objects · PR-02

## 本次交付

为既有 plan/apply 流程引入持久对象身份，保留 Markdown-first、默认 dry-run、人工审核和原始资料保护边界。本 PR 不提供语义去重、自动重命名、Claim 图谱或通用对象数据库。

## 数据契约

正式写出的新知识页增加两个顶层 frontmatter 字段：

```yaml
object_id: kb:9c2345f4-8be3-43b7-a773-b24a8a7bc54a
revision: 1
```

`object_id` 由程序通过 UUIDv4 分配，与标题、路径、文件内容以及页面类型无关。模型或 renderer 不拥有分配权。`revision` 是正整数，表示通过受控写入产生的版本号，不是事实置信度、内容正确性或历史修改总次数。

运行时 `KnowledgeObject` 提供 `object_id`、`canonical_path`、`object_type`、`revision` 和 `content_sha256`。`canonical_path` 从实际文件位置派生，不将文件中可能过期的同名属性作为身份或寻址依据。用户手工编辑不自动增加 revision，但重新索引后的内容 hash 会变化。

对象范围为 `wiki/` 中除目录 `README.md` 外的 Markdown 知识页。`raw/`、`quicknote/`、`inbox/`、运行报告与生成的导航不自动分配对象身份。旧页面的普通 `id` 属性不被接管。没有 `object_id/revision` 的旧页继续作为 legacy 页面读取；已有但不完整或非法的身份字段会作为错误报告，而不是静默修复。

## 计划到落盘

所有 CLI 生成路径，包括 task、plan、init-kb 和 finalize-kb，在 `write_execution_plan()` 序列化之前经过同一个 `bind_plan_objects()` 边界。

- 新建：分配新 ID，revision 为 1。
- 更新已识别对象：保留原 ID，revision 增加 1。
- 明确更新 legacy 派生页：只在该更新 proposal 中首次分配 ID；不批量迁移其他页面。
- 重存同一个已绑定 plan：不重新分配 ID，不增加版本，不刷新修改前基线。

绑定仅修改内存中的 proposal，随后写入计划文件，不修改知识页、原始资料或处理状态。身份字段插入后重新计算 `content_sha256`，因此审核内容与实际 apply 的内容保持一致。低置信度、mock、人工审核和路径等既有门禁不被身份逻辑绕过。

新计划携带 `object_schema_version: 1`。apply 检查计划字段和 Markdown 字段一致，拒绝重复 ID、抢占其他对象的 ID、删除既有身份、错误 revision 和未知 schema 版本。旧的无版本计划仍可创建 legacy 页面，但不能剥离或改配已经建立的对象身份。

更新 proposal 额外保存 `base_revision` 和 `base_sha256`。apply 在任何页面写入前核对基线；计划生成后用户修改了目标文件，即使用户没有修改 revision，也会阻断整批页面写入并要求重新生成计划。apply 不自动合并，也不在背后重新生成已审核的内容。

这一校验不是完整事务：未提供写锁、跨文件原子提交或对非协作外部写者的完整保护；预检与实际写入之间的竞争窗口仍需后续写入事务 PR 解决。旧版无身份的 update plan 不具有完整的 hash 基线保护。

## 读取与冲突

```python
from core.vault import build_index

index = build_index(cfg)
obj = index.objects.get(object_id)
note = index.by_object_id.get(object_id)
```

内存索引可随时从配置扫描范围内的 Markdown 重建，不新增 SQLite 或持久 registry。改名后重建索引，ID 和 revision 不变，canonical_path 指向新路径。本 PR 不自动修复旧路径双链，也不提供 rename/move 命令。

同名页面使用不同 ID，不构成身份冲突。同一 ID 出现在两个页面时，索引报告所有冲突路径，并从无歧义查找表移除这个 ID。`index.objects.get()` 对冲突 ID 抛错，绝不采用最后写入覆盖。重叠扫描目录重复读取同一个路径，不算两个对象。

`healthcheck` 增加 `object_count`、`legacy_object_count` 和 `object_identity_issues`。缺少身份的 legacy 页面不是健康错误；非法身份和重复 ID 计入 P1。存在这些错误时仍可生成健康报告，但知识写入被阻断。对象索引只覆盖配置扫描范围，不宣称覆盖被排除的文件。

## 安全边界与已知限制

本次没有自动迁移真实知识库，也没有修改原始内容。对象写入拒绝通过符号链接间接修改其他路径。ID 校验是数据完整性门禁，不是防篡改签名或用户权限系统。

测试更新对象时发现既有 rollback 会把 update 条目当新建页删除。为避免身份改造后沿用这一危险路径，本 PR 对包含 update 的整次回滚采取保守拒绝，保留当前文件和备份；只有纯 create 运行继续使用原有删除式回滚。完整更新恢复和事务回滚留给后续 PR，不能将此版本称为事务化写入引擎。

直接调用 renderer/executor 得到的是尚未绑定身份的候选内容。应经由 `write_execution_plan()` 和 `apply-plan` 落盘。旧的直接写入内部 helper 尚未全部退役，不应作为新的生产集成入口。

同一语义主题的两份独立新建计划仍可能生成不同 ID。这不是语义去重方案；canonical object 的查找、匹配与 reconcile 是后续迭代。

## 验收

```bash
python -m pytest -q tests/test_knowledge_objects.py tests/test_object_plans.py
python -m pytest -q
```

重点回归：只读 legacy、中文路径改名、同名不同 ID、重复 ID、错误标量、真实 task/finalize 计划、ID 与 hash 一致、计划重存、受控更新、人工编辑冲突、旧计划兼容、审核不放宽、原始资料符号链接保护，以及更新回滚不误删。
