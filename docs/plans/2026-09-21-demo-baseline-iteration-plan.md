# personal-kb-steward：以 demo 为最低基线的迭代计划

日期：2026-09-21  
状态：工程验收通过，内容收尾。最新完整回归 986 项通过、9 项平台权限跳过；一轮真实公开生成经审核写入 15 张五类卡片。Astra 内容评审为 revise：只剩种子标题/弱关联、主题来源范围两包收敛任务，详见 `../iteration-evidence/astra-public-live-content-review.md`。Claude CLI 已恢复；Astra 继续负责规划、调度和独立验收。存量卡修复、可选 demo v2 和新架构不进入收尾。  
核对基线：`4d95bc8a56aec52e088b229d5fc5f872d1be121c`。后续实现若基线前进，检查相关差异并调整任务，不重复实施已合并修复。

## 1. 已确认的范围与取舍

1. **现有 demo 是最低质量基线。** 不重新讨论其是否成立，不降低为仅供参考的样式。系统生成物必须达到对应类型的内容质量；不要求逐字复制，也不以固定条目数代替质量。
2. **不修复存量卡片。** 原计划批次 F 的旧卡迁移、补字段、版本猜测和重处理命令不进入本计划。现有 132 篇来源卡、148 张 seed 仅为历史产物，不是本轮修复对象。
3. **原子 seed 已纳入产品方向。** 新标准是一卡一个可独立表达的念头，允许单源；聚类作为候选发现或去重辅助，不再直接充当卡片内容。
4. **稳定后再删除派生卡并重跑。** 本计划完成条件不包含当前真库删除或重跑。届时依据派生文件归属清单、备份及明确路径另行执行，不清空原始资料或 demo。
5. **可选 demo v2 不阻塞实现。** 先达到现有基线；更细证据标注、行动化方向、关系解释可用少量新样张评估，保留原 demo。
6. 维持五个用户入口，不增加要求用户理解 schema、内部 skill 或模型编排的新操作。默认生成提案，审核和 apply 沿用原通路。

输入材料：

- [第三方 agent 交接工作包](../HANDOVER-第三方agent修复工作包.md)。
- [工程核验与修复计划 v2](../工程核验与修复计划_v2.md)：复用仍相关的 B/C/D/E 内容；A 中已合并内容只做回归，F 退出本轮。
- 工作区根目录 `缺口评估报告-对照demo基准.md`。
- 本地 `OLD_VAULT/_kb-steward-demo/00-示范卡基线说明.md` 及 16 张示范卡。

本计划采用用户最新裁定，覆盖旧交接中“原子 seed 待批准”和“最后修存量”的安排。旧交接末尾的 `a392613` 检查项已过期；不修改历史输入文件。

## 2. 目标与验收样本

最终目标：同一组材料经真实系统路径处理后，能按材料内容生成达到 demo 水平的来源、种子、概念、案例和主题卡；在分批处理与再次执行时保持身份、来源和审核语义一致。

| 类型 | 最低内容标准 | 不合格示例 |
| --- | --- | --- |
| 来源卡 | 原始来源、核心摘要、关键陈述、专题线索、质量标记齐全；说明材料性质、可用范围和核实限制 | 只有摘要；用“暂无明显问题”掩盖无脚注的 AI 报告；把原文声称当作独立核实 |
| seed | 一个念头、具体出处、针对该念头的生长方向、负向边界、真实关联或待创建项 | 用聚类理由当思想；所有卡同一组方向；单源一律判无价值；捏造用户经历和偏好 |
| 概念卡 | 一句话定义、展开、相近概念辨析、边界、必要 aliases、来源 | 泛百科定义；无依据宣称概念包含或因果关系 |
| 案例卡 | 背景、做法、结果、可复用机制、适用边界、证据出处；项目与机制粒度可区分 | 只复述成功故事；将结果数字写成已核实；重复拆卡增加数量 |
| 主题卡 | 主题边界、来源地图、知识对象索引、分歧、缺口、下一步；围绕问题组织 | 单篇摘要升格；罗列材料；为了满三条而编造冲突 |

