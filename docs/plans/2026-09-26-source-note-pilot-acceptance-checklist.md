# Source-note 真实试跑验收清单 v0.1

## 目标与范围

- 目标：验证历史初始化的 `raw → source-note → Source Auto-Apply v0.1` 生产链是否适合继续扩大 Backfill。
- 第一阶段窗口：累计处理 **20 篇不同的 raw 原文**；每次处理 1～5 篇。
- 本轮只评估 source-note。Case、Concept、Topic、Seed、Work Memory 等派生或其他对象不属于通过条件。
- 原始 raw 不改写、不移动、不删除。Auto-Apply、QUARANTINE、AUTO_REJECT 以及无产物/失败均须有可追踪记录。
- 试跑目标是：策略放行的低风险卡片无需事前人工内容审核即可落盘；QUARANTINE 只由人工处理。此项是待验证契约，不预设当前入口已打通；按预先确定的样本和异常规则事后检查。

## 开跑前核对

这些项目须在首批开始前记录。它们不要求本清单作者改代码，但没有证据时不得把相关行为判为 PASS。

- [ ] 记录代码/配置版本或文件哈希、日期、vault 路径、Provider/模型标识与相关运行配置；脱敏，不记录密钥。
- [ ] 确认生产配置 `source_auto_apply.enabled=true`、策略版本为 `source-auto-apply-v0.1`，并记录阈值 `quality_flags <= 5`。
- [ ] 冻结窗口内的策略、prompt、模型、review/apply 流程和阈值。任何一项变更都要标记窗口中断；不要把变更前后结果合并成同一稳定性结论。
- [ ] 先确认真实队列如何表达三种决策。当前策略函数返回 `decision`，但队列写入路径主要通过 `status`、`resolved_by`、`resolution_code`、`auto_apply.policy_version/reason_codes` 表达；QUARANTINE 保持 pending。现有生产台账提到 `auto_apply.decision`，而当前实现中未见该字段写入。确认实际字段映射后再统计，不能按不存在的字段计数。
- [ ] 确认一次 AUTO_APPLY 队列批准最终会经过哪个入口写入 vault，并对磁盘上的 source-note 做内容/hash 核验。策略函数本身只判定并改变队列状态，不单独写卡；“已批准”不能记成“已落盘”。当前普通 `apply-plan` 会拒绝 `review_required=true` 的页面；审核应用入口会用 approved 队列项授权写入。`init-kb --apply` 在存在未处理审核项时会暂停整批。试跑须实际确认 AUTO_APPLY 项能否在 QUARANTINE 项保持 pending 时单独落盘；若不能，记为自动落盘链路未通过，不将队列批准计作成功。
- [ ] 记录既有 `SOURCE_AUTO_APPLY_V01_OBSERVATION_LEDGER.md` 起始状态。该冻结台账当前以 **20 张真实 AUTO_APPLY** 为观察窗口，且结构/公式冻结；本清单按用户定义另统计 **20 篇 raw 输入**。两种分母分开记录，不改写旧台账口径，也不把其中一个窗口完成误报成另一个完成。
- [ ] 首批 raw 清单预先固定为最多 5 篇；记下相对路径、原文哈希、长度/类型及选入原因。后续 20 篇尽量覆盖短/长、不同来源/格式和常见缺损情形；重复 raw 不重复计入 20 篇。
- [ ] 预先登记事后抽查样本：输入序号 **5、10、15、20**。若该输入产生 AUTO_APPLY，则在落盘后抽查；若为 QUARANTINE、AUTO_REJECT 或无产物，记录该结果，不以它替代下一个 AUTO_APPLY 抽查点。样本之外仍执行下方规定的自动证据核验及强制异常抽查。

## 每篇输入的登记项

每个 raw 输入有一行；保留失败项，不因无产物而从分母剔除。

