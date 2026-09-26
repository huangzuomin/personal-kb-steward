# 交接文档 · personal-kb-steward 后续修复工作包

> 交接时间：2026-09-20（**23:55 更新：上游已合并 PR #29**）
> 交接方：本地维护会话（Windows）
> 接手方：**第三方 agent，任务是「执行修复」**（不是重新核验）
> **本文件是唯一入口。请先完整读完 §0–§5，再碰 §6 的代码。**

> ## 🔴 23:55 更新 —— 基线已从 `a392613` 前进到 `4d95bc8`
>
> 上游合并了 **PR #29 `fix/priority-20-25-27`**，把 v2 里「只能修三条时」的那三条**修完了**：
> **#27 渲染 fail-closed / #25 信号安全边界 / #20 run 级审核**。
> 本机验证：**76 passed + 9 passed**（命令见 §3）。
>
> **⇒ §6 的批次 A 已完成，批次 C、D 的部分内容也已完成。动手前先读
> `缺口评估报告-对照demo基准.md`**（库外 `D:\OLD_VAULT-整理后-20260919\`），
> 它列出了 PR #29 之后**仍然存在**的 15 个缺口。
>
> 上游自己的修复说明 `docs/fixes-20-25-27.md` 也划了边界：
> 「**#18 的宿主删除守卫与 #19 的原生 Windows 路径问题不在本次改动内。**」

---

## §0 一句话

上游 `main` = **`4d95bc8`**（PR #29 合并后），本地与它**完全一致**。
v2 的核验已完成，**且上游已自行修掉三条（#27/#25/#20）**。
**你的任务是修剩下的，不要再修这三条。**

剩下最刺眼的一条：`_kb-steward/sources/` 的 **132 篇产物仍然 0 个 `##` 小节** ——
渲染代码已修好，但**存量一篇都没重跑**（上游明示「不自动重跑 processed-index 内的旧资料」）。

---

## §1 你的任务与边界

### 要做

按 `docs/工程核验与修复计划_v2.md` 的**批次 A → B → (C ∥ D) → E → F** 执行修复。
每批都带「改动要点 / 可执行验收 / 回归风险」三节，**验收标准是交付门槛，不是参考建议**。

如果时间只够修三条，v2 已给优先级：**#27（渲染静默降级）→ #25（摘录边界与敏感外发）→ #20（审核绑定 run）**。
另：**#19 必须尽早验证** —— 一旦在原生 Windows 复现真实越库写入，按 P0 处理。

### 不要做

1. **不要重新核验**。11 条 issue + PR #28 已逐条判定过，直接采信 v2 的判定表。
   你的价值在「把计划变成可运行的代码」，不在「再怀疑一遍」。
2. **不要碰真库数据**。`OLD_VAULT` 是用户的真实知识库备份，只读。
3. **不要动 `.pks-pr` worktree**（那是 PR #28 的工作区）。
4. **不要直接把修复推到 `main`**，走分支 + PR。
5. **不要用旧 `HANDOVER.md` 的行号**。见 §2 的「哪份文档有效」。

---

## §2 工作区与基线

### 路径

| 角色 | 路径 |
| --- | --- |
| 工具仓库（**你改这里**） | `D:\OLD_VAULT-整理后-20260919\tools\personal-kb-steward` |
| 真库（**只读**） | `D:\OLD_VAULT-整理后-20260919\OLD_VAULT` |
| 产物落盘 | `OLD_VAULT/_kb-steward/` |
| 运行态 | `tools/personal-kb-steward/.openclaw/` |
| PR #28 工作区（别动） | `D:\OLD_VAULT-整理后-20260919\.pks-pr` |

### 🔴 基线 commit

```
4d95bc8a56aec52e088b229d5fc5f872d1be121c
```

开工第一件事，先验证：

```bash
cd "D:/OLD_VAULT-整理后-20260919/tools/personal-kb-steward"
git rev-parse HEAD        # 必须输出 4d95bc8a56aec52e088b229d5fc5f872d1be121c
git status --short        # 应当只有 §4 列出的那几项
```

**不是这个值就停下来**，先跟维护者确认，不要基于别的 commit 改代码。
（本文档第一版基线是 `a392613`，PR #29 合并后已前进 4 个提交。）

### 🔴 哪份文档有效（最容易踩的坑）

