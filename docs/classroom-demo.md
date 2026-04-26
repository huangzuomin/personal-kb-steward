# Classroom Demo

目标：10 分钟演示个人知识库如何从碎片进入“选题与素材准备”闭环。

## 准备

```powershell
python scripts\init_config.py --kb examples\mini-vault
python scripts\validate_config.py
python scripts\personal_kb_steward.py status
```

## 演示步骤

1. 整理知识库：

```powershell
python scripts\personal_kb_steward.py plan "整理知识库"
```

观察点：

- 默认 dry-run。
- plan 写入 `.openclaw/plans/`。
- raw 长文不会默认进入 seed。

2. 沉淀工作记忆：

```powershell
python scripts\personal_kb_steward.py plan "沉淀工作记忆"
```

观察点：

- 会议记录会被识别为 work-memory 候选。
- 缺日期或缺行动项会进入 manual review。

3. 发现选题：

```powershell
python scripts\personal_kb_steward.py plan "发现选题"
```

观察点：

- 用户入口是“发现选题”，内部 primary skill 是 `topic-insight-miner`。

4. 准备写作素材：

```powershell
python scripts\personal_kb_steward.py plan "准备写作素材：地方媒体AI转型"
```

观察点：

- 默认仍然只生成 plan。
- 写入必须显式 `--apply`。

5. 检查健康：

```powershell
python scripts\personal_kb_steward.py task "检查知识库健康"
python scripts\personal_kb_steward.py review
```

观察点：

- healthcheck 会输出 P0/P1/P2/P3 风险。
- 高风险修复不自动执行。

## 可选 apply

课堂演示建议先不执行 `--apply`。若需要展示写入，建议只对 mini-vault 执行：

```powershell
python scripts\personal_kb_steward.py task --apply "整理知识库"
python scripts\personal_kb_steward.py processed
```

不要在真实知识库上第一次演示时直接 apply。
