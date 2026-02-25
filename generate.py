#!/usr/bin/env python3
"""
[VIDEO] RepoToViralVideo - Generate a viral promo video for any GitHub repo or local file

Usage:
    python generate.py <source> [options]

Sources:
    - GitHub URL: https://github.com/user/repo
    - Local file: ./README.md, ./document.txt, ./article.pdf

Options:
    --content-type    Content type: instagram_reel, youtube_reel, youtube_long
    --music           Background music: chill, upbeat, tech, hype
    --voice           TTS voice: Puck, Kore, Aoede, Charon, Fenrir
    --api             API provider: gemini, vertex
    --output          Output filename
    --skip-render     Generate composition but skip rendering
    --resume          Resume from last checkpoint
    --clean           Start fresh (ignore checkpoints)

Examples:
    python generate.py https://github.com/langchain-ai/langchain
    python generate.py ./README.md --content-type instagram_reel
    python generate.py ./document.pdf --api vertex
    python generate.py https://github.com/user/repo --resume
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from dataclasses import asdict

# Load .env file if it exists
from pathlib import Path
env_file = Path(__file__).parent / ".env"
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())

# Add pipeline to path
sys.path.insert(0, str(Path(__file__).parent / "apps" / "api"))

from pipeline.viral_analyzer import analyze_source_for_viral
from pipeline.viral_tts import generate_voiceover
from pipeline.viral_renderer import generate_composition, render_video
from pipeline.checkpoint import (
    CheckpointManager,
    PipelineStep,
    ContentType,
    create_output_dir,
)
from pipeline.source_validator import (
    validate_source,
    get_source_display_name,
    SourceError,
    check_prerequisites as check_source_prereqs,
)
from pipeline.api_client import get_available_providers

VIDEO_DIR = Path(__file__).parent / "apps" / "video"
DEFAULT_OUTPUT_DIR = Path(__file__).parent / "output"

MUSIC_MAP = {
    "chill": "music/chill.mp3",
    "upbeat": "music/upbeat.mp3",
    "tech": "music/tech.mp3",
    "hype": "music/hype.mp3",
}


def check_prerequisites():
    """Check that required tools and API keys are available."""
    errors = []

    # Check for at least one API key
    gemini_key = os.environ.get("GEMINI_API_KEY")
    vertex_key = os.environ.get("GOOGLE_API_KEY")
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
    
    if not gemini_key and not vertex_key:
        errors.append(
            "No API key set. Set GEMINI_API_KEY or GOOGLE_API_KEY + GOOGLE_CLOUD_PROJECT"
        )
    
    if gemini_key:
        print("[OK] GEMINI_API_KEY found")
    if vertex_key and project_id:
        print("[OK] Vertex AI credentials found")

    if gemini_key:
        print("[OK] GEMINI_API_KEY found")
    if vertex_key and project_id:
        print("[OK] Vertex AI credentials found")

    # Check ffmpeg - check multiple locations
    import platform
    system = platform.system()
    
    ffmpeg_found = False
    ffmpeg_path = None
    
    # First try system PATH
    if system == "Windows":
        ffmpeg_check = os.system("ffmpeg -version >nul 2>&1")
    else:
        ffmpeg_check = os.system("ffmpeg -version > /dev/null 2>&1")
    
    if ffmpeg_check == 0:
        ffmpeg_found = True
    
    # Check for local ffmpeg in project directory
    if not ffmpeg_found:
        base_dir = Path(__file__).parent
        local_ffmpeg = base_dir / "ffmpeg-8.0.1-essentials_build" / "bin" / "ffmpeg.exe"
        if local_ffmpeg.exists():
            ffmpeg_path = str(local_ffmpeg.parent)
            ffmpeg_found = True
            # Add to PATH for this session
            os.environ["PATH"] = ffmpeg_path + os.pathsep + os.environ.get("PATH", "")
            print(f"[OK] Using local ffmpeg from: {local_ffmpeg}")
        else:
            # Try to find any ffmpeg.exe in the project directory
            for ffmpeg_exe in base_dir.rglob("ffmpeg.exe"):
                ffmpeg_path = str(ffmpeg_exe.parent)
                ffmpeg_found = True
                os.environ["PATH"] = ffmpeg_path + os.pathsep + os.environ.get("PATH", "")
                print(f"[OK] Using ffmpeg from: {ffmpeg_exe}")
                break
    
    if not ffmpeg_found:
        errors.append("ffmpeg not found. Please download ffmpeg or place ffmpeg.exe in the project directory.")

    # Check node_modules
    if not (VIDEO_DIR / "node_modules").exists():
        errors.append(f"Node modules not installed. Run: cd {VIDEO_DIR} && npm install")

    # Check optional dependencies
    missing = check_source_prereqs()
    if missing:
        print("[!] Optional dependencies not found:")
        for dep in missing:
            print(f"   - {dep}")

    if errors:
        print("[X] Missing prerequisites:")
        for e in errors:
            print(f"   - {e}")
        sys.exit(1)


def get_or_create_job_id(source: str, output_dir: Path) -> str:
    """Get existing job ID or create new one based on source."""
    # Create a simple job ID from source name
    source_name = Path(source).stem if not source.startswith(("http://", "https://")) else source.split("/")[-1]
    # Remove special characters
    job_id = "".join(c for c in source_name if c.isalnum() or c in "-_")[:50]
    return job_id


async def run_pipeline_step_analyze(
    checkpoint_mgr: CheckpointManager,
    source: str,
    content_type: str,
    api_provider: str,
):
    """Run the analysis step."""
    print("\n[AI] Step 1/4 -- Analyzing source with AI...")
    
    try:
        analysis = await analyze_source_for_viral(
            source,
            content_type=content_type,
            api_provider=api_provider,
        )
        analysis_dict = asdict(analysis)
        
        print(f"   [*] {analysis.stars:,} stars | [F] {analysis.forks:,} forks | [L] {analysis.language}")
        print(f"   Hook: \"{analysis.hook_text}\"")
        print(f"   Scenes: {' -> '.join(analysis.scenes)}")
        print(f"   Style: {analysis.hook_style} ({len(analysis.features)} features, {len(analysis.tech_stack)} tech)")
        
        # Save analysis - escape non-ASCII to prevent Windows encoding issues
        output_dir = Path(checkpoint_mgr.output_dir)
        analysis_path = output_dir / "analysis.json"
        # Use ensure_ascii=True to escape emojis/unicode from AI output
        analysis_path.write_text(json.dumps(analysis_dict, indent=2, ensure_ascii=True), encoding="utf-8")
        
        # Update checkpoint
        checkpoint_mgr.complete_step(
            PipelineStep.ANALYZE,
            analysis=analysis_dict,
        )
        
        return analysis
        
    except SourceError as e:
        # Source validation failed - abort before consuming API quota
        print(f"\n[X] {e}")
        checkpoint_mgr.fail_step(PipelineStep.ANALYZE, str(e))
        sys.exit(1)
    
    except Exception as e:
        checkpoint_mgr.fail_step(PipelineStep.ANALYZE, str(e))
        raise


def run_pipeline_step_tts(
    checkpoint_mgr: CheckpointManager,
    analysis: dict,
    voice: str,
    api_provider: str,
):
    """Run the TTS step."""
    print(f"\n[TTS] Step 2/4 -- Generating voiceover (voice: {voice})...")
    
    output_dir = Path(checkpoint_mgr.output_dir)
    audio_dir = str(output_dir / "audio")
    
    durations = generate_voiceover(
        analysis["voiceover_scripts"],
        audio_dir,
        voice=voice,
        api_provider=api_provider,
    )
    total_dur = sum(durations.values())
    print(f"   Total duration: {total_dur:.1f}s")
    
    # Save durations
    durations_path = output_dir / "durations.json"
    durations_path.write_text(json.dumps(durations, indent=2))
    
    # Save audio files list
    audio_files = list(Path(audio_dir).glob("*.mp3"))
    audio_files_str = [str(f.relative_to(output_dir)) for f in audio_files]
    
    # Update checkpoint
    checkpoint_mgr.complete_step(
        PipelineStep.TTS,
        durations=durations,
        audio_files=audio_files_str,
    )
    
    return durations


def run_pipeline_step_composition(
    checkpoint_mgr: CheckpointManager,
    analysis: dict,
    durations: dict,
    music: str,
    music_volume: float,
):
    """Run the composition generation step."""
    print(f"\n[VIDEO] Step 3/4 — Generating composition...")
    
    music_track = MUSIC_MAP.get(music, "music/tech.mp3")
    
    # Get audio directory - use absolute path for copying
    output_dir = Path(checkpoint_mgr.output_dir)
    audio_dir = str(output_dir / "audio")
    
    generate_composition(
        analysis,
        durations,
        music_track=music_track,
        music_volume=music_volume,
        content_type=analysis.get("content_type", "youtube_reel"),
        audio_dir=audio_dir,
    )
    
    # Update checkpoint
    checkpoint_mgr.complete_step(PipelineStep.GENERATE_SCENES)
    
    return True


def run_pipeline_step_render(
    checkpoint_mgr: CheckpointManager,
    output_name: str,
    concurrency: int = 2,
):
    """Run the video rendering step."""
    print(f"\n[VIDEO] Step 4/4 — Rendering video...")
    
    output_path = render_video(output_name, concurrency=concurrency)
    
    # Update checkpoint
    checkpoint_mgr.complete_step(
        PipelineStep.RENDER_VIDEO,
        video_output=output_path,
    )
    
    return output_path


async def run_pipeline(
    source: str,
    content_type: str,
    music: str,
    voice: str,
    music_volume: float,
    api_provider: str,
    output_name: str,
    skip_render: bool,
    resume: bool,
    clean: bool,
):
    """Run the complete pipeline with checkpoint support."""
    
    # Get or create job ID
    job_id = get_or_create_job_id(source, DEFAULT_OUTPUT_DIR)
    output_dir = create_output_dir(str(DEFAULT_OUTPUT_DIR), job_id)
    
    # Initialize checkpoint manager
    checkpoint_mgr = CheckpointManager(str(output_dir))
    
    # Check for existing checkpoint
    if resume:
        checkpoint = checkpoint_mgr.load_checkpoint()
        if checkpoint:
            print(f"\n[RESUME] Resuming job: {job_id}")
            print(f"   Last completed step: {checkpoint.step}")
            print(f"   Status: {checkpoint.status}")
        else:
            print("[!] No checkpoint found, starting fresh")
            resume = False
    
    if clean or not resume:
        # Clean start
        if clean:
            print(f"\n[CLEAN] Starting fresh (--clean specified)")
        else:
            print(f"\n[START] Starting new job: {job_id}")
        
        # Validate source BEFORE creating checkpoint
        print(f"[SEARCH] Validating source: {get_source_display_name(source)}")
        is_valid, error_msg, _ = validate_source(source)
        if not is_valid:
            print(f"\n[X] Source validation failed: {error_msg}")
            sys.exit(1)
        print("   [OK] Source validated")
        
        # Create new checkpoint
        checkpoint_mgr = CheckpointManager(str(output_dir))
        checkpoint_mgr.create_checkpoint(
            job_id=job_id,
            source=source,
            content_type=content_type,
            music=music,
            voice=voice,
            music_volume=music_volume,
        )
    
    # Run pipeline steps
    try:
        # Step 1: Analysis
        current_step = checkpoint_mgr.get_current_step()
        
        if checkpoint_mgr.has_step_completed(PipelineStep.ANALYZE):
            print("\n[SKIP] Step 1/4 -- Analysis (already completed)")
            # Load existing analysis
            output_dir = Path(checkpoint_mgr.output_dir)
            analysis_path = output_dir / "analysis.json"
            if analysis_path.exists():
                analysis = json.loads(analysis_path.read_text())
            else:
                raise RuntimeError("Analysis file not found")
        else:
            analysis = await run_pipeline_step_analyze(
                checkpoint_mgr, source, content_type, api_provider
            )
            analysis = asdict(analysis)
        
        # Step 2: TTS
        if checkpoint_mgr.has_step_completed(PipelineStep.TTS):
            print("\n[SKIP] Step 2/4 -- TTS (already completed)")
            output_dir = Path(checkpoint_mgr.output_dir)
            durations_path = output_dir / "durations.json"
            if durations_path.exists():
                durations = json.loads(durations_path.read_text())
            else:
                raise RuntimeError("Durations file not found")
        else:
            durations = run_pipeline_step_tts(
                checkpoint_mgr, analysis, voice, api_provider
            )
        
        # Step 3: Composition
        # Check if files exist before skipping
        src_dir = Path(VIDEO_DIR / "src")
        composition_files_exist = (src_dir / "Root.tsx").exists() and (src_dir / "TutorialVideo.tsx").exists()
        
        if checkpoint_mgr.has_step_completed(PipelineStep.GENERATE_SCENES) and composition_files_exist:
            print("\n[SKIP] Step 3/4 -- Composition (already completed)")
        else:
            # Always regenerate composition files to ensure they're up to date
            print("\n[GEN] Step 3/4 -- Generating composition...")
            run_pipeline_step_composition(
                checkpoint_mgr, analysis, durations, music, music_volume
            )
        
        # Step 4: Render
        if skip_render:
            print("\n[SKIP] Step 4/4 -- Rendering (skipped with --skip-render)")
            print(f"\n[OK] Pipeline complete! Composition generated at:")
            print(f"   {output_dir}")
        elif checkpoint_mgr.has_step_completed(PipelineStep.RENDER_VIDEO):
            print("\n[SKIP] Step 4/4 -- Render (already completed)")
            output_dir = Path(checkpoint_mgr.output_dir)
            output_path = output_dir / "out" / output_name
            print(f"\n[OK] Video already rendered:")
            print(f"   {output_path}")
        else:
            output_path = run_pipeline_step_render(
                checkpoint_mgr, output_name
            )
            
            print(f"\n[OK] Done! Your viral video is at:")
            print(f"   {output_path}")
            total_dur = sum(durations.values())
            print(f"   Duration: {total_dur:.1f}s | Ready for social media")
        
        return True
        
    except Exception as e:
        print(f"\n[X] Pipeline failed: {e}")
        import traceback
        traceback.print_exc()
        
        # Mark current step as failed
        current_step = checkpoint_mgr.get_current_step()
        if current_step:
            checkpoint_mgr.fail_step(current_step, str(e))
        
        sys.exit(1)


async def main():
    parser = argparse.ArgumentParser(
        description="Generate a viral promo video for any GitHub repo or local file",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    
    parser.add_argument(
        "source",
        help="GitHub URL or local file path (.md, .txt, .pdf)",
    )
    
    parser.add_argument(
        "--content-type",
        choices=ContentType.list_values(),
        default="youtube_reel",
        help="Content type preset (default: youtube_reel)",
    )
    
    parser.add_argument(
        "--music",
        choices=["chill", "upbeat", "tech", "hype"],
        default="tech",
        help="Background music mood (default: tech)",
    )
    
    parser.add_argument(
        "--voice",
        default="Puck",
        help="TTS voice (Puck, Kore, Aoede, Charon, Fenrir)",
    )
    
    parser.add_argument(
        "--api",
        choices=["gemini", "vertex"],
        default="gemini",
        help="API provider (default: gemini)",
    )
    
    parser.add_argument(
        "--music-volume",
        type=float,
        default=0.22,
        help="Background music volume 0.0-1.0 (default: 0.22)",
    )
    
    parser.add_argument(
        "--output",
        help="Output filename (default: viral-<source>.mp4)",
    )
    
    parser.add_argument(
        "--skip-render",
        action="store_true",
        help="Generate composition but skip rendering",
    )
    
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from last checkpoint if available",
    )
    
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Start fresh, ignore any checkpoints",
    )
    
    parser.add_argument(
        "--list-content-types",
        action="store_true",
        help="List available content types and exit",
    )
    
    parser.add_argument(
        "--list-apis",
        action="store_true",
        help="List available API providers and exit",
    )
    
    args = parser.parse_args()
    
    # Handle list options
    if args.list_content_types:
        print("Available content types:")
        for ct in ContentType.list_values():
            specs = ContentType.from_string(ct).get_specs()
            print(f"  {ct}: {specs['aspect_ratio']}, ~{specs['duration_target']}s")
        sys.exit(0)
    
    if args.list_apis:
        print("Available API providers:")
        providers = get_available_providers()
        for p in providers:
            status = "[OK] Available" if p["available"] else f"[X] {p.get('reason', 'Not available')}"
            print(f"  {p['name']} ({p['id']}): {status}")
            print(f"    Default model: {p['model']}")
        sys.exit(0)
    
    check_prerequisites()
    
    # Extract source name for output
    source = args.source
    if source.startswith(("http://", "https://")):
        repo_name = source.rstrip("/").split("/")[-1]
    else:
        repo_name = Path(source).stem
    
    output_name = args.output or f"viral-{repo_name}.mp4"
    
    print(f"\n[VIDEO] RepoToViralVideo")
    print(f"   Source: {get_source_display_name(source)}")
    print(f"   Content: {args.content_type}")
    print(f"   Music: {args.music} | Voice: {args.voice} | API: {args.api}")
    print()
    
    await run_pipeline(
        source=source,
        content_type=args.content_type,
        music=args.music,
        voice=args.voice,
        music_volume=args.music_volume,
        api_provider=args.api,
        output_name=output_name,
        skip_render=args.skip_render,
        resume=args.resume,
        clean=args.clean,
    )


if __name__ == "__main__":
    asyncio.run(main())
