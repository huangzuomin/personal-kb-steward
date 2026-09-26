"""Regenerate the synthetic source-quality fixtures with exact raw bytes."""
from pathlib import Path

root = Path(__file__).resolve().parent


def w(name: str, text: str, bom: bool = True, crlf: bool = True) -> None:
    if crlf:
        text = text.replace("\n", "\r\n")
    data = text.encode("utf-8")
    if bom:
        data = b"\xef\xbb\xbf" + data
    (root / name).write_bytes(data)


filler = "".join(
    f"段落{i}：本节讨论城市交通治理的背景与常规措施，包含大量铺垫内容。\n"
    for i in range(220)
)  # well past 6000 characters
w("long-article.md", f"""---
title: 城市交通治理长文（合成样本）
type: article
---

# 城市交通治理长文（合成样本）

{filler}
关键转折：2025年9月，该市试点线路的准点率从71%提升至89%，这是全文最关键的证据。
结论部分：以上数字由合成数据生成，仅用于测试。
""")

w("dialogue.md", """---
title: 用户与顾问的对话记录（合成样本）
tags: [对话]
---

顾问：您目前的知识库主要堆积在哪类资料？
用户：主要是行业研报和一些会议记录，找不到的时候居多。
顾问：您希望先解决检索还是先解决提炼？
用户：先提炼，最好每篇都能自动变成卡片。
顾问：好的，我建议先做来源卡，再做原子卡。
用户：这个建议我可以接受。
""")

w("ai-synthesis.md", """---
title: AI 生成的行业综述（合成样本）
tags: [AI生成]
---

以下是AI整理的行业综述：本行业2024年市场规模达到480亿元，同比增长23%。
作为AI助手，我建议您重点关注三家头部企业。
该综述未引用任何具体来源，数字为模型生成内容。
""")

w("oral-case.md", """---
title: 内部案例口述记录（合成样本）
tags: [口述]
---

张工口述：我们团队去年尝试过类似流程，据其转述，上线三个月后返工率下降了四成。
这只是单方陈述，没有书面数据支持。
当事人回忆，当时最大的阻力来自排班。
""")

w("unclear.md", "---\ntitle: 短片段\n---\n\n内容太短，无法判断来源类型。\n")

w("bold-dialogue.md", """---
title: 用户与助手的加粗对话记录（合成样本）
tags: [对话]
---

**用户**：帮我把这份报告改成摘要。
**助手**：好的，我建议保留三个要点：范围、数据、风险。
**用户**：数据那部分可以再压缩吗？
**助手**：可以，我建议只留增长率结论，其余删掉。
**用户**：这个建议我接受，就这么改。
""")

w("uncited-report.md", """---
title: 行业观察报告（合成样本）
type: article
---

本报告为合成测试样本。2025年该市场规模增长至520亿元，同比增长18%。
本报告无外部来源，也无任何可回溯的原始出处，数字均为演示用途。
据传头部企业正在扩张，但文中不做任何引用说明。
""")

w("empty.md", "")

(root / "damaged.md").write_bytes(
    "---\ntitle: 损坏样本\n---\n\n正常开头。".encode("utf-8") + b"\xff\xfe broken bytes \x80")

w("repeated.md", """---
title: 重复句样本（合成样本）
---

同一句话被反复出现：该市完成了年度治理目标。同一句话被反复出现：该市完成了年度治理目标。
同一句话被反复出现：该市完成了年度治理目标。另一句补充：后续仍需人工复核数据。
""")

print("fixtures written to", root)
