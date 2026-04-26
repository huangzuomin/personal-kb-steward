---
title: "How to work with AI: Getting the most out of Deep Research"
source: "https://www.operatorshandbook.com/p/how-to-work-with-ai-getting-the-most?utm_source=multiple-personal-recommendations-email&utm_medium=email&triedRedirect=true"
author:
  - "[[Torsten Walbaum]]"
published: 2025-06-24
created: 2025-07-10
description: "A tactical playbook on how to use the most powerful AI feature for operators. In-depth comparison of ChatGPT, Perplexity, Gemini, Claude and Grok"
tags:
  - "clippings"
---
### 关于如何使用最强大的 AI 功能为操作员提供的终极指南

*👋 大家好，我是 [Torsten](https://www.linkedin.com/in/torsten-walbaum/) 。我每周或每两周都会分享一些切实可行的建议，这些建议基于我在 Uber、Meta 和 Rippling 等公司的运营经验，能够帮助你发展职业和业务。*

*如果您喜欢这篇文章，不妨分享给您的朋友或同事* 📩 *；这对我来说意义重大。如果您不喜欢，请随时给我发送 [仇恨邮件](https://www.operatorshandbook.com/p/) 。*

---

ChatGPT Deep Research 的发布对我来说是一个巨大的“顿悟时刻”。作为一名非工程师，这是我第一次看到 AI 端到端地自动化我工作的核心，而这正是我擅长的。

现在我不用再花几个小时手动谷歌搜索并汇总结果，只需几分钟就能得到一份20页的报告。真是令人难以置信。

但就像人工智能发展过程中常见的情况一样，一旦我克服了最初的兴奋，就会发现研究结果往往不够完善。来源可疑、方法论不可靠、内容冗长、格式混乱——凡是你能想到的，我都在深度研究报告中见过。

潜力显而易见，但“麦肯锡按需分析师”的承诺似乎并不完全准确。至少在没有投入精力去理解和解决该工具的弱点的情况下是如此。

在学习的过程中，我在网上寻找指南。但令我惊讶的是，大多数指南都过于笼统，缺乏可操作性。

**所以我决定自己编写人工智能研究代理的终极指南。**

绝非夸大其词——只是我辛辛苦苦总结的经验教训，告诉你什么方法有效，什么方法无效，以及如何获得最佳效果。文中还包含实际案例，方便你直观感受我所建议的最佳实践的效果。

**我们将介绍：**

- 我如何看待 DeepResearch 的 **核心用例** 和 **局限性**
- **哪种 AI 研究工具最适合** 哪种任务（包括 200 美元 ChatGPT Pro 计划的更便宜的替代品）
- 如何编写 **有效的提示** ，每次都能提供一流的输出
- 如何 从最终报告中 获得 **最大价值**

如果你已经关注过《操作手册》一段时间了，你肯定知道它的内容很详细。那就泡杯咖啡，我们一起开始吧☕。

---

*附言：这是关于如何利用 AI 完成 **实际工作** 的新系列文章的第一部分 ；其风格与其他《操作员手册》文章一样，深入且富有策略性。如果您有想让我写的主题， [请告诉我](https://www.operatorshandbook.com/p/) 。*

---

## 我如何看待用于研究的人工智能工具

无论你的工作是什么，AI 研究代理都非常有用。“研究”听起来可能主要与学术界或某些入门级职位相关；但一旦你仔细观察，我敢打赌你会发现你在这方面花费了 **大量** 时间。

例如：

- 作为 *产品经理* ，你正在研究竞争对手的产品
- 作为 *创始人* ，你正在学习销售税、工资单或股权结构表数学
- 如果你在 *BizOps* ，你的整个工作基本上就是每周尽快完成一个新主题，这样你就能产生影响，然后继续做下一件事

AI 研究代理可以帮上忙，甚至更多。而且它们的作用远不止于工作。

根据我的经验，高级用例包括：

![](https://www.operatorshandbook.com/p/%7B%22src%22:%22https://substack-post-media.s3.amazonaws.com/public/images/01bd48e0-0922-49f3-8f91-65e01a061b1c_1831x845.png%22,%22srcNoWatermark%22:null,%22fullscreen%22:null,%22imageSize%22:null,%22height%22:672,%22width%22:1456,%22resizeWidth%22:null,%22bytes%22:424743,%22alt%22:null,%22title%22:null,%22type%22:%22image/png%22,%22href%22:null,%22belowTheFold%22:true,%22topImage%22:false,%22internalRedirect%22:%22https://www.operatorshandbook.com/i/160819332?img=https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F01bd48e0-0922-49f3-8f91-65e01a061b1c_1831x845.png%22,%22isProcessing%22:false,%22align%22:null,%22offset%22:false})

人工智能可以将完成这些任务所需的时间缩短 80% 到 90%。 **但是：不要完全将这些任务外包，并且不进行监督。** 如果你盲目地将人工智能的输出用于任何重要的事情，你肯定会遇到麻烦。

这些 AI 代理，至少在目前的版本中，需要认真的指导才能产生强大的功能。而要扮演关键的“管理者”角色，你需要知道需要注意什么。

以下是需要注意的五个最大问题：

## 问题 1：AI 代理不会询问他们需要的上下文

正如您将在下面的详细比较中看到的，大多数 AI 研究工具不会主动询问上下文，而只会使用您在提示中提供的信息。

就像过于急切的分析师一样，他们直接开始执行，即使他们不知道你实际上想用这份报告做什么。

即使代理确实询问了背景信息（例如因为你告诉他们这样做）：

1. 这些问题并不总是涵盖所有重要方面，并且
2. 如果你的回答不够充分，他们就不会跟进

![](https://substackcdn.com/image/fetch/$s_!U55v!)

**👉 如何处理这种情况：** 主动提供尽可能多的背景信息，说明你的情况和你想要实现的目标，并告诉代理人询问任何仍然缺失的信息

## 问题 2：AI 代理不知道如何正确处理信息来源

我观察到 AI 代理默认处理来源时存在一些主要问题（即除非你告诉他们如何做得更好）：

- ☝ **过度依赖** 个别来源，导致评估出现偏差或视野狭窄
- 🧩 **混合和匹配** 数据源而不强调注意事项，从而创建毫无意义的拼凑分析
- 🗑️ 使用 **低质量来源** （例如来自匿名用户的随机 Reddit 帖子）
- 📆 来源 **过时** （例如，即使在事物快速变化的领域，数据也来自 5 - 10 年前）

如果你不小心，你最终会得到一份看似漂亮但实际上并不牢靠的报告：

![](https://www.operatorshandbook.com/p/%7B%22src%22:%22https://substack-post-media.s3.amazonaws.com/public/images/42a06d22-d8e7-483f-98d0-eeea8b26bf3a_770x978.png%22,%22srcNoWatermark%22:null,%22fullscreen%22:null,%22imageSize%22:null,%22height%22:978,%22width%22:770,%22resizeWidth%22:455,%22bytes%22:163140,%22alt%22:null,%22title%22:null,%22type%22:%22image/png%22,%22href%22:null,%22belowTheFold%22:true,%22topImage%22:false,%22internalRedirect%22:%22https://www.operatorshandbook.com/i/160819332?img=https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F42a06d22-d8e7-483f-98d0-eeea8b26bf3a_770x978.png%22,%22isProcessing%22:false,%22align%22:null,%22offset%22:false})

**👉 如何处理此问题：** 特别是对于数据密集型报告，您必须 1）提供有关优先考虑哪些来源的指导，以及 2）要求了解 *如何* 使用来源。

## 问题 3：AI 代理无法访问大量高质量数据源

深度研究无法访问 **付费来源** 。但是，根据你的研究领域，付费来源往往蕴藏着大量优质数据。

例如，对于 B2B SaaS 中的许多分析，你可能希望利用来自 LinkedIn API 或市场研究公司的数据。目前，要做到这一点，你需要先下载这些数据集，然后将其提供给 AI 访问。

此外，AI 代理显然只能搜索网络上现有的信息。如果你研究的是细微的、小众的话题（例如复杂的法律问题），那就麻烦了。

**👉 如何处理这种情况：** 在这些情况下，最好将深度研究视为一种可以帮助您 **准备专家电话的工具** （这样您就知道要问什么问题），而不是为您提供建议的端到端解决方案。

## 问题四：人工智能代理有时判断力平庸

DeepResearch 报告中的推理质量差异 **很大** ；无论是在不同的查询之间，还是在不同的工具之间（例如 ChatGPT 与 Gemini）。有时我印象深刻，有时我感觉自己正在审查高中实习生的作业。

此外，你会发现研究人员通常只是重复他们发现的观点（例如在博客文章中），而不是真正 *思考* 问题。换句话说，你把判断权外包给了一个随机的在线用户。

![](https://www.operatorshandbook.com/p/%7B%22src%22:%22https://substack-post-media.s3.amazonaws.com/public/images/516400f7-669d-49a3-924d-df7c9c81ca4b_522x851.png%22,%22srcNoWatermark%22:null,%22fullscreen%22:null,%22imageSize%22:null,%22height%22:851,%22width%22:522,%22resizeWidth%22:360,%22bytes%22:164833,%22alt%22:null,%22title%22:null,%22type%22:%22image/png%22,%22href%22:null,%22belowTheFold%22:true,%22topImage%22:false,%22internalRedirect%22:%22https://www.operatorshandbook.com/i/160819332?img=https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F516400f7-669d-49a3-924d-df7c9c81ca4b_522x851.png%22,%22isProcessing%22:false,%22align%22:null,%22offset%22:false})

**👉 如何处理此问题：**

- 最重要的是，选择最强大的工具（详见下文）
- 确保您提前审查研究计划并提供有关方法的详细说明
- 对初稿给出批判性反馈，以解决任何明显的问题（即使犯了错误，AI 也总是态度良好，乐于解决问题）

## 问题 #5：默认输出格式通常没什么用

默认情况下，您从 ChatGPT 和 Gemini 获得的研究报告都是大量难以理解的文本。

当然，你可以获得人工智能摘要；但在某些情况下，你 ***确实*** 希望深入了解。你只是希望信息以一种易于理解的方式呈现。

**👉 如何处理此问题：** 提供有关报告结构和格式的说明（例如，添加“TL;DR”，使用概览表等）。

---

好了，抱怨够了；让我们来谈谈您可以做哪些具体的事情来充分利用这些工具。

1. 首先，我们将深入研究不同的工具及其优缺点，以便您知道哪一个最适合您的用例
2. 然后，我们将介绍可操作的最佳实践，您可以使用它们 **每次获得高质量的输出**

---

## 哪种 AI 研究工具最好？

你可能听说过 [ChatGPT Deep Research](https://openai.com/index/introducing-deep-research/) ，但它并非唯一的工具。过去几个月，许多其他公司也发布了自己的版本。

最大的问题是：

- [双子座深度研究](https://gemini.google/overview/deep-research/)
- [困惑度研究](https://www.perplexity.ai/hub/blog/introducing-perplexity-deep-research)
- [Grok 深度搜索](https://x.ai/news/grok-3)
- [克劳德研究](https://www.anthropic.com/news/research)

乍一看，它们非常相似。你在聊天窗口中输入一个研究提示，5 到 30 分钟后，你就会得到一份详细的多页报告。

然而，细节决定成败。我已经在数十个用例中对这些工具进行了广泛的测试， 它们在研究方法和输出质量方面 存在 ***巨大*** 差异：

![](https://www.operatorshandbook.com/p/%7B%22src%22:%22https://substack-post-media.s3.amazonaws.com/public/images/02fb63f0-846e-408b-928d-546679e97f93_1500x1190.png%22,%22srcNoWatermark%22:null,%22fullscreen%22:null,%22imageSize%22:null,%22height%22:1155,%22width%22:1456,%22resizeWidth%22:null,%22bytes%22:411004,%22alt%22:null,%22title%22:null,%22type%22:%22image/png%22,%22href%22:null,%22belowTheFold%22:true,%22topImage%22:false,%22internalRedirect%22:%22https://www.operatorshandbook.com/i/160819332?img=https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F02fb63f0-846e-408b-928d-546679e97f93_1500x1190.png%22,%22isProcessing%22:false,%22align%22:null,%22offset%22:false})

***注意** ：我这里比较的是基础版，以便您了解免费用户的实际体验。文章最后会另设章节，介绍高级版的性能差异。*

---

---

## ⭐ 总体推荐

**TL;DR：**

- **ChatGPT Deep Research** 总体来说仍然是真正 ***深入研究*** 的最佳工具 目前还没有其他工具能够达到这样的深度和严谨性
- **Perplexity** 非常适合对新主题进行简短、结构良好的概述

ChatGPT 的两个最大弱点是 1）它如何选择来源以及 2）它创建了大量格式不佳的文本。

不过， 这两种都是 **默认行为，可以** 通过正确的提示进行调整；我们将在下一节中讨论。根据我的经验，可以归结为以下几点：

> *您可以要求 ChatGPT 使用不同的来源或使报告变得漂亮，但您无法真正促使其他工具变得更加 **严谨。***

然而，200 美元的专业版对个人用户来说贵得离谱，免费版和 Plus 版的使用限制也很低。因此，你可能需要根据这里讨论的利弊，选择其他工具作为你的“日常工具”，并将 ChatGPT 深度研究“留到”最重要的任务上使用。

![YARN | I've been saving it for a special occasion. I think this is it. |  One Crazy Summer (1986) | Video gifs by quotes | 6d251acb | 紗](https://substackcdn.com/image/fetch/$s_!JNNe!)

在特殊场合使用 ChatGPT（约 2025 年，彩色）

如果您已经有喜欢的，请随意跳到提示最佳实践。

## 💰 定价和限制

**🏆 获胜者：Grok；🥈 亚军：Perplexity**

![](https://www.operatorshandbook.com/p/%7B%22src%22:%22https://substack-post-media.s3.amazonaws.com/public/images/e2dbf1b7-8cde-49aa-86da-22e0f1fa588d_2183x593.png%22,%22srcNoWatermark%22:null,%22fullscreen%22:null,%22imageSize%22:null,%22height%22:396,%22width%22:1456,%22resizeWidth%22:null,%22bytes%22:246166,%22alt%22:null,%22title%22:null,%22type%22:%22image/png%22,%22href%22:null,%22belowTheFold%22:true,%22topImage%22:false,%22internalRedirect%22:%22https://www.operatorshandbook.com/i/160819332?img=https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2Fe2dbf1b7-8cde-49aa-86da-22e0f1fa588d_2183x593.png%22,%22isProcessing%22:false,%22align%22:null,%22offset%22:false})

Grok 和 Perplexity 都提供了慷慨的免费套餐， ***每天*** 可进行多次查询 ，这使得它们成为任何想要在不订阅的情况下进行深度研究的人的首选。

相比之下，ChatGPT 和 Gemini 的免费套餐 ***每月*** 都有相当严格的限制 ，而且 Claude 的免费套餐中根本没有研究功能。

![](https://substackcdn.com/image/fetch/$s_!yauW!)

要是 Claude Research 能做得足够好就好了，足以证明自己如此自信

作为重度用户，你最终会面临是否应该升级到高级版的问题。除了更高的使用限制外 **，** 你还可以使用更好的模型和更高质量的输出。

我们将在本节结束时讨论这是否会产生明显的差异（ **剧透** ：并非如此）。

## 🤔 研究规划

**🏆 获胜者：Gemini；🥈 亚军：ChatGPT**

![](https://www.operatorshandbook.com/p/%7B%22src%22:%22https://substack-post-media.s3.amazonaws.com/public/images/8e146259-ff35-4bcb-97c6-71fbd28ab347_2183x435.png%22,%22srcNoWatermark%22:null,%22fullscreen%22:null,%22imageSize%22:null,%22height%22:290,%22width%22:1456,%22resizeWidth%22:null,%22bytes%22:184857,%22alt%22:null,%22title%22:null,%22type%22:%22image/png%22,%22href%22:null,%22belowTheFold%22:true,%22topImage%22:false,%22internalRedirect%22:%22https://www.operatorshandbook.com/i/160819332?img=https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F8e146259-ff35-4bcb-97c6-71fbd28ab347_2183x435.png%22,%22isProcessing%22:false,%22align%22:null,%22offset%22:false})

特别是如果您没有写一份冗长的提示，其中包含有关您希望代理如何进行研究的详细说明，那么在开始之前了解其计划做什么就至关重要。

例如，如果您要求对软件工具进行比较，您可能希望了解它计划使用什么标准来评估它们，这样您就不必等待 5 到 10 分钟才得到不符合标准的结果。

**Gemini 是唯一默认共享研究计划的工具。** 其他工具中，ChatGPT、Claude 和 Perplexity 通常会根据请求提供研究计划：

![](https://www.operatorshandbook.com/p/%7B%22src%22:%22https://substack-post-media.s3.amazonaws.com/public/images/3f895e63-2cb6-4bf7-a204-76caad333da9_552x69.png%22,%22srcNoWatermark%22:null,%22fullscreen%22:null,%22imageSize%22:null,%22height%22:69,%22width%22:552,%22resizeWidth%22:null,%22bytes%22:13091,%22alt%22:null,%22title%22:null,%22type%22:%22image/png%22,%22href%22:null,%22belowTheFold%22:true,%22topImage%22:false,%22internalRedirect%22:%22https://www.operatorshandbook.com/i/160819332?img=https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F3f895e63-2cb6-4bf7-a204-76caad333da9_552x69.png%22,%22isProcessing%22:false,%22align%22:null,%22offset%22:false})

另一方面，Grok 倾向于忽略我的请求并继续研究🤷。

**注意：** 为了最大限度地提高代理人分享研究计划的几率，请在 1) 初始提示中以及 2) 回答后续问题时询问。

## 🙋♂️ 上下文收集

**🏆 获胜者：ChatGPT；🥈 亚军：Claude**

![](https://www.operatorshandbook.com/p/%7B%22src%22:%22https://substack-post-media.s3.amazonaws.com/public/images/3f8b52e5-bcae-4283-a72b-5b3385afad5d_2273x429.png%22,%22srcNoWatermark%22:null,%22fullscreen%22:null,%22imageSize%22:null,%22height%22:275,%22width%22:1456,%22resizeWidth%22:null,%22bytes%22:196414,%22alt%22:null,%22title%22:null,%22type%22:%22image/png%22,%22href%22:null,%22belowTheFold%22:true,%22topImage%22:false,%22internalRedirect%22:%22https://www.operatorshandbook.com/i/160819332?img=https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F3f8b52e5-bcae-4283-a72b-5b3385afad5d_2273x429.png%22,%22isProcessing%22:false,%22align%22:null,%22offset%22:false})

ChatGPT 深度研究是唯一一款即使您没有明确要求，也能可靠地提出 3 到 5 个问题来获取背景信息的工具。而且，这些问题通常切中要点（也就是说，与资深分析师会问的问题类似）。

其他人会在你提示时自动执行，尽管不太可靠。以下是对我来说很有效的两件事：

- 使用 Gemini， 在代理分享研究计划后 *重复您的请求* ，询问缺失的背景信息
- 使用 Grok，在提示中包含一个请求， *解释 \[XYZ\] 如何适用于 \[我的情况/我的公司\]。* 它有时会意识到需要额外的信息才能做到这一点

## 🧠 推理与判断

**🏆 获胜者：ChatGPT；🥈 亚军：Perplexity**

![](https://www.operatorshandbook.com/p/%7B%22src%22:%22https://substack-post-media.s3.amazonaws.com/public/images/99e9d762-dde6-41e9-a8c7-8c4197002ad5_2097x759.png%22,%22srcNoWatermark%22:null,%22fullscreen%22:null,%22imageSize%22:null,%22height%22:527,%22width%22:1456,%22resizeWidth%22:null,%22bytes%22:295070,%22alt%22:null,%22title%22:null,%22type%22:%22image/png%22,%22href%22:null,%22belowTheFold%22:true,%22topImage%22:false,%22internalRedirect%22:%22https://www.operatorshandbook.com/i/160819332?img=https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F99e9d762-dde6-41e9-a8c7-8c4197002ad5_2097x759.png%22,%22isProcessing%22:false,%22align%22:null,%22offset%22:false})

推理和判断是一份好的研究报告的基础。

如果您不同意代理商使用的方法或得出的结论，那么报告有多长或多漂亮都无关紧要。

**ChatGPT 显然是这里的赢家** ；它不仅表现出强大的判断力（例如在选择评估标准或得出要点时），而且还给出了强有力的建议，并清楚地解释了它是如何得出该意见的。

所有其他工具（Perplexity 除外）的研究方法都经常出现一些令人质疑的情况，而且它们的建议是如何得出的也常常令人困惑。因此，如果您打算将报告结果用于任何重要用途，就必须仔细阅读报告，并提出后续问题。

## 📖 全面性

**🏆 获胜者：ChatGPT；🥈 亚军：Gemini**

![](https://www.operatorshandbook.com/p/%7B%22src%22:%22https://substack-post-media.s3.amazonaws.com/public/images/d529149f-9404-434a-b2f8-25dab8a5a7f1_2129x478.png%22,%22srcNoWatermark%22:null,%22fullscreen%22:null,%22imageSize%22:null,%22height%22:327,%22width%22:1456,%22resizeWidth%22:null,%22bytes%22:210563,%22alt%22:null,%22title%22:null,%22type%22:%22image/png%22,%22href%22:null,%22belowTheFold%22:true,%22topImage%22:false,%22internalRedirect%22:%22https://www.operatorshandbook.com/i/160819332?img=https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2Fd529149f-9404-434a-b2f8-25dab8a5a7f1_2129x478.png%22,%22isProcessing%22:false,%22align%22:null,%22offset%22:false})

ChatGPT 和 Gemini 提供了迄今为止最全面的报告；然而，ChatGPT 通常深入研究 *重要领域* ，而 Gemini 则经常添加提示中未要求的通用“无用信息”。

ChatGPT 海量报告的明显优势在于，与其他工具相比，您可以获得有关复杂主题的更详细的考虑。

但这也意味着您需要 **添加指令来改进报告结构** **和格式** （例如，为每个部分添加摘要），以及/或者获取这些报告的 AI 摘要（如果您需要快速获得洞察）。我们将在下文中深入探讨。

其他三个工具则面临相反的问题：它们的报告并非真正 *深入的* 研究。即使它们参考了数十个（Claude 甚至参考了数百个）来源，输出结果也读起来像“TL;DR”（长话短说），所以不要指望它们能提供太多细微的差别、详细的比较或超级战术指南。

你 **可以** 通过要求他们“ *格外彻底* ”和“ *至少达到 \[X 千\] 个字* ” 来获得更详细的报告 （尤其是来自 Perplexity 的报告），但它不会达到 ChatGPT 的水平。

## ✨ 报告结构和格式

**🏆 获胜者：Perplexity；🥈 亚军：Grok**

![](https://www.operatorshandbook.com/p/%7B%22src%22:%22https://substack-post-media.s3.amazonaws.com/public/images/94ae669e-d8b5-46d8-b502-f07c906b93fd_2056x465.png%22,%22srcNoWatermark%22:null,%22fullscreen%22:null,%22imageSize%22:null,%22height%22:329,%22width%22:1456,%22resizeWidth%22:null,%22bytes%22:201320,%22alt%22:null,%22title%22:null,%22type%22:%22image/png%22,%22href%22:null,%22belowTheFold%22:true,%22topImage%22:false,%22internalRedirect%22:%22https://www.operatorshandbook.com/i/160819332?img=https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F94ae669e-d8b5-46d8-b502-f07c906b93fd_2056x465.png%22,%22isProcessing%22:false,%22align%22:null,%22offset%22:false})

Perplexity 和 Grok 默认都会生成易于阅读的报告，并充分利用了项目符号列表和概览表。如果您希望快速获得格式良好的洞察，而无需调整提示，那么这些工具非常适合您。

如前所述，其他工具需要提示中的指导才能生成易于解析的内容。

## 📚 来源

**🏆 获胜者：Perplexity；🥈 亚军：Claude**

![](https://www.operatorshandbook.com/p/%7B%22src%22:%22https://substack-post-media.s3.amazonaws.com/public/images/9f048566-d333-4a5c-98f5-bdb2d1341ccd_1924x902.png%22,%22srcNoWatermark%22:null,%22fullscreen%22:null,%22imageSize%22:null,%22height%22:683,%22width%22:1456,%22resizeWidth%22:null,%22bytes%22:285072,%22alt%22:null,%22title%22:null,%22type%22:%22image/png%22,%22href%22:null,%22belowTheFold%22:true,%22topImage%22:false,%22internalRedirect%22:%22https://www.operatorshandbook.com/i/160819332?img=https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F9f048566-d333-4a5c-98f5-bdb2d1341ccd_1924x902.png%22,%22isProcessing%22:false,%22align%22:null,%22offset%22:false})

对于 DeepResearch 的资料来源，有几点很重要：

1. 是否容易选择 **优先考虑哪些（类型）来源**
2. 考虑了 **多少个** 来源（以获得包含广泛意见和数据点的平衡概述）
3. 研究代理人选择的 **来源的** 质量
4. 追踪 **引用** 有多容易 （这样你就可以仔细检查论点背后的数据）

ChatGPT 默认在这些方面表现不佳（除了引用）。不过，这在实际操作中并不是什么大问题，因为 1）它的总结和要点通常仍然切中要点，2）它对反馈的响应非常迅速。

例如，当我要求提供欧盟主要市场的规模概览时，第一个版本使用的方法和数据来源值得怀疑。但我 通过以下两件事，在 5 分钟内 得到了一个 **更好的版本** ：

1. 要求 ChatGPT o3 编制一份用于市场规模估算的最佳数据源列表：

![](https://www.operatorshandbook.com/p/%7B%22src%22:%22https://substack-post-media.s3.amazonaws.com/public/images/c6a75bcc-7aef-4f79-a278-d8bf25e06652_1297x534.png%22,%22srcNoWatermark%22:null,%22fullscreen%22:null,%22imageSize%22:null,%22height%22:534,%22width%22:1297,%22resizeWidth%22:null,%22bytes%22:290102,%22alt%22:null,%22title%22:null,%22type%22:%22image/png%22,%22href%22:null,%22belowTheFold%22:true,%22topImage%22:false,%22internalRedirect%22:%22https://www.operatorshandbook.com/i/160819332?img=https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2Fc6a75bcc-7aef-4f79-a278-d8bf25e06652_1297x534.png%22,%22isProcessing%22:false,%22align%22:null,%22offset%22:false})

1. 要求深度研究在此基础上重新完成报告的该部分，并 **突出显示来自不同信誉来源的数字不一致的地方** （+提供可能造成这种情况的假设）。

---

## 高级版本值得吗？

在对 Deep Research 进行了一些研究之后，您可能会想：昂贵的高级版本是否值得，或者免费版本是否足够？

别担心；我已经把它们都买了，所以你不用再担心了。

**简而言之：** 在我看来，只有 ChatGPT 高级版才值得你重度使用。其他版本只有在你同时使用账户进行其他操作时才有意义。

这里有两个主要考虑因素：

### 1\. 请求限制

Perplexity 和 Grok 在免费版本中提供了大量的研究积分，因此大多数用户无需升级。

Gemini 的重度用户可能会遇到限制，而且 Claude 根本不免费提供研究功能；但在我看来，在这种情况下你最好使用 ChatGPT。

### 2\. 产出质量

在高级层的广告中，你会看到一些关于高级推理、更深入的研究或更多来源/引用的相当崇高的主张。

**但在实践中真的存在明显差异吗？**

简而言之：不。

- **Perplexity Pro** 的报告 看起来与免费版的报告非常相似；我完全没有感受到广告宣传的“10 倍引用”。我注意到的主要区别是，它生成了很多花哨的图表，但实际上并没有那么有用。
- Grok **DeeperSearch** 也没有给我留下深刻的印象。我在两个模型上运行了完全相同的查询，进行了同类比较；DeeperSearch 确实使用了大约 2-3 倍的数据源，在某些情况下，生成的报告长度增加了 30% 到 60%，并添加了更多细节，但它的深度远不及 ChatGPT Deep Research。

![](https://www.operatorshandbook.com/p/%7B%22src%22:%22https://substack-post-media.s3.amazonaws.com/public/images/32450429-c857-4717-89b2-d036114f49c5_950x875.png%22,%22srcNoWatermark%22:null,%22fullscreen%22:null,%22imageSize%22:null,%22height%22:875,%22width%22:950,%22resizeWidth%22:375,%22bytes%22:1294757,%22alt%22:%22%22,%22title%22:null,%22type%22:%22image/png%22,%22href%22:null,%22belowTheFold%22:true,%22topImage%22:false,%22internalRedirect%22:%22https://www.operatorshandbook.com/i/160819332?img=https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F32450429-c857-4717-89b2-d036114f49c5_950x875.png%22,%22isProcessing%22:false,%22align%22:null,%22offset%22:false})

我们在网上争论吧！

> 即使是高级版本仍然感觉像是 ***摘要，*** 而 ChatGPT 则进行真正 ***深入的研究*** ，带您详尽地了解某个主题。

---

## 如何创建良好的深度研究提示

你的提示质量决定了你的研究成果的成败。如果你提交了一个粗心的请求，你将需要等待长达15分钟（甚至更长时间），最终却发现你收到的是一个半成品，根本无法使用，而且你还浪费了宝贵的深度研究积分。

虽然每个模型都有其特点，但构成良好深度研究提示的核心结构在某种程度上与您最终使用的工具无关。

我们将首先介绍各个组件，然后将它们组合在一起。如果您想尽快开始，请跳过此部分。

---

## 第一步：明确阐述你的目标

你的研究目标是什么？你希望得到什么样的成果？如上所述，这可以是概述、建议、比较或详细的分步指南（或以上几种形式的混合）。

- ❌“帮助我了解 AI 搜索的 SEO 工作原理”
- ✅“请简要总结一下人工智能搜索引擎的 SEO 最佳实践，提供一份我可以采取的具体步骤清单，以提高我的内容的知名度，并推荐一个可以帮助我实现这一目标的特定工具”

![](https://www.operatorshandbook.com/p/%7B%22src%22:%22https://substack-post-media.s3.amazonaws.com/public/images/3b1abce8-a7b5-4a1e-aca8-7882a0702dad_1637x902.png%22,%22srcNoWatermark%22:null,%22fullscreen%22:null,%22imageSize%22:null,%22height%22:802,%22width%22:1456,%22resizeWidth%22:null,%22bytes%22:669036,%22alt%22:null,%22title%22:null,%22type%22:%22image/png%22,%22href%22:null,%22belowTheFold%22:true,%22topImage%22:false,%22internalRedirect%22:%22https://www.operatorshandbook.com/i/160819332?img=https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F3b1abce8-a7b5-4a1e-aca8-7882a0702dad_1637x902.png%22,%22isProcessing%22:false,%22align%22:null,%22offset%22:false})

来自 Perplexity Deep Research 的示例

---

## 第 2 步：提供背景信息

这一步需要你付出最大的努力，但也是最重要的。深度研究的魔力不在于你能得到一份长达 20 页的主题摘要，而在于你能获得一份 *根据你的情况定制的* 报告 ，就像你的团队里有一位研究分析师一样。

**请记住：** 对于您遗漏的任何背景信息，AI 只会做出假设或保持其通用性，以适用于所有人。

重要的事情取决于具体情况，但您可能希望包括：

- 💼 **有关您的业务** 或情况的 基本 事实 （例如产品、商业模式、地理位置）
- 🙋♂️ 报告的 **受众** 是谁（例如您、您公司的首席财务官等）以及他们对该主题的熟悉程度
- 🚧 您面临哪些 **限制** （例如您的公司不能/不会考虑的事情）
- 🎯 报告的 **下游用途** 是什么（例如您希望做出的具体决定）

即使是基本背景也会产生 **巨大的** 差异：

- 这是 Gemini 制作的关于增值税法规和合规性的 超级 [通用报告，](https://docs.google.com/document/d/1lQfX4mKBm18lICoL2kfxPv7GxT56r1pRO5MSy0aJmnU/edit?usp=sharing) *没有任何背景信息*
- 由于提示中添加了一句话（美国 B2B SaaS 初创公司向欧盟扩张）， 这份 [报告](https://docs.google.com/document/d/1dHK4L7nRL4Z7AD6GGQ8tWubW7YqT3-x-r_jZxFgfwSc/edit?usp=sharing) 更加 具体，更具可操作性。

由于很难想到所有可能相关的内容，你可以让人工智能帮你集思广益。一个简单的提示对我来说很有效（例如使用 O3）：

> *我计划针对 \[X\] 生成一份深度研究报告，以便 \[Y\] 完成这项工作。我应该提供哪些背景信息才能获得一份定制化、可操作的报告？假设你之前没有任何对话记录。*

最后，如果您想确保没有遗漏任何内容，请直接询问深度研究代理以获取更多背景信息：

![](https://www.operatorshandbook.com/p/%7B%22src%22:%22https://substack-post-media.s3.amazonaws.com/public/images/d0d46bb4-2e86-4c5f-bacd-f807fc8accfb_574x264.png%22,%22srcNoWatermark%22:null,%22fullscreen%22:null,%22imageSize%22:null,%22height%22:264,%22width%22:574,%22resizeWidth%22:498,%22bytes%22:33809,%22alt%22:null,%22title%22:null,%22type%22:%22image/png%22,%22href%22:null,%22belowTheFold%22:true,%22topImage%22:false,%22internalRedirect%22:%22https://www.operatorshandbook.com/i/160819332?img=https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2Fd0d46bb4-2e86-4c5f-bacd-f807fc8accfb_574x264.png%22,%22isProcessing%22:false,%22align%22:null,%22offset%22:false})

双子座的例子

---

## 步骤 3：指定所需的输出

如前所述，默认输出（尤其是 ChatGPT）有点混乱。如果您想要更容易理解的内容，则需要指定。

对我来说，一些行之有效的方法包括：

### 指定文档的内容和结构

明确 1) 整个文档和 2) 各个部分的内容和结构对我来说有很大的不同。

**例如：**

- 口述您想要在交付成果中包含的任何关键内容（例如特定比较、模板、复制示例、代码片段等）
- 要求座席遵循金字塔原则，并以关键要点或建议为主导（在主要摘要和每个单独的小节中）

![](https://www.operatorshandbook.com/p/%7B%22src%22:%22https://substack-post-media.s3.amazonaws.com/public/images/57c72179-b20d-4436-b653-67d52c45be10_795x340.png%22,%22srcNoWatermark%22:null,%22fullscreen%22:null,%22imageSize%22:null,%22height%22:340,%22width%22:795,%22resizeWidth%22:641,%22bytes%22:82184,%22alt%22:null,%22title%22:null,%22type%22:%22image/png%22,%22href%22:null,%22belowTheFold%22:true,%22topImage%22:false,%22internalRedirect%22:%22https://www.operatorshandbook.com/i/160819332?img=https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F57c72179-b20d-4436-b653-67d52c45be10_795x340.png%22,%22isProcessing%22:false,%22align%22:null,%22offset%22:false})

ChatGPT Deep Research 报告中关于 Vibe 编码工具的示例。在提出这个请求之前，我不得不像大海捞针一样费力地寻找相关建议。

- 要求提供所用来源的概述，包括用途、类型（例如政府、商业、新闻媒体、时事通讯/博客）、创建或更新日期等。

![](https://www.operatorshandbook.com/p/%7B%22src%22:%22https://substack-post-media.s3.amazonaws.com/public/images/cba2171e-64c0-4ea2-b961-5ce59462ea20_563x267.png%22,%22srcNoWatermark%22:null,%22fullscreen%22:null,%22imageSize%22:null,%22height%22:267,%22width%22:563,%22resizeWidth%22:null,%22bytes%22:46183,%22alt%22:null,%22title%22:null,%22type%22:%22image/png%22,%22href%22:null,%22belowTheFold%22:true,%22topImage%22:false,%22internalRedirect%22:%22https://www.operatorshandbook.com/i/160819332?img=https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2Fcba2171e-64c0-4ea2-b961-5ce59462ea20_563x267.png%22,%22isProcessing%22:false,%22align%22:null,%22offset%22:false})

Perplexity 中 B2B SaaS 软件的 TAM 分析源概述示例

### 指定所需的输出格式

只需在提示中添加一些基本说明，就会对报告的外观产生巨大的影响。

- 要求在适当的地方使用项目符号列表和粗体文本
- 声明您更喜欢使用表格而不是文本摘要来进行任何类型的比较或概述

![](https://www.operatorshandbook.com/p/%7B%22src%22:%22https://substack-post-media.s3.amazonaws.com/public/images/6669a0eb-be92-4d49-8522-66b60995077f_1500x1089.png%22,%22srcNoWatermark%22:null,%22fullscreen%22:null,%22imageSize%22:null,%22height%22:1057,%22width%22:1456,%22resizeWidth%22:null,%22bytes%22:723841,%22alt%22:null,%22title%22:null,%22type%22:%22image/png%22,%22href%22:null,%22belowTheFold%22:true,%22topImage%22:false,%22internalRedirect%22:%22https://www.operatorshandbook.com/i/160819332?img=https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F6669a0eb-be92-4d49-8522-66b60995077f_1500x1089.png%22,%22isProcessing%22:false,%22align%22:null,%22offset%22:false})

Perplexity 清理摘要示例

---

## 第四步：索取研究计划并提供反馈

正如您在上面的概述中所看到的，只有 Gemini 能够可靠地主动分享研究计划。为了避免意外，请务必在代理开始任何工作之前索取。

例如， 这是我在 *明确要求* 后从 ChatGPT 获得的深入研究氛围编码工具的 [建议研究计划](https://chatgpt.com/s/dr_6855884431cc8191a3fdaa5cfc1eb4fd) 。

![](https://www.operatorshandbook.com/p/%7B%22src%22:%22https://substack-post-media.s3.amazonaws.com/public/images/5f460583-895c-437b-965e-919d3f328a27_758x495.png%22,%22srcNoWatermark%22:null,%22fullscreen%22:null,%22imageSize%22:null,%22height%22:495,%22width%22:758,%22resizeWidth%22:552,%22bytes%22:82826,%22alt%22:null,%22title%22:null,%22type%22:%22image/png%22,%22href%22:null,%22belowTheFold%22:true,%22topImage%22:false,%22internalRedirect%22:%22https://www.operatorshandbook.com/i/160819332?img=https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F5f460583-895c-437b-965e-919d3f328a27_758x495.png%22,%22isProcessing%22:false,%22align%22:null,%22offset%22:false})

ChatGPT 研究计划的片段； 点击此处 查看完整内容

以下是我要注意的关键事项：

- 研究计划是否 **全面** ？您希望代理人做的分析或撰写的部分是否缺失？
- 您是否喜欢经纪人的 **关注** 点 ？如果您对某个特定领域感兴趣，请确保经纪人的报告是围绕该领域撰写的。
- 是否有任何你不同意的隐含或明确 **假设** ？如果有，请提供相关背景来弥补这些不足。
- 您是否同意该 **方法** （例如评估或比较标准）？

如果您希望代理优先考虑某些来源，这也是一个指定好时机 **。**

例如，您可以要求使用来自独立第三方而不是公司网站的数据，或者您只想要比某个截止日期更新的数据。

---

## 可选：举例说明你想要什么

如果您有特定的期望（例如，输出应该是什么样的），那么举例说明会很有帮助。

例如，您可能正在使用深度研究来自动创建以前需要手动完成的报告。在这种情况下，您可以将一些最佳的工作样本放入文档中，并将其作为上下文上传，以便 AI 代理可以模仿它们。

---

## 综合起来：有效的深度研究提示是什么样的

以下是包含上述提示的端到端提示的示例：

![](https://www.operatorshandbook.com/p/%7B%22src%22:%22https://substack-post-media.s3.amazonaws.com/public/images/39f02e0c-2be3-4594-b403-ac2e2b9c0f67_1500x1190.png%22,%22srcNoWatermark%22:null,%22fullscreen%22:null,%22imageSize%22:null,%22height%22:1155,%22width%22:1456,%22resizeWidth%22:null,%22bytes%22:837484,%22alt%22:null,%22title%22:null,%22type%22:%22image/png%22,%22href%22:null,%22belowTheFold%22:true,%22topImage%22:false,%22internalRedirect%22:%22https://www.operatorshandbook.com/i/160819332?img=https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F39f02e0c-2be3-4594-b403-ac2e2b9c0f67_1500x1190.png%22,%22isProcessing%22:false,%22align%22:null,%22offset%22:false})

以下是 ChatGPT 生成的结果：

- [账户评分指南](https://chatgpt.com/share/6859a8d6-715c-8002-9afa-f3174f0a4b72)

我想说，这相当不错——而且比你通过简单的“创建帐户评分指南”提示所获得的结果要好得多。

***附注*** ： *正如你所见，它承诺在继续之前分享一份研究计划，但之后就忘了。所以我建议在回答上下文问题时重复这个请求（这次我没有这样做）。*

---

## 🤖 如何利用人工智能快速创建高质量的提示

您可以自己设计提示，也可以请 AI 帮忙（反馈您的草稿提示或从头开始编写提示）。

例如，如果你向 ChatGPT o3 询问这个问题……

![](https://www.operatorshandbook.com/p/%7B%22src%22:%22https://substack-post-media.s3.amazonaws.com/public/images/b3160d04-2eed-4755-9eeb-aa0e9e9db460_558x179.png%22,%22srcNoWatermark%22:null,%22fullscreen%22:null,%22imageSize%22:null,%22height%22:179,%22width%22:558,%22resizeWidth%22:502,%22bytes%22:38003,%22alt%22:null,%22title%22:null,%22type%22:%22image/png%22,%22href%22:null,%22belowTheFold%22:true,%22topImage%22:false,%22internalRedirect%22:%22https://www.operatorshandbook.com/i/160819332?img=https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2Fb3160d04-2eed-4755-9eeb-aa0e9e9db460_558x179.png%22,%22isProcessing%22:false,%22align%22:null,%22offset%22:false})

…你拿回 [这个](https://docs.google.com/document/d/1rZHtuB0NiKALkwoLN3md34L56tQEArXQvybX-gp0gi0/edit?usp=sharing) 。

**注意：** 我建议不要盲目地复制粘贴 AI 生成的提示，而是根据你的目的进行调整。例如，你会发现 o3 包含了很多非常具体的要求，而这些要求可能并非你真正想要的。

无论哪种方式，这都是一个很好的起点，并且比从头开始创建提示更快。

---

## 💬 将研究视为对话

深度研究的学分有限，因此精心设计可靠的题目至关重要。不过，我建议你以与人类分析师相同的方式进行 AI 研究。

原因如下：

### 1\. 反馈比想象完美的交付成果要容易得多

你能描述一下对一个主题的完美分析是什么样的吗？它需要包含哪些细节？

可能不会。但一旦你看到一个，你就会立刻知道它该如何改进。根据我的经验，相比于一味追求完美的提示，先拿到初稿并提供反馈能更快地获得好结果。

如果你不是该领域的专家，这一点尤其重要。我经常对某个话题知之甚少，甚至不知道应该问什么问题。因此，我会采取以下做法：

1. 首先，我要求进行高层次的概述， *并提出后续深入探讨的建议*
2. 然后，在审阅了初步报告后，我会逐一深入研究最有趣的领域

这样，我就不用再被一份50页的报告弄得不知所措，因为报告里满是我不理解或不需要的信息。而且，随着每一次深入研究，我的理解都会更加深刻，也能够为下一次“研究工作”改进我的问题。

### 2\. 你越是规范，你就越限制模型的推理

这就像你作为经理委派工作一样：当你给予人们一些执行自由时，你就能获得一些最好的交付成果。例如，他们可能会从你意想不到的角度来解决问题。

如果你给出一个非常规范的研究提示，最好的结果就是一份和你预期一样好的报告。但如果你想获得惊喜，你需要给研究留下一些更开放的条件。

### 3\. 研究报告就像一座纸牌屋：没有坚实的基础，一切都会崩塌

想象一下，您收到一份关于如何为某个用例构建 ML 模型的深入报告，其中包括清单、时间表估算、代码示例等，但却发现您忘记提供关键的背景信息。

现在这些东西不仅毫无用处；而且由于报告非常详细，您可能花了太多时间去研究它，直到您意识到它存在根本缺陷。

对于复杂的主题， **你最初的重点应该放在正确分析的核心** 。然后，一旦你对结果感到满意，就可以让人工智能创建下游可交付成果，例如详细的项目计划或实际实施建议所需的任何其他内容。

---

## 如何从最终研究报告中获得最大价值

如上所述，ChatGPT 深度研究报告可能很 **长** ，非常长。有时甚至长达 2 万字甚至更多。

不过，我不建议你一拿到书就从头到尾读完。相反，我建议你把它们当作一种资源，在需要深入研究某个方面时可以选择性地参考。

为了快速概览要点，将报告反馈到 ChatGPT（或其他工具）并要求提供摘要会更有效。如果您在工作中将研究作为跨职能项目的一部分进行， 我强烈建议您针对特定受众 （例如产品经理、财务团队等） **要求提供多份摘要** 。

最后，人类并非唯一能够从深度研究中获得价值的物种。您还可以将报告作为背景信息添加到未来任何 AI 对话或项目中：

![](https://www.operatorshandbook.com/p/%7B%22src%22:%22https://substack-post-media.s3.amazonaws.com/public/images/2dfb0d6e-023d-4ffe-890f-b8ecff574785_463x355.png%22,%22srcNoWatermark%22:null,%22fullscreen%22:null,%22imageSize%22:null,%22height%22:355,%22width%22:463,%22resizeWidth%22:391,%22bytes%22:32142,%22alt%22:null,%22title%22:null,%22type%22:%22image/png%22,%22href%22:null,%22belowTheFold%22:true,%22topImage%22:false,%22internalRedirect%22:%22https://www.operatorshandbook.com/i/160819332?img=https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F2dfb0d6e-023d-4ffe-890f-b8ecff574785_463x355.png%22,%22isProcessing%22:false,%22align%22:null,%22offset%22:false})

示例：向 Claude 项目添加上下文

---

## 回顾与展望

DeepResearch 绝对是一项令人惊叹的功能——前提是你知道如何使用它。希望本指南能为你提供一条捷径，让你最大限度地利用它的价值。

在接下来的几周和几个月里，我会发布更多类似的深度指南。请在下方订阅，即可在您的邮箱中收到。

不过别担心：我也会继续创作非 AI 内容，而且我还有一些精彩的文章正在筹备中。敬请期待！

---

---

## 💼 精选职位

准备好迎接下一场冒险了吗？以下是我最喜欢的一些开放职位，由 [BizOps.careers](https://www.bizops.careers/) 为您带来 （按从早期到晚期的排序）：

**职位：** [业务运营经理](https://www.bizops.careers/jobs/142664459-business-operations-manager) | 🏠︎ **地点：** 纽约 | 💼 **经验：** 3 年以上 | 🚀 **阶段：** A 轮 | 🏛️ **投资者：** 红杉资本、凯鹏华盈

**Pulley：** [战略与运营经理](https://www.bizops.careers/jobs/140628457-strategy-operations-manager) | 🏠︎ **地点：** 远程 | 💰 **薪资：** 15 万 - 19.5 万美元 | 💼 **经验：** 5 年以上 | 🚀 **阶段：** B 轮 | 🏛️ **投资者：** Founders Fund、General Catalyst

**Alloy：** [参谋长 - 支持首席执行官](https://www.bizops.careers/jobs/139747732-chief-of-staff-supporting-ceo) | 🏠︎ **地点：** 纽约 | 💰 **薪资：** 22.5 万美元 - 26 万美元 | 💼 **经验：** 6 年以上 | 🚀 **阶段：** C 轮 | 🏛️ **投资者：** Lightspeed、Bessemer

**Decagon：** [业务运营和数据分析](https://www.bizops.careers/jobs/142664398-business-operations-data-analytics) | 🏠︎ **地点：** 旧金山 | 💰 **薪资：** 17.5 万美元 - 22 万美元 | 💼 **经验：** 5 年以上 | 🚀 **阶段：** C 轮 | 🏛️ **投资者：** a16z、Accel、BOND

**Decagon：** [战略增长](https://www.bizops.careers/jobs/142664400-strategic-growth) | 🏠︎ **地点：** 旧金山 | 💰 **薪资：** 20 万 - 28 万美元 | 💼 **经验：** 3 年以上 | 🚀 **阶段：** C 轮 | 🏛️ **投资者：** a16z、Accel、BOND

**Glean：** [产品运营主管](https://www.bizops.careers/jobs/142664473-product-operations-lead) | 🏠︎ **地点：** 加州帕洛阿尔托 | 💰 **薪资：** 18.5 万美元 - 23.5 万美元 | 💼 **经验：** 灵活 | 🚀 **阶段：** D+ 轮 | 🏛️ **投资者：** 红杉资本、凯鹏华盈、光速资本

**职位：** [市场策略与分析高级助理](https://www.bizops.careers/jobs/142282259-marketplace-strategy-analytics-senior-associate) | 🏠︎ **地点：** 旧金山 | 💰 **薪资：** 129,000 美元 - 177,000 美元 | 💼 **经验：** 3 年以上 | 🚀 **阶段：** D+ 轮 | 🏛️ **投资者：** 红杉资本、Lightspeed、Founders Fund

**Perplexity：** [财务经理](https://www.bizops.careers/jobs/142664488-finance-manager-finance) | 🏠︎ **地点：** 旧金山 | 💰 **薪资：** 18 万 - 23 万美元 | 💼 **经验：** 5 年以上 | 🚀 **阶段：** D+ 轮 | 🏛️ **投资者：** IVP、NEA、Bessemer

**Dropbox：** [首席执行官的幕僚长](https://www.bizops.careers/jobs/142664449-chief-of-staff-to-the-ceo) | 🏠︎ **地点：** 旧金山 / 远程 | 💰 **薪资：** 15 万 - 25.3 万美元 | 💼 **经验：** 5 年以上 | 🚀 **阶段：** 公开

---

## 📚 我最近喜欢读的书

- [下一个分销大](https://substack.com/@brianbalfour/p-166182188) 变革 ：关于如何将 ChatGPT 视为下一个分发平台的必读文章，以及我们可以基于过去平台的类似模式期待哪些发展
- [提示是](https://contraptions.venkateshrao.com/p/prompting-is-managing) 通过 ：一个有趣的反向观点： [最近麻省理工学院的一篇论文](http://chrome-extension//efaidnbmnnnibpcajpcglclefindmkaj/https://arxiv.org/pdf/2506.08872) 在“天哪，我就知道，现在麻省理工学院证明了这一点”的众多反应中脱颖而出
- 吸血鬼袭击：市场如何解决 先 [有鸡还是先有蛋的问题](https://www.gardinercolin.com/p/vampire-attacks-marketplaces) ：仔细看看有多少知名市场通过从更成熟的平台吸走用户而发展壮大
- 我作为大型科技 公司 [高级工程师的（大部分）极简 AI 设置](https://read.highgrowthengineer.com/p/minimalistic-ai-setup) ：这是一个很好的提醒，对于那些对人工智能工具的数量感到不知所措的人来说，少即是多