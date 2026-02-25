"""
🔥 Viral Video Analyzer — Gemini + URL Context + File Support

Analyzes a GitHub repo, local file (MD/TXT/PDF), or other content using 
Gemini's URL context tool or direct content and produces everything needed 
for a viral promo video.

Supports:
- GitHub URLs
- Local markdown, text, and PDF files
- Multiple content types (Instagram Reels, YouTube Shorts, YouTube Long)
- Graceful abort when source is inaccessible
- Vertex AI as alternative to Gemini
"""

import json
import os
import asyncio
import sys
import re
from dataclasses import dataclass
from typing import Optional

from google import genai
from google.genai import types

# Import our new modules
from .checkpoint import ContentType, PipelineStep
from .source_validator import (
    validate_source,
    get_source_display_name,
    detect_source_type,
    SourceError,
)
from .api_client import APIClient, create_api_client, APIProvider


MAX_RETRIES = 3


def _parse_stars(value) -> int:
    """Parse star/fork count that may be a string like '17.8K', '95K+', or '1.2M'."""
    if isinstance(value, (int, float)):
        return int(value)
    if not isinstance(value, str):
        return 0
    s = value.strip().replace(",", "").replace("+", "")
    multiplier = 1
    if s.upper().endswith("K"):
        multiplier = 1000
        s = s[:-1]
    elif s.upper().endswith("M"):
        multiplier = 1_000_000
        s = s[:-1]
    try:
        return int(float(s) * multiplier)
    except ValueError:
        return 0


def _strip_json_fences(text: str) -> str:
    """Strip markdown code fences if Gemini wrapped the JSON response."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


def _clean_json_string(text: str) -> str:
    """Remove JS-style comments and fix common Gemini JSON quirks."""
    lines = text.split("\n")
    cleaned = []
    for line in lines:
        in_string = False
        escape = False
        comment_start = None
        for i, ch in enumerate(line):
            if escape:
                escape = False
                continue
            if ch == '\\':
                escape = True
                continue
            if ch == '"':
                in_string = not in_string
            elif ch == '/' and not in_string and i + 1 < len(line) and line[i + 1] == '/':
                comment_start = i
                break
        if comment_start is not None:
            line = line[:comment_start].rstrip()
        cleaned.append(line)
    text = "\n".join(cleaned)
    text = re.sub(r',\s*([}\]])', r'\1', text)
    return text


def _fix_empty_values(text: str) -> str:
    """Fix Gemini's habit of returning empty values like  \"key\":,  instead of  \"key\": null,"""
    # Match  ": ," or ":," (value missing between colon and comma/newline)
    # Replace with ": null,"
    text = re.sub(r':\s*,', ': null,', text)
    # Also handle empty value at end before closing brace:  "key":}  or  "key":\n}
    text = re.sub(r':\s*}', ': null}', text)
    return text


def _robust_parse_json(raw: str) -> dict:
    """Parse JSON from Gemini with multiple fallback strategies."""
    if not raw or not raw.strip():
        raise ValueError("Gemini returned an empty response.")

    text = _strip_json_fences(raw)

    # Pre-process: fix empty values ("key":, -> "key": null,)
    text = _fix_empty_values(text)

    # Attempt 1: direct parse
    try:
        data = json.loads(text)
        return _sanitize_nulls(data)
    except json.JSONDecodeError:
        pass

    # Attempt 2: clean comments + trailing commas
    cleaned = _clean_json_string(text)
    cleaned = _fix_empty_values(cleaned)
    try:
        data = json.loads(cleaned)
        return _sanitize_nulls(data)
    except json.JSONDecodeError:
        pass

    # Attempt 3: fix invalid escape sequences
    fixed = re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', cleaned)
    try:
        data = json.loads(fixed)
        return _sanitize_nulls(data)
    except json.JSONDecodeError as e:
        print(f"\n❌ All JSON parse attempts failed. Raw ({len(raw)} chars):\n{raw[:1500]}\n",
              file=sys.stderr, flush=True)
        raise ValueError(f"Could not parse Gemini response as JSON: {e}") from e


# Fields that must be lists vs strings
_LIST_FIELDS = {"topics", "frameworks", "features", "tech_stack", "scenes"}
_DICT_FIELDS = {"voiceover_scripts"}