| 文档 | 基线 | 是否有效 |
| --- | --- | --- |
| `缺口评估报告-对照demo基准.md`（库外） | `4d95bc8` | ✅ **当前缺口的权威清单**，开工先读它 |
| `docs/fixes-20-25-27.md` | `4d95bc8` | ✅ 上游自己的修复说明，划清了边界 |
| `docs/工程核验与修复计划_v2.md` | `a392613` | ⚠️ 计划仍有效，但**批次 A 已被 PR #29 完成** |
| `HANDOVER.md`（Patch A–K） | `1355b1a` | ⚠️ **历史文档，行号已全部失效** |
| `LOCAL-PATCHES.md` | 滚动 | ✅ 有效，记录本地补丁（含 Patch L） |
| `UPSTREAM-ISSUE-DRAFT.md` | `1355b1a` | ⚠️ 历史草稿 |
| `PR15-合并验收记录.md` | `1355b1a` | ⚠️ 历史记录 |

`HANDOVER.md` 里的 Patch A–K（路径权威、demo 语料、输出契约、检索预算等）
**主体已随 PR #15 / #17 合并进 main**。它的价值是「问题史与踩坑记录」，
**不要拿它的行号去定位当前代码** —— 你会改错地方。

---

## §3 环境与命令

### Python

```bash
PY="C:/Users/zooma/.workbuddy-ai/binaries/python/envs/default/Scripts/python.exe"
"$PY" -V     # Python 3.13.14
```

已装：`jinja2` ✅、`pytest` ✅、`jsonschema` ✅
（注意 `requirements.txt` 只声明了 `jinja2>=3.0.0` 和 `pytest>=8.0.0`，
`jsonschema` 是本机额外装的，见 §7 问题 2。）

### 跑测试的正确姿势

**不要跑全量 `pytest tests -q`** —— 实测会挂在依赖网络/超时的用例上（12 分钟无输出）。

**必须给一个全新的空 temproot**，否则 pytest 收尾清理历史临时目录会触发宿主删除守卫，
测试会被掐断、统计行永远打不出来：

```bash
cd "D:/OLD_VAULT-整理后-20260919/tools/personal-kb-steward"
mkdir -p "D:/OLD_VAULT-整理后-20260919/.pytest-tmp"      # 🔴 必须先建！

# PR #29 的三个修复（应 76 passed）
PYTEST_DEBUG_TEMPROOT="D:/OLD_VAULT-整理后-20260919/.pytest-tmp" \
  "$PY" -m pytest -q tests/test_render_fail_closed.py \
    tests/test_signal_safety.py tests/test_review_run_scope.py

# PR #29 集成测试（应 9 passed）
PYTEST_DEBUG_TEMPROOT="D:/OLD_VAULT-整理后-20260919/.pytest-tmp" \
  "$PY" -m pytest -q tests/test_priority_fixes_integration.py

# 写入路径相关子集
PYTEST_DEBUG_TEMPROOT="D:/OLD_VAULT-整理后-20260919/.pytest-tmp" \
  "$PY" -m pytest -q tests/test_apply_plan.py tests/test_object_plans.py \
    tests/test_pr15_contracts.py tests/test_reconcile.py \
    tests/test_seed_quality_outputs.py tests/test_runtime_boundaries.py
```

> 🔴 **`PYTEST_DEBUG_TEMPROOT` 指向的目录必须已存在。**
> pytest 内部用 `mkdir(parents=False)`，父目录不存在会直接 `FileNotFoundError`，
> 表现为**整文件 17 个 error**（不是断言失败）。评估时第一遍就踩了这个。

跑相关子集约 7 秒。写入路径子集当前结果应为
`1 failed, 91 passed, 9 subtests passed`，那个 failed 见 §10 已知陷阱。

### 命令行入口

```bash
"$PY" scripts/validate_config.py     # 先验证配置
"$PY" scripts/personal_kb_steward.py status
"$PY" scripts/personal_kb_steward.py lint      # 只读
"$PY" scripts/personal_kb_steward.py task "…"  # 干跑，出 plan
```

---

## §4 当前状态快照

### 同步状态（2026-09-20 23:50 实测）

```
本地 HEAD           = 4d95bc8
origin/main         = 4d95bc8   ← git ls-remote 直接查询
本地 vs 远端        = 0 / 0（无落后、无领先）
```

**上游已合并 PR #29 `fix/priority-20-25-27`**（4 个提交），修掉了 v2 的「只能修三条」：
#27 渲染 fail-closed、#25 信号安全边界、#20 run 级审核。

