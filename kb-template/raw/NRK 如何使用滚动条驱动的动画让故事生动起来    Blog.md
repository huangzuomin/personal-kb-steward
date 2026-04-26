---
title: "NRK 如何使用滚动条驱动的动画让故事生动起来  |  Blog"
source: "https://developer.chrome.com/blog/nrk-casestudy?hl=zh-cn"
author:
  - "[[Chrome for Developers]]"
published:
created: 2025-04-21
description: "了解滚动条驱动的动画和滚动触发的动画如何增强故事性文章的效果"
tags:
  - "clippings"
---
[滚动驱动型动画](https://developer.mozilla.org/docs/Web/CSS/animation-timeline) 已从主线程 JavaScript 实现的卡顿动画演变为使用滚动时间轴和视图时间轴等 [现代 CSS 和界面功能](https://developer.chrome.com/blog/css-ui-ecommerce?hl=zh-cn) 实现的流畅、可访问的非主线程体验。这种转变有助于快速制作原型和高性能动画，同时让团队能够制作出精致的 [滚动式讲述](https://en.m.wiktionary.org/wiki/scrollytelling) 页面，如本文所示。

## NRK 和讲故事

[NRK](https://www.nrk.no/) （挪威广播公司）是 [挪威的公共服务广播机构](https://www.nrk.no/about/a-gigantic-small-broadcaster-1.3698462) 。本文中所述实现背后的团队在挪威语中称为 Visuelle Historier，大致翻译为 *Visual Stories* （视觉故事）。该团队负责为电视、广播和网络编辑项目提供设计、图形和开发服务，开发视觉形象、内容图形、特写文章和新的视觉故事讲述形式。该团队还负责 NRK 的设计规范和子品牌，创建工具和模板，以便更轻松地发布符合 NRK 品牌形象的内容。

## NRK 如何使用滚动条驱动的动画

滚动条驱动的动画和滚动触发的动画可让故事性文章更具互动性、吸引力和记忆点，从而提升文章的效果。这种方法对于提供的图片很少或没有图片的非虚构叙事内容特别有用。

这些动画有助于强化或创造戏剧性要点、推动故事发展，以及开发与文字相符或对其进行强化的小型视觉叙事。由于这些动画是滚动驱动的，因此用户可以通过滚动来控制故事情节的进展。

<video controls="" height="1004" width="1344"><source src="https://developer.chrome.com/static/blog/nrk-casestudy/video/nrk-video-01.mp4?hl=zh-cn" type="video/mp4"></video>

### 提升用户体验

NRK 的用户数据分析显示，读者很欣赏这些动画如何引导他们的注意力。通过在用户滚动时突出显示文本或动画，用户可以更轻松地确定要点，并了解故事中最关键的方面，尤其是在浏览时。

此外，为图形添加动画效果可以简化复杂信息，让用户更轻松地理解各种关系和随时间推移的变化。通过动态构建、添加或突出显示信息，NRK 可以以更具教育性和吸引力的方式呈现内容。

<video controls="" height="1004" width="1344"><source src="https://developer.chrome.com/static/blog/nrk-casestudy/video/nrk-video-02.mp4?hl=zh-cn" type="video/mp4"></video>

### 设置氛围

动画可以成为营造或增强故事氛围的强大工具。通过调整动画的时间、速度和风格，NRK 可以唤起与叙事基调相符的情感。

### 分隔文本并提供视觉缓解

NRK 经常使用小动画插图以简单的图标或小插图的形式打破长篇幅文本，让读者可以暂时离开故事情节。许多用户对这种变体表示赞赏，并指出它可以将文本拆分，使其更易于理解。他们认为这在叙事中提供了一个恰当的停顿点。

### 尊重无障碍功能需求和用户偏好设置

挪威广播公司 (NRK) 的公开页面必须可供所有挪威公民访问。因此，网页必须遵循用户减少动画的偏好设置。所有网页内容都必须向启用了此浏览器设置的用户提供。

## 设计滚动条驱动的动画

NRK 开发并直接集成了一款新的滚动动画工具到其 [Sanity](https://www.sanity.io/) 内容管理系统 (CMS) 中，从而简化了设计工作流程。此工具由开发和维护网站的团队与 CMS 解决方案团队共同开发，可让设计师轻松地通过动画元素的起始位置和结束位置的视觉提示来原型化和实现滚动动画，并能够实时预览动画。这项创新可让设计师在 CMS 中直接获得更大的控制力，并加快设计流程。

![显示工具中滚动到视野中的区域。](https://developer.chrome.com/static/blog/nrk-casestudy/image/image1.png?hl=zh-cn)

类似示例 ：动画元素的起始和结束位置的视觉提示（并非真实的 CMS 工具）。

## 浏览器中的滚动条驱动的动画

### 以故事为驱动的动画

[没有人想念的男人](https://www.nrk.no/stor-oslo/xl/mann-la-dod-i-leilighet-i-oslo-i-ni-ar-1.15337692) 。

这篇文章讲述了一名男子在公寓中死了 9 年，但由于缺少其他视觉元素，因此必须大量依赖插图。插图通过滚动动画来强调故事情节，例如在动画中，夜幕降临，多层建筑中的灯光逐渐亮起，直到只有一间公寓仍未亮起灯。此动画是使用 NRK 的内部滚动条驱动型动画工具制作的。

<video controls="" height="1004" width="1344"><source src="https://developer.chrome.com/static/blog/nrk-casestudy/video/nrk-video-03.mp4?hl=zh-cn" type="video/mp4"></video>

### 文本淡出动画

[永久冻土](https://www.nrk.no/dokumentar/xl/frostens-vokter-1.14755370) 。

本文首先进行简要介绍，就像电影的开场序列一样。简洁的文字搭配全屏视觉效果，旨在提示文章内容，激发读者的好奇心，吸引他们深入阅读整篇文章。标题页的设计类似于电影海报，通过让文字向上和向外平滑呈现动画效果，采用滚动驱动型动画来强化这种感觉。

<video controls="" height="1004" width="1344"><source src="https://developer.chrome.com/static/blog/nrk-casestudy/video/nrk-video-04-new.mp4?hl=zh-cn" type="video/mp4"></video>
```
.article-section {
  animation: fade-up linear;
  animation-timeline: view();
  animation-range: entry 100% exit 100%;
}
```

### 滚动动画排版

文章标题中的动画排版 - [病休](https://www.nrk.no/norge/skyhogt-sjukefravaer_-sjekk-kor-sjuke-folk-pa-din-alder-er-1.17143974) 。

在“Sjukt sjuke”（大致翻译为“病得很厉害”）中，NRK 希望吸引读者阅读一篇关于挪威病休率不断上升的文章。标题旨在吸引读者的视线，让读者知道这不是他们预想的通常的、枯燥的以数字为依据的故事。NRK 团队希望文本和插图能与作品的主题相得益彰，并使用排版和滚动驱动型动画来增强这种效果。该文章采用了 NRK News 的新字体和设计规范。

<video controls="" height="1004" width="1344"><source src="https://developer.chrome.com/static/blog/nrk-casestudy/video/nrk-video-05.mp4?hl=zh-cn" type="video/mp4"></video>
```
<h1 aria-label="sjuke">
  <span>s</span><span>j</span><span>u</span><span>k</span><span>e</span>
<h1>
```
```
h1 span {
  display: inline-block;
}
```
```
if (window.matchMedia('print, (prefers-reduced-motion: reduce)').matches) {
  return;
}

const heading = document.querySelector("h1");
const letters = heading.querySelectorAll("span");

const timeline = new ViewTimeline({ subject: heading });
const scales = [/**/];
const rotations = [/**/];

for ([index, el] of letters.entries()) {
  el.animate(
    {
      scale: ["1", scales[index]],
      rotate: ["0deg", rotations[index]]
    },
    {
      timeline,
      fill: "both",
      rangeStart: "contain 30%",
      rangeEnd: "contain 70%",
      easing: "ease-out"
    }
  );
}
```

### 突出显示滚动截取的项

[机构中的孩子](https://www.nrk.no/stor-oslo/barn-og-unge-i-barnevernet-deler-videoer-om-rus-pa-tiktok-1.16835047) 。

读完一篇文章后，读者往往会想要详细了解同一问题。在关于机构中滥用物质的青少年的文章中，NRK 希望推荐一篇文章作为下一个要阅读的文章，同时也希望在读者愿意的情况下，为他们提供其他几篇文章的选项。解决方案是使用滚动捕获和滚动驱动型动画实现的可滑动导航栏。动画可确保将焦点放在活动元素上，同时使其余元素变暗。

<video controls="" height="1004" width="1344"><source src="https://developer.chrome.com/static/blog/nrk-casestudy/video/nrk-video-06.mp4?hl=zh-cn" type="video/mp4"></video>
```
for (let item of items) {
  const timeline = new ViewTimeline({ subject: item, axis: "inline" });
  const animation = new Animation(effect, timeline);
  item.animate(
    {
      opacity: [0.3, 1, 0.3]
    },
    { timeline, easing: "ease-in-out", fill: "both" }
  );
  animation.rangeStart = "cover calc(50% - 100px)";
  animation.rangeEnd = "cover calc(50% + 100px)";
}
```

### 滚动动画触发常规动画

[预算](https://www.nrk.no/norge/statsbudsjettet-er-lagt-fram_-slik-vil-staten-bruka-skattepengane-dine-1.17055718#:%7E:text=Me%20startar%20med%20det%20du%20brukar%20mest%20pengar%20p%C3%A5%3A) 。

在介绍挪威国家预算的这篇文章中，NRK 旨在让原本枯燥乏味、充斥数字的报道变得更易于理解和个性化。我们的目标是将庞大且难以理解的预算数字拆解开来，让读者能够了解自己的税款都花在了哪些方面。每个子部分都重点介绍了国家预算中的一项具体内容。读者的总税费贡献度用一个蓝色条形表示，该条形被划分为多个部分，以显示读者对这些具体项目的贡献度。该过渡是通过滚动驱动型动画实现的，该动画会触发各个项的动画效果。

<video controls="" height="1004" width="1344"><source src="https://developer.chrome.com/static/blog/nrk-casestudy/video/nrk-video-07.mp4?hl=zh-cn" type="video/mp4"></video>
```
const timeline = new ViewTimeline({
  subject: containerElement
});

// Setup scroll-driven animation
const scrollAnimation = containerElement.animate(
  {
    "--cover-color": ["blue", "lightblue"],
    scale: ["1 0.2", "1 3"]
  },
  {
    timeline,
    easing: "cubic-bezier(1, 0, 0, 0)",
    rangeStart: "cover 0%",
    rangeEnd: "cover 50%"
  }
);

// Wait for scroll-driven animation to complete
await scrollAnimation.finished;
scrollAnimation.cancel();

// Trigger time-driven animations
for (let [index, postElement] of postElements.entries()) {
  const animation = postElement?.animate(
    { scale: ["1 3", "1 1"] },
    {
      duration: 200,
      delay: index * 33,
      easing: "ease-out",
      fill: "backwards"
    }
  );
}
```

> “我们已经使用滚动条驱动的动画很长时间了。在 Web Animations API 出现之前，我们必须使用滚动事件，后来又与 Intersection Observer API 结合使用。这通常是一项非常耗时的任务，而现在，Web 动画和滚动驱动型动画 API 让这项任务变得轻而易举。”- *NRK 的前端开发者 Helge Silset*

NRK 有许多不同的 [Web 组件](https://web.dev/articles/web-components-io-2019?hl=zh-cn) ，可插入其自定义元素之一（称为 `ScrollAnimationDriver` \[`<scroll-animation-driver>`\]），支持以下动画：

- 使用 `[KeyframeEffects](https://developer.mozilla.org/docs/Web/API/KeyframeEffect)` 的图层
- [Lottie](https://airbnb.io/lottie/#/) 动画
- mp4
- [three.js](https://threejs.org/)
- `<canvas>`

以下示例将图层与 `KeyframeEffects` 结合使用：

```
<scroll-animation-driver data-range-start='entry-crossing 50%' data-range-end='exit-crossing 50%'>
  <layered-animation-effect>
    <picture>
      <source />
      <img />
    </picture>

    <picture>
      <source />
      <img />
    </picture>

    <picture>
      <source />
      <img />
    </picture>
  </layered-animation-effect>
</scroll-animation-driver>
```

NRK 对其 `<scroll-animation-driver>` 自定义元素的 JavaScript 实现：

```
export default class ScrollAnimationDriver extends HTMLElement {
  #timeline

  connectedCallback() {
    this.#timeline = new ViewTimeline({subject: this})
    for (const child of this.children) {
      for (const effect of child.effects ?? []) {
        this.#setupAnimationEffect(effect)
      }
    }
  }

  #setupAnimationEffect(effect) {
    const animation = new Animation(effect, this.#timeline) 
    animation.rangeStart = this.rangeStart
    animation.rangeEnd = this.rangeEnd

    if (this.prefersReducedMotion) {
      animation.currentTime = CSS.percent(this.defaultProgress * 100)
    } else {
      animation.play()
    }
  }
}

export default class LayeredAnimationEffect extends HTMLElement {
  get effects() {
    return this.layers.flatMap(layer => toKeyframeEffects(layer))
  }
}
```

### 滚动性能

在使用滚动驱动型动画之前，NRK 的 JavaScript 实现性能非常出色，但现在，借助滚动驱动型动画，NRK 的性能变得更加出色，无需担心滚动卡顿，即使在低功耗设备上也是如此。

- 非 SDA 任务时长：1 毫秒。
- SDA 任务时长：0.16 毫秒。
![Chrome 开发者工具的“Performance”（性能）标签页。](https://developer.chrome.com/static/blog/nrk-casestudy/image/image2.png?hl=zh-cn)

在 Chrome 开发者工具的“性能”标签页中，将 CPU 减速 6 倍后，新帧中的每个任务的记录时间为 0.16 毫秒。

如需详细了解 JavaScript 实现与滚动驱动型动画之间的滚动性能差异，请参阅 [滚动驱动型动画性能案例研究](https://developer.chrome.com/blog/scroll-animation-performance-case-study?hl=zh-cn) 一文。

## 无障碍功能和用户体验注意事项

无障碍功能在 NRK 的公开页面中发挥着重要作用，因为在许多情况下，所有挪威公民都必须能够访问这些页面。NRK 可确保用户可以通过以下几种不同的方式访问滚动动画：

- **尊重用户对减少动画的偏好设置** ：使用媒体查询 `screen and (prefers-reduced-motion: no-preference)` 将动画作为渐进增强功能应用。同时处理打印样式也很有帮助。
- **考虑到设备种类繁多且滚动输入精度各不相同** ：部分用户可能会按步骤滚动（使用空格键或向上/向下键、使用屏幕阅读器导航到地图注点），而不会看到整个动画。确保不会错过关键信息。
- **谨慎使用用于显示或隐藏内容的动画** ：对于依赖操作系统 (OS) 缩放功能的用户，很难注意到隐藏的内容会在滚动时显示。避免让用户搜索它。 如果需要隐藏或显示内容，请确保内容显示和消失的位置一致。
- **避免动画亮度或对比度发生大幅变化** ：由于滚动驱动型动画取决于用户控制，因此突然的亮度变化可能会呈现闪烁效果，这可能会导致某些用户出现癫痫发作。
```
@media (prefers-reduced-motion: no-preference) {
  .article-image {
    opacity: 0;
    transition: opacity 1s ease-in-out;
  }
  .article-image.visible {
    opacity: 1;
  }
}
```

## 浏览器支持

为了让更多浏览器支持 [ScrollTimeline](https://developer.mozilla.org/docs/Web/API/ScrollTimeline) 和 [ViewTimeline](https://developer.mozilla.org/docs/Web/API/ViewTimeline) ，NRK 使用了 [开源 polyfill](https://github.com/flackr/scroll-timeline) ，该 polyfill 拥有 [活跃的贡献者社区](https://github.com/flackr/scroll-timeline/graphs/contributors) 。

目前，当 `ScrollTimeline` 不可用时，系统会有条件地加载该 polyfill，并使用不支持 CSS 的简化版 polyfill。

```
if (!('ScrollTimeline' in window)) {
  await import('scroll-timeline.js')
}
```

在 CSS 中检测和处理浏览器支持：

```
@supports not (animation-timeline: view()) {
  .article-section {
    translate: 0 calc(-15vh * var(--fallback-progress));
    opacity: var(--fallback-progress);
  }
}

@supports (animation-timeline: view()) {
  .article-section {
    animation: --fade-up linear;
    animation-timeline: view();
    animation-range: entry 100% exit 100%;
  }
}
```

在针对不受支持的浏览器的上述示例中，NRK 使用 [CSS 变量](https://developer.mozilla.org/docs/Web/CSS/Using_CSS_custom_properties) `--fallback-progress` 作为回退方式来控制 `translate` 和 `opacity` 属性的动画时间轴。

然后，使用 JavaScript 中的 [`scroll` 事件监听器](https://developer.mozilla.org/docs/Web/API/Document/scroll_event) 和 [`requestAnimationFrame`](https://developer.mozilla.org/docs/Web/API/Window/requestAnimationFrame) 更新 `--fallback-progress` CSS 变量，如下所示：

```
function updateProgress() {
  const end = el.offsetTop + el.offsetHeight;
  const start = end - window.innerHeight;
  const scrollTop = document.scrollingElement.scrollTop;
  const progress = (scrollTop - start) / (end - start);
  document.body.style.setProperty('--fallback-progress', clamp(progress, 0, 1));
}

if (!CSS.supports("animation-timeline: view()")) {
  document.addEventListener('scroll', () => {
    if (!visible || updating) {
      return;
    }

    window.requestAnimationFrame(() => {
      updateProgress();
      updating = false;
    });

    updating = true;
  });
}
```

## 资源

- [滚动条驱动的动画案例研究](https://developer.chrome.com/blog/css-ui-ecommerce-sda?hl=zh-cn)
- [演示：滚动条驱动的动画](https://scroll-driven-animations.style/)
- [使用滚动条驱动的动画在滚动时为元素添加动画效果](https://developer.chrome.com/docs/css-ui/scroll-driven-animations?hl=zh-cn)
- [Codelab：CSS 滚动驱动型动画使用入门](https://codelabs.developers.google.com/scroll-driven-animations?hl=zh-cn#0)
- [Chrome 扩展程序：滚动驱动型动画调试程序](https://chromewebstore.google.com/detail/scroll-driven-animations/ojihehfngalmpghicjgbfdmloiifhoce?hl=zh-cn)
- [滚动时间轴 Polyfill](https://github.com/flackr/scroll-timeline?tab=readme-ov-file#scroll-timeline-polyfill)
- [报告 bug 或新功能？我们期待收到您的反馈](https://issues.chromium.org/issues/new?component=1456613&template=0) 。

*特别感谢 Google 的 Hannah Van Opstal、Bramus 和 Andrew Kean Guan，以及 NRK 的 Ingrid Reime 对本工作做出的宝贵贡献。*

*NRK 保留对其公司名称、徽标以及提供链接和/或引用的文章的所有权利。*

如未另行说明，那么本页面中的内容已根据 [知识共享署名 4.0 许可](https://creativecommons.org/licenses/by/4.0/) 获得了许可，并且代码示例已根据 [Apache 2.0 许可](https://www.apache.org/licenses/LICENSE-2.0) 获得了许可。有关详情，请参阅 [Google 开发者网站政策](https://developers.google.com/site-policies?hl=zh-cn) 。Java 是 Oracle 和/或其关联公司的注册商标。

最后更新时间 (UTC)：2025-02-25。