def _sanitize_nulls(data: dict) -> dict:
    """Convert null values to appropriate empty defaults."""
    for key, val in data.items():
        if val is None:
            if key in _LIST_FIELDS:
                data[key] = []
            elif key in _DICT_FIELDS:
                data[key] = {}
            elif key in ("stars", "forks"):
                data[key] = 0
            else:
                data[key] = ""
    return data


@dataclass
class RepoAnalysis:
    name: str
    full_name: str
    description: str
    stars: int
    forks: int
    language: str
    topics: list[str]
    frameworks: list[str]
    features: list[dict]
    tech_stack: list[dict]
    hook_style: str
    hook_text: str
    tagline: str
    scenes: list[str]
    voiceover_scripts: dict[str, str]
    music_mood: str
    # Additional fields for content type
    content_type: str = "youtube_reel"
    source_content: Optional[str] = None


# ── Schema that Gemini must conform to ──────────────────────────────
FEATURE_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    properties={
        "emoji": types.Schema(type=types.Type.STRING),
        "title": types.Schema(type=types.Type.STRING),
        "desc": types.Schema(type=types.Type.STRING),
    },
    required=["emoji", "title", "desc"],
)

TECH_STACK_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    properties={
        "emoji": types.Schema(type=types.Type.STRING),
        "name": types.Schema(type=types.Type.STRING),
    },
    required=["emoji", "name"],
)

VOICEOVER_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    properties={
        "hook": types.Schema(type=types.Type.STRING),
        "what": types.Schema(type=types.Type.STRING),
        "features": types.Schema(type=types.Type.STRING),
        "tech": types.Schema(type=types.Type.STRING),
        "stats": types.Schema(type=types.Type.STRING),
        "cta": types.Schema(type=types.Type.STRING),
    },
    required=["hook", "what", "features", "tech", "stats", "cta"],
)

RESPONSE_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    properties={
        "name": types.Schema(type=types.Type.STRING),
        "full_name": types.Schema(type=types.Type.STRING),
        "description": types.Schema(type=types.Type.STRING),
        "stars": types.Schema(type=types.Type.INTEGER),
        "forks": types.Schema(type=types.Type.INTEGER),
        "language": types.Schema(type=types.Type.STRING),
        "topics": types.Schema(type=types.Type.ARRAY, items=types.Schema(type=types.Type.STRING)),
        "frameworks": types.Schema(type=types.Type.ARRAY, items=types.Schema(type=types.Type.STRING)),
        "features": types.Schema(type=types.Type.ARRAY, items=FEATURE_SCHEMA),
        "tech_stack": types.Schema(type=types.Type.ARRAY, items=TECH_STACK_SCHEMA),
        "hook_style": types.Schema(
            type=types.Type.STRING,
            enum=["counter", "momentum", "problem"],
        ),
        "hook_text": types.Schema(type=types.Type.STRING),
        "tagline": types.Schema(type=types.Type.STRING),
        "scenes": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(
                type=types.Type.STRING,
                enum=["hook", "what", "features", "tech", "stats", "cta"],
            ),
        ),
        "voiceover_scripts": VOICEOVER_SCHEMA,
        "music_mood": types.Schema(
            type=types.Type.STRING,
            enum=["hype", "tech", "chill", "upbeat"],
        ),
    },
    required=[
        "name", "full_name", "description", "stars", "forks",
        "language", "topics", "frameworks", "features", "tech_stack",
        "hook_style", "hook_text", "tagline", "scenes",
        "voiceover_scripts", "music_mood",
    ],
)


