"""
🎬 Viral Video Renderer — Dynamic Remotion composition generator

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
from dataclasses import asdict
from typing import Optional

from .checkpoint import ContentType


FPS = 30
VIDEO_DIR = Path(__file__).resolve().parent.parent.parent / "video"


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
    
    # Build SCENES array
    scene_entries = []
    for i, scene_id in enumerate(scenes):
        dur = durations.get(scene_id, 5.0)
        scene_entries.append(
            f'  {{ id: "{scene_id}", dur: Math.ceil({dur:.3f} * FPS), audio: "{audio_dir}/scene_{i:02d}.mp3" }}'
        )
    scenes_array = ",\n".join(scene_entries)
    
    total_dur = sum(durations.get(s, 5.0) for s in scenes)
    
    # Build scene data — use proper escaping to prevent broken JS strings
    raw_data = {
        "name": analysis.get("name", ""),
        "fullName": analysis.get("full_name", ""),
        "description": analysis.get("description", ""),
        "stars": analysis.get("stars", 0),
        "forks": analysis.get("forks", 0),
        "language": analysis.get("language", ""),
        "hookStyle": analysis.get("hook_style", "problem"),
        "hookText": analysis.get("hook_text", ""),
        "tagline": analysis.get("tagline", ""),
        "features": analysis.get("features", []),
        "techStack": analysis.get("tech_stack", []),
        "contentType": content_type,
        "aspectRatio": aspect_ratio,
    }
    scene_data = _dict_to_js_object(raw_data)
    
    # Build scene component imports & renders
    scene_imports = set()
    scene_renders = []
    
    for scene_id in scenes:
        component = get_scene_component(scene_id)
        scene_imports.add(component)
        scene_renders.append(f"""
        <TransitionSeries.Sequence durationInFrames={{getSceneDur("{scene_id}")}}>
          <{component} data={{DATA}} />
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
        container_style = "{ width: 1080, height: 1920 }"
    else:
        container_style = "{ width: 1920, height: 1080 }"
    
    tutorial_tsx = f"""import {{ Audio, staticFile }} from "remotion";
import {{ TransitionSeries, linearTiming }} from "@remotion/transitions";
import {{ slide }} from "@remotion/transitions/slide";
import {{ fade }} from "@remotion/transitions/fade";
{imports_str}

const FPS = {FPS};

const SCENES = [
{scenes_array}
];

const DATA = {scene_data};

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
          {{SCENES.map((s, i) => (
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
    (src_dir / "TutorialVideo.tsx").write_text(tutorial_tsx)
    (src_dir / "Root.tsx").write_text(root_tsx)
    
    print(f"  📝 Generated composition: {len(scenes)} scenes, {total_dur:.1f}s")
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
    concurrency: int = 2,
    composition_id: str = "ViralVideo",
) -> str:
    """Render the video using Remotion CLI.
    
    Args:
        output_name: Output filename
        concurrency: Number of parallel renders
        composition_id: Remotion composition ID to render
    
    Returns:
        Path to rendered video
    """
    
    output_path = str(VIDEO_DIR / "out" / output_name)
    
    print(f"  🎬 Rendering video...")
    subprocess.run(
        ["npx", "remotion", "render", composition_id, output_path,
         f"--concurrency={concurrency}"],
        cwd=str(VIDEO_DIR),
        check=True,
    )
    
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
    print(f"  ✅ Output: {output_path} ({size_mb:.1f} MB)")
    
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
