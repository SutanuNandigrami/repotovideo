"""
[VIDEO] Viral Video Renderer - Dynamic Remotion composition generator

Generates TutorialVideo.tsx and Root.tsx dynamically based on repo analysis,
then renders with Remotion CLI.

Supports different content types:
- instagram_reel: 9:16 (1080x1920), ~30s
- youtube_reel: 9:16 (1080x1920), ~45s  
- youtube_long: 16:9 (1920x1080), ~5-10min
"""

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Optional

from .checkpoint import ContentType


FPS = 30
VIDEO_DIR = Path(__file__).resolve().parent.parent.parent / "video"
RENDER_PROFILES: dict[str, dict[str, object]] = {
    "draft": {"codec": "h264", "preset": "veryfast", "crf": 30},
    "balanced": {"codec": "h264", "preset": "medium", "crf": 22},
    "quality": {"codec": "h264", "preset": "slow", "crf": 18},
}
HOOK_STYLES = {"counter", "momentum", "problem"}


def _parse_positive_int_env(var_name: str) -> Optional[int]:
    """Parse a positive integer from environment variables."""
    raw = os.environ.get(var_name)
    if raw is None:
        return None
    try:
        value = int(raw)
        if value > 0:
            return value
    except ValueError:
        return None
    return None


def _resolve_render_profile(
    render_profile: str,
    codec: Optional[str],
    preset: Optional[str],
    crf: Optional[int],
) -> tuple[str, str, int, str]:
    """Resolve render profile and optional encoding overrides."""
    normalized_profile = render_profile if render_profile in RENDER_PROFILES else "balanced"
    profile_defaults = RENDER_PROFILES[normalized_profile]

    resolved_codec = str(codec or profile_defaults["codec"])
    resolved_preset = str(preset or profile_defaults["preset"])
    profile_crf = profile_defaults.get("crf", 22)
    default_crf = profile_crf if isinstance(profile_crf, int) else 22
    resolved_crf = crf if crf is not None else default_crf
    return normalized_profile, resolved_codec, resolved_crf, resolved_preset


def _normalize_hook_style(value: object) -> str:
    """Ensure generated hook style conforms to TS union type."""
    if isinstance(value, str) and value in HOOK_STYLES:
        return value
    return "problem"


def _sanitize_js_string(s: str) -> str:
    """Sanitize a string value for use in generated JS/TS code.
    
    Normalizes unicode characters Gemini may return (smart quotes, dashes, etc.)
    and removes newlines. Does NOT escape quotes — json.dumps handles that.
    """
    if not isinstance(s, str):
        return s
    # Normalize smart/curly quotes to ASCII
    s = s.replace("\u2018", "'").replace("\u2019", "'")   # ' '
    s = s.replace("\u201c", '"').replace("\u201d", '"')   # " "
    s = s.replace("\u2013", "-").replace("\u2014", "-")   # en/em dash
    s = s.replace("\u2026", "...")                         # ellipsis
    # Remove literal newlines (would break string literals)
    s = s.replace("\n", " ").replace("\r", "")
    return s


def _dict_to_js_object(d: dict) -> str:
    """Convert a Python dict to a JS object literal string.
    
    Uses json.dumps with double-quoted strings (valid JS/TS).
    No quote-swapping needed — JSON IS valid JavaScript.
    """
    def _sanitize_value(v):
        if isinstance(v, str):
            return _sanitize_js_string(v)
        elif isinstance(v, list):
            return [_sanitize_value(item) for item in v]
        elif isinstance(v, dict):
            return {k: _sanitize_value(val) for k, val in v.items()}
        return v
    
    sanitized = _sanitize_value(d)
    return json.dumps(sanitized, indent=2, ensure_ascii=False)