样本分两层：

- **本地内容验收集：** demo 对应的三份材料及 16 张示范卡。T0 固定源路径、文件 hash、评阅映射，禁止把范文正文作为生成输入。生成与检索仅使用获准原始材料及本次流水线新产物，排除 demo 和旧派生卡，防止把检索范文冒充生成能力。已认可的思想单元必须被覆盖或说明合理合并/拆分，不机械要求正好生成 16 张。
- **公开回归集：** `examples/mini-vault/` 可用资料，加合成的人机对话、无脚注 AI 报告、口述案例、单源思想、无关材料、无实质内容、受损文本和重复引文等。公开版本不含私人素材及其摘录；不改 `.pks-pr` 工作区。

私人材料只在本地数据边界内处理，不因当前云端模型配置存在而视为允许外发。若可用执行器无法满足边界，完成公开样本的工程和语义验收，将私人样本真实模型验收明确列为未完成，不用 mock 代替。

## 3. 实现决策与接口

### 3.1 复用现有主干

采用“来源快照 → 信息提取 → 按类型生成候选 → 检索已有对象 → 校验 → 计划 → 审核 → apply”。

- 复用 `core.claims` 的原文定位、来源 hash、Claim/Evidence；`fact` 不代表已核实。
- 复用 `core.retrieval.Retriever` 选材和关联候选；区分主题支持、应用、反例与疑似重复。
- 复用对象身份、revision、base hash、Reconcile 和 plan/review/apply，不新增并行写入器。
- 复用 `initializer` 的批次组织与 `finalizer` 的跨批入口，但替换以正文项目和关键词直接拼通用卡的内容生成路径。
- `topic-research-compile` 单文处理默认产来源卡；概念/案例按信息单元提案；主题在跨源综合阶段产生。不是每篇原文必须生成五种卡。

### 3.2 统一数据边界

T0/T1 固定以下合同，后续 worker 按合同交付，不自行修改公共字段语义：

| 对象 | 必要内容 | 程序负责的部分 |
| --- | --- | --- |
| 来源快照 | 相对路径、正文、原始字节 hash、来源性质、说话人信息、阅读覆盖情况 | hash、规范化坐标与覆盖范围；未知性质/说话人明确标未知 |
| 信息单元 | assertion/question/procedure/reference 分类、原文片段、来源、位置提示、归纳或问题 | 验证具体 occurrence；不把清洗后位置当原文位置；信号分类与 Claim 的 fact/inference 不混用 |
| 卡片候选 | type、title、summary、类型专属字段、sources、claims/信息单元引用、related 候选及理由、quality_flags | 分配身份、核对来源与链接、计算 revision；模型不分配 ID/hash |
| 执行结果 | pages/items 或 created 的适配结果、issues、输入覆盖、阶段结果、零产出原因 | 在 adapter 中统一，schema 校验 structured item，不能把执行器外层信封当卡片数据校验 |

候选的新增字段先在类型 schema 中定义。JSON Schema 采用现有草案指定的 Draft 2020-12，使用 `jsonschema` 并显式写入 requirements；不自行实现部分标准。schema 本地加载，不访问远端引用。

类型 schema 的唯一来源为计划新增的 `core/schemas/seed-card.schema.json`、`source-note.schema.json`、`concept-page.schema.json`、`case-story.schema.json`、`topic-page.schema.json`。T1 在 `core/card_contracts.py` 实现 type→schema 的本地注册表及加载器，拥有前两种类型；T4/T5/T7 分别拥有后三种类型。`skills/*/schema.json` 仅描述 items 外层及引用相应类型合同，避免同一种卡在两处维护不同字段规则。

状态最小规则：seed 使用 `status=seed|manual_review`、`stage=candidate|needs_context`；其他新卡默认 `status=growing|manual_review`；来源卡使用 `stage=compiling|needs_context`，概念、案例、主题的类型专属阶段按已实现的 `docs/status-stage-model.md` 和 canonical schema 执行。首轮不自动标记 compiled/linked。各类型确有冲突时保留冲突字段及审核原因。旧页继续只读兼容，不批改旧词表。