| # | raw 路径/哈希 | 批次 / run_id | Provider 结果与重试 | Source 产物 | 分流及原因 | 是否落盘 / 目标路径 | 抽查 / 人工处置 | 结论 |
|---|---|---|---|---|---|---|---|---|
| 01 |  |  |  |  |  |  |  |  |
| 02 |  |  |  |  |  |  |  |  |
| 03 |  |  |  |  |  |  |  |  |
| 04 |  |  |  |  |  |  |  |  |
| 05 |  |  |  |  |  |  |  |  |
| 06 |  |  |  |  |  |  |  |  |
| 07 |  |  |  |  |  |  |  |  |
| 08 |  |  |  |  |  |  |  |  |
| 09 |  |  |  |  |  |  |  |  |
| 10 |  |  |  |  |  |  |  |  |
| 11 |  |  |  |  |  |  |  |  |
| 12 |  |  |  |  |  |  |  |  |
| 13 |  |  |  |  |  |  |  |  |
| 14 |  |  |  |  |  |  |  |  |
| 15 |  |  |  |  |  |  |  |  |
| 16 |  |  |  |  |  |  |  |  |
| 17 |  |  |  |  |  |  |  |  |
| 18 |  |  |  |  |  |  |  |  |
| 19 |  |  |  |  |  |  |  |  |
| 20 |  |  |  |  |  |  |  |  |

## Per-card quality checks

Run mechanical checks on every generated source-note where evidence is available. Human semantic review is limited to QUARANTINE/other exceptions and the pre-registered sample.

- [ ] **Source traceability:** card points to the exact raw path; stored source identity/hash matches the selected original; no card points to an unrelated or ambiguous source.
- [ ] **Quote reliability:** each included quote is an exact substring of the normalized original and its recorded offsets/line coordinates resolve to that quote. Ambiguous, missing, cross-chunk, or altered quotes are not treated as verified.
- [ ] **Factual support:** each sampled factual statement is supported by its linked evidence; inference, uncertainty, attribution, dates, counts, and speaker identity are not strengthened beyond the source.
- [ ] **Coverage honesty:** `full` is used only when every planned range was analyzed; failed/skipped/excluded ranges are visible as partial coverage/limitations. Compare card metadata with provider chunk outcomes, not just the displayed summary.
- [ ] **Content retention:** no material sections or key facts disappear through truncation, rendering, encoding, or response parsing. Record omissions against the original.
- [ ] **Safe output:** title, summary, information units, frontmatter, and links describe the source rather than add unsupported conclusions; no replacement characters, malformed frontmatter, mock text, or unrelated generated claims.
- [ ] **Write proof:** an AUTO_APPLY card is counted as written only after the target file exists in the intended vault directory, its content/hash matches the plan, and reconciliation/write evidence reports success. Verify raw originals remain unchanged.

## 分流语义（按当前 v0.1 实现）

| 结果 | 当前判定 | 试跑登记方式 |
|---|---|---|
| `AUTO_APPLY` | 仅 `source-note`；analysis mode 为 `llm`；目标不存在；coverage 为 `full`；有 `card_state` 和 `info_units`；quality flags 不超过 5；`review_required=true` | 记录策略批准与实际落盘两个状态。它表示通过元数据门槛，不表示语义质量已人工确认 |
| `QUARANTINE` | 非 source 类型、coverage 非 full、缺编译证据、flags > 5 或缺 `review_required` 等 | 保持人工待处理；记录原因及最终 approve/reject。风险高不等于确定错误 |
| `AUTO_REJECT` | 当前策略仅明确拒绝 heuristic 无写入资格及重复目标 | 记录原因。不要把失败、空输出、部分输出或所有“不好”的卡笼统记成 AUTO_REJECT |
| 无 source 产物 / blocked / zero / error | Provider 或输入处理结果，不一定产生 Source Auto-Apply 队列决策 | 单独记录输入结果和错误证据，仍计入 20 篇输入窗口；不得伪装为 AUTO_REJECT 或成功零产出 |

**当前语义缺口：** 用户目标包含“确定无效内容自动拒绝”，但已核对的 Auto-Apply v0.1 判定逻辑没有基于内容质量作 AUTO_REJECT；它只覆盖 heuristic 和重复目标。试跑时要单独观察无实质内容/损坏输入如何退出生成链。若没有明确、可审计的拒绝状态，报告为该目标尚未验证/未满足，不可通过改名把它计入 AUTO_REJECT。

## 抽查与严重 False Auto Apply

计划抽查点沿用现有节奏：AUTO_APPLY 全局序号第 5、10、15、20 张；本 20 篇输入窗口另以第 5、10、15、20 篇作为预登记触发点。两套序号分别记录。以下情况须立即强制抽查，不受计划点限制：flags 为 4 或 5、长度异常、provenance 数量异常、运行日志 warning、rollback/reconcile 异常。

