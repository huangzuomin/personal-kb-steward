---
title: "n8n Workflow Automation A Step-by-Step Tutorial for Report Generation & Scheduling"
source: "https://medium.com/intelliconnect-engineering/n8n-workflow-automation-a-step-by-step-tutorial-for-report-generation-scheduling-19abe06f4d15"
author:
  - "[[Ose Verma]]"
published: 2023-11-16
created: 2025-06-04
description: "n8n is an open-source, workflow automation tool that simplifies and streamlines tasks by connecting various applications and services. n8n offers a visual interface where users can create automated…"
tags:
  - "clippings"
---
[Sitemap](https://medium.com/sitemap/sitemap.xml)## [IntelliconnectQ 工程](https://medium.com/intelliconnect-engineering?source=post_page---publication_nav-e6b9c9a0ba12-19abe06f4d15---------------------------------------)

[![IntelliconnectQ Engineering](https://miro.medium.com/v2/resize:fill:76:76/1*2nYmktVdRwe-k9CyeNGieA.png)](https://medium.com/intelliconnect-engineering?source=post_page---post_publication_sidebar-e6b9c9a0ba12-19abe06f4d15---------------------------------------)

我们构建正确的解决方案，助力您的业务转型与增长！

![](https://miro.medium.com/v2/resize:fit:640/format:webp/1*zjd1qaJuzUI3k_94Z39E3g.png)

![](https://miro.medium.com/v2/resize:fit:640/format:webp/1*KVuzBgzeN0gPlZpXqw9q_Q.png)

n8n 工作流

## 什么是 n8n？

**n8n 是一款开源的工作流自动化工具** ，通过连接各种应用程序和服务来简化和优化任务。

n8n 提供了一个 **可视化界面** ，用户可以通过使用代表 Outlook、Teams 等流行服务的众多预构建节点，创建名为“n8n 工作流”的自动化流程。

用户可以设计在这些服务之间触发操作和数据传输的工作流，从而实现  
a. 自动化重复任务的宝贵工具，  
b. 提高生产力，以及  
c. 集成软件工具。

n8n 具有 **高度可定制性** ，非常适合希望通过自动化提高效率的个人和企业。

**n8n 的基本术语/信息**

节点：动作和触发器被称为节点。

对于所有输入（大多数情况下），输入分为两种类型：

固定值：它是一个静态值  
在这里我们可以从之前的节点添加动态值

> 与 Power Automate 不同，您可以单独运行各个节点来测试流程，无需一次性运行整个流程进行测试。

您可以在左侧查看节点的输入，在右侧查看输出。

**现在让我们构建一个包含调度触发器的流程。**  
此流程调用了一个用于面料报告的 API，我们需要筛选出 *pending\_fabrics* 为 0 和 1 的数据，为此，我们使用 switch 节点，并基于此发送邮件和 Teams 消息。

**第一步：设置计划触发器**

![](https://miro.medium.com/v2/resize:fit:640/format:webp/1*JCIZGpFf2OlxWqD7NZScIg.png)

计划触发器

调度触发器设置为每天下午 4 点运行流程，持续 0 分钟。你也可以使用自定义（cron）来定义时间。 [Cron 自定义时间](https://crontab.guru/#30_9_*_*_1-6)

**第二步：HTTP 请求**

在 HTTP 请求中，我们对 URL 执行 POST 方法，可以将主体以 Json 格式发送。

![](https://miro.medium.com/v2/resize:fit:640/format:webp/1*c7CgtFfIl6bsuGpKobFyHA.png)

![](https://miro.medium.com/v2/resize:fit:640/format:webp/1*c7CgtFfIl6bsuGpKobFyHA.png)

当你点击“执行节点”时，右侧会以 JSON 格式显示输出结果。你可以将格式更改为模式、表格或 JSON。

**步骤3：切换节点**

现在，我们有了报告所需的数据，需要根据名为 *pending\_fabrics* 的列来筛选数据。这里，模式为“规则”，因为我们正在检查数字，所以数据类型为数字。在我们将要比较的值中，表达式来自前一个节点。当你点击该列时，表达式就会显示出来。

![](https://miro.medium.com/v2/resize:fit:640/format:webp/1*q4gUiK-y10j4hyKlDOIKaw.png)

![](https://miro.medium.com/v2/resize:fit:640/format:webp/1*yox2koPHYPQJWKirzOKUsA.png)

切换规则：当等于1时以及当值等于0时。

![](https://miro.medium.com/v2/resize:fit:640/format:webp/1*01ZT8WaPvSzib5G0PHQ-Yw.png)

点击执行节点后，你会看到输出标记为1、2、3等。我们只有两个有用的输出。

![](https://miro.medium.com/v2/resize:fit:640/format:webp/1*jV40tNqVzULaIAvALFuLJQ.png)

**步骤 4：运行 JavaScript 以添加序列号**

在此处，循环针对先前的 JSON 运行，并将字段添加为计数变量。当我们执行它时，你可以在右侧看到序列号已被添加。

![](https://miro.medium.com/v2/resize:fit:640/format:webp/1*WSbpTawF9wh7BVp2uSjQrA.png)

**步骤5：项目列表操作：收集数据并为列命名**

操作项为“项目列表”，具体操作为“拆分项目”。我选择了需要放入报告中的列，并在选项中为所有列指定了目标字段名称。

![](https://miro.medium.com/v2/resize:fit:640/format:webp/1*_QwOQ2JxXZhFp7JLwkQ0Rw.png)

**第 6 步：转换为 HTML 表格**

该操作是 HTML，功能是转换为 HTML 表格。我为表格、表头和单元格添加了一些属性。此节点从前一个节点获取 JSON 数据，并将其添加到 HTML 表格中。

对于表格：

*style = “font-family:Arial, Helvetica, sans-serif;border-collapse: collapse;width: 100%;”*

对于标题，

*style = “font-size:15px;font-weight:bold;height:30px;padding:12px 12px;background-color:#1C6EA4;color:white”*

对于细胞而言，

*style = “边框:1px 实线 #ddd; 内边距:3px 3px”*

![](https://miro.medium.com/v2/resize:fit:640/format:webp/1*Noxv9t2Gx76XCy963o1Nig.png)

**步骤 7：在 Microsoft Teams 中创建聊天消息**

[*创建团队连接的链接*](https://docs.n8n.io/integrations/builtin/credentials/microsoft/?utm_source=n8n_app&utm_medium=left_nav_menu&utm_campaign=create_new_credentials_modal#using-oauth) 连接后，我们可以选择资源和操作。这里的资源是聊天消息，操作是创建。从聊天名称中，选择您想要发送消息的对象。这里，消息类型是 HTML。只需点击一下，我们就可以从表达式中添加之前创建的 HTML 表格！

![](https://miro.medium.com/v2/resize:fit:640/format:webp/1*umFR3sv_9xHQzZRsVTpx2Q.png)

**步骤 8：发送 Outlook 邮件**

操作选择 Microsoft Outlook，具体操作为发送消息。你可以通过 Azure 中的新应用注册，以与 Teams 相同的方式连接凭证。我们添加收件人、主题和消息，方法与在 Teams 中相同。

![](https://miro.medium.com/v2/resize:fit:640/format:webp/1*kxfNg1BTgoJKEE8CoU3pJg.png)

执行完成后，您将收到一封包含报告和团队消息的电子邮件。

## 为什么我们的团队喜欢 n8n？

n8n 使用起来非常出色，因为  
1\. 它拥有出色的 **文档** 。对于每个节点，你都可以看到一个文档标签，点击它会带你进入相应标签的文档页面。

2\. 一个活跃的 **论坛，成员们** 通常在一小时内回复。这个可视化工具使用起来非常得心应手。

3\. 与其他我们使用过的工具不同，这款可视化工具非常直观。

4\. 在工具中加入 JavaScript 和 Python 代码片段可以提升其功能。

5\. 自托管选项让我们的客户免于 IT 安全和隐私方面的担忧。

当然！n8n 和其他工具一样，有其自身的优缺点。以下是一个概述：

**n8n 的优势** :

1\. **开源** : n8n 是一个开源平台，允许用户访问、修改和贡献源代码。这促进了协作社区的发展，并确保了透明度。

2\. **用户友好界面** ：n8n 提供了一个用户友好的可视化工作流编辑器，无需深入的编程知识。这使得它能够被更广泛的用户群体所使用，包括那些不具备强大编程技能的人。

3\. **广泛的集成支持** ：n8n 支持与多种流行应用程序和服务进行集成，使用户能够创建跨多个平台的全面工作流程。

4\. **灵活性与定制化** ：用户可以根据自身需求定制工作流。n8n 支持创建包含条件逻辑、循环及其他高级功能的复杂工作流。

5\. **活跃的社区** ：n8n 拥有一个活跃且不断壮大的社区。用户可以寻求帮助、分享他们的工作流程，并为平台的发展做出贡献。

6\. **跨平台兼容性** ：n8n 可以在不同平台上运行，包括自托管环境、云服务和 Docker 容器。

7\. **安全性高，可自托管 n8n：** n8n 支持自托管，数据因此得到保障。尽管如此，用户仍需确保实施适当的身份验证和访问控制措施，以保护工作流中使用的敏感数据。

8\. **n8n 的速度与性能** ：在使用 Postgres 数据库、配备 4GB 内存的普通硬件上，流程可在 100 秒内处理 200 个请求。

![](https://miro.medium.com/v2/resize:fit:640/format:webp/1*AYEnZu0j0pwezgXj5ih23g.png)

该图表展示了在 100 秒（约 1 分半钟）内，向 webhook 触发节点发出的请求获得响应的百分比，以及这一比例如何随负载变化。在高负载情况下，n8n 通常仍能处理数据，但响应时间会超过 100 秒。

**以下是一些缺点：**

1\. **复杂工作流的学习曲线** ：虽然可视化编辑器使得创建简单的工作流变得容易，但更复杂的场景可能需要一定的学习曲线，尤其对于不熟悉工作流自动化概念的用户来说。

2\. **资源密集型** : 运行 n8n 工作流可能需要大量资源，特别是对于更大、更复杂的工作流。用户在部署 n8n 时应考虑资源需求。

3\. **企业功能有限** ：n8n 可能无法提供与某些商业替代方案相同水平的企业功能和支持。对于有特定需求的大型组织来说，这可能是一个需要考虑的因素。

4\. **对第三方服务的依赖** : n8n 工作流的成功依赖于第三方服务和 API 的稳定性和可用性。如果某个服务发生变化或出现停机，可能会影响工作流的可靠性。

## 结论

n8n 是一款功能强大且灵活的自动化工具，具有一系列优势，尤其适合寻求开源和可定制解决方案的用户。然而，在选择 n8n 或任何其他自动化平台之前，用户应仔细评估其具体使用场景和需求。

## 关于 Intelliconnect

> 我们在 **Intelliconnect** 与那些怀有雄心壮志、计划扩展业务的领导者们合作。我们提供定制化的解决方案。
> 
> 1\. **实现自主决策** ，减少并最终消除对人干预的需求。
> 
> 2\. **提供信号与洞察** ，以 **促成迅速行动** 。
> 
> 3\. **赋能团队** ，通过实时信息支持战略和运营决策，推动数据驱动文化的发展。
> 
> 4\. 是否针对角色进行了 **个性化** 设计，并且易于使用、无缝衔接，即 **用户所需付出的努力** 为零或 **最小化**
> 
> **联系我们，邮箱：solutions\[at\]intelliconnectq.com**

## 尚无回应

温故智新

What are your thoughts?  

## 更多来自 Ose Verma 和 IntelliconnectQ Engineering 的内容

## 来自 Medium 的推荐

[

See more recommendations

](https://medium.com/?source=post_page---read_next_recirc--19abe06f4d15---------------------------------------)