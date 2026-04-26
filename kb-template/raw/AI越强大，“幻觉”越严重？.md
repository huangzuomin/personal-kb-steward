---
title: A.I. Hallucinations Are Getting Worse, Even as New Systems Become More Powerful
source: https://www.nytimes.com/2025/05/05/technology/ai-hallucinations-chatgpt-google.html
author:
  - "[[By Cade Metz and Karen Weise]]"
published: 2025-05-05
created: 2025-05-07
description: A new wave of “reasoning” systems from companies like OpenAI is producing incorrect information more often. Even the companies don’t know why.
tags: clippings
category: hive-180932
permlink: 20250509t152951977z
---
上个月，为计算机程序员提供[一款新兴工具 Cursor](https://www.cursor.com/) 的一个人工智能机器人，向几位客户发送了关于公司政策变更的通知。它声称客户不再被允许在多于一台电脑上使用 Cursor。

客户们在[互联网留言板](https://news.ycombinator.com/item?id=43683012)上愤怒地发帖抱怨。一些人取消了他们的 Cursor 账户。当他们意识到发生了什么时，一些人变得更加愤怒：这个人工智能机器人宣布了一项根本不存在的政策变更。

“我们没有这样的政策。你们当然可以在多台机器上自由使用 Cursor，”该公司首席执行官兼联合创始人 Michael Truell 在一篇 Reddit 帖子中[写道](https://old.reddit.com/r/cursor/comments/1jyy5am/psa_cursor_now_restricts_logins_to_a_single/)。“不幸的是，这是前线人工智能支持机器人给出的错误回复。”

在 [ChatGPT 问世](https://www.nytimes.com/2022/12/10/technology/ai-chat-bot-chatgpt.html)两年多后，科技公司、上班族和普通消费者正在使用人工智能机器人处理越来越广泛的任务。但目前仍然[无法确保这些系统生成准确的信息](https://www.nytimes.com/2023/05/01/business/ai-chatbots-hallucination.html)。

最新、最强大的技术——来自 OpenAI、Google 和中国初创公司 DeepSeek 等公司的所谓[推理系统](https://www.nytimes.com/2025/03/26/technology/ai-reasoning-chatgpt-deepseek.html)——正在产生更多错误，而不是更少。尽管它们的数学能力显著提高，但对事实的把握却变得更加不稳定。原因尚不完全清楚。

当今的人工智能机器人基于[复杂的数学系统](https://www.nytimes.com/2018/03/06/technology/google-artificial-intelligence.html)，它们通过分析海量数字数据来学习技能。它们不会——也无法——判断什么是真的，什么是假的。有时，它们只是凭空捏造信息，这种现象被一些人工智能研究人员称为“幻觉”（hallucinations）。在一项测试中，较新的人工智能系统的幻觉率高达 79%。

这些系统使用数学概率来猜测最佳回复，而不是由人类工程师定义的一套严格规则。因此，它们会犯一定数量的错误。“尽管我们尽了最大努力，它们总是会产生幻觉，”为企业构建人工智能工具的初创公司 Vectara 的首席执行官、前 Google 高管 Amr Awadallah 说。“这永远不会消失。”

![Amr Awadallah, wearing a blue shirt, looks at a large computer monitor.](https://static01.nyt.com/images/2025/04/30/multimedia/00biz-hallucinations-Amr-1-mzvt/00biz-hallucinations-Amr-1-mzvt-mobileMasterAt3x.jpg?quality=75&auto=webp&disable=upscale&width=1800)

Vectara 首席执行官 Amr Awadallah 认为人工智能“幻觉”将持续存在。Vectara 是一家为企业构建人工智能工具的公司。图片来源：Cayce Clifford for The New York Times

几年来，这种现象引发了人们对这些系统可靠性的担忧。尽管它们在某些情况下很有用——比如[撰写学期论文](https://www.nytimes.com/2023/01/16/technology/chatgpt-artificial-intelligence-universities.html)、总结办公文档和[生成计算机代码](https://www.nytimes.com/2021/09/09/technology/codex-artificial-intelligence-coding.html)——但它们的错误可能会导致问题。

与 Google 和 Bing 等搜索引擎相关联的人工智能机器人有时会生成令人啼笑皆非的错误搜索结果。如果你问它们西海岸最好的马拉松比赛，它们可能会推荐费城的一场比赛。如果它们告诉你伊利诺伊州的家庭数量，它们可能会引用一个不包含该信息的来源。

这些幻觉对许多人来说可能不是大问题，但对于使用该技术处理法院文件、医疗信息或敏感商业数据的人来说，这是一个严重的问题。

“你需要花费大量时间来弄清楚哪些回复是事实，哪些不是，”帮助企业应对幻觉问题的公司 [Okahu](https://www.okahu.ai/) 的联合创始人兼首席执行官 Pratik Verma 说。“未能正确处理这些错误基本上消除了人工智能系统的价值，因为它们本应为你自动化任务。”

Cursor 和 Mr. Truell 没有回应置评请求。

两年多来，OpenAI 和 Google 等公司稳步改进了他们的人工智能系统，并降低了这些错误的发生频率。但随着新的[推理系统](https://www.nytimes.com/2025/03/26/technology/ai-reasoning-chatgpt-deepseek.html)的使用，错误正在增加。根据 OpenAI 自己的测试，其最新的系统比该公司之前的系统幻觉率更高。

该公司发现，在其 PersonQA 基准测试（涉及回答关于公众人物的问题）中，其最强大的系统 o3 幻觉率为 33%。这比 OpenAI 之前的推理系统 o1 的幻觉率高出一倍多。新的 o4-mini 的幻觉率甚至更高：48%。

在运行另一项名为 SimpleQA 的测试（提出更一般的问题）时，o3 和 o4-mini 的幻觉率分别为 51% 和 79%。之前的系统 o1 的幻觉率为 44%。

![A hand holds a smartphone open to the ChatGPT chatbot.](https://static01.nyt.com/images/2025/04/30/multimedia/00biz-hallucinations-chatgpt-vtgf/00biz-hallucinations-chatgpt-vtgf-mobileMasterAt3x.jpg?quality=75&auto=webp&disable=upscale&width=1800)

自 ChatGPT 问世以来，幻觉现象引发了人们对人工智能系统可靠性的担忧。图片来源：Kelsey McClellan for The New York Times

在[详细介绍这些测试的一篇论文](https://cdn.openai.com/pdf/2221c875-02dc-4789-800b-e7758f3722c1/o3-and-o4-mini-system-card.pdf)中，OpenAI 表示需要更多研究来理解这些结果的原因。由于人工智能系统从比人类能够理解的更多数据中学习，技术人员很难确定它们为何会以某种方式行事。

“幻觉在推理模型中并非固有地更普遍，尽管我们正在积极努力降低在 o3 和 o4-mini 中看到的更高幻觉率，”公司发言人 Gaby Raila 说。“我们将继续对所有模型的幻觉进行研究，以提高准确性和可靠性。”

华盛顿大学教授、艾伦人工智能研究所研究员 Hannaneh Hajishirzi 是一个团队的成员，该团队最近设计了一种方法，可以将系统的行为追溯到[其训练所用的单个数据片段](https://allenai.org/blog/olmotrace)。但由于系统从如此多的数据中学习——而且它们几乎可以生成任何内容——这个新工具无法解释所有事情。“我们仍然不完全知道这些模型是如何工作的，”她说。

独立公司和研究人员的测试表明，Google 和 DeepSeek 等公司的推理模型的幻觉率也在上升。

自 2023 年底以来，Mr. Awadallah 的公司 Vectara [一直在追踪聊天机器人偏离事实的频率](https://github.com/vectara/hallucination-leaderboard)。该公司要求这些系统执行一项易于验证的简单任务：总结特定的新闻文章。即便如此，聊天机器人仍然持续捏造信息。

Vectara 最初的研究估计，在这种情况下，聊天机器人至少有 3% 的时间会捏造信息，有时甚至高达 27%。

在过去的一年半里，OpenAI 和 Google 等公司将这些数字降至 1% 或 2% 的范围。其他公司，如旧金山初创公司 Anthropic，徘徊在 4% 左右。但推理系统在这项测试中的幻觉率有所上升。DeepSeek 的推理系统 R1 的幻觉率为 14.3%。OpenAI 的 o3 攀升至 6.8%。

（《纽约时报》已[起诉](https://www.nytimes.com/2023/12/27/business/media/new-york-times-open-ai-microsoft-lawsuit.html) OpenAI 及其合作伙伴 Microsoft，指控它们在与人工智能系统相关的新闻内容方面侵犯版权。OpenAI 和 Microsoft 否认了这些指控。）

多年来，OpenAI 等公司依赖一个简单的概念：他们向人工智能系统输入越多的互联网数据，[这些系统的表现就越好](https://www.nytimes.com/2024/04/06/technology/tech-giants-harvest-data-artificial-intelligence.html)。但他们[几乎用尽了互联网上所有的英文文本](https://www.nytimes.com/2024/12/19/technology/artificial-intelligence-data-openai-google.html)，这意味着他们需要一种新的方法来改进他们的聊天机器人。

因此，这些公司更加依赖科学家们称之为强化学习的技术。通过这个过程，系统可以通过试错来学习行为。这在某些领域效果很好，比如数学和计算机编程。但在其他领域却表现不佳。

“这些系统的训练方式是，它们会开始专注于一项任务——然后开始忘记其他任务，”爱丁堡大学研究员 Laura Perez-Beltrachini 说，她是[一个密切研究幻觉问题的团队](https://arxiv.org/abs/2404.05904)的成员。

另一个问题是，推理模型被设计用来在得出答案之前花费时间“思考”复杂问题。当它们试图一步一步解决问题时，它们在每一步都有产生幻觉的风险。随着思考时间的增加，错误可能会累积。

最新的机器人会向用户展示每一步，这意味着用户也可能会看到每一个错误。研究人员还发现，在许多情况下，机器人显示的步骤与[它最终给出的答案无关](https://www.anthropic.com/research/reasoning-models-dont-say-think)。

“系统声称它在思考的内容不一定就是它实际在思考的内容，”爱丁堡大学人工智能研究员、Anthropic 研究员 Aryo Pradipta Gema 说。