所有 issue（#16–#27）仍为 **OPEN**（未逐条关闭）。PR #28（参考卡）仍 **OPEN**。

### 未提交改动（只有这些）

Patch L 已提交到分支 **`local-patch-l-handover`**（commit `eb81d42`），
main 工作区现在是**干净的**，只剩未跟踪文件：

| 文件 | 状态 | 内容 |
| --- | --- | --- |
| `PR15-合并验收记录.md` | ?? | 未跟踪 |
| `UPSTREAM-ISSUE-DRAFT.md` | ?? | 未跟踪 |
| `docs/工程核验与修复计划_v2.md` | ?? | 未跟踪 —— 核验计划书 |
| `docs/HANDOVER-第三方agent修复工作包.md` | ?? | 未跟踪 —— 本文件 |
| `pr-artifacts/` | ?? | 未跟踪 —— 本地补丁与测试证据 |
| `inputs/上游反馈全集.md` | ?? | 本次补齐，见 §9 |

> **Patch L 的去向**：它在 `local-patch-l-handover` 分支上，**不在 main**。
> 它是对 #18 的本地绕过（写探针只写不删）。上游未修 #18，
> 所以**若你要在本机跑真库批次，需要先把它合回来**；但注意 §7 问题 1 的语义缺陷。

### 产物现状（真库 `_kb-steward/`）

| 目录 | md 数 |
| --- | --- |
| `seeds/` | **148**（= 新代 101 + 旧代 47） |
| `sources/` | **132** |
| `concepts/` `cases/` `topics/` `material-packs/` | 各 1 |
| `evidence/` `gaps/` `claim-checks/` `project-reviews/` `reports/` `work-memory/` | 0 |

**分代判据**：文件名带 `-YYYYMMDD-HHMMSS-######` 后缀的 = 旧代（PR #17 修复前生成）。
新代 101 张日报模板残留 0%、可复现 100/101；旧代 47 张模板残留 100%、可复现仅 4/47。
**统计时按目录统计必然混算**，必须按文件名后缀分代。

---

## §5 🔴 红线（违反会造成不可逆损失）

1. **不删真库数据**。清理一律进 `.p0-quarantine/`（点前缀，Obsidian 忽略）。
   绝不 `rm -rf` 真库任何目录。
2. **不批量给 `raw/剪藏/` 加 `status: seed/evergreen`** —— 维护者明确禁止过。
3. **改 frontmatter 不断链，改文件名必断链**。默认不动文件名。
   确需改名：`改名 → 全库 linkcheck → 修所有入链`（**MOC 最容易漏**）。
4. **正则必须容忍 `\r`**（真库有 182 篇 CRLF）。漏了会静默算出 0。
5. **断链检测必须把附件纳入解析目标**：口径 = 所有 `.md` 的 stem ∪ **全库所有文件的 basename**。
   只索引 `.md` 会把 `![[xxx.pdf]]` 全报成断链（曾因此报出 33 条假断链）。
6. **分支名不能含 `/`** —— `git worktree add -b docs/xxx` 会 `fatal: invalid reference`。
7. **`python -c "..."` 双引号包裹时，文本里的反引号会被 bash 当命令替换执行**。
   带反引号的文本一律用 Write 工具写文件，或 heredoc 加 `<<'EOF'`。
8. **Edit/Write 报「成功」不等于落盘** —— 已遇到 2 次「工具回 success 但内容没变」。
   改完关键内容必须 `grep` 复查。
9. **`git fetch` 那行 ref 更新输出可能是陈旧的** —— 远端状态以 `rev-parse` / `ls-remote` 为准。
10. **`scripts/personal_kb_steward.py` 有 1700 行硬上限**（runner 会拒绝超限文件）。
    加代码请放 `core/`，不要在 runner 里堆。
11. **不要读、不要输出 `.env` / `config.json` 里的凭据**。只报「文件名 + 替换处数」。
12. **报数必须注明口径与分代**。「跑通了」不等于「算对了」——
    本项目累计踩过 7 次「正则/口径静默失效、结论正好相反」。
    跑完必须拿**已知答案的小样**验一遍。

---

## §6 修复清单

> 详细内容**以 `docs/工程核验与修复计划_v2.md` 第三部分为准**，这里只给执行顺序与验收命令。

### 🔴 先看完成状态（PR #29 之后）

