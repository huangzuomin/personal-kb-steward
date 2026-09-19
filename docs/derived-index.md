# SQLite 派生索引与基础全文检索

Markdown 是唯一权威来源。索引保存于知识库 `.kb/index.sqlite`，可删除后重建。
本功能是独立的本地检索接口，不接管 Reconcile、审核、apply 或现有 `select_notes()`。
不新增数据库服务、依赖、模型调用或向量检索。

## 使用

沿用现有 `config.json` 的知识库与扫描配置：

```bash
python scripts/kb_index.py rebuild
python scripts/kb_index.py status
python scripts/kb_index.py search "新闻智能体"
python scripts/kb_index.py search "温州 AI" --type topic-page --status growing
python scripts/kb_index.py search "证据" --kind claim --limit 5
python scripts/kb_index.py search "大黄鱼" --kind evidence
python scripts/kb_index.py show "wiki/topics/topic-新闻智能体.md"
```

`show` 也接受 `kb:<UUID>`。所有命令输出 JSON；退出码 0 表示成功，1 表示失败。
`rebuild` 是显式的缓存写入操作，只替换固定路径的索引；不需要知识页的审核或 apply。
`status/search/show` 用 SQLite 只读连接，不创建或刷新索引，不调用模型。
索引不存在时提示先重建，而不是查询时悄悄修改磁盘。

## 存储与重建

- `notes`：路径、已有 object_id/revision、标题、类型、状态、正文与文件原始字节 hash。
  原始资料和无身份旧页也可搜索，但不会分配新身份。
- `claims`：所属页面、claim_id、statement、kind、confidence。
- `evidence`：所属判断、来源路径、来源版本、逐字引文、位置、关系及构建时匹配状态。
- `search_fts`：笔记、判断、证据三类检索条目。`metadata` 记录版本、根目录、扫描配置与构建时间。

每次完整重建，读取配置范围内的 Markdown（包含根目录 Markdown，排除配置的 log.md），
遵守 exclude_dirs，并始终排除 `.kb/.git/.obsidian/.openclaw`。不跟随文件或目录链接；
跳过扫描中发现的链接并报告 warnings。显式配置的非法或越界目录会报错。
只有现有 Reconcile v2 页面提供结构化 claims；v1/普通页面保持普通正文索引，不迁移。
重复身份、损坏判断记录或不可读取的输入会中止重建，保留旧索引。
已改变或缺失的证据来源仍保留原记录并标明状态，不自动重绑或宣布判断失效。

新数据库完整构建、提交并关闭后，才替换旧缓存。中途失败或 Windows 文件被占用时，
旧缓存保留。没有多进程协调，也不是多文件时点一致性快照；这只是可重建的检索缓存。
只允许替换带本项目 application_id 的数据库；损坏/不明文件不会被自动覆盖。
确认它是可丢弃缓存后，可自行删除 `.kb/index.sqlite` 再重建，不涉及任何笔记或备份。

## 查询契约

默认 `--kind note`；可选 `claim/evidence/all`。`--type/--status` 过滤所属页面。
输入按空白分成最多 16 个字面检索项，所有项均须出现；不解释 SQL、FTS 操作符或通配符。
查询最多 200 字符，limit 为 1 至 100。返回路径、身份、版本、摘录和排序分值；
判断/证据结果还附具体证据位置与来源状态，`show` 返回完整的已索引正文及判断。

FTS5 使用 trigram，支持中文连续文本内的子串，例如大黄鱼。
至少三个字符的项走 FTS；一至两个字符的项（如温州、AI）用字面子串过滤。
只有短项时扫描缓存，`engine=short-substring-scan`，速度不能等同于长词 FTS；
混合查询先由 FTS 召回再过滤短项。英文忽略 ASCII 大小写，不做词干、词边界或语义匹配。
FTS 使用标题加权 BM25（数值越小越靠前），短项扫描按稳定路径排序，score 为 0。
`snippet` 是普通文本，不应不经转义直接插入 HTML。

## 新鲜度与数据边界

查询搜索的是 `built_at` 时的内容。只对命中的少量页面核对当前 hash：
`current_status=matched/changed/unavailable`；不扫描全库、不自动改写状态。
返回证据同时带 `match_status_at_build` 和按当前来源核对的 `current_match_status`：
`matched/source_changed/unavailable/mismatch`。这些状态不代表语义上支持判断或事实已证实。

新增内容在重建前搜不到；改名或删除的旧命中会显示 unavailable。更新完成后主动 rebuild。
知识库根目录或扫描配置改变时拒绝使用旧缓存，要求重建，避免混用其他范围的数据。
依赖关系现由同库 dependencies 表派生，impact/stale 可只读检查影响与待更新清单，
见 [依赖与过时传播](dependency-stale.md)。这不自动修改笔记，也没有替换 Agent 的旧检索器。

索引是未加密的正文和引文副本，须按原资料保护。本仓库 `.gitignore` 排除 `.kb/`；
独立知识库也应排除缓存的公开提交与不必要同步。不要上传个人数据库到代码仓库。
本轮测试只使用隔离样例，不代表已在真实大规模知识库上完成性能验收。

技术依据：SQLite 官方 FTS5 的 trigram、BM25 与 Python sqlite3 只读 URI 文档。
需要运行环境的 SQLite 启用 FTS5 和 trigram；缺少能力时明确失败，不加载外部扩展。
