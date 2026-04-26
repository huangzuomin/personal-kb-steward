---
title: "OpenAI's Deep Research: A Guide With Practical Examples"
source: "https://www.datacamp.com/blog/deep-research-openai"
author:
  - "[[Alex Olteanu]]"
published: 2025-02-05
created: 2025-03-02
description: "Learn about OpenAI's new Deep Research tool, which can perform in-depth, multi-step research."
tags:
  - "clippings"
---
OpenAI 刚刚发布了Deep Research ，这是一款由即将推出的[o3 模型](https://www.datacamp.com/blog/o3-openai)版本驱动的 AI 代理。它旨在浏览网页、分析多种来源并综合大量信息。

  
您可能会想：ChatGPT 不是已经这样做了吗？

  
与生成快速响应的常规 ChatGPT 会话不同，深度研究可以进行多步骤调查、参考多个来源并生成结构化报告。

  
例如，如果您曾经研究过要购买的最佳汽车（比较评论、权衡成本等），您就会知道找到可靠的信息需要花费时间和大量的互联网浏览。深度研究正是为这类工作而创建的。

  
我测试过深度研究，既惊讶又失望。它显示出巨大的潜力，但也会产生错误的事实和推论。在这篇博客中，我将扮演您的人工代理，总结您需要了解的有关深度研究的所有信息。我将带您了解实际示例，分享提示技巧，并向您展示深度研究的优势所在——以及您需要格外小心的地方。

##   
OpenAI 的深度研究是什么？

  
OpenAI 的 Deep Research 是一款由人工智能驱动的代理，旨在对互联网进行深入、多步骤的研究。与提供快速响应的标准 ChatGPT 浏览功能不同，Deep Research 可以自主查找、分析和综合来自数百个在线来源的信息。

![OpenAI's DeepResearch can be access from the chat](https://media.datacamp.com/cms/ad_4nxdmqizgrdfu6mlvgtvh8pjsqsl5bzxe-bwc43dmey6rtuyz8-v3xll8wm8fquy2150naufkvfzmkxna_9eje34bavyulpjxd5z-e0q4jybtbu3_cw_oc76_0nqe--sklrnkwwl0iw.png)

  
深度研究专为需要全面、可靠研究的任何人而设计，包括：

- 需要引用充分、结构清晰的报告的金融、科学、政策和工程专业人士
- 进行竞争分析或趋势预测的商业战略家
- 研究人员和学生从多个来源收集信息
- 做出高风险购买决策的购物者和消费者（例如汽车、家电、房地产）
- 需要经过事实核查、多来源见解的作家、记者和分析师

  
本质上，如果一项任务涉及浏览多个来源、交叉引用数据以及将信息综合成有用的格式，那么深度研究就是完成这项工作的工具。

##   
深度研究如何进行？

  
在即将推出的 o3 模型版本的支持下，Deep Research 以 OpenAI 在推理模型方面的进步为基础，但专门针对网页浏览和真实世界数据分析进行了优化。

  
为了实现这一目标，OpenAI 使用[强化学习](https://www.datacamp.com/tracks/reinforcement-learning)对 Deep Research 进行训练，让其在现实世界的浏览和推理任务中进行训练。这使得模型能够遵循迭代的、循序渐进的研究过程，从而提高其将复杂主题综合成结构化报告的能力。

## 深度研究基准

### 人类的最后考试

  
[人类的最后考试](https://lastexam.ai/)是一项新发布的基准，旨在测试人工智能在 100 多个学科（从语言学和火箭科学到生态学和数学）上的专家级多项选择题和简答题。这项评估衡量人工智能跨学科推理和在需要时寻找专业知识的能力——这是研究型模型的关键技能。

  
Deep Research 的准确率达到了创纪录的 26.6%，远远超过了之前的模型，包括 OpenAI 自己的 o1（9.1%）、DeepSeek-R1（9.4%）和 Claude 3.5 Sonnet（4.3%）。值得注意的是，与 OpenAI 的 o1 相比，最大的改进出现在化学、人文和社会科学以及数学领域，Deep Research 在这些领域展示了其分解复杂问题和检索权威信息的能力。

| Model | 准确性 （％） |
| --- | --- |
| GPT-4o | 3.3 |
| 克劳德 3.5 十四行诗 | 4.3 |
| 双子座思维 | 6.2 |
| OpenAI o1 | 9.1 |
| DeepSeek-R1\* | 9.4 |
| OpenAI o3-mini（高）\* | 13.0 |
| **   OpenAI Deep Research（带浏览+Python工具）** | 26.6 |

  
\* 由于模型不是多模式的，因此在考试的纯文本子集上进行测试。资料来源： [OpenAI](https://openai.com/index/introducing-deep-research/)

### 盖亚

  
GAIA（通用人工智能代理基准）评估人工智能系统处理现实世界问题的能力，需要结合推理、网页浏览、多模式流畅性和工具使用熟练程度。

  
Deep Research 创下了新的最先进 (SOTA) 记录，在外部[GAIA 排行榜上](https://huggingface.co/spaces/gaia-benchmark/leaderboard)名列前茅，在所有难度级别上均表现出色。该模型在需要复杂、多步骤研究和综合的 3 级任务中表现出特别高的准确性。

| GAIA 评估 | 1级 | 2 级 | 3 级 | 平均的 |
| --- | --- | --- | --- | --- |
| 上一个 SOTA | 67.92% | 67.44% | 42.31% | 63.64% |
| 深入研究（pass@1） | 74.29% | 69.06% | 47.6% | 67.36% |
| 深入研究（cons@64） | 78.66% | 73.21% | 58.03% | 72.57% |

  
来源： [OpenAI](https://openai.com/index/introducing-deep-research/)

  
Deep Research 的高pass@1 分数表明，即使是第一次尝试回答 GAIA 问题，其准确率也高于之前的模型。cons @64 分数（通过多次响应尝试来衡量性能）进一步凸显了其根据新信息自我纠正和改进答案的能力。

### 内部评估

  
OpenAI 还进行了内部评估，其中 Deep Research 由领域专家在专家级任务上进行评分。我发现内部评估非常有趣！

  
下图显示，随着模型调用更多工具，其通过率会提高。这凸显了让模型反复浏览和分析信息的重要性——给模型更多时间思考可以带来更好的结果。

![pass rate vs max tool calls graph for deep research from openai](https://media.datacamp.com/cms/ad_4nxcfusmychmrzupeplnb6sultgjmaonhot6gcnytv_hexuigoqnjljcloeygw5bbx8kxal82asltfzht_svw_plsogvpeta37zc_jrtclkhcqe-ldvlklqbur9bumtl3xlzgynml.png)

  
来源： [OpenAI](https://openai.com/index/introducing-deep-research/)

  
让我们看看另一张图表——见下文。深度研究在经济价值估计较低的任务上表现最佳，随着任务的潜在财务影响增加，准确率会下降。这表明，经济价值更高的任务往往更复杂，或依赖于网络上无法广泛获取的专有知识。

![pass rate vs estimated economic value graph for openai's deep research](https://media.datacamp.com/cms/ad_4nxemhegaaae5hlndr9v82pxh_dzoq6nby1tq7nsopq49b9dnldpq6lps0ivaemhlym8kcobpxlobk2qu4rwkuielhg1bpq_ycc9z5enmkbpanpgfqspw78ydetp0zmbuobxtustecg.png)

  
来源： [OpenAI](https://openai.com/index/introducing-deep-research/)

  
下图对比了通过率与人类完成每项任务所需的估计小时数。该模型在人类需要 1-3 小时才能完成的任务上表现最佳，但性能不会随着时间的推移而持续下降——这表明人工智能认为困难的事情并不总是与人类认为耗时的事情一致。

![](https://media.datacamp.com/cms/ad_4nxez6lilgu893fobl6vxwwochkv8kvwfdmhlnp4ntbnm6mn2jqppuiraebwmn5hfax7jgwwhnukm-g13_rt0zck-ioylw_baizcnzalqa79gijiqfrqqmmcnuezq4bcliuse5-g_kq.png)

  
来源： [OpenAI](https://openai.com/index/introducing-deep-research/)

##   
如何进行深度研究：实例

  
在发表本文时，深度研究仅对 Pro 用户开放，每月查询次数限制为 100 次，但 OpenAI 计划很快将访问权限扩展到 Plus、Team 和 Enterprise 用户。

  
我认为，深度研究仍处于早期阶段。虽然它前景广阔，但下面的第一个例子凸显了它的许多问题。然而，第二个例子展示了它巨大的潜力。

### 示例 1：人工智能生态系统

  
我一直努力对不同公司的 AI 生态系统有一个全面的了解。以 Google 为例，他们有 Gemini 2.0 Flash、Imagen 3、Veo 2、Project Mariner、Project Astra……我还缺少什么呢？为了最终获得一个清晰的概述，我向 OpenAI 的 Deep Research 提出了这个请求。

![Example of chatting with OpenAI's Deep Research](https://media.datacamp.com/cms/ad_4nxczjxrp1lwqp1ptoy9us48lejk8_06skva3qs-hsyg4if1-dllp69md9ia8ninxsicv4qkgwtt3owlve6gx-g4uh-mvkca9ey4yj_zcgfapj49ne3qtveux5zzvshqyhfgzgfq_.png) 

  
请注意，模型并没有直接开始研究，而是要求澄清。在我的所有测试中，无论我的第一个提示有多具体，模型总是试图缩小研究范围。在我看来，这很有用，因为我经常认为我的提示清晰而具体，但通常需要一些改进。

  
我回答了模型的问题，然后研究就开始了。浏览器右侧打开了一个面板，实时显示代理的活动和来源：

  
这耗时 11 分钟，模型查阅了 25 个来源。请注意，来源是父网站，模型可以浏览该网站的多个页面 - 对于 25 个来源，平均每个来源 4 个页面，您可以预期模型浏览了大约 100 个网页。

![It took OpenAI's Deep Research 11 minutes to complete the search](https://media.datacamp.com/cms/ad_4nxeriww6oz7ghxcg3mprfjlyqaa1n2eixomiuy2ft4vtjwvsyyzjnmgow-o_klg0khnbairnydk2yjvup5ucr0-isfddfh8e3zg8abs7y4qfsq2r0fawpuklcz3zhthr6juhigcgsw.png)

  
总的来说，我对结果感到失望——你可以[在这里](https://chatgpt.com/share/67a22ada-16b8-8001-bf11-11aa3bf3b846)阅读深度研究的答案。但让我们先从我喜欢的地方开始吧：

- 尽管我没有指定结构，但响应组织良好，各个部分清晰，粗体、字体大小和项目符号使用得当。
- 消息来源的位置很好，紧接着它们所引用的信息出现，而且这个系统使得事实核查变得很容易。
- 报告在细节和篇幅之间取得了很好的平衡——内容不浅显，但也不至于花一个小时读完。如果我需要了解更多信息，可以随时询问更多细节。

  
然而，这个答案存在几个问题，我将重点讨论其中主要的问题：

- 不准确之处：它将 DeepSeek-V3 与[DeepSeek-R1](https://www.datacamp.com/blog/deepseek-r1)混淆了（别忘了，您可以[在这里](https://chatgpt.com/share/67a22ada-16b8-8001-bf11-11aa3bf3b846)自己阅读答案）。
- 过时的信息：尽管我特意要求提供最新报告，但 Deep Research 声称 Meta 的最新型号是 Llama 2，Anthropic 的最新型号是 Claude 2，并提到了有关“代号”为[Sonnet](https://www.datacamp.com/blog/claude-sonnet-anthropic)和 Haiku 的传闻。起初我觉得这很有趣，但后来我想到有多少人可能会轻信这些答案。
- 低及时性依从性：我明确告诉 Deep Research 排除 GPT-4 并专注于最新模型，但它并没有遵循该指令。
- 答案不完整：OpenAI 部分未能提及 o1 等关键模型，而在 Google 部分，则完全省略了 Veo。

  
这些问题使得人们很难相信 OpenAI 的深度研究。我特意在自己熟悉的话题上对其进行了测试，这样我就可以核实答案——但如果我不得不依靠深度研究来研究我完全不了解的话题，该怎么办？

###   
示例 2：常青主题

  
深度研究的问题可能在于它还不太擅长识别最新信息。因此，我决定在一个更常青的话题上测试它——一个不太依赖最新发展的主题。

  
我开的是一辆 2013 年制造的汽车，偶尔会考虑换掉它。但我总是被同一个问题困扰：我应该买新车还是二手车？新车贬值很快，但旧车可能意味着更高的维修成本。我想知道专家对此的看法，所以这是一个绝佳的机会，让我请 Deep Research 浏览各种研究和意见并编写一份报告。

  
在继续之前，让我给你一个提示：在你提示深入研究之前，先用你的常用方法优化你的提示LLM以“你是一名提示工程师。请帮我优化这个提示：（此处输入你的提示）”开头。以下是我用于深度研究的优化提示：

![](https://media.datacamp.com/cms/ad_4nxckzndue52ncmlazqp-kag0ydvbw6tscd3oj9e2vxdedwaz6ershc9itknaukvb4bwvloyycjg1eswnaim1muasfxir4nxas1ujopxsxnxhu_5xnsip_6nmbsuotpoaanzl55zxfw.png)

  
与之前一样，Deep Research 在开始之前会要求澄清，然后在六分钟内完成研究，查阅了 12 个来源的多个网页。您可以[在此处](https://chatgpt.com/share/67a33c48-025c-8001-ac79-305d5d425322)阅读完整报告.

  
这次的报告很好，非常好！

  
我从未想象过你可以从如此多的角度来思考这个问题。信息量之广令人印象深刻，据我估计，深度研究为我节省了 10 多个小时的浏览和研究时间。它包含了学术研究、行业报告、市场趋势分析、保险成本比较等。

  
我不是这个领域的专家，所以我无法完全评估这份报告的准确性。但是，从消费者的角度来看，很多信息都是合乎逻辑的，而且确实很有帮助。我还根据引用的来源核实了一些细节，没有发现任何问题。

  
就像第一个示例一样，深度非常均衡，输出结构也非常出色。我特别喜欢下面的表格——只要看看这些折旧值，你就会明白为什么我会保留我 12 年的混合动力车一段时间。

![example of structured output in openai's deep research](https://media.datacamp.com/cms/ad_4nxci1d8jm_fs7iqoyuhjgamyxvopbts9j__ydpb6awgzu2louu7tf50f3oyglf3yos1nz6fkofeq3ysdjuyemwnkfie8wywwvr7hu3oyz6tygfu-n_3rcxflhonlof7lpdo2rbgy.png)

## 结论

  
OpenAI 的深度研究前景广阔，可以为我们节省大量研究时间。然而，它在提供最新信息方面仍然不可靠，有时会产生错误的事实或有缺陷的推论。

  
我仍然认为深度研究仍处于早期阶段，OpenAI 团队在其[公告文章](https://openai.com/index/introducing-deep-research/)中公开承认了这一点.

  
老实说，我会继续关注深度研究，希望它会变得越来越好。