| 批次 | 状态 | 说明 |
| --- | --- | --- |
| **A** 渲染 fail-closed | ✅ **已完成** | PR #29 修了 #27。**不要重做** |
| **B** 输入/产物契约 | ❌ 未做 | schema 三连（E13/E14/E15）仍在 |
| **C** 执行控制 | 🟡 **部分完成** | #20 run 级审核已做；**#18 探针、#19 Windows 未做** |
| **D** 种子信号 | 🟡 **部分完成** | #25 安全边界已做；**信号语义分型（#24）、related（#23）未做** |
| **E** 跨批提升 | ❌ 未做 | `candidate_promotion: []` 仍为空 |
| **F** 存量修补 | ❌ 未做 | **sources 132 篇仍 0 个 `##` 小节** |

**剩余缺口按优先级的完整清单 → `缺口评估报告-对照demo基准.md` §6。**

---

### 批次 A · 止损：先禁止生成明知残缺的页面

- **文件**：`core/jinja_renderer.py` + 新增 `tests/test_renderer_dependency_contract.py`
- **改动**：去掉摘要专用 fallback；缺 Jinja2 时**首次渲染明确抛错并保留 ImportError cause**，不返回伪完整页面
- **验收**：
  ```bash
  "$PY" -m pytest -q tests/test_renderer_dependency_contract.py
  ```
  缺依赖抛错 / 带哨兵字段的 source-note 保留字段及 5 个小节 / 模板必需字段缺失仍抛错
- **补做**：v2 未执行「依赖缺失时不推进 processed-index」的端到端断言，**这是你的活**

### 批次 B · 机器可检查的输入/产物契约

- **文件**：`skills/*/schema.json`、`core/skill_executor.py`、`core/skill_runtime.py`、
  `core/json_contract.py`、`core/validator.py`、`core/vault.py`、source renderer、CLI page gate、状态文档
- **要点**：按 skill 校验 structured item；source-note 增明确 schema 与
  `analysis_mode/render_mode/quality_flags`；门禁不再 grep 自然语言文案；
  损坏输入记为可审核的数据质量问题；文档区分 `writes_by_default` / `conditional_outputs` / `follow_up_outputs`
- **验收**：新增 `tests/test_output_contracts.py`、`tests/test_source_quality_contract.py`
- ⚠️ **顺序**：必须先对齐 schema，**再**打开强校验。一上来启用旧 schema 会拒绝当前所有 candidate

### 批次 C · 执行范围、探测与失败恢复可控

- **文件**：`scripts/personal_kb_steward.py`、`core/review_queue.py`、`core/run_records.py`、
  `core/output_paths.py`、`core/safety.py`、CLI 文档、Windows 测试
- **要点**：`review apply-approved` 加 `--run-id`；每 run 单独输出选中计划与写入数；
  错误事件结构化记录异常链；**preflight 按父目录去重探针**；#19 先加原生 Windows 测试
- **验收**：`tests/test_review_run_scope.py`、`tests/test_preflight_probe_policy.py`、`tests/test_failure_diagnostics.py`
- ⚠️ **与 Patch L 冲突，见 §7 问题 1 —— 开工前先看**

### 批次 D · 改进可生长信息（与 C 并行）

- **文件**：`core/seed_quality.py`、`core/clustering.py`、`core/seed_updates.py`、
  seed executor/renderer/schema、检索与链接验证层 + 新增有界信号分类/secret-screening 模块
- **要点**：围栏状态保存 marker 字符与长度；增加 signal kind（assertion/question/procedure/reference）；
  提炼 statement 必须带 exact quote + source + hash + span；秘密筛查放在**模型 payload 之前**；
  `growth_directions` 按 stage 给真实动作；related 从配置允许的已知候选集合解析
- **验收**：`tests/test_seed_signal_contract.py`、`tests/test_seed_growth_links.py`
- **全部不读真实私库、不使用真实秘密**

### 批次 E · 跨批提升与真实阶段账本

- **文件**：`core/initializer.py`、`core/finalizer.py`、`core/layout.py`、workflows/config 文档
- **要点**：拒绝 `max_sources < min_sources` 等不可满足规则；每个声明阶段记录
  executed/skipped/blocked/error；跨批提升以**已落盘且质量合格**的 source-note 为基础，复用 finalizer
- **验收**：`tests/test_cross_batch_promotion.py`、`tests/test_stage_ledger.py`
- ⚠️ 必须分开覆盖「有 quicknote 但 executor 返回零页」与「无 quicknote」两种分支