新 seed 策略键采用 `seed_generation.mode=atomic|topic`（计划新增）：新默认和验收使用 atomic；显式 topic 保留旧模式可用性，但不对旧卡执行转换。无模型时 atomic 不能静默回落为主题聚合并宣称达标，只能提供标明局限的待审核预览或明确阻塞。

### 3.3 链接与身份

- 普通 related 从限定检索范围中产生，记录 not_attempted/no_match/candidates_found；允许空关联，不允许未检索却报告无匹配。
- 所有双链使用可解析的知识库相对路径，不沿用 demo 中依赖全库 basename 的宽松解析作为工程合同。
- 同批候选尚未落盘时使用内部待解析引用；基础卡审核写入后再经计划补互链。被拒绝或失败的页不能留下正式双链。
- 同标题不等于同对象。原子 seed 不能继续仅按标题精确匹配自动合并；优先匹配已确认身份与来源信息单元，语义近似只产生复核建议。
- 同一批次拆分处理后的身份一致性指同一工作库内沿用已确认对象；不要求两个全新库随机分配的 ID 相等。

## 4. 里程碑与任务分工

整体依赖：`T0 → T1 → (T2 ∥ T3) → M1 → (T4 ∥ T5) → T6 → T7 → T8`。

T9 的 Windows 写入边界验证在 T0 后即可开展；首次隔离库 apply 前必须完成。T10 批量稳定性依赖 T8/T9。本表概述实施状态；逐次审核结论与证据以 `docs/iteration-evidence/LEDGER.md` 为准。

| 任务 | 负责人 | 依赖 | 交付物 | 当前状态 |
| --- | --- | --- | --- | --- |
| T0 基线、样本、内容判据 | Astra 设计；Claude CLI 建夹具与清单 | 无 | 样本 manifest、五类评阅表、反例清单 | 公开夹具与基线判据已验收 |
| T1 公共契约与调用适配 | 单个 Claude CLI 集成 worker | T0 | 类型合同、schema 校验、状态统一、适配入口 | 工程基础已验收 |
| T2 来源卡 | Claude CLI source worker | T1 | 完整来源分析、覆盖报告、来源卡样张 | 工程与显式零产出已验收；真实模型评测待执行 |
| T3 原子 seed | Claude CLI seed worker | T1 | 原子提炼、生长方向、关系候选、样张 | 工程与 mock 样张已验收；真实模型评测待执行 |
| T4 概念卡 | Claude CLI concept worker | M1 | 概念提取、边界与 aliases、样张 | 工程与角色约束已验收；真实模型评测待执行 |
| T5 案例卡 | Claude CLI case worker | M1 | 项目/机制卡、数字归因与边界、样张 | 工程与角色约束已验收；真实模型评测待执行 |
| T6 概念/案例流程接入 | T1 集成 worker | T4/T5 | 类型路由、按需产出、关联写回 | A1/A2/B1a/B1b/B2-source 已通过工程验收；B2-seed 实施中，逐卡审核待接入 |
| T7 主题综合 | Claude CLI，额度中断后 Luna 接续 | T6 | 来源地图、分歧/缺口、行动顺序 | 生成器、mock 样张与 B1a 实际流水线接入已通过工程验收；真实内容验收待执行 |
| T8 跨批与阶段账本 | T1 集成 worker | T7 | 合格输入选择、去重更新、零产出解释 | 类型更新、来源回执与逐卡审核纯函数已验收；seed 回执实施中，跨类型重复运行与审核写入待完成 |
| T9 Windows 执行边界 | Claude CLI runtime worker | T0 | 原生路径证据、探针与失败恢复验证 | 探针与 junction 已验收；真实 symlink 因权限未验证 |
| T10 批量与最终验收 | Claude CLI 执行；Astra 验收 | T8/T9 | 回归日志、真实模型样张、内容评阅、稳定性报告 | 调用适配器及 C2/C3 工程验收通过；最小闭环修复后执行冻结回归与一轮完整真实模型评审，按实际失败补测 |

