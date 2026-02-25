# RepoToViralVideo

> Turn any GitHub repository or local file into a viral promo video in just one-click.

**RepoToViralVideo** analyzes any GitHub repository or local file and generates a short, high-energy promo video designed to go viral on X/LinkedIn with AI voiceover, kinetic typography, animated stats, and background music.

<p align="left">
  <img src="app_demo.png" width="100%" alt="RepoToViralVideo">
</p>

> Powered by **Gemini 2.5 Flash** for analysis and TTS

---

## Features

- **Multiple Input Sources:** GitHub URLs, local files (.md, .txt, .pdf)
- **AI Voiceover:** Gemini TTS generates natural, conversational narration
- **Kinetic Typography:** Words slam in from all directions with spring physics
- **Animated Counters:** Star counts and fork counts animate from 0 to their final number
- **Background Music:** 4 bundled royalty-free tracks (chill, upbeat, tech, hype)
- **Fast Cuts:** Slide transitions between scenes, nothing stays static
- **Smart Analysis:** Gemini reads the repo/file and extracts impressive stats and features
- **Adaptive Scenes:** Automatically selects different video styles based on content (4-6 scenes)
- **Checkpoint & Resume:** Failed runs can be resumed from where they left off

---

## Installation

### Prerequisites

- **Python 3.10+**
- **Node.js 18+**
- **FFmpeg:** Required for audio processing
- **Gemini API key:** Get from [Google AI Studio](https://aistudio.google.com)

### Setup

```bash
# 1. Clone the repo
git clone https://github.com/Shubhamsaboo/repotovideo.git
cd repotovideo

# 2. Install dependencies
npm run install:all

# 3. Set your Gemini API key (choose one)
export GEMINI_API_KEY="your-key-here"    # Linux/Mac
set GEMINI_API_KEY=your-key-here          # Windows
```

---

## Usage

### CLI Commands

```bash
# Generate from GitHub repo
python generate.py https://github.com/langchain-ai/langchain

# Generate from local file
python generate.py ./README.md
python generate.py ./document.pdf

# With custom options
python generate.py https://github.com/user/repo --music hype --voice Puck
```

### Command Options

| Option | Description | Default |
|--------|-------------|---------|
| `source` | GitHub URL or local file path | Required |
| `--content-type` | Video format: instagram_reel, youtube_reel, youtube_long | youtube_reel |
| `--music` | Background music: chill, upbeat, tech, hype | tech |
| `--voice` | TTS voice: Puck, Kore, Aoede, Charon, Fenrir | Puck |
| `--api` | API provider: gemini, vertex | gemini |
| `--music-volume` | Background music volume (0.0-1.0) | 0.22 |
| `--output` | Output filename | viral-<source>.mp4 |
| `--skip-render` | Generate composition only, skip rendering | false |
| `--resume` | Resume from last checkpoint | false |
| `--clean` | Start fresh, ignore checkpoints | false |
| `--list-content-types` | List available content types | - |
| `--list-apis` | List available API providers | - |

### Voice Options

| Voice | Style |
|-------|-------|
| **Puck** | Playful, energetic - great for hype videos |
| **Kore** | Warm, confident |
| **Aoede** | Smooth, warm |
| **Charon** | Deep, authoritative |
| **Fenrir** | Bold, strong |

### Music Options

| Music | Mood |
|-------|------|
| **tech** | Futuristic, modern (default) |
| **hype** | Energetic, exciting |
| **chill** | Relaxed, calm |
| **upbeat** | Positive, motivating |

---

## Pipeline

The video generation runs in **4 steps**:

1. **AI Analysis** - Gemini analyzes the source (repo URL or file content) and extracts:
   - Stars, forks, language, topics
   - Key features and selling points
   - Tech stack information
   - Generates scene selection and voiceover scripts

2. **TTS Voiceover** - Gemini TTS generates narration for each scene:
   - 6 scenes: hook, what, features, tech, stats, cta
   - Each scene gets custom tone hints for natural delivery

3. **Composition** - Generates Remotion React components:
   - Dynamic TutorialVideo.tsx with scene data
   - Root.tsx with composition settings

4. **Render** - Remotion renders the final video:
   - 1080x1920 (9:16) for social media
   - Spring animations, transitions, background music

---

## Checkpoint & Resume

The pipeline saves progress after each step. If something fails, you can resume:

```bash
# Resume from last checkpoint
python generate.py https://github.com/user/repo --resume

# Start completely fresh (ignore checkpoints)
python generate.py https://github.com/user/repo --clean
```

**What gets saved:**
- Analysis data (analysis.json)
- Voiceover audio (audio/scene_*.mp3)
- Scene durations (durations.json)
- Generated composition (TutorialVideo.tsx, Root.tsx)

---

## Output

Generated videos are saved to:

```
apps/video/out/viral-<source>.mp4
```

Example:
```
apps/video/out/viral-langchain.mp4
```

---

## Project Structure

```
repotovideo/
|
|-- generate.py                  # CLI entry point
|
|-- apps/
|   |-- api/                     # Python pipeline
|   |   |-- server.py            # API server (optional)
|   |   |-- requirements.txt
|   |   |-- pipeline/
|   |   |   |-- viral_analyzer.py    # AI analysis
|   |   |   |-- viral_tts.py         # Voice generation
|   |   |   |-- viral_renderer.py    # Composition generator
|   |   |   |-- checkpoint.py        # Checkpoint system
|   |   |   |-- source_validator.py  # URL/file validation
|   |   |   |-- api_client.py        # API client
|   |
|   |-- video/                   # Remotion video project
|       |-- src/
|       |   |-- TutorialVideo.tsx    # Main composition
|       |   |-- Root.tsx             # Remotion root
|       |   |-- types.ts
|       |   |-- scenes/              # Scene components
|       |       |-- HookScene.tsx
|       |       |-- WhatScene.tsx
|       |       |-- FeaturesScene.tsx
|       |       |-- TechScene.tsx
|       |       |-- StatsScene.tsx
|       |       |-- CTAScene.tsx
|       |-- public/
|           |-- music/               # Background tracks
|           |-- audio/               # TTS audio (generated)
|
|-- ffmpeg-8.0.1-essentials_build/  # Bundled FFmpeg (Windows)
```

---

## Tech Stack

- **AI:** Gemini 2.5 Flash (analysis + TTS)
- **Video:** [Remotion](https://remotion.dev) (React -> MP4)
- **Backend:** Python 3.10+
- **Audio:** FFmpeg

---

## License

MIT