### 批次 F · 最后修存量（不清空索引、不按文件名猜版本）

- **文件**：`core/state.py`、`core/seed_updates.py`、plan/update/reconcile 通路 + 新增显式 reprocess/migrate 命令
- **要点**：以 `generator_version` + 来源快照 + 派生页特征生成候选迁移清单；
  legacy 无版本**仅列为待核验**；修补字段而非整库重写；执行前核对 base hash/revision，冲突即停
- **验收**：`tests/test_reprocess_migration.py`

---

## §7 🔴 需要先裁定的 3 个问题

这三件事**不是你能单方面决定的**，开工前请向维护者确认；无法确认时按「保守选项」执行。

### 问题 1 · 写探针策略冲突（**最高优先级，批次 C 会直接撞上**）

| 方案 | 行为 | 问题 |
| --- | --- | --- |
| **上游现状** | 每页 `create + delete` `.write-check-{run_id}.tmp` | N 页 = N 次删除 → 长批次必被宿主守卫拦死（第 5–8 轮） |
| **本地 Patch L** | 固定名 `.write-check.tmp`，**存在即跳过**，写完不删 | 删除数降到 0，但**「历史成功不能证明当前可写」** —— 权限变化会漏检 |
| **v2 批次 C 第 4 条** | **按父目录去重探针**，每次执行重新判断 | 比上游好（M 目录 vs N 页），但 M 个目录仍会产生 M 次删除 |

> **现状**：PR #29 **没有修 #18**（上游明示），Patch L 已移到分支 `local-patch-l-handover`
> （commit `eb81d42`，**不在 main**）。若要在本机跑真库批次，需先把它合回来；
> 但请注意它的语义缺陷（存在即跳过 = 权限变化漏检）。

**v2 在第「不建议采纳」第 7 条明确反对 Patch L 的做法。**
**保守选项**：实现 v2 的「按父目录去重」，但**每次都写**（不判断 `exists`），
写完的清理策略由维护者定 —— 若宿主守卫是硬约束，可保留残留文件（最多 2 个 2 字节隐藏文件），
并在收尾命令里一次性清掉。

> 相关：宿主删除守卫 `[safe-delete]` 额度 **50 次/会话回合**、`scope: "turn"`，
> 额度按**会话回合**累计（不按进程）。拆进程 / 每轮清理 / 关沙箱**三种绕行全部实测无效**，
> 且守卫会把退出码强行改写成 1。**跑测试与跑批次不要放在同一回合**，否则互相抢额度。

### 问题 2 · `jsonschema` 要不要进 `requirements.txt`

v2 批次 B 提到「仅选用 JSON Schema 校验器时新增运行依赖」。
本机已装 `jsonschema`，但 `requirements.txt` 里没有。
**这是接口决策**：一旦代码 import 它，所有部署都必须补装。请维护者确认。

### 问题 3 · #26「原子 seed 模式」是否立项

v2 明确写了：**「原子 seed 模式须维护者明确批准再立项，不借修 bug 强行改产品。」**
现有 `SKILL.md` 明写的是**主题型 seed**。
维护者确实提过想要「一个念头发芽」的原子卡形态，但那是**产品变更**，不是缺陷修复。
**在你得到明确批准前，批次 D/E 只做「生长方向 + 关联候选」的机制改进，不改 seed 的定义。**

---

## §8 交付要求

1. **按批次提交**，每批一个 commit（或按需拆分），提交信息写清对应 issue 号。
2. **必须附测试证据**：新增测试文件 + 实际运行输出。v2 里每条「验收」都是门槛，不是建议。
3. **走分支 + PR**，分支名**不含 `/`**（用 `fix-render-fail-closed` 这类）。
4. **PR 描述里逐条回应 v2 的「回归风险」**那一节 —— 说明你的实现怎么规避。
5. **不要修改 `docs/工程核验与修复计划_v2.md`** —— 它是输入，不是产出。
   你的结论写在 PR 里。
6. **不要顺手清理** §4 列出的未跟踪文件（`pr-artifacts/`、`PR15-合并验收记录.md` 等）。

---

## §9 缺失材料与补齐情况

### 已补齐 ✅

`inputs/上游反馈全集.md` —— v2 引用的原始附件。已从本地
`D:\OLD_VAULT-整理后-20260919\pr-artifacts\上游反馈全集.md` 复制过来，
**SHA-256 与 v2 声明的一致**：

