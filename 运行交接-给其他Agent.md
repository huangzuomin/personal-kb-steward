# 新部署系统运行交接：给接手的 Agent

更新日期：2026-09-22（B12）。用途：操作当前已部署的个人知识库管家。这里的命令按本机部署版核对；运行前仍应读取当前用户任务与活配置。

**B12 接手先读 `docs/B12运行变更.md` 和 `部署验收记录-B12-2026-09-22.md`。** 当前 `initialize.seed_stage=false`，初始化不生成种子；非 LLM 源页只保留诊断，不再进入可写计划。失败来源可重试，正常源可独立审核写入。不要删除旧队列或用 `--all` 代替完整 `run_id`。

模型默认最多 3 次尝试；重试只针对瞬时错误，不保证外部服务变快。审核摘要已分列 approved/applied，新队列时间标注 UTC。外层 `scripts/run_init_batches.py` 已补完整 run_id 传递和子集完成记录识别，但仍沿用其自动批准策略，只用于用户明确允许自动放行的任务；通常任务继续逐页审查。

当前生产批处理实际使用且已验证的解释器为 Python 3.13.14：`C:\Users\zooma\.workbuddy-ai\binaries\python\envs\default\Scripts\python.exe`。若终端没有 `python` 命令，使用 PowerShell 的 `& '该绝对路径' scripts/personal_kb_steward.py ...` 调用，不必重装环境。

## 1. 先明确运行位置和任务范围

| 项目 | 本机位置 / 状态 |
|---|---|
| 正式程序目录 | `D:/OLD_VAULT-整理后-20260919/tools/personal-kb-steward` |
| 原始知识库 | `D:/OLD_VAULT-整理后-20260919/OLD_VAULT`，实际以config.json解析结果为准 |
| 生成内容 | 知识库内 `_kb-steward/` 下各类型目录；以config.json的write字段为准 |
| 活配置、凭据 | 正式程序目录内 `config.json`、`.env` |
| 计划、审核队列、执行记录 | 正式程序目录内 `.openclaw/`；路径以safety配置为准 |
| 开发迭代区 | 工作区根目录 `.pks-iteration`，不要从这里执行日常生产任务 |
| 历史验收目录 | 工作区根目录 `iteration-artifacts/`，其中计划、ID、状态属于隔离测试，不用于生产 |

本机 `AGENTS.md` 开头的 `C:\path\to\...` 是通用模板路径，不是本机真实路径。读完项目规则后，以本表和活配置定位。

用户已确定的边界：**存量卡片暂不修复；删除旧卡并重跑是后续独立任务。** 当前部署完成不代表授权清空旧卡、processed记录或全库重建。遵循当次任务已经给出的授权；不重复索取已明确授权，也不把之前的隔离验收批准当成生产页面的批准。

多个 Agent 共用生产库时，同一时间只安排一个执行者处理生成、审核和写入，其他 Agent 可只读检查。交接时记录正在处理的完整run_id，避免互相重跑或操作对方队列。

## 2. 接手后的最小检查

PowerShell：

```powershell
Set-Location -LiteralPath 'D:\OLD_VAULT-整理后-20260919\tools\personal-kb-steward'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
python --version
python scripts/validate_config.py
python scripts/personal_kb_steward.py --help
python scripts/personal_kb_steward.py status
python scripts/personal_kb_steward.py review list
```

先读同目录 `AGENTS.md`、`部署验收记录-B12-2026-09-22.md`；按需查 `docs/product-entries.md`。上述检查不生成知识页。`review list` 用于了解待处理任务，不代表应批准旧队列。

B12 全回归使用 Python **3.13.2**，并以生产批处理的 **3.13.14** 完成定向兼容检查，依赖已齐全。不需要重新安装或重新初始化。2026-09-21 的旧部署快照为2174份笔记、350条processed记录；这不是当前状态，也不是以后必须匹配的固定数值。

## 3. 模型连接：区分系统运行与编码 Agent

- 当前config.json配置OpenAI兼容接口 `https://open.bigmodel.cn/api/coding/paas/v4`，模型名 `GLM-5.3-Flash`，超时300秒。这是配置值，不是对服务端真实模型身份的额外保证。
- `core/llm.py`导入时自动读取正式程序目录的`.env`。已有进程环境变量不会被覆盖；`OPENAI_BASE_URL`、`OPENAI_MODEL`（或`LLM_MODEL`）可覆盖配置。发现行为异常时检查是否有继承的覆盖项，但不要打印完整环境或密钥。
- 不展示、提交或上传`.env`；不要把完整备份交给外部编码Agent，因为备份也含凭据。
- Claude CLI可以作为编码执行者，但**不是该系统的生产模型调用通道**。启动Claude CLI不会替代程序自身的LLM配置。
- `--llm`会向当前provider发送选中的材料；保持既有数据边界，遇到明确禁止云处理的材料不要发送。不要为了运行成功更换provider或扩大扫描范围。
- 清除进程中的API key不等于保证离线，程序可能从`.env`重新加载。隔离验证应明确使用模拟响应/阻断网络等方式；`--mock-llm`只适合链路检查，不能当成内容质量验收。

