---
title: "Building an AI-Powered News Aggregator: My First n8n Workflow"
source: "https://medium.com/%40learningsomethingnew/building-an-ai-powered-news-aggregator-my-first-n8n-workflow-40cf3753a387"
author:
  - "[[Joe Taylor]]"
published: 2024-09-11
created: 2025-06-04
description: "I recently discovered n8n, which piqued my interest in the world of workflow automation tools. While friends had previously mentioned Zappier and Make, I was hesitant to commit to another $20 monthly…"
tags:
  - "clippings"
---
[Sitemap](https://medium.com/sitemap/sitemap.xml)

## TL;DR

- 创建了一个 n8n 工作流，用于从多个来源聚合和分析科技新闻
- 工作流获取 RSS 订阅源，筛选与 AI 相关的内容，并生成详细文章
- 利用 OpenAI 的 GPT 模型等 AI 服务进行内容分析和文章生成
- 展示了工作流自动化在内容策划与创作中的强大能力

## 引言

最近我发现了 n8n，这让我对工作流自动化工具的世界产生了浓厚兴趣。虽然朋友们之前提到过 [Zappier](https://zapier.com/) 和 [Make](https://www.make.com/en) ，但我一直犹豫是否要再支付每月 20 美元的订阅费用。

[n8n](https://n8n.io/) 却因两个引人注目的原因吸引了我的注意：

1. 它提供了自托管选项
2. 它在 GitHub 上拥有超过 45,000 颗星，令人印象深刻

对于那些更倾向于使用托管服务的用户，还有一个付费版本，这让我想起了 Supabase，我对它的使用体验相当不错。我尤其被那些允许我托管核心平台并根据需要调整代码的项目所吸引。

出于对 n8n 潜力的浓厚兴趣，我决定创建我的第一个工作流，以解决一个紧迫问题：我收件箱中铺天盖地的 AI 相关新闻。

我的 Gmail 账户几乎要被大量未打开的邮件通知撑爆了。

我的目标是实现收集、筛选和总结 AI 新闻流程的自动化。跟随我一起探索如何利用 n8n 来驯服我那混乱的收件箱，并紧跟 AI 领域的最新发展动态…

## 最终输出的快速截图：

![](https://miro.medium.com/v2/resize:fit:640/format:webp/1*ZtVb7e-tl8NXDcwirsEScA.png)

定制新闻源的梦想

![](https://miro.medium.com/v2/resize:fit:640/format:webp/1*9Vu-SuOjtELFe4e-BBSDvQ.png)

配备 AI 摘要功能

![](https://miro.medium.com/v2/resize:fit:640/format:webp/1*jS1CMa-xWJyHKqO2H1dV8A.png)

这将引用来源

## 什么是 n8n？

在深入探讨工作流细节之前，让我们先简单介绍一下 n8n 是什么。n8n（发音为“n-eight-n”）是一个开源的工作流自动化工具，它允许你连接各种服务并自动化任务，而无需编写代码。它提供了一个可视化界面，通过链接不同的节点来创建复杂的工作流，每个节点代表一个特定的操作或服务。

## 工作流程概述

再次，手头的任务是清理我的 Gmail 账户，而一个突出的关键用例是利用 AI 总结所有与 AI 相关的关键新闻头条。这样我就可以取消订阅所有这些通知。

我决定构建一个 n8n 工作流，它将：

1. 从多个新闻源获取 RSS 订阅
2. 解析 RSS 内容
3. 筛选与 AI 相关的文章
4. 快速在互联网上搜索该主题
5. 利用 AI 基于互联网搜索结果生成扩展文章
6. 将结果保存到数据库
7. 发布到网站

让我们逐一分解工作流的每个组件。

![](https://miro.medium.com/v2/resize:fit:640/format:webp/1*mFdGD268e2CoAmPMn_iFZA.png)

完整工作流程

## 获取 RSS 订阅源

工作流程首先从几个知名科技新闻来源获取 RSS 订阅源：

- 《纽约时报》（科技版块）
- 《金融时报》
- BBC 新闻（科技版块）
- 《华盛顿邮报》（科技版块）
- 《华尔街日报》（科技版块）

这是通过使用“HTTP 请求”节点来实现的，这些节点被配置为从每个 RSS 订阅源 URL 获取 XML 内容。

## 解析 RSS 内容

获取 RSS 源后，工作流使用“XML”节点将 XML 内容解析为结构化格式，以便在后续步骤中轻松处理。

## 筛选与人工智能相关的内容

这个工作流最有趣的一个方面是它能够筛选与人工智能相关的内容。这是通过使用 OpenAI 的 GPT 模型实现的。对于 RSS 订阅源中的每篇文章：

1. 标题和内容片段已提取
2. GPT4o-mini 被提示判断文章是否与 AI 相关
3. 如果文章被判定为与 AI 相关，则进入下一阶段；否则，跳过该文章

这一过滤步骤确保了只有相关的人工智能新闻能够通过流程。我曾考虑通过 Groq 使用 Llama 3.1 70b，尽管我是 Groq 的忠实粉丝，但其速率限制使得该平台几乎无法使用。我真心希望他们能推出付费选项，目前看来这似乎仅适用于付费企业账户。

## 生成扩展文章

对于通过 AI 相关筛选的文章，工作流程更进一步，生成扩展后的、更为详尽的文章。这一过程通过结合多种服务实现：

1. [JinaAI](https://jina.ai/) 搜索被采用——对此我赞不绝口。我在多个项目中使用了他们的服务，均未遇到任何问题。
2. 原始文章片段与搜索结果一同输入到 OpenAI GPT4o-mini 中。我确实测试了其他模型，但在文章输出质量上并未观察到太大差异。当然，GPT-4o 表现更佳，Sonnet 也是如此，但差异并不足以让我愿意支付 16 到 20 倍的费用。
3. 随后，AI 生成了一篇详尽的文章，内容包括：
- 一个简短的总结部分
- Markdown 格式化
- 正确引用
- 包含关键词的元数据部分

此步骤将简短的新闻片段转化为完整的文章，为读者（即我本人）提供更多的背景信息和深度内容。

## 保存结果

工作流程的最后一步是将生成的新闻文章和元数据保存到数据库中。该工作流程使用了 Supabase，这是我目前首选的数据库选项。

- 原始 RSS 项目详情
- AI 生成的文章内容
- 相关元数据，如发布日期、来源和图片 URL

## 工作流调度

为了保持新闻源的时效性，整个工作流程通过 n8n 的“定时触发器”节点定期运行。这确保了新文章能够被定期抓取、处理并添加到数据库中。

## 成功了吗？

于是，在这之后，我得以运行工作流并审视结果……对此我相当满意。执行工作流后，我观察到生成了 53 篇文章，每篇成本仅为 0.007 美元。此外，我还注意到 AI 生成的文章与原出版商发布的实际文章在实质内容上并无显著差异……鉴于此，我实在找不出理由继续每月在这些新闻平台上花费 99 美元，既然我只需将标题和谷歌搜索结果输入 OpenAI 的基础模型即可。这不禁让人深思传统新闻业基础设施的未来究竟何在。

这个话题改天再写一篇文章讨论。

## 代码：

```c
{
  "meta": {
    "instanceId": "2b378d4b73951813863a038ece98d49c1d584c4e4ec592c16ed4a68cc5f28162"
  },
  "nodes": [
    {
      "parameters": {
        "url": "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml",
        "options": {}
      },
      "id": "aeccb68b-d6da-4f28-988f-56252884351a",
      "name": "HTTP Request1",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4.2,
      "position": [
        1060,
        760
      ]
    },
    {
      "parameters": {
        "options": {}
      },
      "id": "1955e9a6-1063-4cba-b3ca-40df6fd390c0",
      "name": "XML1",
      "type": "n8n-nodes-base.xml",
      "typeVersion": 1,
      "position": [
        1280,
        760
      ]
    },
    {
      "parameters": {
        "fieldToSplitOut": "rss.channel.item",
        "options": {}
      },
      "id": "144bfd63-7f64-49b8-bc11-1f309914d46b",
      "name": "Split Out1",
      "type": "n8n-nodes-base.splitOut",
      "typeVersion": 1,
      "position": [
        1500,
        760
      ]
    },
    {
      "parameters": {
        "options": {}
      },
      "id": "9f45e2b0-418d-4362-b8d6-28534522d300",
      "name": "Loop Over Items2",
      "type": "n8n-nodes-base.splitInBatches",
      "typeVersion": 3,
      "position": [
        1740,
        760
      ]
    },
    {
      "parameters": {
        "url": "=https://s.jina.ai/ {{ encodeURIComponent($json.title) }}",
        "options": {}
      },
      "id": "69b20423-d9ed-4be7-b973-dc0f4ed0c8da",
      "name": "JinaAI Search3",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4.2,
      "position": [
        3100,
        800
      ]
    },
    {
      "parameters": {
        "model": "gpt-4o-mini-2024-07-18",
        "options": {}
      },
      "id": "d81fd6ae-ab6f-4239-9ed4-ce20f1704273",
      "name": "OpenAI Chat Model5",
      "type": "@n8n/n8n-nodes-langchain.lmChatOpenAi",
      "typeVersion": 1,
      "position": [
        3320,
        1020
      ],
      "credentials": {
        "openAiApi": {
          "id": "",
          "name": "OpenAi"
        }
      }
    },
    {
      "parameters": {
        "tableId": "ai_articles",
        "fieldsUi": {
          "fieldValues": [
            {
              "fieldId": "rss_feed_id",
              "fieldValue": "={{ $('Supabase3').item.json.id }}"
            },
            {
              "fieldId": "title",
              "fieldValue": "={{ $('Supabase3').item.json.title }}"
            },
            {
              "fieldId": "content",
              "fieldValue": "={{ $json.text }}"
            }
          ]
        }
      },
      "id": "857b7101-40f6-419f-91b6-02031c622e20",
      "name": "Save Article3",
      "type": "n8n-nodes-base.supabase",
      "typeVersion": 1,
      "position": [
        3660,
        800
      ],
      "credentials": {
        "supabaseApi": {
          "id": "",
          "name": "Supabase"
        }
      },
      "onError": "continueRegularOutput"
    },
    {
      "parameters": {
        "model": "gpt-4o-mini-2024-07-18",
        "options": {}
      },
      "id": "83745ea7-fdb7-4c05-b4de-9965feed5585",
      "name": "OpenAI Chat Model6",
      "type": "@n8n/n8n-nodes-langchain.lmChatOpenAi",
      "typeVersion": 1,
      "position": [
        2340,
        1060
      ],
      "credentials": {
        "openAiApi": {
          "id": "",
          "name": "OpenAi"
        }
      }
    },
    {
      "parameters": {
        "tableId": "rss_feed",
        "fieldsUi": {
          "fieldValues": [
            {
              "fieldId": "title",
              "fieldValue": "={{ $json.title }}"
            },
            {
              "fieldId": "link",
              "fieldValue": "={{ $json.link }}"
            },
            {
              "fieldId": "pub_date",
              "fieldValue": "={{ $json.pubDate }}"
            },
            {
              "fieldId": "content",
              "fieldValue": "={{ $json.description }}"
            },
            {
              "fieldId": "content_snippet",
              "fieldValue": "={{ $json.description }}"
            },
            {
              "fieldId": "guid",
              "fieldValue": "={{ $json.guid }}"
            },
            {
              "fieldId": "categories",
              "fieldValue": "={{ $json.category }}"
            },
            {
              "fieldId": "img_url",
              "fieldValue": "={{ $json['media:content'].url }}"
            },
            {
              "fieldId": "source",
              "fieldValue": "The New York Times"
            }
          ]
        }
      },
      "id": "e9ca40cd-43b1-40ba-80fa-ea501156ccba",
      "name": "Create RSS Item2",
      "type": "n8n-nodes-base.supabase",
      "typeVersion": 1,
      "position": [
        1960,
        780
      ],
      "credentials": {
        "supabaseApi": {
          "id": "",
          "name": "Supabase"
        }
      },
      "onError": "continueRegularOutput"
    },
    {
      "parameters": {
        "conditions": {
          "options": {
            "caseSensitive": true,
            "leftValue": "",
            "typeValidation": "strict"
          },
          "conditions": [
            {
              "id": "8e8ff64b-e59c-415c-af8b-211d7a7d144c",
              "leftValue": "={{ $json.text }}",
              "rightValue": "true",
              "operator": {
                "type": "string",
                "operation": "contains"
              }
            }
          ],
          "combinator": "and"
        },
        "options": {}
      },
      "id": "9ac40e39-9621-489e-9df0-d252447f8b68",
      "name": "If - Is AI2",
      "type": "n8n-nodes-base.if",
      "typeVersion": 2,
      "position": [
        2640,
        840
      ]
    },
    {
      "parameters": {
        "conditions": {
          "options": {
            "caseSensitive": true,
            "leftValue": "",
            "typeValidation": "strict"
          },
          "conditions": [
            {
              "id": "8e8ff64b-e59c-415c-af8b-211d7a7d144c",
              "leftValue": "={{ $json.error }}",
              "rightValue": "",
              "operator": {
                "type": "string",
                "operation": "exists",
                "singleValue": true
              }
            }
          ],
          "combinator": "and"
        },
        "options": {}
      },
      "id": "950f2e2e-db05-4925-9d02-8d8e80a65cfc",
      "name": "If - Exists Already2",
      "type": "n8n-nodes-base.if",
      "typeVersion": 2,
      "position": [
        2120,
        780
      ]
    },
    {
      "parameters": {
        "operation": "update",
        "tableId": "rss_feed",
        "filters": {
          "conditions": [
            {
              "keyName": "id",
              "condition": "eq",
              "keyValue": "={{ $('Create RSS Item2').item.json.id }}"
            }
          ]
        },
        "fieldsUi": {
          "fieldValues": [
            {
              "fieldId": "should_draft_article",
              "fieldValue": "True"
            }
          ]
        }
      },
      "id": "b7ae19a7-58a6-41b7-b674-b37f98c0dc84",
      "name": "Supabase3",
      "type": "n8n-nodes-base.supabase",
      "typeVersion": 1,
      "position": [
        2900,
        800
      ],
      "credentials": {
        "supabaseApi": {
          "id": "",
          "name": "Supabase"
        }
      }
    },
    {
      "parameters": {
        "rule": {
          "interval": [
            {
              "field": "cronExpression",
              "expression": "*/30 8-20 * * *"
            }
          ]
        }
      },
      "id": "ec09f75c-4140-4309-8a4e-0421cbd2b415",
      "name": "Schedule Trigger",
      "type": "n8n-nodes-base.scheduleTrigger",
      "typeVersion": 1.2,
      "position": [
        320,
        -320
      ]
    },
    {
      "parameters": {
        "promptType": "define",
        "text": "=Analyze the following article headline and content snippet.  \n\nDetermin if it is AI related.\n\nout put single word as either true or false\n\ndo not output codeblocks or markdown, just the word true or false.\n\n<article_title>\n{{ $('Create RSS Item2').item.json.title }}\n</article_title>\n\n<article_snippet>\n{{ $('Create RSS Item2').item.json.content_snippet }}\n</article_snippet>",
        "hasOutputParser": true
      },
      "id": "8a5caac9-a1a1-4e52-a232-c79d58cd23a6",
      "name": "Is AI Related2",
      "type": "@n8n/n8n-nodes-langchain.chainLlm",
      "typeVersion": 1.4,
      "position": [
        2320,
        840
      ]
    },
    {
      "parameters": {
        "url": "https://www.ft.com/myft/following/6362d893-8d20-4ab6-b60f-4fcfc8c3e3fc.rss",
        "options": {}
      },
      "id": "f7ec7c24-99f1-4dd6-b9e8-46286a7393c2",
      "name": "HTTP Request",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4.2,
      "position": [
        1060,
        1220
      ]
    },
    {
      "parameters": {
        "options": {}
      },
      "id": "6262922a-11b1-4a8f-a942-f38272f51a91",
      "name": "XML",
      "type": "n8n-nodes-base.xml",
      "typeVersion": 1,
      "position": [
        1280,
        1220
      ]
    },
    {
      "parameters": {
        "fieldToSplitOut": "rss.channel.item",
        "options": {}
      },
      "id": "105bfd4d-34de-488c-94a2-bbe3f6ceff26",
      "name": "Split Out",
      "type": "n8n-nodes-base.splitOut",
      "typeVersion": 1,
      "position": [
        1500,
        1220
      ]
    },
    {
      "parameters": {
        "options": {}
      },
      "id": "9d8db46f-a393-41f3-aa0e-b6eb8ffbf3e8",
      "name": "Loop Over Items3",
      "type": "n8n-nodes-base.splitInBatches",
      "typeVersion": 3,
      "position": [
        1740,
        1220
      ]
    },
    {
      "parameters": {
        "url": "=https://s.jina.ai/ {{ encodeURIComponent($json.title) }}",
        "options": {}
      },
      "id": "84b870bf-536b-4a8d-ae57-7fa74ab14764",
      "name": "JinaAI Search4",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4.2,
      "position": [
        3340,
        1260
      ]
    },
    {
      "parameters": {
        "model": "gpt-4o-mini-2024-07-18",
        "options": {}
      },
      "id": "51d2dd1a-8d9c-46ec-85c0-b73d2b4d5820",
      "name": "OpenAI Chat Model7",
      "type": "@n8n/n8n-nodes-langchain.lmChatOpenAi",
      "typeVersion": 1,
      "position": [
        3560,
        1480
      ],
      "credentials": {
        "openAiApi": {
          "id": "",
          "name": "OpenAi"
        }
      }
    },
    {
      "parameters": {
        "tableId": "ai_articles",
        "fieldsUi": {
          "fieldValues": [
            {
              "fieldId": "rss_feed_id",
              "fieldValue": "={{ $('Supabase4').item.json.id }}"
            },
            {
              "fieldId": "title",
              "fieldValue": "={{ $('Supabase4').item.json.title }}"
            },
            {
              "fieldId": "content",
              "fieldValue": "={{ $json.text }}"
            }
          ]
        }
      },
      "id": "db8701c4-dc15-492c-91d0-7ebb86794be3",
      "name": "Save Article4",
      "type": "n8n-nodes-base.supabase",
      "typeVersion": 1,
      "position": [
        3900,
        1260
      ],
      "credentials": {
        "supabaseApi": {
          "id": "",
          "name": "Supabase"
        }
      },
      "onError": "continueRegularOutput"
    },
    {
      "parameters": {
        "model": "gpt-4o-mini-2024-07-18",
        "options": {}
      },
      "id": "0c90c9fb-a9b0-48a7-8560-78531663c04b",
      "name": "OpenAI Chat Model8",
      "type": "@n8n/n8n-nodes-langchain.lmChatOpenAi",
      "typeVersion": 1,
      "position": [
        2580,
        1520
      ],
      "credentials": {
        "openAiApi": {
          "id": "",
          "name": "OpenAi"
        }
      }
    },
    {
      "parameters": {
        "tableId": "rss_feed",
        "fieldsUi": {
          "fieldValues": [
            {
              "fieldId": "title",
              "fieldValue": "={{ $json.title }}"
            },
            {
              "fieldId": "link",
              "fieldValue": "={{ $json.link }}"
            },
            {
              "fieldId": "pub_date",
              "fieldValue": "={{ $json.pubDate }}"
            },
            {
              "fieldId": "content",
              "fieldValue": "={{ $json.descriptionText }}"
            },
            {
              "fieldId": "content_snippet",
              "fieldValue": "={{ $json.descriptionText }}"
            },
            {
              "fieldId": "guid",
              "fieldValue": "={{ $json.guid._ }}"
            },
            {
              "fieldId": "img_url",
              "fieldValue": "={{ $json.imageURL }}"
            },
            {
              "fieldId": "source",
              "fieldValue": "The Financial Times"
            }
          ]
        }
      },
      "id": "7185fa8c-b212-4742-9892-defc14a12c5e",
      "name": "Create RSS Item3",
      "type": "n8n-nodes-base.supabase",
      "typeVersion": 1,
      "position": [
        2180,
        1240
      ],
      "credentials": {
        "supabaseApi": {
          "id": "",
          "name": "Supabase"
        }
      },
      "onError": "continueRegularOutput"
    },
    {
      "parameters": {
        "conditions": {
          "options": {
            "caseSensitive": true,
            "leftValue": "",
            "typeValidation": "strict"
          },
          "conditions": [
            {
              "id": "8e8ff64b-e59c-415c-af8b-211d7a7d144c",
              "leftValue": "={{ $json.text }}",
              "rightValue": "true",
              "operator": {
                "type": "string",
                "operation": "contains"
              }
            }
          ],
          "combinator": "and"
        },
        "options": {}
      },
      "id": "77dfad1d-e155-4567-98b2-2a1818af9a05",
      "name": "If - Is AI3",
      "type": "n8n-nodes-base.if",
      "typeVersion": 2,
      "position": [
        2880,
        1300
      ]
    },
    {
      "parameters": {
        "conditions": {
          "options": {
            "caseSensitive": true,
            "leftValue": "",
            "typeValidation": "strict"
          },
          "conditions": [
            {
              "id": "8e8ff64b-e59c-415c-af8b-211d7a7d144c",
              "leftValue": "={{ $json.error }}",
              "rightValue": "",
              "operator": {
                "type": "string",
                "operation": "exists",
                "singleValue": true
              }
            }
          ],
          "combinator": "and"
        },
        "options": {}
      },
      "id": "6dbed84f-77c3-4793-aab2-bac773d49362",
      "name": "If - Exists Already3",
      "type": "n8n-nodes-base.if",
      "typeVersion": 2,
      "position": [
        2360,
        1240
      ]
    },
    {
      "parameters": {
        "operation": "update",
        "tableId": "rss_feed",
        "filters": {
          "conditions": [
            {
              "keyName": "id",
              "condition": "eq",
              "keyValue": "={{ $('Create RSS Item3').item.json.id }}"
            }
          ]
        },
        "fieldsUi": {
          "fieldValues": [
            {
              "fieldId": "should_draft_article",
              "fieldValue": "True"
            }
          ]
        }
      },
      "id": "8a18cac2-3458-45f5-8b84-4b523c478fb3",
      "name": "Supabase4",
      "type": "n8n-nodes-base.supabase",
      "typeVersion": 1,
      "position": [
        3140,
        1260
      ],
      "credentials": {
        "supabaseApi": {
          "id": "",
          "name": "Supabase"
        }
      }
    },
    {
      "parameters": {
        "promptType": "define",
        "text": "=Analyze the following article headline and content snippet.  \n\nDetermin if it is AI related.\n\nout put single word as either true or false\n\ndo not output codeblocks or markdown, just the word true or false.\n\n<article_title>\n{{ $('Create RSS Item3').item.json.title }}\n</article_title>\n\n<article_snippet>\n{{ $('Create RSS Item3').item.json.content_snippet }}\n</article_snippet>",
        "hasOutputParser": true
      },
      "id": "d2131dfe-13dc-4966-b0d0-358b14925175",
      "name": "Is AI Related3",
      "type": "@n8n/n8n-nodes-langchain.chainLlm",
      "typeVersion": 1.4,
      "position": [
        2560,
        1300
      ]
    },
    {
      "parameters": {
        "jsCode": "function processDescription(description) {\n  const imgSrcRegex = /<img.*?src=\"(.*?)\"/;\n  const imageURL = description.match(imgSrcRegex)?.[1] || '';\n\n  const textRegex = /<img.*?>(.*?)<br/;\n  const descriptionText = description.match(textRegex)?.[1]?.trim() || '';\n\n  return { imageURL, descriptionText };\n}\n\nconst processedItems = items.map(item => {\n  const { imageURL, descriptionText } = processDescription(item.json.description);\n  \n  return {\n    ...item.json,\n    imageURL,\n    descriptionText\n  };\n});\n\nreturn processedItems;"
      },
      "id": "af697f7f-ed41-47c9-a139-9ed15db669a3",
      "name": "Extract Img and Description",
      "type": "n8n-nodes-base.code",
      "typeVersion": 2,
      "position": [
        1980,
        1240
      ]
    },
    {
      "parameters": {
        "promptType": "define",
        "text": "=You are an AI assistant tasked with writing a news article based on an RSS title, content snippet, and reference material from a Google search. Follow these instructions carefully:\n\n1. You will be provided with an RSS title and content snippet from a news feed:\n\n   \`\`\`\n   <rss_title>\n  {{ $('Supabase4').item.json.title }}\n   </rss_title>\n\n   <content_snippet>\n  {{ $('Supabase4').item.json.content_snippet }}\n   </content_snippet>\n   \`\`\`\n\n2. You will also be given content from a Google search related to the headline:\n\n   \`\`\`\n   <google_search_content>\n{{ JSON.stringify($json.data.substring(0, 400000)) }}\n   </google_search_content>\n   \`\`\`\n\n3. Write an article that expands on the RSS headline and content snippet, using information from the Google search content. The article should be:\n   - Informative\n   - Engaging\n   - Well-structured\n\n4. Format the article using Markdown. Use appropriate Markdown syntax for:\n   - Headings (use ## for the main title, ### for subheadings)\n   - Paragraphs (separate with blank lines)\n   - Bold and italic text where appropriate\n   - Bullet points or numbered lists if needed\n   - Blockquotes for any direct quotes from sources\n\n5. Incorporate information from both the RSS headline/snippet and the Google search content:\n   - Use the headline to guide the main topic\n   - Use the search content to provide additional details and context\n\n6. Maintain a neutral, journalistic tone throughout the article:\n   - Present facts objectively\n   - Do not include personal opinions or biases\n   - Use third-person perspective\n\n7. Structure your article with:\n   - Begin with a TL;DR section. Provide quick bullet points that capture the highlights of the article.\n   - A compelling introduction that summarizes the key points\n   - A conclusion that wraps up the article and potentially suggests future implications\n\n8. If applicable, include:\n   - Relevant statistics or data points\n   - Brief mentions of key stakeholders or experts\n   - Context on why this news is important or impactful\n\n9. Use Wikipedia-style citations in Markdown format:\n   - In the text, use footnote-style references like [^1], [^2], etc.\n   - Use footnotes sequentially without skipping any numbers\n   - At the end of the article, include a ## References section\n   - Format each reference as follows:\n     [^1]: Author Name (if available) (Date). \"[Article Title](URL)\". Publication Name. Retrieved [Current Date].\n   - If an author name is not available, start with the article title\n   - Ensure all article titles are clickable links using Markdown syntax\n   - Include ALL sources provided in the Google search content in the References section, even if not directly cited in the text\n\n10. Begin your response with <article> and end it with </article>. The entire article, including the Markdown formatting and references, should be contained within these tags.\n\n11. After the article, provide a brief metadata section with:\n    - Main keywords or tags (do not include links in this section)\n\n12. Double-check your footnotes before completing the article:\n    - Ensure all footnote numbers used in the text have corresponding entries in the References section\n    - Verify that footnote numbers are sequential (1, 2, 3, etc.) without any gaps\n\nRemember to adhere to journalistic standards and ethics in your writing. Stick to the facts presented in the provided sources and avoid sensationalism."
      },
      "id": "855cb2d2-4104-44b5-aa7b-d6ae67558d29",
      "name": "Write Article4",
      "type": "@n8n/n8n-nodes-langchain.chainLlm",
      "typeVersion": 1.4,
      "position": [
        3540,
        1260
      ]
    },
    {
      "parameters": {
        "url": "https://feeds.bbci.co.uk/news/technology/rss.xml",
        "options": {}
      },
      "id": "024fe7f0-30ee-4482-9533-23f2c953b72d",
      "name": "HTTP Request2",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4.2,
      "position": [
        1060,
        1680
      ]
    },
    {
      "parameters": {
        "options": {}
      },
      "id": "f8e1920b-4a32-4b0f-a8dd-bfd30b027089",
      "name": "XML2",
      "type": "n8n-nodes-base.xml",
      "typeVersion": 1,
      "position": [
        1280,
        1680
      ]
    },
    {
      "parameters": {
        "fieldToSplitOut": "rss.channel.item",
        "options": {}
      },
      "id": "8dc0ce33-d166-4ec8-a990-d0d823689b6e",
      "name": "Split Out2",
      "type": "n8n-nodes-base.splitOut",
      "typeVersion": 1,
      "position": [
        1500,
        1680
      ]
    },
    {
      "parameters": {
        "options": {}
      },
      "id": "f699edfa-fd74-45aa-ac3f-3105ba10a509",
      "name": "Loop Over Items4",
      "type": "n8n-nodes-base.splitInBatches",
      "typeVersion": 3,
      "position": [
        1740,
        1680
      ]
    },
    {
      "parameters": {
        "url": "=https://s.jina.ai/ {{ encodeURIComponent($json.title) }}",
        "options": {}
      },
      "id": "a5fa0411-9818-460f-8691-a9f18a8d29d5",
      "name": "JinaAI Search5",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4.2,
      "position": [
        3180,
        1720
      ]
    },
    {
      "parameters": {
        "model": "gpt-4o-mini-2024-07-18",
        "options": {}
      },
      "id": "011a4dd6-78e8-42d3-ad75-25045006b419",
      "name": "OpenAI Chat Model9",
      "type": "@n8n/n8n-nodes-langchain.lmChatOpenAi",
      "typeVersion": 1,
      "position": [
        3300,
        1860
      ],
      "credentials": {
        "openAiApi": {
          "id": "",
          "name": "OpenAi"
        }
      }
    },
    {
      "parameters": {
        "model": "gpt-4o-mini-2024-07-18",
        "options": {}
      },
      "id": "39c9512a-3536-49de-9f1c-bbba719bf4cd",
      "name": "OpenAI Chat Model10",
      "type": "@n8n/n8n-nodes-langchain.lmChatOpenAi",
      "typeVersion": 1,
      "position": [
        2300,
        1840
      ],
      "credentials": {
        "openAiApi": {
          "id": "",
          "name": "OpenAi"
        }
      }
    },
    {
      "parameters": {
        "tableId": "rss_feed",
        "fieldsUi": {
          "fieldValues": [
            {
              "fieldId": "title",
              "fieldValue": "={{ $json.title }}"
            },
            {
              "fieldId": "link",
              "fieldValue": "={{ $json.link }}"
            },
            {
              "fieldId": "pub_date",
              "fieldValue": "={{ $json.pubDate }}"
            },
            {
              "fieldId": "content",
              "fieldValue": "={{ $json.description }}"
            },
            {
              "fieldId": "content_snippet",
              "fieldValue": "={{ $json.description }}"
            },
            {
              "fieldId": "img_url",
              "fieldValue": "={{ $json['media:thumbnail'].url }}"
            },
            {
              "fieldId": "source",
              "fieldValue": "BBC News"
            },
            {
              "fieldId": "guid",
              "fieldValue": "={{ $json.guid._ }}"
            }
          ]
        }
      },
      "id": "fbdd03b2-3676-47e3-a3bd-fa23a6d4dff7",
      "name": "Create RSS Item4",
      "type": "n8n-nodes-base.supabase",
      "typeVersion": 1,
      "position": [
        2000,
        1700
      ],
      "credentials": {
        "supabaseApi": {
          "id": "",
          "name": "Supabase"
        }
      },
      "onError": "continueRegularOutput"
    },
    {
      "parameters": {
        "conditions": {
          "options": {
            "caseSensitive": true,
            "leftValue": "",
            "typeValidation": "strict"
          },
          "conditions": [
            {
              "id": "8e8ff64b-e59c-415c-af8b-211d7a7d144c",
              "leftValue": "={{ $json.text }}",
              "rightValue": "true",
              "operator": {
                "type": "string",
                "operation": "contains"
              }
            }
          ],
          "combinator": "and"
        },
        "options": {}
      },
      "id": "246801e0-54a2-41f3-94df-7d59f6bf6c58",
      "name": "If - Is AI4",
      "type": "n8n-nodes-base.if",
      "typeVersion": 2,
      "position": [
        2720,
        1760
      ]
    },
    {
      "parameters": {
        "conditions": {
          "options": {
            "caseSensitive": true,
            "leftValue": "",
            "typeValidation": "strict"
          },
          "conditions": [
            {
              "id": "8e8ff64b-e59c-415c-af8b-211d7a7d144c",
              "leftValue": "={{ $json.error }}",
              "rightValue": "",
              "operator": {
                "type": "string",
                "operation": "exists",
                "singleValue": true
              }
            }
          ],
          "combinator": "and"
        },
        "options": {}
      },
      "id": "6f539020-50ed-44de-845d-ebef97682965",
      "name": "If - Exists Already4",
      "type": "n8n-nodes-base.if",
      "typeVersion": 2,
      "position": [
        2200,
        1700
      ]
    },
    {
      "parameters": {
        "operation": "update",
        "tableId": "rss_feed",
        "filters": {
          "conditions": [
            {
              "keyName": "id",
              "condition": "eq",
              "keyValue": "={{ $('Create RSS Item4').item.json.id }}"
            }
          ]
        },
        "fieldsUi": {
          "fieldValues": [
            {
              "fieldId": "should_draft_article",
              "fieldValue": "True"
            }
          ]
        }
      },
      "id": "44753353-5591-4981-816b-b3bcaf42ada1",
      "name": "Supabase5",
      "type": "n8n-nodes-base.supabase",
      "typeVersion": 1,
      "position": [
        2980,
        1720
      ],
      "credentials": {
        "supabaseApi": {
          "id": "",
          "name": "Supabase"
        }
      }
    },
    {
      "parameters": {
        "promptType": "define",
        "text": "=Analyze the following article headline and content snippet.  \n\nDetermin if it is AI related.\n\nout put single word as either true or false\n\ndo not output codeblocks or markdown, just the word true or false.\n\n<article_title>\n{{ $('Create RSS Item4').item.json.title }}\n</article_title>\n\n<article_snippet>\n{{ $('Create RSS Item4').item.json.content_snippet }}\n</article_snippet>",
        "hasOutputParser": true
      },
      "id": "1f77c84e-8097-4b0a-a4ae-139586365693",
      "name": "Is AI Related4",
      "type": "@n8n/n8n-nodes-langchain.chainLlm",
      "typeVersion": 1.4,
      "position": [
        2400,
        1760
      ]
    },
    {
      "parameters": {
        "promptType": "define",
        "text": "=You are an AI assistant tasked with writing a news article based on an RSS title, content snippet, and reference material from a Google search. Follow these instructions carefully:\n\n1. You will be provided with an RSS title and content snippet from a news feed:\n\n   \`\`\`\n   <rss_title>\n  {{ $('Supabase5').item.json.title }}\n   </rss_title>\n\n   <content_snippet>\n  {{ $('Supabase5').item.json.content_snippet }}\n   </content_snippet>\n   \`\`\`\n\n2. You will also be given content from a Google search related to the headline:\n\n   \`\`\`\n   <google_search_content>\n{{ JSON.stringify($json.data.substring(0, 300000)) }}\n   </google_search_content>\n   \`\`\`\n\n3. Write an article that expands on the RSS headline and content snippet, using information from the Google search content. The article should be:\n   - Informative\n   - Engaging\n   - Well-structured\n\n4. Format the article using Markdown. Use appropriate Markdown syntax for:\n   - Headings (use ## for the main title, ### for subheadings)\n   - Paragraphs (separate with blank lines)\n   - Bold and italic text where appropriate\n   - Bullet points or numbered lists if needed\n   - Blockquotes for any direct quotes from sources\n\n5. Incorporate information from both the RSS headline/snippet and the Google search content:\n   - Use the headline to guide the main topic\n   - Use the search content to provide additional details and context\n\n6. Maintain a neutral, journalistic tone throughout the article:\n   - Present facts objectively\n   - Do not include personal opinions or biases\n   - Use third-person perspective\n\n7. Structure your article with:\n   - Begin with a TL;DR section. Provide quick bullet points that capture the highlights of the article.\n   - A compelling introduction that summarizes the key points\n   - A conclusion that wraps up the article and potentially suggests future implications\n\n8. If applicable, include:\n   - Relevant statistics or data points\n   - Brief mentions of key stakeholders or experts\n   - Context on why this news is important or impactful\n\n9. Use Wikipedia-style citations in Markdown format:\n   - In the text, use footnote-style references like [^1], [^2], etc.\n   - Use footnotes sequentially without skipping any numbers\n   - At the end of the article, include a ## References section\n   - Format each reference as follows:\n     [^1]: Author Name (if available) (Date). \"[Article Title](URL)\". Publication Name. Retrieved [Current Date].\n   - If an author name is not available, start with the article title\n   - Ensure all article titles are clickable links using Markdown syntax\n   - Include ALL sources provided in the Google search content in the References section, even if not directly cited in the text\n\n10. Begin your response with <article> and end it with </article>. The entire article, including the Markdown formatting and references, should be contained within these tags.\n\n11. After the article, provide a brief metadata section with:\n    - Main keywords or tags (do not include links in this section)\n\n12. Double-check your footnotes before completing the article:\n    - Ensure all footnote numbers used in the text have corresponding entries in the References section\n    - Verify that footnote numbers are sequential (1, 2, 3, etc.) without any gaps\n\nRemember to adhere to journalistic standards and ethics in your writing. Stick to the facts presented in the provided sources and avoid sensationalism."
      },
      "id": "d2356b63-beec-4dfd-8a29-8ccd3e301b81",
      "name": "Write Article5",
      "type": "@n8n/n8n-nodes-langchain.chainLlm",
      "typeVersion": 1.4,
      "position": [
        3380,
        1720
      ]
    },
    {
      "parameters": {
        "tableId": "ai_articles",
        "fieldsUi": {
          "fieldValues": [
            {
              "fieldId": "rss_feed_id",
              "fieldValue": "={{ $('Supabase5').item.json.id }}"
            },
            {
              "fieldId": "title",
              "fieldValue": "={{ $('Supabase5').item.json.title }}"
            },
            {
              "fieldId": "content",
              "fieldValue": "={{ $('Write Article5').item.json.text }}"
            }
          ]
        }
      },
      "id": "c0c9e6f7-97b3-4d86-b4de-dfb1e20a41ad",
      "name": "Save Article5",
      "type": "n8n-nodes-base.supabase",
      "typeVersion": 1,
      "position": [
        4080,
        1720
      ],
      "credentials": {
        "supabaseApi": {
          "id": "",
          "name": "Supabase"
        }
      },
      "onError": "continueRegularOutput"
    },
    {
      "parameters": {
        "url": "https://www.googleapis.com/customsearch/v1",
        "authentication": "genericCredentialType",
        "genericAuthType": "httpQueryAuth",
        "sendQuery": true,
        "queryParameters": {
          "parameters": [
            {
              "name": "q",
              "value": "={{ $('Supabase5').item.json.title }} "
            },
            {
              "name": "cx",
              "value": "{{ String($('Globals1').item.json.google_search_cx).trim() }}"
            },
            {
              "name": "searchType",
              "value": "image"
            },
            {
              "name": "num",
              "value": "1"
            }
          ]
        },
        "options": {}
      },
      "id": "8958d252-26b9-460c-b7c1-ea954750084d",
      "name": "Get Image",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4.2,
      "position": [
        3720,
        1720
      ],
      "credentials": {
        "httpQueryAuth": {
          "id": "",
          "name": "Google Search Key"
        }
      }
    },
    {
      "parameters": {
        "operation": "update",
        "tableId": "rss_feed",
        "filters": {
          "conditions": [
            {
              "keyName": "id",
              "condition": "eq",
              "keyValue": "={{ $('Supabase5').item.json.id }}"
            }
          ]
        },
        "fieldsUi": {
          "fieldValues": [
            {
              "fieldId": "img_url",
              "fieldValue": "={{ $json.items[0].link }}"
            }
          ]
        }
      },
      "id": "5c68e57a-7713-4bb4-955f-08885c8edc86",
      "name": "Supabase6",
      "type": "n8n-nodes-base.supabase",
      "typeVersion": 1,
      "position": [
        3900,
        1720
      ],
      "credentials": {
        "supabaseApi": {
          "id": "",
          "name": "Supabase"
        }
      }
    },
    {
      "parameters": {
        "content": "# NYT",
        "height": 80,
        "color": 5
      },
      "id": "05f3ca26-4611-4255-a4d0-5a60f2af34af",
      "name": "Sticky Note1",
      "type": "n8n-nodes-base.stickyNote",
      "typeVersion": 1,
      "position": [
        740,
        760
      ]
    },
    {
      "parameters": {
        "content": "# FT",
        "height": 80,
        "color": 5
      },
      "id": "d4dd9943-1315-4ed6-90cc-f7a71f3bdda3",
      "name": "Sticky Note2",
      "type": "n8n-nodes-base.stickyNote",
      "typeVersion": 1,
      "position": [
        740,
        1240
      ]
    },
    {
      "parameters": {
        "content": "# BBC",
        "height": 80,
        "color": 5
      },
      "id": "ccf15d80-a500-4368-b210-78c7d94a00d2",
      "name": "Sticky Note3",
      "type": "n8n-nodes-base.stickyNote",
      "typeVersion": 1,
      "position": [
        740,
        1700
      ]
    },
    {
      "parameters": {
        "url": "https://feeds.washingtonpost.com/rss/business/technology",
        "options": {}
      },
      "id": "462860b1-2f25-4103-9419-41c03045cf85",
      "name": "HTTP Request5",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4.2,
      "position": [
        1060,
        -220
      ]
    },
    {
      "parameters": {
        "options": {}
      },
      "id": "34a43fdb-ab78-4005-8639-046ff048c64b",
      "name": "XML5",
      "type": "n8n-nodes-base.xml",
      "typeVersion": 1,
      "position": [
        1280,
        -220
      ]
    },
    {
      "parameters": {
        "fieldToSplitOut": "rss.channel.item",
        "options": {}
      },
      "id": "34bddc2c-0fc1-4baf-bb1c-ed1ec96b91bc",
      "name": "Split Out5",
      "type": "n8n-nodes-base.splitOut",
      "typeVersion": 1,
      "position": [
        1500,
        -220
      ]
    },
    {
      "parameters": {
        "options": {}
      },
      "id": "73937277-fb32-4591-9c0a-286607aaa4b1",
      "name": "Loop Over Items7",
      "type": "n8n-nodes-base.splitInBatches",
      "typeVersion": 3,
      "position": [
        1740,
        -220
      ]
    },
    {
      "parameters": {
        "url": "=https://s.jina.ai/ {{ encodeURIComponent($json.title) }}",
        "options": {}
      },
      "id": "a21cc7bd-6c12-47c6-902b-86f85075b7a2",
      "name": "JinaAI Search8",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4.2,
      "position": [
        3180,
        -180
      ]
    },
    {
      "parameters": {
        "model": "gpt-4o-mini-2024-07-18",
        "options": {}
      },
      "id": "70de1d46-7b9d-4cc2-aa6c-4ef77cc994a1",
      "name": "OpenAI Chat Model15",
      "type": "@n8n/n8n-nodes-langchain.lmChatOpenAi",
      "typeVersion": 1,
      "position": [
        3380,
        40
      ],
      "credentials": {
        "openAiApi": {
          "id": "",
          "name": "OpenAi"
        }
      }
    },
    {
      "parameters": {
        "tableId": "ai_articles",
        "fieldsUi": {
          "fieldValues": [
            {
              "fieldId": "rss_feed_id",
              "fieldValue": "={{ $('Supabase9').item.json.id }}"
            },
            {
              "fieldId": "title",
              "fieldValue": "={{ $('Supabase9').item.json.title }}"
            },
            {
              "fieldId": "content",
              "fieldValue": "={{ $('Write Article8').item.json.text }}"
            }
          ]
        }
      },
      "id": "09a3c049-e17a-41eb-b45d-79dfcaebb667",
      "name": "Save Article8",
      "type": "n8n-nodes-base.supabase",
      "typeVersion": 1,
      "position": [
        4100,
        -180
      ],
      "credentials": {
        "supabaseApi": {
          "id": "",
          "name": "Supabase"
        }
      },
      "onError": "continueRegularOutput"
    },
    {
      "parameters": {
        "model": "gpt-4o-mini-2024-07-18",
        "options": {}
      },
      "id": "fbc569d5-1c64-4526-bfed-6848761d1a3a",
      "name": "OpenAI Chat Model16",
      "type": "@n8n/n8n-nodes-langchain.lmChatOpenAi",
      "typeVersion": 1,
      "position": [
        2420,
        80
      ],
      "credentials": {
        "openAiApi": {
          "id": "",
          "name": "OpenAi"
        }
      }
    },
    {
      "parameters": {
        "tableId": "rss_feed",
        "fieldsUi": {
          "fieldValues": [
            {
              "fieldId": "title",
              "fieldValue": "={{ $json.title }}"
            },
            {
              "fieldId": "link",
              "fieldValue": "={{ $json.link }}"
            },
            {
              "fieldId": "pub_date",
              "fieldValue": "={{ $json.pubDate }}"
            },
            {
              "fieldId": "content",
              "fieldValue": "={{ $json.description }}"
            },
            {
              "fieldId": "content_snippet",
              "fieldValue": "={{ $json.description }}"
            },
            {
              "fieldId": "img_url",
              "fieldValue": "="
            },
            {
              "fieldId": "source",
              "fieldValue": "The Washington Post"
            },
            {
              "fieldId": "guid",
              "fieldValue": "={{ $json.guid._ }}"
            }
          ]
        }
      },
      "id": "06c121d5-fbd8-41c3-819a-7819008372d9",
      "name": "Create RSS Item7",
      "type": "n8n-nodes-base.supabase",
      "typeVersion": 1,
      "position": [
        2000,
        -200
      ],
      "credentials": {
        "supabaseApi": {
          "id": "",
          "name": "Supabase"
        }
      },
      "onError": "continueRegularOutput"
    },
    {
      "parameters": {
        "conditions": {
          "options": {
            "caseSensitive": true,
            "leftValue": "",
            "typeValidation": "strict"
          },
          "conditions": [
            {
              "id": "8e8ff64b-e59c-415c-af8b-211d7a7d144c",
              "leftValue": "={{ $json.text }}",
              "rightValue": "true",
              "operator": {
                "type": "string",
                "operation": "contains"
              }
            }
          ],
          "combinator": "and"
        },
        "options": {}
      },
      "id": "b15a7a5a-fea8-4c9c-81eb-ffe16d160806",
      "name": "If - Is AI7",
      "type": "n8n-nodes-base.if",
      "typeVersion": 2,
      "position": [
        2720,
        -140
      ]
    },
    {
      "parameters": {
        "conditions": {
          "options": {
            "caseSensitive": true,
            "leftValue": "",
            "typeValidation": "strict"
          },
          "conditions": [
            {
              "id": "8e8ff64b-e59c-415c-af8b-211d7a7d144c",
              "leftValue": "={{ $json.error }}",
              "rightValue": "",
              "operator": {
                "type": "string",
                "operation": "exists",
                "singleValue": true
              }
            }
          ],
          "combinator": "and"
        },
        "options": {}
      },
      "id": "7d651663-afc4-4e8a-9ed4-c554aa1dd575",
      "name": "If - Exists Already7",
      "type": "n8n-nodes-base.if",
      "typeVersion": 2,
      "position": [
        2200,
        -200
      ]
    },
    {
      "parameters": {
        "operation": "update",
        "tableId": "rss_feed",
        "filters": {
          "conditions": [
            {
              "keyName": "id",
              "condition": "eq",
              "keyValue": "={{ $('Create RSS Item7').item.json.id }}"
            }
          ]
        },
        "fieldsUi": {
          "fieldValues": [
            {
              "fieldId": "should_draft_article",
              "fieldValue": "True"
            }
          ]
        }
      },
      "id": "7fda4ea9-b458-463c-9b1f-c3100810ee18",
      "name": "Supabase9",
      "type": "n8n-nodes-base.supabase",
      "typeVersion": 1,
      "position": [
        2980,
        -180
      ],
      "credentials": {
        "supabaseApi": {
          "id": "",
          "name": "Supabase"
        }
      }
    },
    {
      "parameters": {
        "url": "https://www.googleapis.com/customsearch/v1",
        "authentication": "genericCredentialType",
        "genericAuthType": "httpQueryAuth",
        "sendQuery": true,
        "queryParameters": {
          "parameters": [
            {
              "name": "q",
              "value": "={{ $('Supabase9').item.json.title }} "
            },
            {
              "name": "cx",
              "value": "={{ String($('Globals1').item.json.google_search_cx).trim() }}"
            },
            {
              "name": "searchType",
              "value": "image"
            },
            {
              "name": "num",
              "value": "1"
            }
          ]
        },
        "options": {}
      },
      "id": "87f48a74-5909-42e7-8449-385916815251",
      "name": "Get Image3",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4.2,
      "position": [
        3740,
        -180
      ],
      "credentials": {
        "httpQueryAuth": {
          "id": "",
          "name": "Google Search Key"
        }
      }
    },
    {
      "parameters": {
        "operation": "update",
        "tableId": "rss_feed",
        "filters": {
          "conditions": [
            {
              "keyName": "id",
              "condition": "eq",
              "keyValue": "={{ $('Supabase9').item.json.id }}"
            }
          ]
        },
        "fieldsUi": {
          "fieldValues": [
            {
              "fieldId": "img_url",
              "fieldValue": "={{ $json.items[0].link }}"
            }
          ]
        }
      },
      "id": "c4913f2c-aacb-4922-bfda-090d45f8ef87",
      "name": "Supabase10",
      "type": "n8n-nodes-base.supabase",
      "typeVersion": 1,
      "position": [
        3920,
        -180
      ],
      "credentials": {
        "supabaseApi": {
          "id": "",
          "name": "Supabase"
        }
      }
    },
    {
      "parameters": {
        "content": "# Washington Post",
        "height": 126.69426322803548,
        "color": 5
      },
      "id": "88f0ed34-2190-4a3a-ac6b-03281360f57f",
      "name": "Sticky Note6",
      "type": "n8n-nodes-base.stickyNote",
      "typeVersion": 1,
      "position": [
        740,
        -200
      ]
    },
    {
      "parameters": {
        "promptType": "define",
        "text": "=Analyze the following article headline and content snippet.  \n\nDetermin if it is AI related.\n\nout put single word as either true or false\n\ndo not output codeblocks or markdown, just the word true or false.\n\n<article_title>\n{{ $('Create RSS Item7').item.json.title }}\n</article_title>\n\n<article_snippet>\n{{ $('Create RSS Item7').item.json.content_snippet }}\n</article_snippet>",
        "hasOutputParser": true
      },
      "id": "c006886f-aa7f-440e-bb3b-145b23f89450",
      "name": "Is AI Related7",
      "type": "@n8n/n8n-nodes-langchain.chainLlm",
      "typeVersion": 1.4,
      "position": [
        2400,
        -140
      ]
    },
    {
      "parameters": {
        "promptType": "define",
        "text": "=You are an AI assistant tasked with writing a news article based on an RSS title, content snippet, and reference material from a Google search. Follow these instructions carefully:\n\n1. You will be provided with an RSS title and content snippet from a news feed:\n\n   \`\`\`\n   <rss_title>\n  {{ $('Supabase3').item.json.title }}\n   </rss_title>\n\n   <content_snippet>\n  {{ $('Supabase3').item.json.content_snippet }}\n   </content_snippet>\n   \`\`\`\n\n2. You will also be given content from a Google search related to the headline:\n\n   \`\`\`\n   <google_search_content>\n{{ JSON.stringify($json.data.substring(0, 400000)) }}\n   </google_search_content>\n   \`\`\`\n\n3. Write an article that expands on the RSS headline and content snippet, using information from the Google search content. The article should be:\n   - Informative\n   - Engaging\n   - Well-structured\n\n4. Format the article using Markdown. Use appropriate Markdown syntax for:\n   - Headings (use ## for the main title, ### for subheadings)\n   - Paragraphs (separate with blank lines)\n   - Bold and italic text where appropriate\n   - Bullet points or numbered lists if needed\n   - Blockquotes for any direct quotes from sources\n\n5. Incorporate information from both the RSS headline/snippet and the Google search content:\n   - Use the headline to guide the main topic\n   - Use the search content to provide additional details and context\n\n6. Maintain a neutral, journalistic tone throughout the article:\n   - Present facts objectively\n   - Do not include personal opinions or biases\n   - Use third-person perspective\n\n7. Structure your article with:\n   - Begin with a TL;DR section. Provide quick bullet points that capture the highlights of the article.\n   - A compelling introduction that summarizes the key points\n   - A conclusion that wraps up the article and potentially suggests future implications\n\n8. If applicable, include:\n   - Relevant statistics or data points\n   - Brief mentions of key stakeholders or experts\n   - Context on why this news is important or impactful\n\n9. Use Wikipedia-style citations in Markdown format:\n   - In the text, use footnote-style references like [^1], [^2], etc.\n   - Use footnotes sequentially without skipping any numbers\n   - At the end of the article, include a ## References section\n   - Format each reference as follows:\n     [^1]: Author Name (if available) (Date). \"[Article Title](URL)\". Publication Name. Retrieved [Current Date].\n   - If an author name is not available, start with the article title\n   - Ensure all article titles are clickable links using Markdown syntax\n   - Include ALL sources provided in the Google search content in the References section, even if not directly cited in the text\n\n10. Begin your response with <article> and end it with </article>. The entire article, including the Markdown formatting and references, should be contained within these tags.\n\n11. After the article, provide a brief metadata section with:\n    - Main keywords or tags (do not include links in this section)\n\n12. Double-check your footnotes before completing the article:\n    - Ensure all footnote numbers used in the text have corresponding entries in the References section\n    - Verify that footnote numbers are sequential (1, 2, 3, etc.) without any gaps\n\nRemember to adhere to journalistic standards and ethics in your writing. Stick to the facts presented in the provided sources and avoid sensationalism."
      },
      "id": "947ad72b-ae1a-42b5-b95d-b6224266b432",
      "name": "Write Article3",
      "type": "@n8n/n8n-nodes-langchain.chainLlm",
      "typeVersion": 1.4,
      "position": [
        3300,
        800
      ]
    },
    {
      "parameters": {
        "content": "# WSJ",
        "height": 80,
        "color": 5
      },
      "id": "2462e0a7-9353-4475-a72d-636cbd6013f1",
      "name": "Sticky Note",
      "type": "n8n-nodes-base.stickyNote",
      "typeVersion": 1,
      "position": [
        740,
        300
      ]
    },
    {
      "parameters": {
        "url": "https://feeds.a.dj.com/rss/RSSWSJD.xml",
        "options": {}
      },
      "id": "929c230b-64e3-4aa7-90d4-93efe1896c98",
      "name": "HTTP Request6",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4.2,
      "position": [
        1040,
        300
      ]
    },
    {
      "parameters": {
        "options": {}
      },
      "id": "0cb78450-1740-4990-a195-3a7fb5f36b68",
      "name": "XML6",
      "type": "n8n-nodes-base.xml",
      "typeVersion": 1,
      "position": [
        1260,
        300
      ]
    },
    {
      "parameters": {
        "fieldToSplitOut": "rss.channel.item",
        "options": {}
      },
      "id": "1a3e047a-f10c-4131-a6b9-67bbeade641c",
      "name": "Split Out6",
      "type": "n8n-nodes-base.splitOut",
      "typeVersion": 1,
      "position": [
        1480,
        300
      ]
    },
    {
      "parameters": {
        "options": {}
      },
      "id": "f2843d46-bd8e-4d03-886d-22ee6289f44c",
      "name": "Loop Over Items",
      "type": "n8n-nodes-base.splitInBatches",
      "typeVersion": 3,
      "position": [
        1720,
        300
      ]
    },
    {
      "parameters": {
        "url": "=https://s.jina.ai/ {{ encodeURIComponent($json.title) }}",
        "options": {}
      },
      "id": "87bae5cd-0247-4fa0-90e4-d6dd8a2fc827",
      "name": "JinaAI Search",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4.2,
      "position": [
        3160,
        340
      ]
    },
    {
      "parameters": {
        "model": "gpt-4o-mini-2024-07-18",
        "options": {}
      },
      "id": "6079624f-c65a-4a2b-94e5-87c6a72240f0",
      "name": "OpenAI Chat Model",
      "type": "@n8n/n8n-nodes-langchain.lmChatOpenAi",
      "typeVersion": 1,
      "position": [
        3360,
        560
      ],
      "credentials": {
        "openAiApi": {
          "id": "",
          "name": "OpenAi"
        }
      }
    },
    {
      "parameters": {
        "tableId": "ai_articles",
        "fieldsUi": {
          "fieldValues": [
            {
              "fieldId": "rss_feed_id",
              "fieldValue": "={{ $('Supabase11').item.json.id }}"
            },
            {
              "fieldId": "title",
              "fieldValue": "={{ $('Supabase11').item.json.title }}"
            },
            {
              "fieldId": "content",
              "fieldValue": "={{ $('Write Article').item.json.text }}"
            }
          ]
        }
      },
      "id": "aaac3a9d-2a6d-46c7-b347-b3da0e5c4b40",
      "name": "Save Article",
      "type": "n8n-nodes-base.supabase",
      "typeVersion": 1,
      "position": [
        4080,
        340
      ],
      "credentials": {
        "supabaseApi": {
          "id": "",
          "name": "Supabase"
        }
      },
      "onError": "continueRegularOutput"
    },
    {
      "parameters": {
        "model": "gpt-4o-mini-2024-07-18",
        "options": {}
      },
      "id": "1a5dcc98-6955-4732-8892-e56175f03e7b",
      "name": "OpenAI Chat Model17",
      "type": "@n8n/n8n-nodes-langchain.lmChatOpenAi",
      "typeVersion": 1,
      "position": [
        2400,
        600
      ],
      "credentials": {
        "openAiApi": {
          "id": "",
          "name": "OpenAi"
        }
      }
    },
    {
      "parameters": {
        "tableId": "rss_feed",
        "fieldsUi": {
          "fieldValues": [
            {
              "fieldId": "title",
              "fieldValue": "={{ $json.title }}"
            },
            {
              "fieldId": "link",
              "fieldValue": "={{ $json.link }}"
            },
            {
              "fieldId": "pub_date",
              "fieldValue": "={{ $json.pubDate }}"
            },
            {
              "fieldId": "content",
              "fieldValue": "={{ $json.description }}"
            },
            {
              "fieldId": "content_snippet",
              "fieldValue": "={{ $json.description }}"
            },
            {
              "fieldId": "img_url",
              "fieldValue": "="
            },
            {
              "fieldId": "source",
              "fieldValue": "The Wall Street Journal"
            },
            {
              "fieldId": "guid",
              "fieldValue": "={{ $json.guid._ }}"
            },
            {
              "fieldId": "img_url"
            }
          ]
        }
      },
      "id": "daaa556a-8d84-4e42-843f-afa0ea5acbfe",
      "name": "Create RSS Item",
      "type": "n8n-nodes-base.supabase",
      "typeVersion": 1,
      "position": [
        2000,
        320
      ],
      "credentials": {
        "supabaseApi": {
          "id": "",
          "name": "Supabase"
        }
      },
      "onError": "continueRegularOutput"
    },
    {
      "parameters": {
        "conditions": {
          "options": {
            "caseSensitive": true,
            "leftValue": "",
            "typeValidation": "strict"
          },
          "conditions": [
            {
              "id": "8e8ff64b-e59c-415c-af8b-211d7a7d144c",
              "leftValue": "={{ $json.text }}",
              "rightValue": "true",
              "operator": {
                "type": "string",
                "operation": "contains"
              }
            }
          ],
          "combinator": "and"
        },
        "options": {}
      },
      "id": "3b5482b7-fb9b-4c80-99e8-e08c9ec6097a",
      "name": "If - Is AI",
      "type": "n8n-nodes-base.if",
      "typeVersion": 2,
      "position": [
        2700,
        380
      ]
    },
    {
      "parameters": {
        "conditions": {
          "options": {
            "caseSensitive": true,
            "leftValue": "",
            "typeValidation": "strict"
          },
          "conditions": [
            {
              "id": "8e8ff64b-e59c-415c-af8b-211d7a7d144c",
              "leftValue": "={{ $json.error }}",
              "rightValue": "",
              "operator": {
                "type": "string",
                "operation": "exists",
                "singleValue": true
              }
            }
          ],
          "combinator": "and"
        },
        "options": {}
      },
      "id": "aef6e1a2-73f5-4907-97f9-fa1a3a25be82",
      "name": "If - Exists Already",
      "type": "n8n-nodes-base.if",
      "typeVersion": 2,
      "position": [
        2180,
        320
      ]
    },
    {
      "parameters": {
        "operation": "update",
        "tableId": "rss_feed",
        "filters": {
          "conditions": [
            {
              "keyName": "id",
              "condition": "eq",
              "keyValue": "={{ $('Create RSS Item').item.json.id }}"
            }
          ]
        },
        "fieldsUi": {
          "fieldValues": [
            {
              "fieldId": "should_draft_article",
              "fieldValue": "True"
            }
          ]
        }
      },
      "id": "7977b9f2-09da-4ccb-bcda-0d1f928cd3ef",
      "name": "Supabase11",
      "type": "n8n-nodes-base.supabase",
      "typeVersion": 1,
      "position": [
        2960,
        340
      ],
      "credentials": {
        "supabaseApi": {
          "id": "",
          "name": "Supabase"
        }
      }
    },
    {
      "parameters": {
        "url": "https://www.googleapis.com/customsearch/v1",
        "authentication": "genericCredentialType",
        "genericAuthType": "httpQueryAuth",
        "sendQuery": true,
        "queryParameters": {
          "parameters": [
            {
              "name": "q",
              "value": "={{ $('Supabase11').item.json.title }} "
            },
            {
              "name": "cx",
              "value": "{{ String($('Globals1').item.json.google_search_cx).trim() }}"
            },
            {
              "name": "searchType",
              "value": "image"
            },
            {
              "name": "num",
              "value": "1"
            }
          ]
        },
        "options": {}
      },
      "id": "aa933864-42f6-445a-9e40-fabacfa4adc6",
      "name": "Get Image4",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4.2,
      "position": [
        3720,
        340
      ],
      "credentials": {
        "httpQueryAuth": {
          "id": "",
          "name": "Google Search Key"
        }
      }
    },
    {
      "parameters": {
        "operation": "update",
        "tableId": "rss_feed",
        "filters": {
          "conditions": [
            {
              "keyName": "id",
              "condition": "eq",
              "keyValue": "={{ $('Supabase11').item.json.id }}"
            }
          ]
        },
        "fieldsUi": {
          "fieldValues": [
            {
              "fieldId": "img_url",
              "fieldValue": "={{ $json.items[0].link }}"
            }
          ]
        }
      },
      "id": "f57de610-5993-4f60-b8c8-458f1516aee3",
      "name": "Supabase12",
      "type": "n8n-nodes-base.supabase",
      "typeVersion": 1,
      "position": [
        3900,
        340
      ],
      "credentials": {
        "supabaseApi": {
          "id": "",
          "name": "Supabase"
        }
      }
    },
    {
      "parameters": {
        "promptType": "define",
        "text": "=Analyze the following article headline and content snippet.  \n\nDetermin if it is AI related.\n\nout put single word as either true or false\n\ndo not output codeblocks or markdown, just the word true or false.\n\n<article_title>\n{{ $('Create RSS Item').item.json.title }}\n</article_title>\n\n<article_snippet>\n{{ $('Create RSS Item').item.json.content_snippet }}\n</article_snippet>",
        "hasOutputParser": true
      },
      "id": "6735df27-f00d-4cac-b8f2-a4ccc7e42350",
      "name": "Is AI Related",
      "type": "@n8n/n8n-nodes-langchain.chainLlm",
      "typeVersion": 1.4,
      "position": [
        2380,
        380
      ]
    },
    {
      "parameters": {
        "promptType": "define",
        "text": "=You are an AI assistant tasked with writing a news article based on an RSS title, content snippet, and reference material from a Google search. Follow these instructions carefully:\n\n1. You will be provided with an RSS title and content snippet from a news feed:\n\n   \`\`\`\n   <rss_title>\n  {{ $('Supabase9').item.json.title }}\n   </rss_title>\n\n   <context_snippet>\n  {{ $('Supabase9').item.json.content_snippet }}\n   </context_snippet>\n   \`\`\`\n\n2. You will also be given content from a Google search related to the headline:\n\n   \`\`\`\n   <google_search_content>\n{{ JSON.stringify($json.data.substring(0, 300000)) }}\n   </google_search_content>\n   \`\`\`\n\n3. Write an article that expands on the RSS headline and content snippet, using information from the Google search content. The article should be:\n   - Anchored on the Title and Context Snippet\n   - Informative\n   - Engaging\n   - Well-structured\n\n4. Format the article using Markdown. Use appropriate Markdown syntax for:\n   - Headings (use ## for the main title, ### for subheadings)\n   - Paragraphs (separate with blank lines)\n   - Bold and italic text where appropriate\n   - Bullet points or numbered lists if needed\n   - Blockquotes for any direct quotes from sources\n\n5. Incorporate information from both the RSS headline/snippet and the Google search content:\n   - Use the headline to guide the main topic\n   - Use the search content to provide additional details and context\n\n6. Maintain a neutral, journalistic tone throughout the article:\n   - Present facts objectively\n   - Do not include personal opinions or biases\n   - Use third-person perspective\n\n7. Structure your article with:\n   - Begin with a TL;DR section. Provide quick bullet points that capture the highlights of the article.\n   - A compelling introduction that summarizes the key points\n   - A conclusion that wraps up the article and potentially suggests future implications\n\n8. If applicable, include:\n   - Relevant statistics or data points\n   - Brief mentions of key stakeholders or experts\n   - Context on why this news is important or impactful\n\n9. Use Wikipedia-style citations in Markdown format:\n   - In the text, use footnote-style references like [^1], [^2], etc.\n   - Use footnotes sequentially without skipping any numbers\n   - At the end of the article, include a ## References section\n   - Format each reference as follows:\n     [^1]: Author Name (if available) (Date). \"[Article Title](URL)\". Publication Name. Retrieved [Current Date].\n   - If an author name is not available, start with the article title\n   - Ensure all article titles are clickable links using Markdown syntax\n   - Include ALL sources provided in the Google search content in the References section, even if not directly cited in the text\n\n10. Begin your response with <article> and end it with </article>. The entire article, including the Markdown formatting and references, should be contained within these tags.\n\n11. After the article, provide a brief metadata section with:\n    - Main keywords or tags (do not include links in this section)\n\n12. Double-check your footnotes before completing the article:\n    - Ensure all footnote numbers used in the text have corresponding entries in the References section\n    - Verify that footnote numbers are sequential (1, 2, 3, etc.) without any gaps\n\nRemember to adhere to journalistic standards and ethics in your writing. Stick to the facts presented in the provided sources and avoid sensationalism."
      },
      "id": "e5cabf00-0a9c-475a-ac0f-7f7085972ce2",
      "name": "Write Article8",
      "type": "@n8n/n8n-nodes-langchain.chainLlm",
      "typeVersion": 1.4,
      "position": [
        3380,
        -180
      ]
    },
    {
      "parameters": {
        "promptType": "define",
        "text": "=You are an AI assistant tasked with writing a news article based on an RSS title, context snippet, and reference material from a Google search. Follow these instructions carefully:\n\n1. You will be provided with an RSS title and content snippet from a news feed:\n\n   \`\`\`\n   <rss_title>\n  {{ $('Supabase11').item.json.title }}\n   </rss_title>\n\n   <context_snippet>\n  {{ $('Supabase11').item.json.content_snippet }}\n   </context_snippet>\n   \`\`\`\n\n2. You will also be given content from a Google search related to the headline:\n\n   \`\`\`\n   <google_search_content>\n{{ JSON.stringify($json.data.substring(0, 300000)) }}\n   </google_search_content>\n   \`\`\`\n\n3. Write an article that expands on the RSS headline and content snippet, using information from the Google search content. The article should be:\n   - Anchored on the Title and Context Snippet\n   - Informative\n   - Engaging\n   - Well-structured\n\n4. Format the article using Markdown. Use appropriate Markdown syntax for:\n   - Headings (use ## for the main title, ### for subheadings)\n   - Paragraphs (separate with blank lines)\n   - Bold and italic text where appropriate\n   - Bullet points or numbered lists if needed\n   - Blockquotes for any direct quotes from sources\n\n5. Incorporate information from both the RSS headline/snippet and the Google search content:\n   - Use the headline to guide the main topic\n   - Use the search content to provide additional details and context\n\n6. Maintain a neutral, journalistic tone throughout the article:\n   - Present facts objectively\n   - Do not include personal opinions or biases\n   - Use third-person perspective\n\n7. Structure your article with:\n   - Begin with a TL;DR section. Provide quick bullet points that capture the highlights of the article.\n   - A compelling introduction that summarizes the key points\n   - A conclusion that wraps up the article and potentially suggests future implications\n\n8. If applicable, include:\n   - Relevant statistics or data points\n   - Brief mentions of key stakeholders or experts\n   - Context on why this news is important or impactful\n\n9. Use Wikipedia-style citations in Markdown format:\n   - In the text, use footnote-style references like [^1], [^2], etc.\n   - Use footnotes sequentially without skipping any numbers\n   - At the end of the article, include a ## References section\n   - Format each reference as follows:\n     [^1]: Author Name (if available) (Date). \"[Article Title](URL)\". Publication Name. Retrieved [Current Date].\n   - If an author name is not available, start with the article title\n   - Ensure all article titles are clickable links using Markdown syntax\n   - Include ALL sources provided in the Google search content in the References section, even if not directly cited in the text\n\n10. Begin your response with <article> and end it with </article>. The entire article, including the Markdown formatting and references, should be contained within these tags.\n\n11. After the article, provide a brief metadata section with:\n    - Main keywords or tags (do not include links in this section)\n\n12. Double-check your footnotes before completing the article:\n    - Ensure all footnote numbers used in the text have corresponding entries in the References section\n    - Verify that footnote numbers are sequential (1, 2, 3, etc.) without any gaps\n\nRemember to adhere to journalistic standards and ethics in your writing. Stick to the facts presented in the provided sources and avoid sensationalism."
      },
      "id": "dcda847d-aeac-4fef-8e88-5704506af2ce",
      "name": "Write Article",
      "type": "@n8n/n8n-nodes-langchain.chainLlm",
      "typeVersion": 1.4,
      "position": [
        3360,
        340
      ]
    },
    {
      "parameters": {
        "assignments": {
          "assignments": [
            {
              "id": "62266f8c-0f97-494a-adb6-4b5c082cc1c1",
              "name": "google_search_cx",
              "value": "",
              "type": "string"
            }
          ]
        },
        "options": {}
      },
      "id": "2b0fe2a4-36ee-4a38-9642-269e9cf8b283",
      "name": "Globals1",
      "type": "n8n-nodes-base.set",
      "typeVersion": 3.4,
      "position": [
        500,
        -320
      ]
    }
  ],
  "connections": {
    "HTTP Request1": {
      "main": [
        [
          {
            "node": "XML1",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "XML1": {
      "main": [
        [
          {
            "node": "Split Out1",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Split Out1": {
      "main": [
        [
          {
            "node": "Loop Over Items2",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Loop Over Items2": {
      "main": [
        null,
        [
          {
            "node": "Create RSS Item2",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "JinaAI Search3": {
      "main": [
        [
          {
            "node": "Write Article3",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "OpenAI Chat Model5": {
      "ai_languageModel": [
        [
          {
            "node": "Write Article3",
            "type": "ai_languageModel",
            "index": 0
          }
        ]
      ]
    },
    "Save Article3": {
      "main": [
        [
          {
            "node": "Loop Over Items2",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "OpenAI Chat Model6": {
      "ai_languageModel": [
        [
          {
            "node": "Is AI Related2",
            "type": "ai_languageModel",
            "index": 0
          }
        ]
      ]
    },
    "Create RSS Item2": {
      "main": [
        [
          {
            "node": "If - Exists Already2",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "If - Is AI2": {
      "main": [
        [
          {
            "node": "Supabase3",
            "type": "main",
            "index": 0
          }
        ],
        [
          {
            "node": "Loop Over Items2",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "If - Exists Already2": {
      "main": [
        [
          {
            "node": "Loop Over Items2",
            "type": "main",
            "index": 0
          }
        ],
        [
          {
            "node": "Is AI Related2",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Supabase3": {
      "main": [
        [
          {
            "node": "JinaAI Search3",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Schedule Trigger": {
      "main": [
        [
          {
            "node": "Globals1",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Is AI Related2": {
      "main": [
        [
          {
            "node": "If - Is AI2",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "HTTP Request": {
      "main": [
        [
          {
            "node": "XML",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "XML": {
      "main": [
        [
          {
            "node": "Split Out",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Split Out": {
      "main": [
        [
          {
            "node": "Loop Over Items3",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Loop Over Items3": {
      "main": [
        null,
        [
          {
            "node": "Extract Img and Description",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "JinaAI Search4": {
      "main": [
        [
          {
            "node": "Write Article4",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "OpenAI Chat Model7": {
      "ai_languageModel": [
        [
          {
            "node": "Write Article4",
            "type": "ai_languageModel",
            "index": 0
          }
        ]
      ]
    },
    "Save Article4": {
      "main": [
        [
          {
            "node": "Loop Over Items3",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "OpenAI Chat Model8": {
      "ai_languageModel": [
        [
          {
            "node": "Is AI Related3",
            "type": "ai_languageModel",
            "index": 0
          }
        ]
      ]
    },
    "Create RSS Item3": {
      "main": [
        [
          {
            "node": "If - Exists Already3",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "If - Is AI3": {
      "main": [
        [
          {
            "node": "Supabase4",
            "type": "main",
            "index": 0
          }
        ],
        [
          {
            "node": "Loop Over Items3",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "If - Exists Already3": {
      "main": [
        [
          {
            "node": "Loop Over Items3",
            "type": "main",
            "index": 0
          }
        ],
        [
          {
            "node": "Is AI Related3",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Supabase4": {
      "main": [
        [
          {
            "node": "JinaAI Search4",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Is AI Related3": {
      "main": [
        [
          {
            "node": "If - Is AI3",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Extract Img and Description": {
      "main": [
        [
          {
            "node": "Create RSS Item3",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Write Article4": {
      "main": [
        [
          {
            "node": "Save Article4",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "HTTP Request2": {
      "main": [
        [
          {
            "node": "XML2",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "XML2": {
      "main": [
        [
          {
            "node": "Split Out2",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Split Out2": {
      "main": [
        [
          {
            "node": "Loop Over Items4",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Loop Over Items4": {
      "main": [
        null,
        [
          {
            "node": "Create RSS Item4",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "JinaAI Search5": {
      "main": [
        [
          {
            "node": "Write Article5",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "OpenAI Chat Model9": {
      "ai_languageModel": [
        [
          {
            "node": "Write Article5",
            "type": "ai_languageModel",
            "index": 0
          }
        ]
      ]
    },
    "OpenAI Chat Model10": {
      "ai_languageModel": [
        [
          {
            "node": "Is AI Related4",
            "type": "ai_languageModel",
            "index": 0
          }
        ]
      ]
    },
    "Create RSS Item4": {
      "main": [
        [
          {
            "node": "If - Exists Already4",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "If - Is AI4": {
      "main": [
        [
          {
            "node": "Supabase5",
            "type": "main",
            "index": 0
          }
        ],
        [
          {
            "node": "Loop Over Items4",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "If - Exists Already4": {
      "main": [
        [
          {
            "node": "Loop Over Items4",
            "type": "main",
            "index": 0
          }
        ],
        [
          {
            "node": "Is AI Related4",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Supabase5": {
      "main": [
        [
          {
            "node": "JinaAI Search5",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Is AI Related4": {
      "main": [
        [
          {
            "node": "If - Is AI4",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Write Article5": {
      "main": [
        [
          {
            "node": "Get Image",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Save Article5": {
      "main": [
        [
          {
            "node": "Loop Over Items4",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Get Image": {
      "main": [
        [
          {
            "node": "Supabase6",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Supabase6": {
      "main": [
        [
          {
            "node": "Save Article5",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "HTTP Request5": {
      "main": [
        [
          {
            "node": "XML5",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "XML5": {
      "main": [
        [
          {
            "node": "Split Out5",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Split Out5": {
      "main": [
        [
          {
            "node": "Loop Over Items7",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Loop Over Items7": {
      "main": [
        null,
        [
          {
            "node": "Create RSS Item7",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "JinaAI Search8": {
      "main": [
        [
          {
            "node": "Write Article8",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "OpenAI Chat Model15": {
      "ai_languageModel": [
        [
          {
            "node": "Write Article8",
            "type": "ai_languageModel",
            "index": 0
          }
        ]
      ]
    },
    "Save Article8": {
      "main": [
        [
          {
            "node": "Loop Over Items7",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "OpenAI Chat Model16": {
      "ai_languageModel": [
        [
          {
            "node": "Is AI Related7",
            "type": "ai_languageModel",
            "index": 0
          }
        ]
      ]
    },
    "Create RSS Item7": {
      "main": [
        [
          {
            "node": "If - Exists Already7",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "If - Is AI7": {
      "main": [
        [
          {
            "node": "Supabase9",
            "type": "main",
            "index": 0
          }
        ],
        [
          {
            "node": "Loop Over Items7",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "If - Exists Already7": {
      "main": [
        [
          {
            "node": "Loop Over Items7",
            "type": "main",
            "index": 0
          }
        ],
        [
          {
            "node": "Is AI Related7",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Supabase9": {
      "main": [
        [
          {
            "node": "JinaAI Search8",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Get Image3": {
      "main": [
        [
          {
            "node": "Supabase10",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Supabase10": {
      "main": [
        [
          {
            "node": "Save Article8",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Is AI Related7": {
      "main": [
        [
          {
            "node": "If - Is AI7",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Write Article3": {
      "main": [
        [
          {
            "node": "Save Article3",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "HTTP Request6": {
      "main": [
        [
          {
            "node": "XML6",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "XML6": {
      "main": [
        [
          {
            "node": "Split Out6",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Split Out6": {
      "main": [
        [
          {
            "node": "Loop Over Items",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Loop Over Items": {
      "main": [
        null,
        [
          {
            "node": "Create RSS Item",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "JinaAI Search": {
      "main": [
        [
          {
            "node": "Write Article",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "OpenAI Chat Model": {
      "ai_languageModel": [
        [
          {
            "node": "Write Article",
            "type": "ai_languageModel",
            "index": 0
          }
        ]
      ]
    },
    "Save Article": {
      "main": [
        [
          {
            "node": "Loop Over Items",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "OpenAI Chat Model17": {
      "ai_languageModel": [
        [
          {
            "node": "Is AI Related",
            "type": "ai_languageModel",
            "index": 0
          }
        ]
      ]
    },
    "Create RSS Item": {
      "main": [
        [
          {
            "node": "If - Exists Already",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "If - Is AI": {
      "main": [
        [
          {
            "node": "Supabase11",
            "type": "main",
            "index": 0
          },
          {
            "node": "JinaAI Search",
            "type": "main",
            "index": 0
          }
        ],
        [
          {
            "node": "Loop Over Items",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "If - Exists Already": {
      "main": [
        [
          {
            "node": "Loop Over Items",
            "type": "main",
            "index": 0
          }
        ],
        [
          {
            "node": "Is AI Related",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Supabase11": {
      "main": [
        [
          {
            "node": "JinaAI Search",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Get Image4": {
      "main": [
        [
          {
            "node": "Supabase12",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Supabase12": {
      "main": [
        [
          {
            "node": "Save Article",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Is AI Related": {
      "main": [
        [
          {
            "node": "If - Is AI",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Write Article8": {
      "main": [
        [
          {
            "node": "Get Image3",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Write Article": {
      "main": [
        [
          {
            "node": "Get Image4",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Globals1": {
      "main": [
        [
          {
            "node": "HTTP Request5",
            "type": "main",
            "index": 0
          },
          {
            "node": "HTTP Request6",
            "type": "main",
            "index": 0
          },
          {
            "node": "HTTP Request1",
            "type": "main",
            "index": 0
          },
          {
            "node": "HTTP Request",
            "type": "main",
            "index": 0
          },
          {
            "node": "HTTP Request2",
            "type": "main",
            "index": 0
          }
        ]
      ]
    }
  },
  "pinData": {}
}
```

## 更多来自乔·泰勒的文章

## 来自 Medium 的推荐

[

See more recommendations

](https://medium.com/?source=post_page---read_next_recirc--40cf3753a387---------------------------------------)