```
00032435026dacb2f3681b7a790258e7b9c40e1ebcaecefe210426c4520c1edd
```

（11 个 issue 正文 + 5 个评论块 + 1 个 PR 正文。v2 里的「附件 Lx–Ly」行号即指此文件。）

### 不在本地 ❌

| 材料 | 位置 | 影响 |
| --- | --- | --- |
| `0001-fail-closed-rendering.patch` | 第三方核验 agent 的容器 | 批次 A 的参考补丁。**可自行重写**，v2 已把改动描述清楚 |
| `evidence/*.json`（results / blob-hashes / signal-order / attachment-manifest） | 同上 | 核验证据，修复不需要 |
| `audit_repro.py`、`audit_feedback_manifest.py`、`check_signal_order.py` | 同上 | 核验脚本，修复不需要 |
| `种子卡质量复盘报告.md` | `D:\OLD_VAULT-整理后-20260919\` | 依赖未提供材料，但**本地有**，见 §11 |

### 需要维护者裁定

- 是否重跑 `sources/` 的 132 篇（批次 F 的存量修补涉及）
- 旧代 47 张 seed 卡是否进入迁移清单

---

## §10 已知陷阱

| 陷阱 | 症状 | 处置 |
| --- | --- | --- |
| 宿主删除守卫 | 报 `[safe-delete][SAFE_DELETE_BULK_CONFIRM_REQUIRED]`，且**退出码被改写成 1** | 见 §7 问题 1；不要试图绕过 |
| pytest 收尾回收临时目录 | 一次 `pytest` 就触发 `count:51` 被拦，统计行打不出来 | 给全新空 `PYTEST_DEBUG_TEMPROOT` |
| 全量 pytest | 12 分钟无输出，挂在网络/超时用例 | 只跑相关子集 |
| `test_configured_auxiliary_directory_symlink_is_rejected_before_apply` | 本机固定 failed | **已 A/B 对照证明是先于 Patch L 存在的上游/Windows 语义差异**，不是回归 |
| 分支名含 `/` | `fatal: invalid reference` | 不用斜杠 |
| `git stash` | 本仓库危险 | 用 worktree 或先 commit |
| 跨测试污染 | 模块级可变缓存导致顺序相关失败 | 改过 3 次，注意别引入 |
| runner 行数上限 | 1700 行 | 加代码放 `core/` |

---

## §11 材料索引

### 必读（按顺序）

1. `docs/工程核验与修复计划_v2.md` —— **修复计划书（357 行）**
2. `inputs/上游反馈全集.md` —— 原始反馈（11 issue + 5 评论 + PR #28）
3. 本文件

### 背景参考

| 材料 | 位置 | 用途 |
| --- | --- | --- |
| `LOCAL-PATCHES.md` | 仓库根 | 本地补丁记录（含 Patch L） |
| `HANDOVER.md` | 仓库根 | Patch A–K 的问题史与踩坑（**基线已过期，只看故事不看行号**） |
| `pr-artifacts/local-patches.patch` | 仓库内 | Patch A–K 完整补丁（194KB） |
| `种子卡质量复盘报告.md` | 库外 `D:\OLD_VAULT-整理后-20260919\` | #24/#26 的原始统计来源 |
| `sources生成质量复盘报告.md` | 同上 | #27 的原始统计来源 |
| `personal-kb-steward-部署说明.md` | 同上 | #18/#21 的部署与宿主信息 |
| `上游优化建议.md` | 同上 | E13–E15 / F16 的细节 |
| `docs/status-stage-model.md` | 仓库内 | status/stage 迁移规则（与 schema 有冲突，见 v2 G4） |

### 上游地址

- 仓库：https://github.com/huangzuomin/personal-kb-steward （PUBLIC）
- PR #28（参考卡，OPEN，维护者正在 review）：https://github.com/huangzuomin/personal-kb-steward/pull/28

---

## 附 · 交接自检清单

开工前逐条打勾：

- [ ] `git rev-parse HEAD` == `a39261384433d6b2ba35a323653733ab4ae33f57`
- [ ] 读完 `docs/工程核验与修复计划_v2.md` 的**第三部分（修复计划）与第五部分（不建议采纳）**
- [ ] 读过 §5 十二条红线
- [ ] 对 §7 三个问题拿到维护者裁定（至少问题 1）
- [ ] 确认 `PYTEST_DEBUG_TEMPROOT` 用法
- [ ] 知道「跑测试」与「跑批次」不能同回合
