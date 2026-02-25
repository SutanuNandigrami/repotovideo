"""
[TTS] Viral Video TTS - Gemini 2.5 Pro Preview TTS + Vertex AI Support

Generates voiceover audio for each scene using Gemini's natural TTS.
Supports both Gemini API and Vertex AI API.
"""

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from google import genai
from google.genai import types

from .api_client import create_api_client, APIProvider


TTS_MODEL = os.environ.get("TTS_MODEL", "gemini-2.5-pro-preview-tts")
VOICE = "Puck"  # Natural, playful, energetic

TONE_HINTS = {
    "hook": "Say this with excitement and energy, like revealing something amazing. Grab attention immediately:",
    "what": "Say this with confidence and authority, introducing something impressive:",
    "features": "Say this with building excitement, each item more impressive than the last:",
    "tech": "Say this like listing an impressive roster, with emphasis on each name:",
    "stats": "Say this with pride, emphasizing the numbers like they're incredible achievements:",
    "cta": "Say this as a powerful, memorable call to action. End strong:",
}


def generate_voiceover(
    voiceover_scripts: dict[str, str],
    output_dir: str,
    voice: str = VOICE,
    api_provider: str = "gemini",
) -> dict[str, float]:
    """Generate TTS audio for each scene.
    
    Args:
        voiceover_scripts: Dict of scene_id -> script text
        output_dir: Output directory        voice: Voice for audio files
 name (Puck, Kore, Aoede, Charon, Fenrir)
        api_provider: API provider ("gemini" or "vertex")
    
    Returns:
        dict of scene_id -> duration in seconds
    """
    # Create API client
    client = create_api_client(provider=api_provider)
    
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    
    durations = {}
    scene_index = 0
    
    for scene_id, script in voiceover_scripts.items():
        fname = f"scene_{scene_index:02d}.mp3"
        
        # Use platform-aware temp directory
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            raw_path = tmp.name
        
        mp3_path = str(out / fname)
        
        tone = TONE_HINTS.get(scene_id, "Say this naturally and engagingly:")
        prompt = f"{tone} {script}"
        
        print(f"  [TTS] Generating {scene_id} ({fname})...")
        
        try:
            # Use the TTS model explicitly for audio generation
            response = client.generate_content(
                model=TTS_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                voice_name=voice
                            )
                        )
                    ),
                ),
            )
        except Exception as e:
            raise RuntimeError(f"TTS generation failed for scene '{scene_id}': {e}")
        
        # Extract audio data from response
        audio_data = None
        if response.candidates:
            for part in response.candidates[0].content.parts:
                if part.inline_data:
                    audio_data = part.inline_data.data
                    break
        
        if not audio_data:
            raise RuntimeError(
                f"No audio data returned by TTS for scene '{scene_id}'. "
                f"Check your API key and quota."
            )
        
        with open(raw_path, "wb") as f:
            f.write(audio_data)
        
        # Convert to MP3 (check exit code) - cross-platform
        import platform
        system = platform.system()
        
        if system == "Windows":
            # Windows may need different ffmpeg path
            ffmpeg_cmd = "ffmpeg"
        else:
            ffmpeg_cmd = "ffmpeg"
        
        ffmpeg_result = subprocess.run(
            [ffmpeg_cmd, "-y", "-f", "s16le", "-ar", "24000", "-ac", "1",
             "-i", raw_path, "-b:a", "192k", mp3_path],
            capture_output=True, text=True,
        )
        if ffmpeg_result.returncode != 0:
            raise RuntimeError(
                f"ffmpeg conversion failed for scene '{scene_id}': {ffmpeg_result.stderr}"
            )
        
        # Get duration (with fallback)
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                 "-of", "csv=p=0", mp3_path],
                capture_output=True, text=True,
            )
            dur = float(result.stdout.strip())
        except (ValueError, AttributeError):
            print(f"   Could not read duration for {scene_id}, using estimate")
            dur = max(len(script.split()) * 0.35, 3.0)  # ~0.35s per word
        
        durations[scene_id] = dur
        print(f"    [OK] {dur:.2f}s")
        
        # Cleanup temp file
        try:
            os.remove(raw_path)
        except OSError:
            pass
        
        scene_index += 1
    
    return durations


# Backwards compatibility - keep old function signature
def generate_voiceover_legacy(
    voiceover_scripts: dict[str, str],
    output_dir: str,
    voice: str = VOICE,
) -> dict[str, float]:
    """Legacy function for backwards compatibility."""
    return generate_voiceover(voiceover_scripts, output_dir, voice, api_provider="gemini")


if __name__ == "__main__":
    import json, sys
    
    if len(sys.argv) < 2:
        print("Usage: python viral_tts.py <analysis.json> [output_dir] [--api gemini|vertex]")
        sys.exit(1)
    
    with open(sys.argv[1]) as f:
        analysis = json.load(f)
    
    out_dir = sys.argv[2] if len(sys.argv) > 2 else "./audio_viral"
    api_provider = "gemini"
    
    # Check for API arg
    if "--api" in sys.argv:
        idx = sys.argv.index("--api")
        if idx + 1 < len(sys.argv):
            api_provider = sys.argv[idx + 1]
    
    durations = generate_voiceover(
        analysis["voiceover_scripts"], 
        out_dir,
        api_provider=api_provider,
    )
    print(json.dumps(durations, indent=2))