并行上限依实际运行槽位；每个 worker 不独占工作区，不回退他人变更。T1/T6/T8 由同一集成负责人顺序接续，避免公共入口多人修改。

### M0：明确合同与样本（T0/T1）

允许文件：`core/json_contract.py`、`core/validator.py`、`core/skill_executor.py`、`core/skill_runtime.py`、`core/renderer.py`、`core/templates/base_frontmatter.j2`、`core/config.py`、`config.example.json`、`scripts/validate_config.py`、`docs/status-stage-model.md`、`requirements.txt`；新增 `core/card_contracts.py`、公开夹具及类型合同文档。既有 seed schema 与新增 source schema 由 T1 定义，后续各卡 worker 可修改自己的类型 schema，但不得擅改共同 envelope。公共渲染和 frontmatter 字段扩展由集成 worker 统一处理，避免各生成器落盘后丢失质量字段。

工作：

- 把五类基线写成“必要内容/反例/证据与链接要求”，对已认可 demo 逐项建立映射，不增加重新认可 demo 的环节。
- 校验放在所有相关调用路径的渲染前；非法 stage、布尔值、来源、类型字段阻断，不输出伪完整页。
- 保留 PR #29 的渲染依赖前置、敏感内容筛查和 run 范围审核；不重新开发。
- 为新产物记录 schema_version、generator_version、analysis_mode、来源 hash 与 coverage。版本用于新产物审计，不引入旧产物迁移。
- 公共配置默认值由集成 worker 修改代码及无秘密示例；不读取、打印或覆盖当前凭据配置。
- T1 明确负责 `seed_generation.mode` 的 atomic 默认值、atomic/topic 枚举校验、示例配置和两种模式的测试夹具；T3 仅消费该合同，不等待晚于自己的 T6 再补配置。

验收：正常 structured item 通过；非法项在渲染/计划前拒绝；缺依赖不调用模型且不推进 processed；损坏内容不会被生成器补成流畅事实；UTF-8/BOM/CRLF 正常输入通过。

### M1：来源卡 + 原子 seed（T2/T3，第一轮产品交付）

**T2 文件所有权：** `skills/topic-research-compile/executor.py`、`renderer.py`、`schema.json`（新增）、`SKILL.md`、`core/templates/source_note.j2`；必要新增 `core/source_analysis.py` 及专属测试。

- 从按“行业报告”统一提示改为识别对话、AI 汇编、口述、原始报告等材料性质；识别用户/AI/讲述人，不将 AI 发言写成用户观点。
- 对完整来源做有界分段提取，保留原文位置和分段覆盖。当前 `max_source_chars=6000` 截断路径不能静默丢掉后文；超预算时报告未处理范围并标记 partial，不能算完整验收。
- 先提取有出处的信息单元，再归纳摘要、事实/观点、专题线索和来源评估。无脚注的具体数字标明未经独立核实；检索不到原始出处不造出处。
- `quality_flags` 除格式问题外，应反映说话人、转述、脚注、选择偏差等与实际材料相关的限制。没有发现问题不等于已核实。

**T3 文件所有权：** `core/seed_quality.py`、`core/seed_updates.py`、`skills/mindseed-grow/executor.py`、`renderer.py`、`schema.json`、`SKILL.md`、`docs/seed-quality.md`；必要新增 `core/atomic_seed.py` 与 `core/card_relations.py`。`core/clustering.py` 仅在必要适配时修改。

- 按信息单元提炼念头，不用聚类 reasoning 充当 summary。允许一源多个独立念头，也允许多源支持一个念头；空内容允许零产出。
- 每个生长方向必须与该念头的证据或未知项相关；覆盖反例、代价或失效边界中的适用项，不为凑数改写同一句。
- 明确“卡片边界/暂不扩展到的方向”；没有用户原话时不可生成假装用户表态的第一人称偏好。
- 用 Retriever 提供真实候选、输出关系解释；没有合适候选时正确保留空关联。
- 保留旧主题模式显式可用；新默认 atomic 及配置行为同步到文档与测试。调整标题匹配更新逻辑，防止不同念头被同名自动吞并。
- 原子提取不意味着取消输入范围限制：长文来源处理后，可向 seed 阶段提交已提取的候选；与直接 quicknote 路径复用同一生成器。