def get_system_prompt(content_type: str = "youtube_reel") -> str:
    """Get the system prompt based on content type."""
    
    content_spec = ContentType.from_string(content_type).get_specs()
    duration_target = content_spec.get("duration_target", 45)
    max_features = content_spec.get("max_features", 4)
    max_tech = content_spec.get("max_tech", 8)
    
    # Adjust prompt based on content type
    if content_type == "instagram_reel":
        duration_hint = f"Keep it SHORT - {duration_target} seconds maximum."
        scene_hint = "Include: hook, what, features, cta. Skip tech and stats for brevity."
    elif content_type == "youtube_reel":
        duration_hint = f"Keep it concise - around {duration_target} seconds."
        scene_hint = "Include: hook, what, features, tech (if interesting), stats (if impressive), cta."
    else:  # youtube_long
        duration_hint = f"This is longer content - {duration_target//60} minutes. Be more detailed."
        scene_hint = "Include all scenes: hook, what, features, tech, stats, cta. Go deeper on features."
    
    return f"""You are a viral video producer analyzing content for a promo video. Your job is to extract the most impressive, shareable aspects and write punchy voiceover scripts.

RULES:
- Write like Fireship — punchy, opinionated, no filler
- Stars and forks must be actual numbers if available, not made up
- Voiceover must sound conversational, not robotic
- {duration_hint}
- Return {max_features} features max, up to {max_tech} tech_stack items
- tagline: 8 words max
- hook_text: opening hook to grab attention in 3 seconds
- hook_style: choose "counter" if there are massive stars (>10K), "momentum" if growing (>100 stars), or "problem" if newer/smaller — focus on the problem it solves
- scenes: choose which scenes to include from [hook, what, features, tech, stats, cta]. {scene_hint}
- voiceover_scripts: write a script for EVERY key (hook, what, features, tech, stats, cta) regardless of scenes chosen
- If <100 stars, focus voiceovers on WHAT IT DOES, not vanity metrics
- If >10K stars, lead with impressive numbers in the hook"""


async def analyze_source_for_viral(
    source: str,
    content_type: str = "youtube_reel",
    api_provider: str = "gemini",
    validate_before: bool = True,
) -> RepoAnalysis:
    """Analyze a source (GitHub URL or local file) for viral video generation.
    
    This is the main entry point that:
    1. Validates the source BEFORE any API calls
    2. Extracts content from local files if applicable
    3. Analyzes with Gemini/Vertex AI
    
    Args:
        source: GitHub URL or path to local file (.md, .txt, .pdf)
        content_type: Content type preset (instagram_reel, youtube_reel, youtube_long)
        api_provider: API provider ("gemini" or "vertex")
        validate_before: Whether to validate source before API calls (default: True)
    
    Returns:
        RepoAnalysis object with all data needed for video generation
    
    Raises:
        SourceError: If source is inaccessible
        ValueError: If analysis fails after retries
    """
    
    # Step 1: Validate source BEFORE any API calls
    if validate_before:
        print(f"🔍 Validating source: {get_source_display_name(source)}...")
        is_valid, error_msg, content = validate_source(source)
        
        if not is_valid:
            raise SourceError(
                f"❌ Source validation failed: {error_msg}\n"
                f"   Source: {source}\n"
                f"   Aborting before any API calls to save quota."
            )
        
        # For GitHub URLs, content is fetched via API
        # For local files, content is extracted directly
        source_type = detect_source_type(source)
        if source_type == "local_file":
            print(f"   ✅ Source validated. Content extracted ({len(content)} chars)")
        else:
            print(f"   ✅ Source validated (GitHub URL)")
    else:
        content = None
        source_type = detect_source_type(source)
    
    # Step 2: Create API client
    client = create_api_client(provider=api_provider)
    
    # Step 3: Build the prompt based on source type
    if source_type == "github_url":
        prompt = f"Analyze this GitHub repo for a viral promo video: {source}"
        tools = [types.Tool(url_context=types.UrlContext())]
    else:
        # For local files, provide the content directly
        prompt = f"""Analyze this content for a viral promo video:

{content}

Provide a JSON response with the following structure based on the content."""
        tools = []
    
    # Step 4: Run the analysis with retries
    return await _analyze_with_retry(
        client=client,
        prompt=prompt,
        content_type=content_type,
        tools=tools,
        source=source,
    )


