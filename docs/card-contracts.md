# Card Contracts（M0）— 契约、接口与接线说明

面向 source/seed 两条生产线的 worker 与 M1 接手者。单一类型真值是 JSON Schema（Draft 2020-12），不是 Python 内的临时检查器。

## 1. Canonical schemas（唯一类型真值）

| $id | 文件 | 生产 skill |
|---|---|---|
| `seed-card.schema.json` | `core/schemas/seed-card.schema.json` | mindseed-grow |
| `source-note.schema.json` | `core/schemas/source-note.schema.json` | topic-research-compile |

状态-阶段严格配对（schema `allOf/anyOf` 强制，其余组合一律拒绝）：

| 类型 | 合法对 |
|---|---|
| seed-card | `(seed, candidate)`、`(manual_review, needs_context)` |
| source-note | `(growing, compiling)`、`(manual_review, needs_context)` |

必填字段：`title, type, status, stage, sources(min 1 非空字符串), summary, confidence, review_required(严格 boolean), schema_version, analysis_mode`。
source-note 另有 `key_statements`、`topic_hints`（每项必须含 `title`）、`quality_flags`。无强制基数：数组可以为空，禁止编造内容。

未来 concept/case/topic schema：`register_card_schema(schema_dict)`（带 `$id`，注册时 `check_schema`），无需改 loader。

## 2. 公共接口（core/card_contracts.py）

```python
validate_card_item(item, card_type=None) -> list[str]   # [] 即合法；未知 type 拒绝（fail closed）
validate_skill_payload(skill_name, data) -> list[str]   # {"items":[...]} 信封校验；未登记 skill 返回 []
prepare_card_item(item, card_type, analysis_mode, *, trusted_source_hashes=None, trusted_coverage=None) -> dict
register_card_schema(schema) -> str
CardContractError                                        # 未登记引用/缺 envelope 时抛出；绝不远程获取
SKILL_CARD_TYPES = {"mindseed-grow": "seed-card", "topic-research-compile": "source-note"}
```

- **Provenance 信任边界**：`source_hashes`/`coverage` 只有通过 `trusted_source_hashes`/`trusted_coverage` 显式关键字
  传入才被采纳（`coverage` 仅接受 `full|partial`，full/partial 之外一律 `unknown`）；item 上的模型字段**无条件丢弃**
  ——generic runtime 直接处理模型 items，伪造的 hash 或 `coverage="full"` 不会被提升。无可信值记录 `{}`/`"unknown"`。
  严禁把清洗后文本的 hash 冒充原始字节 hash。
- **model 必须提供的内容字段**（runtime prompt 的 `output_contract.content_requirements` 声明；source-note schema
  同样必填）：`key_statements: array<string>`、`topic_hints: array<object{title, content}>`；seed 的
  `signals`/`growth_directions` 在 prompt 中要求。**program-owned 元数据（schema_version/generator_version/
  analysis_mode/source_hashes/coverage）绝不向模型请求**，模型给的值一律被覆盖。
- Envelope schema 位于 `skills/<skill>/schema.json`，`$ref` 引用 canonical `$id`，由本地 `referencing.Registry` 解析；未登记 URI 抛 `CardContractError`（测试 monkeypatch `urllib.request.urlopen` 证明零网络）。
- 要求 `jsonschema>=4.18`（requirements.txt 已声明）。刻意不提供旧 RefResolver 兜底。
- Schema 文件以 `utf-8-sig` 读取（容忍原始 BOM），读取时 CRLF 归一。
- **hash 语义**：原始来源 hash = 源文件**原始字节**的 hash。`core.claims.digest` 是规范化文本/引文 hash，不得冒充源快照 hash。producer 拿不到完整源字节 hash 时记录 `source_hashes: {}`、`coverage: "unknown"`，不得用清洗后正文自造。M1 source 提取提供精确快照。

## 3. Program-owned 元数据