M1 必须交付：来源卡与 seed 的系统生成样张、输入覆盖报告、逐卡 demo 对照、正常和反例测试证据。私人样本完成时至少覆盖 demo 中三份来源的质量特征及四个 seed 的思想单元；不要求标题完全相同。

M1 通过条件：来源可追溯、思想粒度正确、方向具体、无虚构、链接真实；新增样本无需大幅改写即可达到 demo 水平。失败项返回对应 worker，不以“schema 通过”代替内容达标。

### M2：概念与案例（T4/T5/T6）

**T4 文件所有权：** 新增 `core/concept_generation.py`、`core/templates/concept_page.j2`、概念类型 schema、专属测试。

- 从合格信息单元抽取定义、概念差异与 aliases；有依据的单源概念合法。
- 边界辨析区分原文已有主张与生成解释，解释需标明推断，不凭模型常识补写库外事实。
- 用现有对象检索处理别名与近似概念；不按词面相似自动合并。

**T5 文件所有权：** 新增 `core/case_generation.py`、`core/templates/case_story.j2`、案例类型 schema、专属测试；更新 `skills/case-story-bank-builder/SKILL.md` 与其实际调用适配说明。

- 按项目样本和机制单元切分。两卡共用材料时说明分工，避免同一故事换标题重复输出。
- 分开记录做法、观察到的结果、来源声称的结果与机制推论；数字有出处及核实状态。
- 适用边界必须与案例条件有关，证据不足时标明待验证，不制造“普遍成功方法”。

**T6 集成所有权：** `core/initializer.py`、`core/finalizer.py`、`core/skill_executor.py`、`scripts/personal_kb_steward.py` 的技能集合与薄 adapter、必要的 `workflows.json`、`router.json`、配置默认值与调用适配。接入独立案例 skill 时新增 `skills/case-story-bank-builder/executor.py`，仅委托共享的 `core/case_generation.py`，不复制生成逻辑。若需调整 `topic-research-compile/executor.py` 的调度，T2 完成后由 T6 接手。公共入口更改仅由集成 worker 实施，主 CLI 保持 1700 行上限。

- 在新流程中接入自动候选发现，不再要求用户预先填每个概念/案例的标题或 marker；旧显式规则可兼容。
- 候选发现默认可运行，是否写入仍由证据资格与审核决定；不强开旧 promotion 并降低阈值凑产出。
- 单源合格概念/案例可产出；多源但没有该类型内容时正确零产出；不套用专题的统一来源数门槛。

M2 验收：demo 的概念辨析与案例机制覆盖；无关输入零强造卡；互链指向已经写入的真实页；卡片有差异化价值。案例专属 skill、初始化和 finalize 不得形成三套不一致生成逻辑。

T6 新增 `tests/test_card_pipeline_integration.py`：在临时 vault 中分别经初始化、finalize 和案例 skill 的实际 adapter 生成提案，审核后 apply，断言落盘 type/专属字段、来源 hash、对象身份、processed 与审核记录正确；拒绝一张候选后，其余已写页面不得出现指向它的双链。仅调用生成器函数不能算此项通过。

### M3：主题综合与跨批生长（T7/T8）

**T7 文件所有权：** 新增 `core/topic_generation.py`、`core/templates/topic_page.j2`、主题类型 schema、专属测试；与既有 `core/synthesis.py` 共用证据和检索入口，公共适配交 T8。

- 围绕问题生成来源地图、种子/概念/案例索引、已知判断、分歧、缺口和下一步。
- 真冲突必须有两侧判断及其证据；情境差异和待检验张力分列，未发现冲突可明确说明。
- 缺口写清缺少哪种证据、影响哪个判断；下一步按判断价值和可执行性排序。
- 专题默认沿用至少 3 个具体来源的既有要求，同时说明转载或共同来源；不足时只能是明确标记的 topic stub，不宣称达到完整主题基线。

