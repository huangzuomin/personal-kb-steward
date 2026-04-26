---
title: This Rumor About GPT-5 Changes Everything
source: https://www.thealgorithmicbridge.com/p/this-rumor-about-gpt-5-changes-everything?utm_source=post-email-title&publication_id=883883&post_id=154958095&utm_campaign=email-post-title&isFreemail=true&r=10pftm&triedRedirect=true&utm_medium=email
author: []
published: 2025-01-17
created: 2025-01-17
description: Let’s start the year on an exciting note
tags: cn
category: hive-180932
permlink: 20250117t092728114z
---
![](https://substackcdn.com/image/fetch/w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F61d7c2f7-6d0d-4624-9498-e006d3b5bc96_1792x1024.webp)

## 摘要：关于 GPT-5 的传言，或预示 AI 发展新方向

本文推测 OpenAI 可能已秘密完成 GPT-5 的研发，但并未公开发布，而是将其保留在内部以获取更大的战略回报，而非直接的经济利益。作者通过分析 Anthropic 对 Claude Opus 3.5 的处理方式作为类比：Anthropic 训练了 Opus 3.5 但因成本效益比不高而未发布，转而将其用于“蒸馏”技术，提升了 Claude Sonnet 3.6 的性能。

文章认为，OpenAI 或许也在采用类似策略，秘密训练 GPT-5 这样更强大的模型，并将其作为“教师”模型，用于提升更小、更经济的“学生”模型（如 GPT-4o）。这既能解决高昂的推理成本问题，又能避免因新模型性能提升不足而引起的公众不满。

此外，文章还指出 OpenAI 与微软的 AGI 条款可能也是 GPT-5 未发布的原因之一。该条款规定，一旦 OpenAI 声明达到 AGI（可能有一个秘密的盈利门槛），与微软的合作将终止。因此，OpenAI 可能有意推迟发布被认为可能达到 AGI 标准的 GPT-5。

文章的核心观点是，AI 发展的重心可能正在从公开发布最强大的基础模型转向内部利用这些模型来提升其他产品的性能，并为未来的发展积累优势。这预示着我们可能不会直接接触到所有最先进的 AI 技术，而是在幕后默默享受其带来的进步。



正文：

如果我告诉你 GPT-5 确有其事，你会怎么想？它不仅存在，而且已经在我们看不见的地方悄然地塑造着这个世界。我的假设是：OpenAI 已经构建了 GPT-5，但将其保留在内部，因为其投资回报远高于将其发布给数百万 ChatGPT 用户。而且，他们所获得的回报 *并非金钱*，而是其他东西。正如你所见，这个想法很简单，挑战在于串联起那些指向它的蛛丝马迹。本文将深入探讨我相信这一切并非空穴来风的原因。

请允许我明确一点：这纯粹是推测。证据是公开的，但没有任何泄露或内部传言证实我的观点。事实上，我正在通过这篇文章构建这个理论，而非仅仅是分享它。我没有特权信息——如果我有，我也要遵守保密协议。这个假设之所以引人入胜，是因为它 *合情合理*。坦白地说，为流言蜚语添一把柴火，我还需要什么呢？

是否相信就由你来判断了。即使我是错的——我们最终会知道真相——我也认为这是一场有趣的侦探游戏。我邀请你在评论区进行推测，但请保持建设性和思考性。并且，请先完整阅读这篇文章。除此之外，欢迎一切讨论。

在深入探讨 GPT-5 之前，我们不得不先拜访一下它的远房表亲，同样“失踪”的 Anthropic 的 Claude Opus 3.5。

众所周知，三大顶级 AI 实验室——OpenAI、Google DeepMind 和 Anthropic——提供一系列模型，旨在覆盖性价比（价格/延迟与性能的权衡）谱系。OpenAI 提供了诸如 GPT-4o、GPT-4o mini 以及 o1 和 o1-mini 等选项。Google DeepMind 提供 Gemini Ultra、Pro 和 Flash，而 Anthropic 则有 Claude Opus、Sonnet 和 Haiku。目标很明确：尽可能满足各种客户的需求。一些客户优先考虑顶级的性能，不惜成本；而另一些则寻求经济实惠、足够好用的解决方案。目前来看，一切正常。

但 2024 年 10 月发生了一些奇怪的事情。每个人都期待 Anthropic 发布 Claude Opus 3.5 作为对 GPT-4o（[2024 年 5 月发布](https://openai.com/index/hello-gpt-4o/)）的回应。然而，在 10 月 22 日，他们发布了 [Claude Sonnet 3.5 的更新版本](https://www.anthropic.com/news/3-5-models-and-computer-use)（人们开始称之为 Sonnet 3.6）。Opus 3.5 却不见踪影，似乎让 Anthropic 在与 GPT-4o 的直接竞争中处于劣势。很奇怪，对吧？以下是关于 Opus 3.5 的传闻以及实际发生情况的时间线：

* 10 月 28 日，我在我的每周回顾文章中写道 [这个](https://www.thealgorithmicbridge.com/p/weekly-top-picks-86)：“有[传言](https://x.com/apples_jimmy/status/1849248421636682196)称 Sonnet 3.6 是……备受期待的 Opus 3.5 训练失败后的中间检查点。” 同样在 10 月 28 日，r/ClaudeAI subreddit 上出现了一个[帖子](https://www.reddit.com/r/ClaudeAI/comments/1gdvhph/claude_35_opus_has_been_scrapped/)：“Claude 3.5 Opus 已被取消”，并附有一个指向 [Anthropic 模型页面](https://docs.anthropic.com/en/docs/about-claude/models) 的链接，截至今日，该页面上仍未提及 Opus 3.5。一些人推测，移除它是为了在即将到来的 [融资轮](https://www.reuters.com/technology/artificial-intelligence/anthropic-raise-2-bln-deal-valuing-ai-startup-60-bln-wsj-reports-2025-01-07/) 之前维护投资者的信任。
* 11 月 11 日，Anthropic 首席执行官 Dario Amodei 在 Lex Fridman 的播客中 [否认](https://www.youtube.com/watch?v=ugvHCXCOmm4&t=2232s&ab_channel=LexFridman) 他们放弃了 Opus 3.5，从而平息了这些传言：“不会给你确切的日期，但据我们所知，计划仍然是推出 Claude 3.5 Opus。” 谨慎而含糊，但有效。
* 11 月 13 日，《彭博社》加入了讨论，[证实了早前的传言](https://www.bloomberg.com/news/articles/2024-11-13/openai-google-and-anthropic-are-struggling-to-build-more-advanced-ai)：“在训练后，Anthropic 发现 3.5 Opus 在评估中表现优于旧版本，但提升幅度不如模型规模和构建及运行成本所预期的那么大。”  似乎 Dario 没有给出日期的原因是，尽管 Opus 3.5 的训练运行并未失败，但其结果令人失望。请注意，重点是 *相对于性能的成本*，而非仅仅是性能。
* 12 月 11 日，半导体专家 Dylan Patel 和他的 Semianalysis 团队带来了最终的剧情反转，[给出了一个解释](https://semianalysis.com/2024/12/11/scaling-laws-o1-pro-architecture-reasoning-training-infrastructure-orion-and-claude-3-5-opus-failures/#synthetic-data%e2%80%99s-integral-role-in-post-training)，将所有数据点串联成一个连贯的故事：“Anthropic 完成了 Claude 3.5 Opus 的训练，并且表现良好，符合预期扩展……然而，Anthropic 并未公开发布它。这是因为 Anthropic *使用 Claude 3.5 Opus 生成合成数据* 并进行奖励建模，从而显著提升了 Claude 3.5 Sonnet 的性能，同时还使用了用户数据。”

简而言之，Anthropic 确实训练了 Claude Opus 3.5。他们放弃了这个名字，因为它不够出色。Dario 相信不同的训练运行可以改善结果，因此避免给出具体日期。《彭博社》证实，结果优于现有模型，但不足以证明推理成本（推理 = 用户使用模型）是合理的。Dylan 和他的团队揭示了神秘的 Sonnet 3.6 和失踪的 Opus 3.5 之间的联系：后者被内部用于生成合成数据以提升前者的性能。

我们可以用下图来表示：

![](https://substackcdn.com/image/fetch/w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F02c06e98-88d6-44fb-a7c2-4fd63a886fef_348x432.png)

使用一个强大且昂贵的模型来生成数据，从而增强一个能力稍逊但更便宜的模型的性能的过程，被称为蒸馏。这是一种常见的做法。这种技术使 AI 实验室能够将其较小的模型提升到仅通过额外的预训练无法达到的水平。

蒸馏有多种方法，但我们暂且不深入探讨。你需要记住的是，一个强大的模型充当“老师”，可以将“学生”模型从【小巧、廉价、快速】+ *弱* 变成【小巧、廉价、快速】+ *强大*。蒸馏将一个强大的模型变成了一座金矿。Dylan 解释了为什么 Anthropic 使用 Opus 3.5-Sonnet 3.6 组合进行蒸馏是合理的：

> 新的 Sonnet 相对于旧的 Sonnet，推理成本没有显著变化，但模型的性能却提升了。当从成本角度来看，发布 3.5 Opus 并不具备经济意义时，为什么还要发布它呢？相对于发布一个通过 3.5 Opus 进一步进行后训练的 3.5 Sonnet 而言。

我们又回到了成本问题：蒸馏可以在保持较低推理成本的同时提高性能。这完美地解决了《彭博社》报道的主要问题。Anthropic 选择不发布 Opus 3.5，除了其结果不尽如人意之外，还因为它在内部更有价值。（Dylan 说，这就是开源社区如此迅速地赶上 GPT-4 的原因——他们直接从 OpenAI 的金矿中获取黄金。）

最引人注目的启示是：Sonnet 3.6 不仅仅是好——它 *好到足以称得上是顶尖水平*。[比 GPT-4o 更好](https://x.com/AnthropicAI/status/1848742740420341988)。得益于 Opus 3.5 的蒸馏（可能还有其他原因，AI 领域的五个月非常漫长），Anthropic 的中端模型超越了 OpenAI 的旗舰模型。突然间，高成本暴露了其作为高性能代理的谬误。

“越大越好”的时代到哪里去了？OpenAI 的首席执行官 Sam Altman 曾警告说，[那个时代已经结束了](https://www.wired.com/story/openai-ceo-sam-altman-the-age-of-giant-ai-models-is-already-over/)。我也 [写过相关文章](https://www.thealgorithmicbridge.com/p/size-doesnt-matter)。一旦顶尖实验室变得讳莫如深，小心翼翼地守护着他们珍贵的知识，他们就停止分享具体参数。参数量不再是一个可靠的指标，我们明智地将注意力转向了基准性能。OpenAI 最后一次官方披露模型规模是在 2020 年的 GPT-3，拥有 1750 亿个参数。到 2023 年 6 月，有传言称 GPT-4 是一个混合专家模型，总计约 [1.8 万亿个参数](https://www.thealgorithmicbridge.com/p/gpt-4s-secret-has-been-revealed)。Semianalysis 后来在一份详细的评估报告中 [证实](https://semianalysis.com/2023/07/10/gpt-4-architecture-infrastructure/) 了这一点，结论是 GPT-4 拥有 1.76 万亿个参数。那是 2023 年 7 月。

直到 2024 年 12 月，时隔一年半之后，EpochAI（一个关注 AI 未来影响的组织）的研究员 Ege Erdil [估计](https://epoch.ai/gradient-updates/frontier-language-models-have-become-much-smaller)，包括 GPT-4o 和 Sonnet 3.6 在内的一批领先 AI 模型，其规模远小于 GPT-4（尽管它们在[各项基准测试中都优于 GPT-4](https://openai.com/index/hello-gpt-4o/)）：

> ……目前的尖端模型，例如最初的 GPT-4o 和 Claude 3.5 Sonnet，可能比 GPT-4 *小* 一个数量级，其中 4o 大约有 2000 亿个参数，而 3.5 Sonnet 大约有 4000 亿个参数……尽管考虑到我得出这个数字的方式比较粗略，这个估计值很容易出现两倍的误差。

他深入解释了在实验室未发布任何架构细节的情况下，他是如何得到这个数字的，但这对我们来说并不重要。重要的是，迷雾正在消散：Anthropic 和 OpenAI 似乎都在遵循类似的轨迹。他们最新的模型不仅更好，而且比上一代更小、更便宜。我们知道 Anthropic 是如何通过将 Opus 3.5 蒸馏到 Sonnet 3.6 来实现这一点的。但是，OpenAI 又做了什么呢？

![](https://substackcdn.com/image/fetch/w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F1a67718e-6a06-4b9f-a334-6cf2a732d5f0_681x433.png)

人们可能会认为 Anthropic 的蒸馏方法是出于独特的境遇——即 Opus 3.5 的训练运行不尽如人意。但事实是，Anthropic 的情况远非个例。Google DeepMind 以及 OpenAI 都报告了他们最新训练运行的次优结果。（请记住，次优并不等于 *更差的模型*。）造成这种情况的原因对我们来说并不重要：由于缺乏数据而导致的回报递减、Transformer 架构固有的局限性、预训练规模定律的瓶颈等等。无论如何，Anthropic 的独特境遇实际上是相当普遍的。

但请记住《彭博社》的报道：性能指标的好坏是相对于成本而言的。这是另一个共同因素吗？是的，并且 [Ege 解释了原因](https://epoch.ai/gradient-updates/frontier-language-models-have-become-much-smaller)：ChatGPT/GPT-4 的爆火导致需求激增。生成式 AI 的普及速度如此之快，以至于实验室难以跟上，并遭受了越来越多的损失。这种情况促使他们都降低推理成本（训练运行只进行一次，但推理成本会随着用户数量和使用量的增加而成比例增长）。如果 [每周有 3 亿人使用你的 AI 产品](https://www.theverge.com/2024/12/4/24313097/chatgpt-300-million-weekly-users)，运营支出可能会突然让你破产。

促使 Anthropic 将 Sonnet 3.6 从 Opus 3.5 中蒸馏出来的因素，对 OpenAI 的影响 *要大得多*。蒸馏之所以有效，是因为它将这两个普遍的挑战转化为优势：你通过向用户提供较小的模型来解决推理成本问题，并通过不发布较大的模型来避免因性能不佳而引起的公众强烈反对。

Ege 认为 OpenAI 可能选择了另一种方法：过拟合。其想法是在比计算最优值更多的数据上训练一个小模型：“当推理成为模型支出中的重要或主要部分时，最好……在更多的 tokens 上训练较小的模型。” 但过拟合已经不再可行。AI 实验室已经耗尽了用于预训练的高质量数据源。[Elon Musk](https://techcrunch.com/2025/01/08/elon-musk-agrees-that-weve-exhausted-ai-training-data/) 和 [Ilya Sutskever](https://www.theverge.com/2024/12/13/24320811/what-ilya-sutskever-sees-openai-model-data-training) 最近几周都承认了这一点。

我们又回到了蒸馏。Ege 总结道：“我认为 GPT-4o 和 Claude 3.5 Sonnet 都可能是从更大的模型中蒸馏出来的。”

到目前为止，所有的证据都表明，OpenAI 正在做 Anthropic 对 Opus 3.5 所做的事情（训练并隐藏），以相同的方式（蒸馏），并出于相同的原因（结果不佳/成本控制）。这是一个发现。但是等等，Opus 3.5 仍然被隐藏着。OpenAI 类似的模型在哪里？它是否藏在公司的地下室里？不妨猜猜它的名字……？

![](https://substackcdn.com/image/fetch/w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F0adcb09b-71f4-4682-b82f-bb095d04b35e_917x516.png)

我最初的研究始于 Anthropic 的 Opus 3.5 的故事，因为我们掌握着更多关于它的信息。然后，我通过蒸馏的概念，在它和 OpenAI 之间架起了一座桥梁，并解释了推动 Anthropic 的潜在力量也同样在推动着 OpenAI。然而，我们的理论又面临一个新的障碍：由于 OpenAI 是先行者，他们可能面临着像 Anthropic 这样的竞争对手尚未遇到的障碍。

其中一个障碍是训练 GPT-5 的硬件要求。Sonnet 3.6 可以与 GPT-4o 相媲美，但它的发布滞后了五个月。我们应该假设 GPT-5 处于另一个层次。更强大、更大。不仅推理成本更高，训练成本也更高。我们可能在谈论一次耗资五亿美元的训练运行。使用当前的硬件是否有可能实现这样的目标？

Ege 再次提供了帮助：是的。向 3 亿用户提供这样一个庞然大物是难以承受的。但是训练？易如反掌：

> 原则上，即使是我们当前的硬件也足以支持比 GPT-4 更大的模型：例如，一个规模是 GPT-4 的 50 倍的版本，拥有约 100 万亿个参数，或许可以以每百万个输出 tokens 3000 美元的价格和每秒 10-20 个 tokens 的输出速度来提供服务。然而，要使其可行，这些大型模型必须为使用它们的客户解锁大量的经济价值。

然而，花费如此巨额的推理费用，即使对于微软、谷歌或亚马逊（分别是 OpenAI、DeepMind 和 Anthropic 的赞助商）来说，也是不合理的。那么他们是如何解决这个问题的呢？很简单：只有当他们计划向公众提供数万亿参数的模型时，他们才需要“解锁大量的经济价值”。所以他们不这样做。

他们训练它。他们意识到它“比他们目前提供的产品性能更好”。但他们不得不承认它“尚未取得足够的进步来证明维持其运行的巨大成本是合理的”。（这种措辞是否听起来很熟悉？这是 [一个月前《华尔街日报》对 GPT-5 的报道](https://www.wsj.com/tech/ai/openai-gpt5-orion-delays-639e7693)。与 [《彭博社》](https://www.bloomberg.com/news/articles/2024-11-13/openai-google-and-anthropic-are-struggling-to-build-more-advanced-ai) 对 Opus 3.5 的评价惊人地相似。）

他们报告了不尽如人意的结果（或多或少是准确的，他们总能操纵叙事）。他们将其保留在内部，作为一个大型的教师模型，用于蒸馏较小的学生模型。然后他们发布这些学生模型。我们得到了 Sonnet 3.6 以及 GPT-4o 和 o1，并对它们的廉价和出色感到非常满意。对 Opus 3.5 和 GPT-5 的期待仍然存在，即使我们的不耐烦日益增长。而他们的腰包却像金矿一样闪闪发光。

当我到达研究的这个阶段时，我仍然不相信。当然，所有的证据都表明这对 OpenAI 来说完全合理，但某种事物合理——甚至是可能的——与它是真实的之间存在差距。我不会为你弥合这个差距——毕竟，这仅仅是猜测。但我可以进一步加强论证。

是否有任何额外的证据表明 OpenAI 以这种方式运作？除了性能不佳和损失不断增加之外，他们还有更多理由扣留 GPT-5 吗？我们能从 OpenAI 高管关于 GPT-5 的公开声明中提取出什么信息？他们反复推迟发布模型，难道不会冒着损害声誉的风险吗？毕竟，OpenAI 是 AI 革命的代表，而 Anthropic 则在其阴影下运作。Anthropic 可以承担得起这些举动，但 OpenAI 呢？也许代价不菲。

说到钱，让我们挖掘一些关于 OpenAI-微软合作关系的相关细节。首先，这是每个人都知道的事实：AGI 条款。在 [OpenAI 关于其结构的博客文章](https://openai.com/our-structure/) 中，他们有五个治理条款，界定了其运作方式、与非营利组织、董事会以及微软的关系。第五条条款将 AGI 定义为“一种高度自主的系统，在大多数具有经济价值的工作方面超越人类”，并规定一旦 OpenAI 董事会声称已经实现了 AGI，“这样的系统将不包括在与微软的知识产权许可和其他商业条款中，这些条款仅适用于 AGI 之前的技术。”

毋庸置疑，两家公司都不希望合作关系破裂。OpenAI 设定了这一条款，但会尽一切努力避免遵守它。其中一种方法是推迟发布可能被标记为 AGI 的系统。“但 GPT-5 肯定不是 AGI，” 你会说。我会说，这里有第二个事实，几乎无人知晓：OpenAI 和微软 [对 AGI 有一个秘密的定义](https://www.theinformation.com/articles/microsoft-and-openais-secret-agi-definition?rc=j0xnsg)，尽管与科学目的无关，但它在法律层面上界定了他们的合作关系：AGI 是一种“可以产生至少 1000 亿美元利润”的 AI 系统。

如果 OpenAI 假设性地以 GPT-5 尚未准备就绪为借口而扣留它，那么除了成本控制和防止公众强烈反对之外，他们还将实现一件事：他们可以避免声明它是否符合 AGI 的分类门槛。虽然 1000 亿美元的利润是一个天文数字，但没有什么可以阻止有雄心的客户在其基础上构建应用并赚取如此多的利润。另一方面，让我们明确一点：如果 OpenAI 预测 GPT-5 的年度经常性收入将达到 1000 亿美元，他们不会介意触发 AGI 条款并与微软分道扬镳。

大多数公众对 OpenAI 未发布 GPT-5 的反应都基于这样的假设，即他们不发布是因为它不够好。即使这是真的，也没有哪个怀疑论者停下来思考过，OpenAI 可能有比从外部获得收益更好的内部用例。创造一个优秀的模型和创造一个可以廉价地提供给 3 亿用户的优秀模型之间存在巨大的差异。如果做不到，你就不会发布。而且，如果 *你不需要*，你也不会发布。他们过去向我们提供他们最好的模型是因为他们需要我们的数据。现在已经不那么需要了。他们也没有追逐我们的金钱。那是微软在做的事情，而不是他们。他们想要 AGI，然后是 ASI。他们想要留下历史印记。

![](https://substackcdn.com/image/fetch/w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F1a0060b5-47fd-47cc-a4f5-87f5b7c24c86_917x516.png)

我们即将结束。我相信我已经提出了足够的论据来证明一个可靠的观点：OpenAI 很可能在内部运行着 GPT-5，就像 Anthropic 内部运行着 Opus 3.5 一样。甚至有可能 OpenAI 永远不会发布 GPT-5。公众现在衡量性能的标准是 o1/o3，而不仅仅是 GPT-4o 或 Claude Sonnet 3.6。随着 OpenAI 探索测试时规模定律，GPT-5 需要跨越的门槛越来越高。他们如何才能发布一个真正超越 o1、o3 以及即将推出的 o 系列模型的 GPT-5 呢？更何况，他们不再需要我们的钱或我们的数据了。

训练新的基础模型——GPT-5、GPT-6 以及更远——对于 OpenAI 内部而言始终是有意义的，但不一定作为产品推出。那种模式可能已经结束了。他们现在唯一重要的目标是继续为下一代模型生成更好的数据。从今往后，基础模型可能会在后台运行，赋能其他模型实现它们自身无法完成的壮举——就像一位隐居深山的智者传授智慧，只不过这个山洞是一个巨大的数据中心。无论我们是否能见到他，我们都将体验到他智慧带来的影响。

![](https://substackcdn.com/image/fetch/w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F1e3d9c90-a653-461e-b6aa-49ac780ff715_725x393.png)

即使 GPT-5 最终发布，这个事实似乎也无关紧要了。如果 OpenAI 和 Anthropic 真的启动了 *递归式自我提升* 行动（尽管仍有人工参与），那么他们公开提供什么就无关紧要了。他们会越来越遥遥领先——就像宇宙以如此快的速度膨胀，以至于遥远星系的光芒再也无法到达我们。

或许这就是 OpenAI 如何在 [短短三个月内](https://x.com/_jasonwei/status/1870184982007644614) 从 o1 跃升到 o3 的原因。以及他们将如何跃升到 o4 和 o5。这可能也是他们最近在社交媒体上如此兴奋的原因。因为他们已经实施了一种新的、改进的运作模式。

你真的认为接近 AGI 意味着你可以在指尖获得越来越强大的 AI 吗？他们会将每一项进展都发布供我们使用吗？当然，你不会相信吧。当他们说他们的模型会让他们遥遥领先，以至于无人能及的时候，他们是认真的。每一代新模型都是一个挣脱束缚的引擎。从同温层，他们已经在挥手告别了。

他们是否会返回，仍有待观察。

原文连接：https://www.thealgorithmicbridge.com/p/this-rumor-about-gpt-5-changes-everything