---
title: "Bring your ideas to life: Veo 2 video generation available for developers- Google Developers Blog"
source: "https://developers.googleblog.com/zh-hans/veo-2-video-generation-now-generally-available/"
author:
published:
created: 2025-04-16
description: "Create high-quality videos using the AI-powered Veo 2 model in Gemini API and Google AI Studio to enhance your creative and marketing projects"
tags:
  - "clippings"
---
四月 15, 2025

![Veo 2 in the Gemini API and Google AI Studio](https://storage.googleapis.com/gweb-developer-goog-blog-assets/images/Gemini-API-Veo-2-banner_3.original.png)

## Veo 2 in the Gemini API and now in Google AI Studio

  
We’re thrilled to announce that Veo 2, our state-of-the-art video generation model, is now available for developers to integrate into their applications. You can experiment with its capabilities in [Google AI Studio](https://aistudio.google.com/generate-video) and then start building on a [paid tier](https://ai.google.dev/gemini-api/docs/billing) in the [Gemini API](https://ai.google.dev/gemini-api/docs/video).

![Screenshot of Veo 2 in Google AI Studio](https://storage.googleapis.com/gweb-developer-goog-blog-assets/images/image5_Ww5DzCD.original.png)

Screenshot of Veo 2 in Google AI Studio

Veo 2 represents a new frontier in turning text, images, or both into video. It excels at interpreting both simple and complex instructions from text or image prompts, generating eight second video clips that accurately simulate real-world physics and capture a diverse spectrum of visual and cinematic styles.

### Core capabilities

Veo 2 empowers developers to generate eight second videos directly within their applications from both text and image prompts:

- **Text-to-Video (t2v):** Transform detailed text descriptions into dynamic video scenes. Explore different styles and create your own with extensive camera controls.
- **Image-to-Video (i2v):** Start with an image from your library or generate your own with models like Imagen and use Veo 2 to animate it. You can use optional text prompts for style and motion.

## Getting started with Veo 2

The easiest way to start experimenting and exploring Veo 2’s capabilities is directly within [Google AI Studio](https://aistudio.google.com/generate-video). You will be able to test prompts, adjust parameters like aspect ratio and duration, then immediately see the generated video results.

Use Google AI Studio to familiarize yourself with Veo 2’s potential. Once you’re ready to integrate Veo 2’s power directly into your own applications and workflow, you can leverage the [Gemini API.](https://ai.google.dev/gemini-api/docs/video)

```
import time
from google import genai
from google.genai import types

client = genai.Client()

operation = client.models.generate_videos(
    model="veo-2.0-generate-001",
    prompt="Panning wide shot of a calico kitten sleeping in the sunshine",
    config=types.GenerateVideosConfig(
        person_generation="allow_adult",
        aspect_ratio="16:9",    
    ),
)

while not operation.done:
    time.sleep(20)
    operation = client.operations.get(operation)

for n, generated_video in enumerate(operation.response.generated_videos):
    client.files.download(file=generated_video.video)
    generated_video.video.save(f"video{n}.mp4")  # save the video
```

## Crafting effective prompts

Generating stunning videos with Veo 2 hinges on your ability to communicate your vision clearly and effectively. Think of your prompt as a set of instructions – the more detailed and precise you are, the closer the final product will be to what you imagined. The key elements are: clarity, detail, and visual keywords. Let’s break this down with examples.

**Clarity:** Avoid vague terms and general descriptions.

**Detail:** The more information you provide, the richer and more nuanced the generated video will be.

Consider elements like:

- **Subject**: What is the primary focus of the video?
- **Action**: What is happening in the scene? Is the subject moving, interacting with something, or static?
- **Setting**: Where is the scene taking place? What is the environment like?
- **Camera Angle/Movement:** Is it a close-up, wide shot, or a dynamic tracking shot?
- **Lighting**: How is the scene lit? Is it bright and sunny, or dark and moody?
- **Style/Mood**: What is the overall feeling or aesthetic you want to convey? (e.g., elegant, futuristic, naturalistic)

Let’s review a couple examples.

### Example 1: Veo 2 prompting - Perfume Bottle

Let's say you want a video showcasing a new perfume bottle. Here's how you can build up a detailed prompt:

- **Basic Prompt:** " *Perfume bottle.*" (Too vague, will produce unpredictable results)
- **Improved Prompt:** " *A glass perfume bottle on a marble surface.*" (Better, but still lacking)
- **Effective Prompt**: " *A close-up shot of a modern, faceted crystal perfume bottle with rose gold accents, resting on polished white marble. Soft, diffused light highlights the bottle's angles, creating a subtle shimmer, as a delicate hand gently touches the top of the bottle. A single drop of perfume rolls slowly down the side. Elegant and luxurious aesthetic.*"

<video><source src="https://storage.googleapis.com/gweb-developer-goog-blog-assets/original_videos/Perfume_bottle_1.mp4" type="video/mp4"><p>Sorry, your browser doesn't support playback for this video</p></video>

This works by detailing the **Subject** \[faceted crystal bottle, rose gold accents, marble surface\], **Action** \[drops rolls down the side\], **Lighting** \[soft,diffused light\], **Camera Angle** \[close-up shot\], and **Style** \[elegant, luxurious\]

**  
Example 2: Get more precise by using Image-to-Video capabilities**.

Use Image-to-Video capabilities to showcase an existing product following your style and aesthetic. Upload an existing image or create one with [Imagen](https://deepmind.google/technologies/imagen-3/):

![Veo 2 - perfume bottle example image](https://storage.googleapis.com/gweb-developer-goog-blog-assets/images/PERFUME.original.png)

Veo 2 - perfume bottle example image

**Prompt:**

*Create a luxurious promotional video showcasing a perfume bottle. Begin with a tight close-up dolly left shot, focusing on the faceted cap of a clear glass perfume bottle filled with amber liquid. Water droplets subtly cling to the glass. The bottle rests on a clean, white marble bathroom countertop. Soft, natural light streams in from a window in the background, illuminating the scene. Eucalyptus leaves and natural wood fragrance diffuser sticks are subtly arranged around the bottle. The overall mood is elegant, fresh, and sophisticated.*

**Video output:**

<video><source src="https://storage.googleapis.com/gweb-developer-goog-blog-assets/original_videos/Perfume.mp4" type="video/mp4"><p>Sorry, your browser doesn't support playback for this video</p></video>

By mastering these principles, you'll be well on your way to crafting prompts that unlock the full potential of Veo 2 and bring your creative visions to life. Remember to iterate and refine your prompts based on the results you get – experimentation is key!

## See Veo 2 in action

To illustrate the transformative potential of Veo 2, let's look at how developers are already leveraging it to build next-generation creative tools.

### AlphaWave

[AlphaWave](https://alpha-wave.ai/) helps fashion and retail brands scale their content production using AI. Their core tool, AlphaFrame, automates the creation of high-performing marketing videos, solving the challenge of quickly and cost-effectively producing engaging, conversion-focused content for product drops and promotions.

By integrating **Veo 2,** AlphaWave can now generate polished, brand-aligned videos in minutes from simple text prompts or existing static assets like product images. This enables their clients to rapidly test ad variations, turn static catalogs into dynamic motion content, and empower brands with limited resources to access quality video production, ultimately making them more agile and competitive.

In the example below, AlphaWave has taken the static Pixel product images and turned it into a dynamic marketing video.

<video><source src="https://storage.googleapis.com/gweb-developer-goog-blog-assets/original_videos/AlphaWave-Veo2-Pixel.mp4" type="video/mp4"><p>Sorry, your browser doesn't support playback for this video</p></video>

### Trakto Studio

[Trakto](https://www.trakto.io/) helps teams scale the creation of high-quality marketing assets with its creative automation platform. To accelerate video production, their AI-powered Trakto Director feature transforms simple prompts into complete, editable commercials.

![Trakto Director feature transforms simple prompts into complete, editable commercials.](https://storage.googleapis.com/gweb-developer-goog-blog-assets/images/image6_lHlEQBN.original.png)

Trakto Director feature transforms simple prompts into complete, editable commercials.

After Gemini Flash scripts scenes and Imagen creates storyboard visuals, Veo 2 generates the final video. For Trakto, Veo 2 is crucial, delivering the temporal consistency, creative understanding, format flexibility, and polished output needed to rapidly turn ideas into high-quality, adaptable video content, significantly streamlining the path from concept to campaign-ready asset.

<video><source src="https://storage.googleapis.com/gweb-developer-goog-blog-assets/original_videos/Veo2-driving-demo_1.mp4" type="video/mp4"><p>Sorry, your browser doesn't support playback for this video</p></video>

## Start building today!

Veo 2 is ready to revolutionize how you create and integrate video content. Dive deeper and start building:

- **Experiment in** [**Google AI Studio**](https://aistudio.google.com/generate-video)
- **Explore the** [**Colab Notebook**](https://colab.sandbox.google.com/github/google-gemini/cookbook/blob/main/quickstarts/Get_started_Veo.ipynb) **from the the Gemini** [**Cookbook**](https://github.com/google-gemini/cookbook)**:** Get started with code examples and find some practical examples and recipes for using Veo in the Gemini API
- **Read the** [**API Documentation**](https://ai.google.dev/gemini-api/docs/video)**:** Find detailed API references and guides

  
We can't wait to see what you create with Veo 2!