`prepare_card_item` 无条件覆盖写入（不信任模型）：`schema_version="m0-1"`、`generator_version="pks-m0"`、`analysis_mode`（由调用方给出：executor 路径 `heuristic`，runtime 真实模型 `llm`、mock `unknown`）；`source_hashes`/`coverage` 默认 `{}`/`"unknown"`。

Legacy 状态归一化（producer normalization，只映射不扩权）：seed `growing→seed`、`seed(stage)→candidate`；source `compiled→growing`、`compiled(stage)→compiling`。映射外的值原样保留并由 schema 拒绝。

## 4. Source adapter（topic-research-compile）

renderer.py `render()` 内完成（渲染前，fail closed）：

```
source_summary → summary          key_facts → key_statements
topics → topic_hints              quality_flags → quality_flags（保留进 frontmatter）
review = mode != "llm" or flags   → (manual_review, needs_context, low) 否则 (growing, compiling, medium)
```

- `analysis_mode` 必须属于 `llm|heuristic|heuristic-fallback|unknown`，非法值直接 `ValueError`（executor 在成功调用 provider 后 program-owned 置 `llm`，不信任模型值）。
- 校验失败抛 `ValueError("source-note 契约校验失败…")`：不产生页面、不推进 processed 状态。
- 元数据 + quality_flags 通过 `base_frontmatter.j2` 条件块写入 frontmatter；旧模板不含这些变量时块整体跳过，互不影响。

## 5. Seed producer（mindseed-grow）

executor 在 `seed_item()` 之后、`render()` 之前：`prepare_card_item(item, "seed-card", "heuristic")` → `validate_card_item`；失败记入 issues、跳过该页（不渲染、不产出）。出现任何契约失败时该次生成尝试 **`processed=0`、`ok=false`**，
显式错误写入 issues——经真实 plan/state 路径证明：`apply_executor_pages` + `update_processed_index` 后
`operation_status=needs_review`，`is_processed=False`，输入保持 unprocessed（有效零产出/无实质内容处理与此不同，
照常走 review 门，不视为 schema 失败）。renderer frontmatter 固定输出 5 个元数据字段。

## 6. Generic runtime（core/skill_runtime.py）

`validate_contract` → 链接规范化 → `validate_skill_items` 之后：对 `SKILL_CARD_TYPES` 中的 skill，先注入/归一化 items，再 `validate_skill_payload`（envelope）。任何契约问题 → `ok=False`、无 previews。未登记 skill 完全不受影响；pages/created 信封不作为 card items 校验。

## 7. 配置 seam

```python
from core.config import seed_generation_mode  # 字段缺省时才默认 atomic；present 的 false/0/""/非映射等一律 ValueError
SEED_GENERATION_MODES = {"atomic", "topic"}
```

`config.example.json` 已含 `"seed_generation": {"mode": "atomic"}`；`scripts/validate_config.py::seed_generation_errors`
与 core helper 语义一致（缺省→默认；存在但类型/值非法→报错，不做类型强转）。**M0 只交付 seam：atomic 生成的实际
行为是 M1 工作，当前尚无新原子生成器功能。**

## 8. 预览与元数据持久化

- `core/renderer.py::render_preview` 对含契约元数据/quality_flags 的卡片原样写入 preview frontmatter
  （无关卡片的 preview 语义不变）。
- `base_frontmatter.j2` 条件输出 `schema_version/generator_version/analysis_mode/coverage/source_hashes` 与
  `quality_flags`；旧模板无这些变量时块整体跳过。
- 测试对 executor 产出与 generic preview 两条路径都做 `parse_frontmatter` 验证，含 quality_flags。

## 9. 兼容性承诺

- 旧页面（含 `stage: compiled`、无 schema_version）只读兼容，绝不重写；作为新卡片条目送检会被拒绝。
- `related/pending_links/manual_review` 语义不变；`claims.py` 仍是 ID/hash/span 的唯一权威。
