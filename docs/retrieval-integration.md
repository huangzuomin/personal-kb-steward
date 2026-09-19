# Agent Retrieval 接入

本地检索现在进入真实的选题、写作材料和证据选材流程，而不只是独立 CLI。
沿用 `task/plan`、Skill executor、LLM 预览、审核及 apply，不增加模型或数据库依赖。

## 使用

```bash
python scripts/kb_index.py rebuild
python scripts/personal_kb_steward.py task "围绕大黄鱼生成材料包"
python scripts/personal_kb_steward.py plan "发现选题 新闻智能体"
```

控制台显示选材方式、选中数量及回退/复查提示；完整记录在计划的 `retrieval` 数组中。
仅生成提案，应用仍走现有 review/apply。Reconcile 的显式 `--source` 不被隐式改成搜索。
整理、原始资料初始化和定时输入处理仍按原扫描/processed-index 逻辑，未换成关键词搜索。

## 检索和范围

`core.retrieval.Retriever` 每份计划一个实例。复用 SQLite FTS/短词扫描、类型/状态过滤，
目录过滤在 LIMIT 之前完成。抽掉少量已知命令词（围绕、生成材料包等）后逐词召回，
按命中词数、标题命中和 FTS 名次排序、路径去重；不是语义分词或向量检索。
纯入口请求没有主题时保留 AI/新闻/媒体/温州/知识的旧默认提示词。

每词最多召回 100 个候选，总输出仍受调用方 limit 限制。
缓存只提供候选路径/排序；交给 executor/模型的正文永远来自本次 VaultIndex 的 Markdown。
对比缓存 hash，把当前扫描中新增/修改的匹配文件补进来；删除或已不匹配的旧命中不继续使用。
即使未 rebuild，新建资料也可被 Agent 的实时补查找到（独立 kb_index search 仍是快照查询）。

在剩余名额内只扩展一层明确的上游来源，遵守同一目录/类型/状态过滤；不挤掉直接命中。
不沿普通双链和 related 扩展，不从过时目标的旧依赖元数据选材，不跟随文件/目录链接。
LLM 的有界正文窗口定位到实际命中处，避免长文后段命中却只给模型看开头。

## 过时提示和提案

复用 dependency stale 的直接/间接复查信息，每请求最多检查一次并随输入传给 executor/LLM。
每个命中携带路径、ID/revision、原始文件 hash、选中原因、缓存匹配状态和依赖状态：
`stale / no_signal / unversioned / unchecked / not_applicable`。
`no_signal` 仅表示本次已记录依赖未发现异常，不代表事实成立。
无版本/无依赖的知识页不声称新鲜，缓存变化后也不把旧 claim 状态贴到新正文上。

有待复查、未完整核对或页面本身有审核标记时，派生页保持 `review_required: true`，
正文附来源复查提示；计划保留完整诊断，不把旧判断无提示地当作现行事实。
输入已过时时可以生成带警告的研究提案，不自动改判真假或自动修复上游。

每个新检索产物在计划中携带 `retrieval_source_hashes`。首次保存、重存和 apply 前
都核对实际输入文件；变化或不可读时拒绝旧提案，不能刷新基线绕过。旧保存计划兼容。
该校验针对实际选中的输入文件，不是未选中全库资料的持续监控或跨文件事务。
LLM 结果仍沿用原本的预览契约，不把预览未经审核自动替换 executor 产物。

## 降级和边界

没有缓存、版本/扫描范围不符或缓存损坏时，明确回退当前 VaultIndex 的全文字面匹配，
不自动建库、不覆盖坏缓存；依赖状态未核对会明示并使派生知识材料进入原审核流程。
原始输入内容未被本功能修改，SQLite 连接只读。检索不额外调用模型或发送数据。

仍需构建现有 VaultIndex；stale 检查也会扫描已索引的依赖来源。这轮不是消除全库扫描
或大规模性能优化，也没有新增向量库。独立 `select_notes/query_results` 旧 helper 为兼容
保留，但真实 query Skill 的 executor 与 LLM 输入已走 Retriever。
