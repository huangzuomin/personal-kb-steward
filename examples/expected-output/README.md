# Expected Output

课堂演示的最小闭环预期：

1. `整理知识库`：从 quicknote 生成 seed plan，会议记录进入 work-memory 候选。
2. `发现选题`：生成 topic-card 候选计划。
3. `准备写作素材`：生成 evidence/material pack 计划。
4. `检查知识库健康`：输出 health score、P0/P1/P2/P3、断链和来源问题。

默认 dry-run 只写 `.openclaw/plans/`，不会写 mini-vault。

## 参考卡（`cards/`）

上面的清单描述的是**行为**预期；`cards/` 描述的是**产出内容**的预期。

`cards/` 下有 10 张人工示范卡片，全部由 `examples/mini-vault/` 生成，覆盖
`seed-card` / `concept-page` / `case-story` / `source-note` / `topic-page` 五种类型，
可作为「产出正确时长什么样」的对照基线。

详见 [`cards/README.md`](cards/README.md)，其中包含：
- 五条基线主张（模板骨架不变、改的是填充语义）
- 各类型的骨架来源（哪些沿用仓库既有，哪些是新提出的）
- 三条可直接转成回归断言的检查
- 顺带发现的四个缺陷（`raw/industry_report.md` 编码损坏、`schema.json` 从未被代码引用、
  真实产物 30% 超出自己的 schema、`stage` 存在两套冲突词汇表）
