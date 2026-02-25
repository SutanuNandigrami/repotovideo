# RepoToViralVideo

Turn any GitHub repository or local file into a short promo video with AI analysis, AI voiceover, animated scenes, and optional final render.

<p align="left">
  <img src="app_demo.png" width="100%" alt="RepoToViralVideo">
</p>

---

## Features

- GitHub URL + local file input (`.md`, `.txt`, `.pdf`)
- 4-step checkpointed pipeline (analyze → TTS → composition → render)
- Provider switch via `--api gemini|vertex`
- Style presets via `--style`
- Render tuning via `--render-profile`, `--codec`, `--preset`, `--crf`, `--concurrency`
- Resume support via `--resume` and clean rerun via `--clean`

---

## Installation

### Prerequisites

- Python 3.10+
- Node.js 18+
- FFmpeg in PATH (or bundled under project directory on Windows)

### Setup

```bash
# 1) Clone
git clone https://github.com/Shubhamsaboo/repotovideo.git
cd repotovideo

# 2) Install dependencies
npm run install:all

# 3) Create env file
copy .env.example .env   # Windows (cmd)
# cp .env.example .env   # Linux/macOS
```

---

## Provider setup: Gemini vs Vertex AI

The CLI always routes both **analysis** and **TTS** through the selected `--api` provider.

### Option A: Gemini API (`--api gemini`)

Required env:

```env
GEMINI_API_KEY=your-gemini-key
```

Example:

```bash
python generate.py https://github.com/langchain-ai/langchain --api gemini
```

### Option B: Vertex AI (`--api vertex`)

Required env:

```env
GOOGLE_CLOUD_PROJECT=your-gcp-project-id
```

Runtime auth requirement:

- Configure **Application Default Credentials (ADC)** for Vertex requests (for example with `gcloud auth application-default login`), or provide a valid service-account JSON and point `GOOGLE_APPLICATION_CREDENTIALS` to it.

Optional env:

```env
# may be present in your environment, but current google-genai vertex mode can still rely on ADC
GOOGLE_API_KEY=your-google-api-key
```

Optional env:

```env
# preferred
GOOGLE_CLOUD_LOCATION=us-central1

# accepted fallback alias
GOOGLE_CLOUD_REGION=us-central1
```

If no location is set, the pipeline defaults to `us-central1`.

Example:

```bash
python generate.py https://github.com/langchain-ai/langchain --api vertex
```

---

## Usage

### Basic commands

```bash
# GitHub source
python generate.py https://github.com/langchain-ai/langchain

# Local markdown/text/pdf
python generate.py .\README.md
python generate.py .\docs\brief.pdf

# Fast verification path (skip final render)
python generate.py .\README.md --skip-render
```

### CLI options

| Option | Description | Default |
|---|---|---|
| `source` | GitHub URL or local file path | Required |
| `--content-type` | `instagram_reel`, `youtube_reel`, `youtube_long` | `youtube_reel` |
| `--music` | `chill`, `upbeat`, `tech`, `hype` | `tech` |
| `--voice` | TTS voice (e.g. `Puck`, `Kore`, `Aoede`, `Charon`, `Fenrir`) | `Puck` |
| `--api` | API provider: `gemini`, `vertex` | `gemini` |
| `--music-volume` | Background music volume (0.0–1.0) | `0.22` |
| `--output` | Output filename | `viral-<source>.mp4` |
| `--style` | Narration/scene style (`auto`, `repo-promo`, `explainer`, `story`, `listicle`, `myth-vs-fact`, `case-study`, `launch-teaser`) | `auto` |
| `--render-profile` | Render profile: `draft`, `balanced`, `quality` | `balanced` |
| `--concurrency` | Render concurrency (`0` = auto) | `0` |
| `--codec` | Codec override (example: `h264`, `h265`) | auto |
| `--preset` | Encoder preset override | auto |
| `--crf` | CRF override (lower = higher quality) | auto |
| `--skip-render` | Generate composition only, skip render step | `false` |
| `--resume` | Resume from checkpoint | `false` |
| `--clean` | Ignore checkpoint and start fresh | `false` |
| `--list-content-types` | List available content presets and exit | - |
| `--list-apis` | List provider availability and exit | - |

---

## Pipeline steps

1. **Analyze** (`apps/api/pipeline/viral_analyzer.py`) - builds structured scene/script plan from source.
2. **TTS** (`apps/api/pipeline/viral_tts.py`) - generates scene voiceovers.
3. **Composition** - writes Remotion scene data/components.
4. **Render** - outputs final MP4 (unless `--skip-render`).

Checkpoint artifacts include:

- `analysis.json`
- `audio/scene_*.mp3`
- `durations.json`
- generated composition files

---

## Verification checklist

Use this sequence when validating setup on a fresh machine:

```bash
# 1) Verify provider detection
python generate.py dummy --list-apis

# 2) Verify option plumbing and content presets
python generate.py dummy --list-content-types

# 3) Verify full pipeline path without render (small local source)
python generate.py .\README.md --api gemini --skip-render --clean
python generate.py .\README.md --api vertex --skip-render --clean
```

For Vertex, step 3 requires live network access + valid Vertex credentials.

---

## Troubleshooting

- **`GEMINI_API_KEY is required when using --api gemini`**
  - Set `GEMINI_API_KEY` in `.env` or shell.

- **`GOOGLE_API_KEY is required when using --api vertex`**
  - If you use this warning path, set `GOOGLE_API_KEY`; however, Vertex calls can still require ADC in current runtime/auth mode.

- **`GOOGLE_CLOUD_PROJECT is required when using --api vertex`**
  - Set your GCP project ID in `GOOGLE_CLOUD_PROJECT`.

- **`Your default credentials were not found`**
  - Configure ADC (`gcloud auth application-default login`) or set `GOOGLE_APPLICATION_CREDENTIALS` to a valid service-account JSON file.

- **Vertex location issues**
  - Set `GOOGLE_CLOUD_LOCATION` (or `GOOGLE_CLOUD_REGION`) explicitly.

- **FFmpeg not found**
  - Install FFmpeg and ensure it is in PATH (or place local Windows bundle in project).

- **Node modules missing**
  - Run `npm run install:all`.

---

## License

MIT
