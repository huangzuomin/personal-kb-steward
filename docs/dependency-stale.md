# Dependency + Stale Propagation v1

本阶段回答：这份来源影响哪些知识？来源变化后，哪些判断和主题需要复查？
只读生成待更新清单，不修改 Markdown 的 status/revision、SQLite、审核队列或运行记录。
`stale` 表示依据需要复查，不等于判断已错误，也不自动决定新结论。

## 用法

```bash
python scripts/kb_index.py rebuild
python scripts/kb_index.py impact "raw/资料.md"
python scripts/kb_index.py stale
```

`impact` 也接受来源对象的 `kb:<UUID>`，返回潜在直接/间接下游、受影响 claim ID
与一条最短依赖路径；即使来源没变，也可以查。它不宣布这些下游已经过时。
`stale` 对索引中被引用的来源检查当前字节，输出实际发现的 signals 和 pending_updates。
所有命令输出 JSON。首次升级需要 rebuild：缓存 schema 从 1 升为 2，旧缓存不静默迁移。

## 依赖依据

新增可重建的 `dependencies` 表。依赖方向为来源到使用它的知识页/判断：

- Reconcile v1/v2 的 source_hashes：页面使用的确切来源版本。
- Claim + Evidence：某个判断引用的确切版本、supports/contradicts 及片段定位。
- 普通知识页 sources（兼容 source）：保留无版本的显式引用。

不从 related、正文双链或相似标题推测依赖，不给旧笔记补造来源版本。
每条判断以所属页 + claim_id 区分。普通 source-note/material-pack 等可参与传播；
只有 topic-page 可以获得当前 Reconcile 命令参数。raw 的内容不被当成待更新知识页。

sources 无版本时：只知道索引构建后来源是否改变，不知道作者写作时用了哪个版本。
这类边计入 coverage.unversioned_dependencies，不能由零条 stale 推导全库知识都新鲜。
重建会刷新其扫描基线，但不会伪造作者基线；有确切版本的过时边在重建后仍然存在。
无法解析的 sources 或非规范路径会列入 warnings，不能据此声称依赖覆盖完整。

## 传播与更新顺序

逐条比较依赖版本，而不是把同一来源的所有使用者一律标旧：已经引用新版本的页
不会因为另一个页还引用旧版本而被直接标旧。某页的上游过时，即使该页尚未改动，
其下游引用仍会收到间接复查提示。循环/重复路径只遍历一次，不做无限传播。

清单保留原页面 status，另输出 dependency_state=stale、当前文件匹配状态、受影响
claims、根源和传播路径。action 有四种：

- reconcile：目标仍匹配索引，来源可读、上游已无待复查项。reconcile_args 是参数数组，
  不是已执行命令。运行它只生成新提案，仍须已有 review/apply 审核。
- review_upstream：先处理 blocked_by 中的上游；循环依赖可能相互等待，需人工消解。
- refresh_index：目标页已变/改名/删除，先重建核对，不能据旧目标发出更新命令。
- manual_review：来源缺失/不在扫描范围、证据位置不一致，或页面不是 topic-page。

典型闭环：修改来源 → stale → 更新上游专题并审核应用 → rebuild → stale → 更新下游
专题并审核应用 → rebuild → stale 清单清除。扫描与重建本身不把旧证据绑定到新来源。
不同下游可有不同复查原因；路径只展示一条最短见证，并非枚举所有路径。

## 边界

图来自 built_at 时的索引。新增笔记、改动依赖、更新或改名后要主动 rebuild；查询不自动
重建或调用模型。来源仅在原索引范围内读取，链接/越界/不可读路径按不可用处理。
没有定时监控、持久任务调度、自动重写、图数据库或跨文件事务。扫描期间不锁定外部编辑器；
真正落盘仍以 Reconcile 的新快照及 plan/apply 检查为准。未作真实大规模库性能验收。