符合任一项即记为严重 `False Auto Apply`：无来源事实、事实强度升级、数字错误、归属错误、引文错误、来源身份错误，或明显不应生成的卡片已落盘。表达重复或文案一般本身不算严重误放。

- [ ] 严重 `False Auto Apply` = **0**。
- [ ] 如出现第 1 张严重误放，立即停止灰度并关闭 `source_auto_apply.enabled`，恢复人工模式；保留产物/日志，仅调查该案例的 Last PASS → First FAIL → 根因，不继续自动放行。
- [ ] 任何疑似严重误放先按未解决异常保留，不在统计前将其改判成轻微问题。

## 观察指标与第一阶段通过条件

每个批次及累计 20 篇分别报告输入数、生成数、AUTO_APPLY、QUARANTINE、AUTO_REJECT、无产物/blocked/zero/error、实际落盘数、写入失败/rollback、Provider 调用/成功/失败/重试/超时、人工处理项、抽查项及发现的问题。

- **实际人工复核覆盖率** = 被人工查看的不同输入数 ÷ 已处理 raw 输入数。计入全部 QUARANTINE、异常调查和抽查的 AUTO_APPLY；同一篇重复查看只在覆盖率分子计一次。
- **实际人工复核下降比例** = 1 − 实际人工复核覆盖率。以“若全人工则 20/20 输入需要人工查看”为基线，同时另记人工耗时，避免把少量抽查误当成零成本。
- 现有 v0.1 台账的 `HUMAN_REVIEW_REDUCTION_RATE` 公式按自动分流比例计算，不等于上述“实际人工看过多少篇”的下降比例；两项分开报告，不改旧公式。
- Provider 稳定性报告原始成功/失败/超时/重试和耗时分布。当前尚无约定的数值 SLA；不得凭单个成功样本或 provider 返回成功就判定稳定。任何错误被静默转换为 `full`、成功零产出或自动批准，均为失败。

第一阶段可进入“扩大历史 Backfill”的最低条件：

- [ ] 20 篇不同 raw 全部有可追踪的终态记录；无漏项、重复计数或把计划数当处理数。
- [ ] 真实 source 产物的来源、机器可核验引文及 coverage 证据可回到原文；抽查中无事实强度升级或关键来源/数字/归属/引文错误。
- [ ] 严重 `False Auto Apply` 为 0；无未解释的 apply、hash、reconcile 或 rollback 失败。
- [ ] AUTO_APPLY、QUARANTINE、AUTO_REJECT 和无产物结果与实际队列/文件状态一致；隔离内容没有落盘为可用 Source 卡。
- [ ] 低风险 AUTO_APPLY 页面无需人工内容审批即可实际落盘；高风险 QUARANTINE 保持待人工处置。若只能由 `init-kb --apply` 批次整体暂停，或 AUTO_APPLY 仍要求人工批准，当前链路不满足本轮目标。
- [ ] Provider 稳定性及实际人工复核下降比例均有数据支撑；对“确定无效内容自动拒绝”的实现缺口有明确结论。
- [ ] 观察期内没有更改冻结策略。若更改，旧窗口停止，变更后的数据另起窗口。

达到 20 篇只是第一阶段观察点，不自动等于通过；按上述条件给出 `PASS / FAIL / UNKNOWN` 结论，并分别决定扩大 Backfill、继续观察或暂停自动放行。派生卡是否自动化不阻塞本阶段。

## 当前基线（2026-09-26 只读核对）

- `config.json` 中 `source_auto_apply.enabled=true`，策略版本为 `source-auto-apply-v0.1`。
- 策略阈值为 `quality_flags <= 5`；flags > 5 进入 QUARANTINE，不是 AUTO_REJECT。
- `SOURCE_AUTO_APPLY_V01_OBSERVATION_LEDGER.md` 报告起始进度 `0/20`，其窗口和口径是 20 张真实 AUTO_APPLY；本清单新建 20 篇 raw 输入窗口。
- 本文只定义检查方法；本次没有处理 raw、执行生成、改变队列/台账、修改代码或验证真实写入。

## 依据

- `core/auto_apply_policy.py`
- `core/review_queue.py`
- `scripts/personal_kb_steward.py`
- `core/source_analysis.py`
- `config.json`
- 仓库根目录 `SOURCE_AUTO_APPLY_V01_OBSERVATION_LEDGER.md`