**T8 集成所有权：** `core/initializer.py`、`core/finalizer.py`、`core/synthesis.py`、`core/layout.py`、`core/skill_executor.py`、`scripts/personal_kb_steward.py` 的薄 adapter、必要新增 `core/stage_ledger.py`。

- 从已落盘、覆盖合格、来源可追溯的 source-note 取材；存在质量限制的材料可以作为线索，但不被自动升级为已核实证据。
- 记录 executed/skipped/blocked/error 与 reason、输入输出数量。区分 no_inputs、zero_output、not_configured、insufficient_evidence、partial_input、model_error。
- 拒绝 `max_sources < min_sources` 等不可能满足的配置；不让批次大小决定一张概念/案例是否有资格存在。
- 同一工作库中整批/逐篇/重复输入最终指向同一已确认知识对象和来源集合。新增证据通过既有审核更新，人工正文与自定义字段保留。
- 新产物继续支持正常增量更新与冲突保护；这属于系统运行能力，不扩展为旧库迁移任务。

M3 验收：同组材料整批与拆批处理结果语义一致，无重复卡；主题具备 demo 的来源地图、分歧、缺口和下一步；失败和零产出有准确解释。

跨批比较口径：固定 mock/录制响应的确定性测试比较 `(type, 已确认思想或案例机制键)`、去重后的 `(source_path, source_sha256)` 集合、claim statement/kind 与证据片段集合、关系类型与目标键、质量标记及阶段原因；忽略时间戳、run_id、列表顺序和不同新库的随机 object_id。同一库重复执行必须保留原 object_id，内容无变化时不推进 revision。真实模型运行按固定评阅表比较思想覆盖、来源支持、边界、冲突/缺口，不以词面相似度作为语义一致证明。

### M4：执行稳定性与发布门槛（T9/T10）

T9 负责 `core/output_paths.py`、`core/safety.py` 的必要改动及独立 Windows 测试；涉及公共 run/CLI 的变更交集成 worker 顺序落地。

- 在原生 Windows 验证 symlink/junction、库内受保护目录、库外目录、未存在目标。无权限 skip 记未验证；确认实际越界才做针对性修复，首次 apply 前不得留未解释的边界失败。
- 探针按每次 apply 的实际父目录去重，不跨 run 缓存，不以历史文件存在认定当前可写。保留宿主删除守卫，不绕过；如需要保留探针文件，明确程序所有权、再次写入和清理策略。
- 中断保留真实已写页和 manifest，不错误推进 processed，不建议无条件重跑；更新型 run 不使用删除式 rollback。
- 用公开/合成材料在隔离库执行多批次（至少 3 批，包含重复输入、一次失败和正常续行），验证 new/default 配置可发现类型并输出准确账本。
- 同一公开语义验收集在固定模型/提示词版本下运行 3 次，全部保留结果；不要求逐字一致，必须无硬性违规并达到类型基线。重试只修明确失败，不挑最好一轮宣称稳定。
- 检查中文产物编码、正文可读性和链接；新增流水线的冷启动与再次执行都必须通过。

M4 完成后交付“系统可用于派生卡重建”的结论及证据。真库派生卡删除、备份清单确认与全量重跑另作执行任务，不在此处运行。

## 5. 验收制度与证据交付

### 5.1 两层检查

**机器硬门槛：** schema/状态合法；来源与引文位置可核对；原始文件 hash 不变；无凭据泄漏；无越界写入；无虚构链接；模型失败或截断被显式记录；审核绑定 run；同输入不重复造页；人工更新冲突被阻断。

**内容门槛：** 按第 2 节逐卡评阅，记录 pass/revise/fail 及具体问题。Astra 独立检查实际样张与证据；worker 的 done 是交接，不等于验收通过。若对已认可 demo 的覆盖需要实质改写，该项为 revise，不算达标。

现有 demo 的用户认可已经成立。新生成卡的基线对照由实施验收完成；只有出现新的产品语义取舍或用户偏好不明时才集中提出问题，不逐批请求重复授权。

### 5.2 每个任务的交付格式

