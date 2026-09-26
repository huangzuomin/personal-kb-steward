# Seed quality contract（M1 atomic）

M1 起 `mindseed-grow` 默认以 `seed_generation.mode=atomic` 运行；显式 `topic` 保留旧聚类通路。单一类型真值仍是 `core/schemas/seed-card.schema.json`；本文说明原子 seed 的质量语义与实现位置。

## 1. 信息单元（information units）

- 来源：`core/atomic_seed.information_units`。从完整 `source_text`（source worker 注入的原始文本，保留 BOM/CRLF）全量提取，不做前缀截断；单笔记预算 `MAX_UNITS_PER_NOTE=64`。
- 每个单元：`source`（库相对路径）、`quote`（逐字原文句）、`kind`（question/assertion）、`body_line`、`speaker`、`source_sha256`、`verified`。
- **Provenance 是精确字节校验**：`sha256(source_text.encode('utf-8'))` 必须与 `source_sha256` 完全一致才算 verified；归一化换行或补 BOM 的变体一律不通过。提供了 hash 但不匹配 → 整批 blocked（error），绝不静默缩减后照常调用模型。没有 source_text/hash 的 body-only 笔记记为 provenance unknown，只允许受限预览。
- **说话人归属**：只来自原文中的显式标签（如「一位读者说：」「**管理员**：」），标签激活后延续到同句后续与后续行，直到出现新标签；无标签即 unknown。笔记级 metadata 不能给整篇对话统一归属，调用方伪造的 speaker 会被原文重推的标签覆盖。
- 外部预提取单元（`units=` 入参）必须同时提供已验证快照（`snapshots=`）；每条 quote 在快照中定位：唯一直接通过；多重出现需行号提示命中唯一；错误提示或不可定位 → 拒绝该单元。

## 2. 批次预算与覆盖

- 全批上限 `MAX_UNITS=64`、总引文 `MAX_TOTAL_QUOTE_CHARS=24000`。超预算 → `coverage=partial`、`excluded_units` 记录、模型 payload 附带「非完整覆盖」声明；不允许把前缀当成完整分析。
- `coverage=full` 仅当全部单元 verified 且无排除。

## 3. 念头（thought）与身份

- 模型（或受限预览）按单元合成念头；一单元可支撑多个念头，多源可支撑一个念头。statement/kind 必填；question 单元被写成 assertion 会被标记复核，不当作事实。
- `thought_id = sha256(kind + statement + 已排序的单元身份)`：基于证据身份而非数组下标——重排不变、换源不同、追加证据变化（走复核更新而非提前跳过）。`unit_identity = sha256(kind+source+原始字节hash+规范化quote digest)`。
- 生长方向必须有具体 action 与 ≥4 字实质 basis；负向边界（negative_scope）必填。解析严格失败即拒绝该候选；**全部候选非法 = blocked 错误，不是零产出**。完全核验输入上的显式 `thoughts: []` 才是合法零产出。

## 4. 关系候选（core/card_relations）

- 只经 `core.retrieval.Retriever` 在已配置索引内检索，不另建索引/全库扫描。B1b 集成路径向 mindseed executor 注入 `vault_index`/`retriever`；独立调用缺少该上下文时仍记录 `link_search=not_attempted`，不虚构关联。
- `candidates_found` 只在存在可用 related 候选时报；同标题或同单元的既有 seed 记为疑似重复（怀疑≠已确认关系），进入 manual_review。检索报告按 path 对齐 hits，给出具体命中理由。不可验证的目标保持 pending；free text 中的 `[[ ]]` 一律转全角，避免渲染出新双链。

## 5. 更新与重用（core/seed_updates）

- 同标题 ≠ 同对象。对象重用判定键是 **(kind, statement_sha256) + 证据包含关系**，而非存储的证据版本指纹：已确认念头的相同表述且新证据 ⊆ 已记录证据 → NOOP（即使存储指纹是较早证据版）；证据超集 → 走既有 update 语义，保留稳定 `object_id`、手写正文和自定义 YAML，并将 `revision` 精确递增 1；NOOP 保持原 `revision` 不变。合并后 `seed_state.thought_id`/`card_state.thought_id` 同步为合并集指纹，后续完全相同重复为 NOOP。
- 同 statement 但证据无交集、同源不同表述、不同念头 → 各自独立的复核提案/另建卡（disambiguated 文件名），不自动合并。身份查找独立于用户改过的标题（thought_id 与同 claim+证据交集两条路径）；歧义匹配仍只产生复核建议。
- **hash 不重绑**：更新时旧来源沿用其已记录验证 hash，新来源用生成 hash；任一 hash 与当前索引不一致 → fail-closed 拒绝（不重绑旧证据）。无已存验证 hash 的 legacy 记录保留原 index-pin 语义。外层 `source_hashes`、`seed_state`、`card_state`（含 `source_hashes`/`thought_id`/`thought_units`）全部同步。
- **不收养 legacy 旧卡**：atomic 页面命中无版本化 card_state 的同名旧 seed → 另建带复核标记的独立新卡；显式 legacy topic 模式行为不变。

## 6. 诚实状态（executor）

| 情形 | ok | processed | 说明 |
| --- | --- | --- | --- |
| 模型提炼、全核验、无丢弃 | true | len(notes) | `meta.complete` |
| 显式零产出、全核验 | true | len(notes) | `zero_reason` |
| 无模型受限预览 | true | 0 | 明确标注受限预览，不算语义生成成功 |
| 模型失败回退预览 | true | 0 | `analysis_mode=heuristic-fallback`，safe error message |
| 非法响应/坏快照/敏感内容 | false | 0 | blocked；契约校验失败同样 processed=0 |

- 机密筛查覆盖出站 payload 与完整原始响应（含未用字段）；异常一律经 `safe_error_message`（类名 + 非敏感短消息）。
- 渲染文本中的模型自造 `[[ ]]` 全部转义；结构化 `card_state.evidence` 保留原始 quote 字节与坐标供核验。
- 集成状态（B1b/B2 seed acceptance）：`mvp_executor_plan` 的实际 mindseed 路径已传入 `vault_index`/`retriever`，并按每个输入的最终 updater disposition 回写 `processed`；`create`、`update`、`noop` 以及完全核验的显式 `zero` 可计入成功，blocked、拒绝、预览和未完成 sibling 不计入。证据见 [B1b acceptance](iteration-evidence/astra-B1b-acceptance.md) 和 [B2-seed acceptance](iteration-evidence/astra-B2-seed-acceptance.md)。derived receipts、subset apply 和 live semantic review 仍按迭代台账跟进。
