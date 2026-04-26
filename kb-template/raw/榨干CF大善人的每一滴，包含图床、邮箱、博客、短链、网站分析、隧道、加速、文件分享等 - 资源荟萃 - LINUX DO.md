---
title: "榨干CF大善人的每一滴，包含图床、邮箱、博客、短链、网站分析、隧道、加速、文件分享等 - 资源荟萃 - LINUX DO"
source: "https://linux.do/t/topic/53944"
author:
  - "[[LINUX DO]]"
published: 2024-04-11
created: 2025-03-11
description: "一切尽在这个仓库， zhuima/awesome-cloudflare: :partly_sunny: 精选的 Cloudflare 工具、开源项目、指南、博客和其他资源列表。 (github.com) 以下是复制的readme Awe…"
tags:
  - "clippings"
---
一切尽在这个仓库， [zhuima/awesome-cloudflare: 精选的 Cloudflare 工具、开源项目、指南、博客和其他资源列表。 (github.com)](https://github.com/zhuima/awesome-cloudflare)

以下是复制的readme

> [![Typing SVG](https://readme-typing-svg.demolab.com/?font=Fira+Code&pause=1000&vCenter=true&multiline=true&random=false&height=80&lines=%E7%B2%BE%E9%80%89%E7%9A%84%E4%BA%92%E8%81%94%E7%BD%91%E4%B9%8B%E5%85%89+Cloudflare+%E5%BC%80%E6%BA%90%E9%A1%B9%E7%9B%AE;%E3%80%81%E6%8C%87%E5%8D%97%E3%80%81%E5%8D%9A%E5%AE%A2%E5%92%8C%E5%85%B6%E4%BB%96%E8%B5%84%E6%BA%90%E5%88%97%E8%A1%A8%E3%80%82)](https://git.io/typing-svg)

被称为赛博菩萨的 Cloudflare 提供内容交付网络 （CDN） 服务、DDoS 缓解、互联网安全和分布式域名服务器 （DNS） 服务，位于访问者和 Cloudflare 用户的托管提供商之间，充当网站的反向代理。

本仓库只收录基于Cloudflare的开源工具，为独立开发者早期摸索期提供一个省心省时的工具集，持续整理中……

**收录标准：**

- 帮助但不限于独立开发者提升开发效率
- 帮助但不限于独立开发者降低成本
- 足够简单便捷

欢迎提 pr 和 issues 更新。 部署或操作过程中有任何问题可以提issue或者私信咨询～

## Contents

- [图床](https://untitled+.vscode-resource.vscode-cdn.net/Untitled-2#%E5%9B%BE%E5%BA%8A)
- [邮箱](https://untitled+.vscode-resource.vscode-cdn.net/Untitled-2#%E9%82%AE%E7%AE%B1)
- [博客](https://untitled+.vscode-resource.vscode-cdn.net/Untitled-2#%E5%8D%9A%E5%AE%A2)
- [短链](https://untitled+.vscode-resource.vscode-cdn.net/Untitled-2#%E7%9F%AD%E9%93%BE)
- [网站分析](https://untitled+.vscode-resource.vscode-cdn.net/Untitled-2#%E7%BD%91%E7%AB%99%E5%88%86%E6%9E%90)
- [隧道](https://untitled+.vscode-resource.vscode-cdn.net/Untitled-2#%E9%9A%A7%E9%81%93)
- [加速](https://untitled+.vscode-resource.vscode-cdn.net/Untitled-2#%E5%8A%A0%E9%80%9F)
- [文件分享](https://untitled+.vscode-resource.vscode-cdn.net/Untitled-2#%E6%96%87%E4%BB%B6%E5%88%86%E4%BA%AB)
- [测速](https://untitled+.vscode-resource.vscode-cdn.net/Untitled-2#%E6%B5%8B%E9%80%9F)
- [文章](https://untitled+.vscode-resource.vscode-cdn.net/Untitled-2#%E6%96%87%E7%AB%A0)
- [其他](https://untitled+.vscode-resource.vscode-cdn.net/Untitled-2#%E5%85%B6%E4%BB%96)

## 图床

| 名称 | 特性 | 在线地址 | 状态 |
| --- | --- | --- | --- |
| [Telegraph-Image-Hosting](https://github.com/missuo/Telegraph-Image-Hosting) | 使用 Telegraph 构建免费图像托管 |  | 不再维护 |
| [cf-image-hosting](https://github.com/ifyour/cf-image-hosting) | 在 Telegraph 上免费无限制地托管图像，部署在 Cloudflare 上。 | [https://images.mingming.dev](https://images.mingming.dev/) | 维护中 |
| [img-mom](https://github.com/beilunyang/img-mom) | 基于 Cloudflare Workers 运行时构建, 轻量使用完全免费，支持多种图床（Telegram/Cloudfalre R2/Backblaze B2, 更多图床正在支持中），快速部署。使用 Wrangler 可快速实现自部署 |  | 维护中 |
| [workers-image-hosting](https://github.com/iiop123/workers-image-hosting) | 基于cloudflare workers数据存储于KV的图床 |  | 维护中 |
| [Telegraph-Image](https://github.com/cf-pages/Telegraph-Image) | 免费图片托管解决方案，Flickr/imgur 替代品。使用 Cloudflare Pages 和 Telegraph。 | [https://im.gurl.eu.org/](https://im.gurl.eu.org/) | 维护中 |
| [cloudflare-worker-image](https://github.com/ccbikai/cloudflare-worker-image) | 使用 Cloudflare Worker 处理图片, 依赖 Photon，支持缩放、剪裁、水印、滤镜等功能。 |  | 维护中 |
| [tgState](https://github.com/csznet/tgState) | 使用Telegram作为存储的文件外链系统，不限制文件大小和格式。 | [https://tgstate.vercel.app](https://tgstate.vercel.app/) | 维护中 |

## 邮箱

| 名称 | 特性 | 在线地址 | 状态 |
| --- | --- | --- | --- |
| [vmail](https://github.com/oiov/vmail) | Open source temporary email tool. 开源临时邮箱工具，支持收发邮件。 | [https://vmail.dev/](https://vmail.dev/) | 维护中 |
| [smail](https://github.com/akazwz/smail) | 临时邮箱服务 | [https://smail.pw/](https://smail.pw/) | 维护中 |
| [Email.ML](https://email.ml/) | 一个运行在 Cloudflare 网络中的临时邮箱 |  | 未开源 |
| [cloudflare\_temp\_email](https://github.com/dreamhunter2333/cloudflare_temp_email) | 使用 cloudflare 免费服务，搭建临时邮箱 | [https://temp-email.dreamhunter2333.xyz/](https://temp-email.dreamhunter2333.xyz/) | 维护中 |
| [mail2telegram](https://github.com/TBXark/mail2telegram) | 这是一个基于 Cloudflare Email Routing Worker 的 Telegram Bot，可以将电子邮件转换为 Telegram 消息。您可以将任何前缀的收件人的电子邮件转发到 Bot，然后将创建一个具有无限地址的临时邮箱 Bot。 |  | 维护中 |

## 博客

| 名称 | 特性 | 在线地址 | 状态 |
| --- | --- | --- | --- |
| [cloudflare-workers-blog](https://github.com/gdtool/cloudflare-workers-blog) | 这是一个运行在cloudflare workers 上的博客程序,使用 cloudflare KV作为数据库,无其他依赖. 兼容静态博客的速度,以及动态博客的灵活性,方便搭建不折腾. | [https://blog.gezhong.vip/](https://blog.gezhong.vip/) | 维护中 |
| [cloudflare-workers-blog](https://github.com/kasuganosoras/cloudflare-worker-blog) | Cloudflare workers + Github 实现的动态博客系统，使用边缘计算，无需服务器 |  | 好像是不维护了 |
| [microfeed](https://github.com/microfeed/microfeed) | 一个在 Cloudflare 上自托管的轻量级内容管理系统 (CMS)。通过 microfeed，您可以轻松地将各种内容（例如音频、视频、照片、文档、博客文章和外部 URL）以 Web、RSS 和 JSON 的形式发布到 feed。对于想要自行托管自己的 CMS 而无需运行自己的服务器的精通技术的个人来说，这是完美的解决方案。 | [https://www.microfeed.org/](https://www.microfeed.org/) | 维护中 |
| [emaction.frontend](https://github.com/emaction/emaction.frontend) | 基于Cloudflare D1实现的 GitHub 风格的 Reactions 点赞功能， 本项目是后端。 | [https://emaction.cool/](https://emaction.cool/) | 维护中 |
| [emaction.backend](https://github.com/emaction/emaction.backend) | 基于Cloudflare D1实现的 GitHub 风格的 Reactions 点赞功能， 本项目是后端。 | [https://emaction.cool/](https://emaction.cool/) | 维护中 |

## 短链

| 名称 | 特性 | 在线地址 | 状态 |
| --- | --- | --- | --- |
| [short](https://github.com/igengdu/short/) | 一个使用 Cloudflare Pages 创建的 URL 缩短器。 | [https://d.igdu.xyz/](https://d.igdu.xyz/) | 维护中 |
| [short](https://github.com/x-dr/short) | 一个使用 Cloudflare Pages 创建的 URL 缩短器。 | [https://d.131213.xyz/](https://d.131213.xyz/) | 维护中 |
| [linklet](https://github.com/harrisonwang/linklet) | 个使用 Cloudflare Pages 创建的 URL 缩短器。这个是基于API模式实现，使用场景更多一些 | [https://wss.so/](https://wss.so/) | 维护中 |
| [Url-Shorten-Worker](https://github.com/crazypeace/Url-Shorten-Worker) | 使用秘密路径访问操作页面。支持自定义短链。API 不公开服务。页面缓存设置过的短链。长链接文本框预搜索localStorage。增加删除某条短链的按钮。增加读取KV的按钮。变身网络记事本 Pastebin。变身图床 Image Hosting。A URL Shortener created using Cloudflare worker and KV | [Shorter URL](https://urlsrv.crazypeace.workers.dev/bodongshouqulveweifengci) | 维护中 |
| [duanwangzhi](https://github.com/Closty/duanwangzhi) | 无需服务即可缩短您的链接，因为它基于 Cloudflare 工作人员功能，具有极简风格。 |  | 好像是不维护了 |
| [Url-Shorten-Worker](https://github.com/horsemail/Url-Shorten-Worker) | 这个是fork的crazypeace的Url-Shorten-Worker， 使用秘密路径访问操作页面。支持自定义短链。API 不公开服务。页面缓存设置过的短链。长链接文本框预搜索localStorage。增加删除某条短链的按钮。增加读取KV的按钮。变身网络记事本 Pastebin。变身图床 Image Hosting。A URL Shortener created using Cloudflare worker and KV。 | [Shorter URL](https://1way.eu.org/bodongshouqulveweifengci) | 维护中 |

## 网站分析

| 名称 | 特性 | 在线地址 | 状态 |
| --- | --- | --- | --- |
| [analytics\_with\_cloudflare](https://github.com/yestool/analytics_with_cloudflare) | 免费开源网页访客计数器, Webviso 是一个基于Cloudflare worker服务+Cloudflare D1数据库实现的完全免费的在线web访客统计服务。 功能与目前常用的 不蒜子 - 极简网页计数器 相同。Webviso完全开源，你可以实现自定义需求。 基于Cloudflare的微服务架构可快速自行部署上线。 | [https://webviso.yestool.org/](https://webviso.yestool.org/) | 维护中 |
| [counterscale](https://github.com/benvinegar/counterscale) | Counterscale 是一个简单的 Web 分析跟踪器和仪表板，效果和 umami 类似，您可以在 Cloudflare 上自行托管。它的设计易于部署和维护，即使在高流量的情况下，您的操作成本也应该接近于零（Cloudflare 的免费套餐假设可以支持每天高达 10 万次点击）。 | [https://counterscale.dev/](https://counterscale.dev/) | 维护中 |

## 隧道

| 名称 | 特性 | 在线地址 | 状态 |
| --- | --- | --- | --- |
| [Cloudflared-web](https://github.com/WisdomSky/Cloudflared-web) | Cloudflared-web 是一个 docker 镜像，它打包了 cloudflared cli 和简单的 Web UI，以便轻松启动/停止 cloudflare 隧道。 |  | 维护中 |

## 加速

| 名称 | 特性 | 在线地址 | 状态 |
| --- | --- | --- | --- |
| [gh-proxy](https://github.com/hunshcn/gh-proxy) | github release、archive以及项目文件的加速项目，支持clone，有Cloudflare Workers无服务器版本以及Python版本。 | [https://gh.api.99988866.xyz/](https://gh.api.99988866.xyz/) | 维护中 |

## 文件分享

| 名称 | 特性 | 在线地址 | 状态 |
| --- | --- | --- | --- |
| [pastebin-worker](https://github.com/SharzyL/pastebin-worker) | 介绍一个部署在 Cloudflare Workers 上的开源 Pastebin，通过URL分享"文本"或"文件"。如CF免费套餐：每天允许 10W 次读取、1000 次写入和 删除操作，大小限制在 25 MB 以下，轻量用足够了。自己部署或直接用。它还有“删除时间设置”和“密码”功能，可以设置一段时间后删除您的paste。用于twitter分享文件和文本，极好 | [https://shz.al/](https://shz.al/) | 维护中 |
| [FileWorker](https://github.com/yllhwa/FileWorker) | 运行在Cloudflare Worker上的在线剪贴板/文件共享 |  | 维护中 |
| [dingding](https://github.com/iiop123/dingding) | 一款基于cloudflare workers的文件传输工具，文件存储在cloudflare KV中 |  | 好像不维护了 |

## 测速

| 名称 | 特性 | 在线地址 | 状态 |
| --- | --- | --- | --- |
| [CloudflareSpeedTest](https://github.com/XIU2/CloudflareSpeedTest) | 国外很多网站都在使用 Cloudflare CDN，但分配给中国内地访客的 IP 并不友好（延迟高、丢包多、速度慢）。虽然 Cloudflare 公开了所有 IP 段 ，但想要在这么多 IP 中找到适合自己的，怕是要累死，于是就有了这个软件。 |  | 维护中 |
| [SpeedTest](https://speed.cloudflare.com/) | 官方的SpeedTest工具。 |  | 运行中 |

## 文章

| 名称 | 特性 | 在线地址 | 状态 |
| --- | --- | --- | --- |
| [workers](https://igdux.com/workers) | Cloudflare Workers优秀项目收集。 |  | 有效中 |
| [accelerate-and-secure-with-cloudflared](https://nova.moe/accelerate-and-secure-with-cloudflared/) | 这是一篇博客，主要是教你使用 Cloudflare Argo Tunnel(cloudflared) 来加速和保护你的网站。 |  | 有效中 |
| [jsonbin](https://www.owenyoung.com/blog/jsonbin/) | 在 Cloudflare Workers 部署一个 JSON as a Storage 服务。 |  | 有效中 |
| [cronbin](https://www.owenyoung.com/blog/cronbin/) | 在 Cloudflare Workers 部署一个带有 Dashboard 的 Cron 服务。 |  | 有效中 |
| [using-cloudflare-worker-proxy-google](https://xiaowangye.org/posts/using-cloudflare-worker-proxy-google/) | 使用 Cloudflare Worker 代理 Google 站点。 |  | 有效中 |
| [Use-Cloudflare-Zero-Trust-protect-your-web-applications](https://jiapan.me/2023/Use-Cloudflare-Zero-Trust-protect-your-web-applications/) | 使用 Cloudflare Zero Trust 保护你的 Web 应用。 |  | 有效中 |
| [Nextjs-app-router-with-cloudflare-r2](https://juejin.cn/post/7306723921717166131) | 如何在 Next.js 13的 app/ 目录中使用 Cloudflare R2 存储。 |  | 有效中 |
| [cloudflare-webssh-zerotrust](https://josephcz.xyz/technology/network/cloudflare-webssh-zerotrust/) | 使用 Cloudflare ZeroTrust 搭建 WebSSH。 |  | 有效中 |

## 其他

| 名称 | 特性 | 在线地址 | 状态 |
| --- | --- | --- | --- |
| [silk-privacy-pass-client](https://chromewebstore.google.com/detail/silk-privacy-pass-client/ajhmfdgkijocedmfjonnpjfojldioehi) | 频繁出现Cloudflare人机验证，可以用这个Cloudflare官方插件解决，装了之后，再也不会动不动跳出人机验证了。 |  | 维护中 |
| [WARP-Clash-API](https://github.com/vvbbnn00/WARP-Clash-API) | 该项目可以让你通过订阅的方式使用WARP+，支持Clash、Shadowrocket等客户端。项目内置了 刷取WARP+流量的功能，可以让你的WARP+流量不再受限制（每18秒可获得1GB流量），同时， 配备了IP选优功能。支持Docker compose 一键部署，无需额外操作，即可享受你自己的WARP+私 有高速节点！ |  | 维护中 |
| [ip-api](https://github.com/ccbikai/ip-api) | 利用 Cloudflare Workers / Vercel Edge / Netlify Edge 快速搭一个获取 IP 地址和地理位置信息的接口。 | [本机 IP 查询 \| HTML.ZONE](https://html.zone/ip) | 维护中 |
| [ChatGPT-Telegram-Workers](https://github.com/TBXark/ChatGPT-Telegram-Workers) | 轻松在 Cloudflare Workers 上部署您自己的 Telegram ChatGPT 机器人，有详细的视频和图文教程，搭建过程也不复杂，小白也能上手。 |  | 维护中 |
| [RSSWorker](https://github.com/yllhwa/RSSWorker) | RSSWorker 是一个轻量级的 RSS 订阅工具，可以部署在 Cloudflare Worker 上。 |  | 维护中 |
| [deeplx-for-cloudflare](https://github.com/ifyour/deeplx-for-cloudflare) | Deploy DeepLX on Cloudflare。 | [https://deeplx.mingming.dev/](https://deeplx.mingming.dev/) | 维护中 |
| [sub\_converter\_convert](https://github.com/zzNeutrino/sub_converter_convert) | 转换ssr/v2ray订阅链接转换的工具。 |  | 好像不维护了 |
| [telegram-counter](https://github.com/iamshaynez/telegram-counter) | 用纯粹的 Cloudflare Worker 和 D1 数据库写了个 Telegram 的后端，方便可以随时随地的做一些打卡的记录……。 |  | 好像不维护了 |
| [Cloudflare-No-Tracked](https://github.com/fwqaaq/Cloudflare-No-Tracked) | 用于去除 b 站以及小红书的跟踪链接，同时也有 tg 的 bot 版本 | [https://notracked.fwqaq.us/](https://notracked.fwqaq.us/) | 维护中 |

- [佬们 是怎么把大善人搞成图床的](https://linux.do/t/topic/101810/7)
- [请推荐一下基于Cloudflare的简单个人博客](https://linux.do/t/topic/101144/2)
- [在spaceship注册了个xyz 不知道用来干啥](https://linux.do/t/topic/181655/2)
- [Cloudflare Worker可以做什么？](https://linux.do/t/topic/324637/16)
- [求助:我有几个cloudns的域名，想搞域名邮箱](https://linux.do/t/topic/284309/6)
- 其他 2 个

[3](https://linux.do/u/ljnchn "ljnchn")

[2](https://linux.do/u/icbc "icbc")

[2](https://linux.do/u/littleking "littleking")

[2](https://linux.do/u/xcf "xcf")

[2](https://linux.do/u/mika24 "mika24")

阅读时间 14 分钟