公开/合成证据写 `docs/iteration-evidence/<task-id>/report.md`，包括：基线 commit、变更文件、命令与退出码、测试日志位置、样张位置、通过/失败项、已知限制。该目录为计划新增，不视为当前存在。

私人样张、来源 manifest 和逐卡对照写工作区根目录下 `iteration-artifacts/2026-09-21-demo-baseline/` 的本地子目录；不提交仓库、不发送上游。报告中不打印秘密或不必要的私人摘录。

每轮报告明确区分：离线合同验证、mock 编排验证、真实模型内容验收、隔离库实际写入、真库执行。只有前两项通过不能标记 demo 达标。

记录模型调用次数、失败/重试次数、耗时和可取得的 token 使用量；不虚报成本节省。私人或付费执行超出既有授权时保留该项未执行，继续独立的公开和离线工作。

## 6. 测试执行约定

本计划编制阶段不运行业务测试，不把历史测试数字当作本轮验证结果。实现后每轮只执行相关现有测试和新增测试；最终执行受影响的离线回归集合，不直接跑可能阻塞的全量网络测试。

仓库中已存在且应保留的回归入口：

- PR #29：`tests/test_render_fail_closed.py`、`tests/test_signal_safety.py`、`tests/test_review_run_scope.py`、`tests/test_priority_fixes_integration.py`。
- 来源/seed/证据：`tests/test_source_traceability.py`、`tests/test_seed_quality_outputs.py`、`tests/test_claim_evidence.py`。
- 写入与运行：`tests/test_apply_plan.py`、`tests/test_object_plans.py`、`tests/test_pr15_contracts.py`、`tests/test_reconcile.py`、`tests/test_runtime_boundaries.py`。
- 检索与综合：`tests/test_retrieval.py`、`tests/test_synthesis.py`。
- 编排与失败恢复：`tests/test_workflows.py`、`tests/test_producer_recovery.py`、`tests/test_run_recovery.py`。

严格离线执行必须显式关闭或 mock 模型 provider，并验证无外部调用。已发现 `tests/test_mvp_skill_executors.py::test_mindseed_executor_returns_page_specs` 未显式关闭 LLM，不纳入无人看护的离线集合；实施时修正 fixture 的执行模式，不通过读取当前凭据来判断是否会联网。新默认 atomic 上线后，旧主题模式测试须显式指定 topic，atomic 内容质量另以真实模型样张验收。

PowerShell 示例（已确认解释器文件存在；每次使用新的临时根，运行后恢复环境变量）：

```powershell
Set-Location 'D:\OLD_VAULT-整理后-20260919\tools\personal-kb-steward'
$pksPython = 'C:\Users\zooma\.workbuddy-ai\binaries\python\envs\default\Scripts\python.exe'
$pksTemp = Join-Path $env:TEMP ('pks-iteration-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $pksTemp | Out-Null
$pksPreviousTemp = $env:PYTEST_DEBUG_TEMPROOT
try {
    $env:PYTEST_DEBUG_TEMPROOT = $pksTemp
    & $pksPython -m pytest -q tests/test_render_fail_closed.py tests/test_signal_safety.py tests/test_review_run_scope.py tests/test_priority_fixes_integration.py
    if ($LASTEXITCODE -ne 0) { throw 'PR29 regression suite failed; inspect output.' }
} finally {
    $env:PYTEST_DEBUG_TEMPROOT = $pksPreviousTemp
}
```

新增测试文件按任务创建后再运行，不能在文件尚不存在时宣称命令可用：