## 4. 常用入口与副作用

| 需求 | 示例 | 注意事项 |
|---|---|---|
| 当前状态 | `python scripts/personal_kb_steward.py status` | 只读 |
| 健康检查 | `python scripts/personal_kb_steward.py healthcheck` | 不带`--write`时不保存报告 |
| 整理本轮材料 | `python scripts/personal_kb_steward.py task --llm "整理知识库"` | 默认以本轮变更为输入范围；不是raw全量初始化入口 |
| 发现选题 | `python scripts/personal_kb_steward.py task --llm "发现选题：新闻编辑室的AI应用边界"` | 查询检索结果仍需核对来源和时效 |
| 工作记忆 | `python scripts/personal_kb_steward.py task --llm "沉淀工作记忆：梳理某项目安排、已发生经历与待办"` | 已支持配置中的项目原件；生成目录不回流为工作记忆原材料 |
| 写作材料包 | `python scripts/personal_kb_steward.py task --llm "准备写作素材：某主题。区分报道、自述、AI分析，列出待核实项"` | 模型内容进入待审核页，不等于可直接发布的事实稿 |

**生成命令不是只读命令。** `task`及`plan`会保存plan、审核队列和相关操作记录，即使尚未写入知识页。不要为查看帮助或连通性随手执行真实任务。

`task`/`plan`默认不启用模型；要使用本轮验收过的模型生成路径，显式加`--llm`。省略它得到的启发式结果不能冒充LLM产出。`task --apply`也不会绕过审核直接落盘。

`--all`是扩大输入候选范围，不是“只处理提示词中那个项目”，也不是忽略processed状态或突破数量/字符预算的开关。不要默认加它。自然语言任务不是严格文件白名单；对“只能处理这些文件”的任务，应先建立可验证的隔离输入范围。

## 5. 标准链路：生成 → 核对 → 审核 → 应用

1. 运行一次范围明确的生成任务，记录输出的plan完整路径和完整run_id。不要看到等待较久就再启动同一任务。
2. 打开保存后的plan全文，检查`planned_pages`、`manual_review`、LLM结果和阶段错误。页面预览只显示部分内容，不能替代全文审核。保存后可能绑定object_id，审核和hash核对以**保存后的最终计划**为准。
3. 按完整run_id查看该轮审核项：

```powershell
$runId = '替换为本轮完整run_id'
python scripts/personal_kb_steward.py review list --run-id $runId
python scripts/personal_kb_steward.py review show '替换为审核项ID'
```

4. 按当次任务授权完成内容审核；若用户已授权Agent审核，Agent可逐页审核并记理由，否则将具体页面交给有审核权的人。不能仅因JSON合法、测试通过或confidence高就批准。

```powershell
python scripts/personal_kb_steward.py review approve '替换为合格项ID' --reason '写出来源核对、内容边界及保留限制'
python scripts/personal_kb_steward.py review reject '替换为不合格项ID' --reason '写出具体问题'
python scripts/personal_kb_steward.py review apply-approved --run-id $runId
```

5. 检查实际写入清单、run manifest和文件内容。被拒绝页应不存在；获批页应与最终审核计划一致。重复应用同一已完成轮次应为`terminal_noop`；它表示没有新写入，不表示又生成了一批。

有审核项时使用上述review链路。只有计划确实无审核要求、且写入属于当前授权范围时，才使用`apply-plan`。不要使用`review apply-approved --all`或无具体范围的批量批准替代逐轮核对。

## 6. 内容审核重点

- **计划与事实分开**：招募通知不能写成已经举办；准备学习不能直接升级为正式决策或已完成成果。
- **来源类型分开**：媒体报道、访谈自述、AI生成研究文本分别标注。原文引文匹配只能证明出处匹配，不证明观点为真。
- **数字不擅自升级可信度**：无一手核验的数据保持待核实；不能因为出现在source note中就视为核实。
- **说话人不猜测**：已排除元数据、网址和普通标题误归属。孤立、缺少对话结构/句末标点的冒号标签仍可能为未知；不要自行补人名。
- **输出可回查**：sources应为具体文件；未存在的目标放“待创建链接”纯文本中，不能伪造双链。`stale/unversioned/unchecked`表示仍需复核。
- **不改写元数据绕过门禁**：object_id/revision、来源hash、审核状态由程序维护；不手工把候选文件拷入生成目录冒充已批准结果。

已有真实审核实例：3页工作记忆候选中，2页获批，1页因强化“正式决策”和未证实的SD效果判断被拒绝。审核拒绝是正常结果，不要以“凑齐产物”为理由降低标准。