def generate_composition(
    analysis: dict,
    durations: dict[str, float],
    music_track: str = "music/tech.mp3",
    music_volume: float = 0.22,
    content_type: str = "youtube_reel",
    audio_dir: str = "audio",
) -> None:
    """Generate TutorialVideo.tsx with dynamic scenes based on analysis.
    
    Args:
        analysis: Repository analysis data
        durations: Dict of scene_id -> duration in seconds
        music_track: Path to background music
        music_volume: Volume level (0.0-1.0)
        content_type: Content type preset (instagram_reel, youtube_reel, youtube_long)
        audio_dir: Directory containing TTS audio files (relative to output)
    """
    
    scenes = analysis.get("scenes", [])
    
    # Get content type specs
    content_spec = ContentType.from_string(content_type).get_specs()
    width = content_spec.get("width", 1920)
    height = content_spec.get("height", 1080)
    aspect_ratio = content_spec.get("aspect_ratio", "16:9")
    
    # Copy audio files to public directory for Remotion
    public_audio_dir = VIDEO_DIR / "public" / "audio"
    public_audio_dir.mkdir(parents=True, exist_ok=True)
    
    # Get absolute path to source audio files
    source_audio_dir = Path(audio_dir)
    
    if source_audio_dir.exists():
        # Copy each audio file
        for audio_file in source_audio_dir.glob("*.mp3"):
            dest_file = public_audio_dir / audio_file.name
            # Only copy if source is newer or dest doesn't exist
            if not dest_file.exists() or dest_file.stat().st_mtime < audio_file.stat().st_mtime:
                import shutil
                shutil.copy2(audio_file, dest_file)
                print(f"   [COPY] {audio_file.name} -> public/audio/")
    else:
        print(f"   [!] Audio source not found: {source_audio_dir}")
    
    # Update audio_dir to use public folder
    audio_dir_for_template = "audio"
    
    # Build SCENES array with paths relative to public/audio
    scene_entries = []
    for i, scene_id in enumerate(scenes):
        dur = durations.get(scene_id, 5.0)
        scene_entries.append(
            f'  {{ id: "{scene_id}", dur: Math.ceil({dur:.3f} * FPS), audio: "{audio_dir_for_template}/scene_{i:02d}.mp3" }}'
        )
    scenes_array = ",\n".join(scene_entries)
    
    total_dur = sum(durations.get(s, 5.0) for s in scenes)
    
    # Build scene data — use proper escaping to prevent broken JS strings
    repo_data = {
        "name": analysis.get("name", ""),
        "fullName": analysis.get("full_name", ""),
        "description": analysis.get("description", ""),
        "stars": analysis.get("stars", 0),
        "forks": analysis.get("forks", 0),
        "language": analysis.get("language", ""),
        "hookStyle": _normalize_hook_style(analysis.get("hook_style")),
        "hookText": analysis.get("hook_text", ""),
        "tagline": analysis.get("tagline", ""),
        "features": analysis.get("features", []),
        "techStack": analysis.get("tech_stack", []),
        "style": analysis.get("style", "repo-promo"),
        "requestedStyle": analysis.get("requested_style", "auto"),
        "styleReason": analysis.get("style_reason", ""),
    }
    scene_data = _dict_to_js_object(repo_data)
    
    # Build scene component imports & renders
    scene_imports = set()
    scene_renders = []
    
    for scene_id in scenes:
        component = get_scene_component(scene_id)
        scene_imports.add(component)
        scene_renders.append(f"""
        <TransitionSeries.Sequence durationInFrames={{getSceneDur("{scene_id}")}}>
          <{component} data={{REPO_DATA}} />
        </TransitionSeries.Sequence>
        <TransitionSeries.Transition
          presentation={{slide({{ direction: "from-right" }})}}
          timing={{linearTiming({{ durationInFrames: 8 }})}}
        />""")
    
    # Remove trailing transition
    if scene_renders:
        scene_renders[-1] = scene_renders[-1].rsplit("<TransitionSeries.Transition", 1)[0]
    
    imports_str = "\n".join(
        f'import {{ {c} }} from "./scenes/{c}";'
        for c in sorted(scene_imports)
    )
    
    # Calculate background position based on aspect ratio
    # For vertical video (9:16), center the 16:9 content
    bg_width = 1920
    bg_height = 1080
    bg_style = "{ backgroundColor: '#0a0a0a' }"
    
    if aspect_ratio == "9:16":
        # Vertical video - use a centered container
        bg_style = """{{ 
          backgroundColor: "#0a0a0a",
          width: "100%",
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center"
        }}"""
        container_style = "{{ width: 1080, height: 1920 }}"
    else:
        container_style = "{{ width: 1920, height: 1080 }}"
    
    tutorial_tsx = f"""import {{ Audio, staticFile }} from "remotion";
import {{ TransitionSeries, linearTiming }} from "@remotion/transitions";
import {{ slide }} from "@remotion/transitions/slide";
{imports_str}
import type {{ RepoData }} from "./types";

const FPS = {FPS};

const SCENES = [
{scenes_array}
];

const REPO_DATA: RepoData = {scene_data};

function getSceneDur(id: string): number {{
  return SCENES.find(s => s.id === id)?.dur ?? 150;
}}

export const TutorialVideo = () => {{
  return (
    <div style={bg_style}>
      <div style={container_style}>
        {{/* Background music */}}
        <Audio src={{staticFile("{music_track}")}} volume={{{music_volume}}} />
        
        <TransitionSeries>
          {{/* Scene audio tracks */}}
          {{SCENES.map((s) => (
            <TransitionSeries.Sequence key={{s.id + "-audio"}} durationInFrames={{s.dur}}>
              <Audio src={{staticFile(s.audio)}} volume={{0.9}} />
            </TransitionSeries.Sequence>
          ))}}
        </TransitionSeries>

        <TransitionSeries>
          {"".join(scene_renders)}
        </TransitionSeries>
      </div>
    </div>
  );
}};
"""
    
    root_tsx = f"""import {{ Composition }} from "remotion";
import {{ TutorialVideo }} from "./TutorialVideo";

const FPS = {FPS};
// {" + ".join(f"{durations.get(s, 5.0):.3f}" for s in scenes)} = {total_dur:.3f}s
const TOTAL = Math.ceil({total_dur:.3f} * FPS);

export const RemotionRoot = () => {{
  return (
    <Composition
      id="ViralVideo"
      component={{TutorialVideo}}
      durationInFrames={{TOTAL}}
      fps={{FPS}}
      width={{{width}}}
      height={{{height}}}
    />
  );
}};
"""
    
    # Write files
    src_dir = VIDEO_DIR / "src"
    (src_dir / "TutorialVideo.tsx").write_text(tutorial_tsx, encoding="utf-8")
    (src_dir / "Root.tsx").write_text(root_tsx, encoding="utf-8")
    
    print(f"   Generated composition: {len(scenes)} scenes, {total_dur:.1f}s")
    print(f"     Resolution: {width}x{height} ({aspect_ratio})")