| 任务 | 计划新增测试 | 必须覆盖 |
| --- | --- | --- |
| T1 | `tests/test_card_contracts.py` | 各类型 schema、两类执行器返回结构适配、状态、依赖缺失不推进处理 |
| T2 | `tests/test_source_quality_contract.py` | 说话人、无脚注、数字归因、尾部关键内容、截断覆盖、重复引文定位、坏编码 |
| T3 | `tests/test_atomic_seed.py`、`tests/test_seed_growth_links.py` | 单源多念头、多源同念头、零内容、方向具体、无匹配、同名不同念头、模式兼容 |
| T4 | `tests/test_concept_generation.py` | 定义/边界依据、别名、不强造概念、不按相似标题误合并 |
| T5 | `tests/test_case_generation.py` | 机制拆分、项目/机制重叠、数字核实状态、适用边界 |
| T6–T8 | `tests/test_card_pipeline_integration.py`、`tests/test_topic_generation.py`、`tests/test_cross_batch_promotion.py`、`tests/test_stage_ledger.py` | 实际 adapter→审核→apply、真冲突/情境差异、缺口、零产出原因、规范化跨批比较、审核拒绝后的链接完整性 |
| T9/T10 | `tests/test_preflight_probe_policy.py`、`tests/test_windows_write_boundaries.py`、`tests/test_demo_pipeline.py` | 真实路径边界、跨 run 权限变化、多批重复输入与中断、五类型贯通 |

隔离库测试从既有 test harness 构造独立 cfg、vault、plans、review queue、runs 和 processed index，不使用当前真库 `config.json` 执行 `--apply`。CLI 当前无 `--config` 参数；不要在工单中编造该命令。端到端驱动的具体命令随 harness 落地后写入对应 report。

## 7. 覆盖与完成定义

| 原缺口 | 处理任务 |
| --- | --- |
| G1/G2/G3：seed 粒度、方向、关联 | T3；单源成卡及关系解释为硬要求 |
| G4/G5/G6：概念、案例、主题 | T4–T8；以实际默认新流程可达为准 |
| G7：旧来源卡残缺 | 存量修复排除；T2 确保新产物完整 |
| G8/G9/G10：schema 与状态漂移 | T1，后续类型扩展同步更新合同 |
| G11/G12：探针与 Windows 边界 | T9，首次 apply 前验证 |
| G13：候选提升与跨批限制 | T6/T8，不以每批必须产出代替正确性 |
| G14：损坏夹具 | T0 记录；有可信原版才能恢复，否则换明确的合成正例并保留损坏负例，不猜原文 |
| G15：信号语义分型 | T1/T2/T3，与证据资格及秘密筛查分开 |

不在范围：旧卡迁移器、当前真库重跑、自动删除、全库重命名、重新设计存储、重写全部 11 个 skill、新 UI、强制每篇材料产出五类型、未经授权将私库材料上传第三方。

完成定义：五类内容均达到已认可 demo 最低水平；所有硬门槛通过；默认新流程可达；跨批与重复运行可靠；真实模型语义结果和隔离库写入都有证据；无尚未解释的关键失败。实现完成、Astra 验收通过、真库重建完成分别报告，不混称。

第一张实施工单：**T0/T1，固定样本和公共合同**。紧接着 T2/T3 形成第一轮可读交付；不插入旧库修复或先做 demo v2 的前置工作。



## 当前剩余的实施与验收顺序

按用户最新要求收敛：聚焦达到已认可 demo 的最低质量和稳定的新卡生产，不再扩展机制或增加无关的边界测试矩阵。

五类生成与更新主链、逐卡审核和写入已实现；逐卡写入/恢复的独立检查为 86 项通过及 6 项子测试通过。最新联调中，三批输入测试已通过；正向增长仍在最终未变重跑时重复更新，旧任务入口的处理索引也需要恢复正确的完成状态。这两项尚未关闭。

1. **最小闭环修复：** Claude CLI 只处理上述已复现的失败，复用现有处理记录、产物证据和状态写入函数；Astra 独立检查。工单：`docs/work-orders/FINAL-minimum-closure.md`。
2. **冻结回归：** 跑一次完整离线回归及既定必要检查，确认默认入口贯通，只修真正影响交付的回归。
3. **内容验收：** 按用户“聚焦目标、不要过度工程化”的最新要求，先做一轮完整公开合成素材的真实模型生产，逐类检查实际样张；仅针对实际失败修正和补测，不把原先规划的三轮重复评测作为最低交付前提。最多 30 次尝试调用的既定上限保留。公开评测与私有 demo 等价性分别报告。

当前尚未达到整体验收。存量卡修复、真实库删除重跑、合并主分支和发布均不在这些步骤中。