## 7. 遇到这些情况如何处理

| 现象 | 操作 |
|---|---|
| 退出码0，但没有可写页 | 继续看plan中的`llm_runtime.ok/issues/writeback_used`及阶段`input_outcomes/issues`等字段；退出0可能只表示计划已保存。区分无候选、已处理、待审核、来源不足与provider失败 |
| 本轮没有变化或候选为空 | 先查status、processed和该轮选材；不删除state/processed，不改原文mtime，也不自动加`--all`强行生成 |
| 已有pending审核项 | 先处理/交接该轮，不通过重复生成或清空队列规避pending状态 |
| 模型超时、过滤或返回非法内容 | 保留失败计划与日志，报告具体阶段；确认状态后再决定是否有必要小范围重试，不无限重试，不用模板伪装成功 |
| 来源hash或目标revision冲突 | 停止应用，重新核对当前来源/目标并生成新提案；不把旧计划hash改成新值 |
| 缺少检索索引或依据状态未检查 | 如实报告扫描回退/unchecked；需要且在任务范围内时可执行`python scripts/kb_index.py rebuild`，它写检索缓存，不替代来源核实 |
| 中文出现乱码、问号替代或替换字符 | 停止批准相关页，保留原字节并检查UTF-8读取/输出；不要把坏文本继续传给下游 |

查问题优先定位该轮plan、队列和manifest。保留失败证据，不因清理日志而删掉恢复线索。

## 8. 初始化、维护和回滚另行处理

- `init-kb`面向raw材料的分批初始化，`finalize-kb`面向已保存来源的后续类型化编排；它们不是启动检查。默认可调用LLM并保存计划，不能把“不带--apply”理解为完全无副作用。
- 仅在任务确实要求初始化时，从小批开始，例如`python scripts/personal_kb_steward.py init-kb --batch-size 2`；审阅本批结果后再继续。不要直接运行默认多批`init-kb --apply`，也不要把空topic输出一概认作失败：还受来源质量、显式问题和类型契约约束。
- 活配置未显式设置时，新版seed默认atomic、card pipeline默认typed；不要为兼容旧卡悄悄切回legacy。
- 不修改扫描配置、模型、超时、预算来掩盖缺陷；不运行`git reset --hard`、`git clean`或直接用上游覆盖本地补丁。部署含尚未提交的本地迭代成果，上游HEAD不能代表当前部署代码。
- 不在生产目录反复重跑全部测试作为日常启动步骤。修复后做相关验证；需要完整回归时，注意测试会创建公开fixture快照和缓存。
- 应用级`rollback`与程序版本回退是两件事。包含update的运行不能靠自动删除式回滚处理；手写修改不能被旧备份覆盖。

部署前完整备份位于：
`D:/OLD_VAULT-整理后-20260919/iteration-artifacts/2026-09-21-deployment/backup-before`。
按同目录`deployment-manifest.json`核对需要恢复的文件，保留部署后产生的业务数据；不要对整个目录做删除式镜像恢复。

## 9. 已验收的范围与交班输出

2026-09-21部署目录完整回归：**1003通过、9个Windows符号链接权限项跳过、0失败**。配置、CLI和生产库只读status通过。部署后的两个入口验证使用此前真实模型响应进行隔离回放，包含真实审核/落盘/重复执行；不是部署后新发起的实时模型调用，也未做全库生产重跑。provider稳定性、所有内容的语义正确性不由这些结果保证。

每轮交班至少交付：任务和输入范围、使用的正式程序目录、是否真实调用模型、完整run_id/plan路径、候选/批准/拒绝/实际写入数量、失败或待核事项、下一步。区分“已生成候选”“已审核”“已落盘”，不笼统报“完成”。

参考文件：

- [本机部署验收记录](D:/OLD_VAULT-整理后-20260919/tools/personal-kb-steward/部署验收记录-2026-09-21.md)
- [部署证据目录](D:/OLD_VAULT-整理后-20260919/iteration-artifacts/2026-09-21-deployment)
- [三处修复验收与样本](D:/OLD_VAULT-整理后-20260919/iteration-artifacts/2026-09-21-three-fixes/三处修复验收报告.md)
- [产品入口说明](D:/OLD_VAULT-整理后-20260919/tools/personal-kb-steward/docs/product-entries.md)

可以给下一位Agent的任务开场：

> 请先读取 `D:/OLD_VAULT-整理后-20260919/tools/personal-kb-steward/运行交接-给其他Agent.md` 和同目录AGENTS.md，在正式部署目录操作。先核对当前任务授权、活配置与待审核轮次；按生成计划→内容审核→指定run_id应用的流程执行。存量卡片暂不修复，不默认全库重跑；完成后提供plan、审核及实际写入证据。