def get_scene_component(scene_id: str) -> str:
    """Map scene ID to React component name."""
    return {
        "hook": "HookScene",
        "what": "WhatScene",
        "features": "FeaturesScene",
        "tech": "TechScene",
        "stats": "StatsScene",
        "cta": "CTAScene",
    }.get(scene_id, "HookScene")


def render_video(
    output_name: str = "viral-output.mp4",
    concurrency: Optional[int] = None,
    composition_id: str = "ViralVideo",
    render_profile: str = "balanced",
    codec: Optional[str] = None,
    preset: Optional[str] = None,
    crf: Optional[int] = None,
) -> str:
    """Render the video using Remotion CLI.
    
    Args:
        output_name: Output filename
        concurrency: Number of parallel renders
        composition_id: Remotion composition ID to render
        render_profile: Render speed/quality preset (draft, balanced, quality)
        codec: Optional codec override (e.g. h264, h265)
        preset: Optional encoder preset override (x264 preset for h264)
        crf: Optional CRF override
    
    Returns:
        Path to rendered video
    """
    
    output_path = str(VIDEO_DIR / "out" / output_name)

    # Resolve render profile + knobs with backward-compatible defaults.
    resolved_profile, resolved_codec, resolved_crf, resolved_preset = _resolve_render_profile(
        render_profile=render_profile,
        codec=codec,
        preset=preset,
        crf=crf,
    )

    # Resolve concurrency dynamically when not provided.
    # Default heuristic: CPU cores - 1, clamped to [1, 8] for stability.
    # Optional env overrides:
    # - REMOTION_CONCURRENCY
    # - REMOTION_CONCURRENCY_MAX
    cpu_count = os.cpu_count() or 4
    default_auto_concurrency = max(1, min(cpu_count - 1, 8))
    env_concurrency = _parse_positive_int_env("REMOTION_CONCURRENCY")
    env_concurrency_max = _parse_positive_int_env("REMOTION_CONCURRENCY_MAX")

    if env_concurrency is not None:
        resolved_concurrency = env_concurrency
    elif concurrency is None or concurrency <= 0:
        resolved_concurrency = default_auto_concurrency
    else:
        resolved_concurrency = max(1, concurrency)

    if env_concurrency_max is not None:
        resolved_concurrency = min(resolved_concurrency, env_concurrency_max)
    
    # Use local remotion from node_modules on Windows
    import platform
    if platform.system() == "Windows":
        # Check for local remotion.cmd
        remotion_cmd = VIDEO_DIR / "node_modules" / ".bin" / "remotion.cmd"
        if remotion_cmd.exists():
            render_cmd = str(remotion_cmd)
        else:
            # Fall back to npx
            render_cmd = "npx"
    else:
        render_cmd = "npx"
    
    print(
        "  [VIDEO] Rendering video... "
        f"(profile: {resolved_profile}, codec: {resolved_codec}, crf: {resolved_crf}, "
        f"preset: {resolved_preset}, CPU cores: {cpu_count}, concurrency: {resolved_concurrency})"
    )
    
    # Build the command - if using npx, need 'remotion render', if using remotion.cmd, just 'render'
    if "npx" in render_cmd:
        cmd_base = [render_cmd, "remotion", "render", composition_id, output_path]
    else:
        cmd_base = [render_cmd, "render", composition_id, output_path]

    def _build_render_cmd(conc: int) -> list[str]:
        cmd = [
            *cmd_base,
            f"--concurrency={conc}",
            f"--codec={resolved_codec}",
            f"--crf={resolved_crf}",
        ]
        if resolved_codec == "h264" and resolved_preset:
            cmd.append(f"--x264-preset={resolved_preset}")
        return cmd

    current_concurrency = resolved_concurrency
    max_attempts = 3
    last_error: Optional[subprocess.CalledProcessError] = None

    for attempt in range(1, max_attempts + 1):
        try:
            subprocess.run(
                _build_render_cmd(current_concurrency),
                cwd=str(VIDEO_DIR),
                check=True,
            )
            last_error = None
            break
        except subprocess.CalledProcessError as err:
            last_error = err
            if current_concurrency <= 1 or attempt == max_attempts:
                raise
            reduced = max(1, current_concurrency // 2)
            if reduced == current_concurrency:
                reduced = current_concurrency - 1
            print(
                f"  [WARN] Render attempt {attempt} failed with concurrency={current_concurrency}. "
                f"Retrying with concurrency={reduced}..."
            )
            current_concurrency = max(1, reduced)

    if last_error is not None:
        raise last_error
    
    # Cleanup chrome processes - cross-platform
    import platform
    system = platform.system()
    if system == "Windows":
        subprocess.run(["taskkill", "/F", "/IM", "chrome.exe"], capture_output=True)
        subprocess.run(["taskkill", "/F", "/IM", "chrome-headless-shell.exe"], capture_output=True)
    elif system == "Darwin":  # macOS
        subprocess.run(["pkill", "-f", "chrome"], capture_output=True)
    else:  # Linux
        subprocess.run(["pkill", "-f", "chrome-headless-shell"], capture_output=True)
    
    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"  [OK] Output: {output_path} ({size_mb:.1f} MB)")
    
    return output_path


def get_content_type_from_analysis(analysis: dict) -> str:
    """Extract content type from analysis data."""
    return analysis.get("content_type", "youtube_reel")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 3:
        print("Usage: python viral_renderer.py <analysis.json> <durations.json> [output.mp4] [content_type]")
        sys.exit(1)
    
    with open(sys.argv[1]) as f:
        analysis = json.load(f)
    with open(sys.argv[2]) as f:
        durations = json.load(f)
    
    output = sys.argv[3] if len(sys.argv) > 3 else "viral-output.mp4"
    content_type = sys.argv[4] if len(sys.argv) > 4 else "youtube_reel"
    
    generate_composition(analysis, durations, content_type=content_type)
    render_video(output)