async def _analyze_with_retry(
    client: APIClient,
    prompt: str,
    content_type: str,
    tools: list,
    source: str,
) -> RepoAnalysis:
    """Run analysis with retry logic."""
    
    last_error = None
    
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(f"🔍 Attempt {attempt}/{MAX_RETRIES}: Analyzing {get_source_display_name(source)}...",
                  flush=True)

            response = client.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=get_system_prompt(content_type),
                    tools=tools if tools else None,
                    response_mime_type="application/json",
                    response_schema=RESPONSE_SCHEMA,
                ),
            )

            raw = response.text
            print(f"✅ Got response ({len(raw) if raw else 0} chars)", flush=True)

            data = _robust_parse_json(raw)
            
            # Successfully parsed — build the result
            return _build_analysis(data, content_type)

        except Exception as e:
            last_error = e
            print(f"⚠️  Attempt {attempt} failed: {e}", file=sys.stderr, flush=True)
            if attempt < MAX_RETRIES:
                wait = attempt * 2  # 2s, 4s backoff
                print(f"   Retrying in {wait}s...", flush=True)
                await asyncio.sleep(wait)

    # All retries exhausted
    raise ValueError(
        f"Failed after {MAX_RETRIES} attempts. Last error: {last_error}"
    )


def _build_analysis(data: dict, content_type: str = "youtube_reel") -> RepoAnalysis:
    """Build a RepoAnalysis from parsed JSON data. Model decides structure."""
    stars = _parse_stars(data.get("stars", 0))
    forks = _parse_stars(data.get("forks", 0))

    # Get content type specs
    content_spec = ContentType.from_string(content_type).get_specs()
    max_features = content_spec.get("max_features", 4)
    max_tech = content_spec.get("max_tech", 8)
    allowed_scenes = content_spec.get("scenes", ["hook", "what", "features", "cta"])
    
    # Model chooses scenes; use 'or' so empty lists from null-fix also get defaults
    scenes = data.get("scenes") or allowed_scenes
    # Filter to allowed scenes for content type
    scenes = [s for s in scenes if s in allowed_scenes]
    if not scenes:
        scenes = allowed_scenes[:4]
    
    features = (data.get("features") or [])[:max_features]
    tech_stack = (data.get("tech_stack") or [])[:max_tech]

    # Drop scenes that have no data to display
    if not features and "features" in scenes:
        scenes = [s for s in scenes if s != "features"]
    if not tech_stack and "tech" in scenes:
        scenes = [s for s in scenes if s != "tech"]
    if stars < 100 and "stats" in scenes:
        scenes = [s for s in scenes if s != "stats"]

    voiceover = data.get("voiceover_scripts") or {}
    voiceover = {k: v for k, v in voiceover.items() if k in scenes and v}

    # Safety: ensure every chosen scene has a voiceover
    repo_name = data.get("name", "this repo")
    for scene_id in scenes:
        if scene_id not in voiceover:
            voiceover[scene_id] = f"Check out {repo_name}."

    return RepoAnalysis(
        name=data.get("name", ""),
        full_name=data.get("full_name", ""),
        description=data.get("description", ""),
        stars=stars,
        forks=forks,
        language=data.get("language", ""),
        topics=data.get("topics") or [],
        frameworks=data.get("frameworks") or [],
        features=features,
        tech_stack=tech_stack,
        hook_style=data.get("hook_style") or "problem",
        hook_text=data.get("hook_text", ""),
        tagline=data.get("tagline", ""),
        scenes=scenes,
        voiceover_scripts=voiceover,
        music_mood=data.get("music_mood") or "tech",
        content_type=content_type,
    )


# Backwards compatibility - keep the old function name
async def analyze_repo_for_viral(repo_url: str) -> RepoAnalysis:
    """Analyze a repo using Gemini with URL context for viral video generation.
    
    This is the legacy function - recommends using analyze_source_for_viral instead.
    """
    return await analyze_source_for_viral(repo_url)


if __name__ == "__main__":
    from dataclasses import asdict

    if len(sys.argv) < 2:
        print("Usage: python viral_analyzer.py <github-url|local-file> [--content-type type] [--api gemini|vertex]")
        sys.exit(1)

    source = sys.argv[1]
    content_type = "youtube_reel"
    api_provider = "gemini"
    
    # Parse optional args
    i = 2
    while i < len(sys.argv):
        if sys.argv[i] == "--content-type" and i + 1 < len(sys.argv):
            content_type = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == "--api" and i + 1 < len(sys.argv):
            api_provider = sys.argv[i + 1]
            i += 2
        else:
            i += 1

    async def main():
        analysis = await analyze_source_for_viral(
            source,
            content_type=content_type,
            api_provider=api_provider,
        )
        print(json.dumps(asdict(analysis), indent=2))

    asyncio.run(main())
