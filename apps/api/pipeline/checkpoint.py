"""
📦 Checkpoint System — Step-based Progress Tracking with Local File Outputs

Provides checkpoint functionality to save progress after each step and 
allow resuming from a specific step if it fails.

Steps:
- analyze: Repository/Content analysis
- generate_scenes: Scene generation
- tts: Text-to-speech audio generation
- render_video: Final video rendering
"""

import json
import os
import shutil
from dataclasses import dataclass, asdict, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class PipelineStep(Enum):
    """Pipeline steps in execution order."""
    ANALYZE = "analyze"
    GENERATE_SCENES = "generate_scenes"
    TTS = "tts"
    RENDER_VIDEO = "render_video"
    
    @classmethod
    def from_string(cls, s: str) -> "PipelineStep":
        """Convert string to PipelineStep."""
        for step in cls:
            if step.value == s:
                return step
        raise ValueError(f"Unknown step: {s}")
    
    @classmethod
    def list_values(cls) -> list[str]:
        """Get list of step values."""
        return [step.value for step in cls]


class ContentType(Enum):
    """Content type presets for different platforms."""
    INSTAGRAM_REEL = "instagram_reel"      # 9:16, ~30s
    YOUTUBE_REEL = "youtube_reel"         # 9:16, ~45s
    YOUTUBE_LONG = "youtube_long"          # 16:9, ~5-10min
    
    @classmethod
    def from_string(cls, s: str) -> "ContentType":
        """Convert string to ContentType."""
        for ct in cls:
            if ct.value == s:
                return ct
        # Default to youtube_reel if unknown
        return cls.YOUTUBE_REEL
    
    @classmethod
    def list_values(cls) -> list[str]:
        """Get list of content type values."""
        return [ct.value for ct in cls]
    
    def get_specs(self) -> dict[str, Any]:
        """Get specifications for this content type."""
        specs = {
            "instagram_reel": {
                "aspect_ratio": "9:16",
                "width": 1080,
                "height": 1920,
                "duration_target": 30,
                "scenes": ["hook", "what", "features", "cta"],
                "max_features": 3,
                "max_tech": 5,
            },
            "youtube_reel": {
                "aspect_ratio": "9:16",
                "width": 1080,
                "height": 1920,
                "duration_target": 45,
                "scenes": ["hook", "what", "features", "tech", "stats", "cta"],
                "max_features": 4,
                "max_tech": 8,
            },
            "youtube_long": {
                "aspect_ratio": "16:9",
                "width": 1920,
                "height": 1080,
                "duration_target": 300,  # 5 minutes
                "scenes": ["hook", "what", "features", "tech", "stats", "cta"],
                "max_features": 6,
                "max_tech": 10,
            },
        }
        return specs.get(self.value, specs["youtube_reel"])


class SourceType(Enum):
    """Type of input source."""
    GITHUB_URL = "github_url"
    LOCAL_FILE = "local_file"
    
    @classmethod
    def from_string(cls, s: str) -> "SourceType":
        """Detect source type from input."""
        if s.startswith(("http://", "https://")):
            if "github.com" in s or "gitlab.com" in s or "bitbucket.org" in s:
                return cls.GITHUB_URL
        return cls.LOCAL_FILE


@dataclass
class PipelineCheckpoint:
    """Represents the current state of the pipeline."""
    job_id: str
    source: str
    source_type: str
    content_type: str
    step: str
    status: str  # "in_progress", "completed", "failed", "aborted"
    started_at: str
    updated_at: str
    output_dir: str
    
    # Step-specific data
    analysis: Optional[dict] = None
    scenes: Optional[dict] = None
    audio_files: Optional[list[str]] = None
    durations: Optional[dict] = None
    video_output: Optional[str] = None
    
    # Error tracking
    error_message: Optional[str] = None
    
    # Configuration
    music: str = "tech"
    voice: str = "Puck"
    music_volume: float = 0.22
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "PipelineCheckpoint":
        """Create from dictionary."""
        return cls(**data)


class CheckpointManager:
    """Manages pipeline checkpoints and file outputs."""
    
    def __init__(self, output_dir: str):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoint_file = self.output_dir / "checkpoint.json"
    
    def create_checkpoint(
        self,
        job_id: str,
        source: str,
        content_type: str = "youtube_reel",
        music: str = "tech",
        voice: str = "Puck",
        music_volume: float = 0.22,
    ) -> PipelineCheckpoint:
        """Create a new checkpoint."""
        source_type = SourceType.from_string(source).value
        
        checkpoint = PipelineCheckpoint(
            job_id=job_id,
            source=source,
            source_type=source_type,
            content_type=content_type,
            step=PipelineStep.ANALYZE.value,
            status="in_progress",
            started_at=datetime.utcnow().isoformat() + "Z",
            updated_at=datetime.utcnow().isoformat() + "Z",
            output_dir=str(self.output_dir),
            music=music,
            voice=voice,
            music_volume=music_volume,
        )
        
        self._save_checkpoint(checkpoint)
        return checkpoint
    
    def load_checkpoint(self) -> Optional[PipelineCheckpoint]:
        """Load existing checkpoint if available."""
        if not self.checkpoint_file.exists():
            return None
        
        try:
            data = json.loads(self.checkpoint_file.read_text(encoding="utf-8"))
            return PipelineCheckpoint.from_dict(data)
        except (json.JSONDecodeError, TypeError, KeyError) as e:
            print(f"⚠️  Failed to load checkpoint: {e}")
            return None
    
    def _save_checkpoint(self, checkpoint: PipelineCheckpoint):
        """Save checkpoint to disk."""
        checkpoint.updated_at = datetime.utcnow().isoformat() + "Z"
        self.checkpoint_file.write_text(
            json.dumps(checkpoint.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
    
    def update_step(
        self,
        step: PipelineStep,
        status: str = "in_progress",
        **kwargs,
    ) -> PipelineCheckpoint:
        """Update the current step."""
        checkpoint = self.load_checkpoint()
        if not checkpoint:
            raise ValueError("No checkpoint found")
        
        checkpoint.step = step.value
        checkpoint.status = status
        
        # Update step-specific data
        for key, value in kwargs.items():
            if hasattr(checkpoint, key):
                setattr(checkpoint, key, value)
        
        self._save_checkpoint(checkpoint)
        return checkpoint
    
    def complete_step(self, step: PipelineStep, **kwargs) -> PipelineCheckpoint:
        """Mark a step as completed."""
        return self.update_step(step, status="completed", **kwargs)
    
    def fail_step(self, step: PipelineStep, error_message: str) -> PipelineCheckpoint:
        """Mark a step as failed."""
        return self.update_step(step, status="failed", error_message=error_message)
    
    def get_current_step(self) -> Optional[PipelineStep]:
        """Get the current step."""
        checkpoint = self.load_checkpoint()
        if not checkpoint:
            return None
        return PipelineStep.from_string(checkpoint.step)
    
    def can_resume_from(self, step: PipelineStep) -> bool:
        """Check if we can resume from a specific step."""
        checkpoint = self.load_checkpoint()
        if not checkpoint:
            return False
        
        # Check if previous steps are completed
        step_order = PipelineStep.list_values()
        current_idx = step_order.index(checkpoint.step)
        target_idx = step_order.index(step.value)
        
        # Can resume if target step is at or before current step (hasn't been completed yet)
        return target_idx <= current_idx and checkpoint.status == "completed"
    
    def get_step_output_files(self, step: PipelineStep) -> dict[str, Path]:
        """Get output files for a specific step."""
        checkpoint = self.load_checkpoint()
        if not checkpoint:
            return {}
        
        files = {}
        
        if step == PipelineStep.ANALYZE:
            files["analysis"] = self.output_dir / "analysis.json"
        
        elif step == PipelineStep.GENERATE_SCENES:
            files["scenes"] = self.output_dir / "scenes.json"
        
        elif step == PipelineStep.TTS:
            audio_dir = self.output_dir / "audio"
            if audio_dir.exists():
                files["audio_dir"] = audio_dir
                files["audio_files"] = list(audio_dir.glob("*.mp3"))
        
        elif step == PipelineStep.RENDER_VIDEO:
            if checkpoint.video_output:
                files["video"] = Path(checkpoint.video_output)
        
        return files
    
    def has_step_completed(self, step: PipelineStep) -> bool:
        """Check if a step has already completed."""
        checkpoint = self.load_checkpoint()
        if not checkpoint:
            return False
        
        step_order = PipelineStep.list_values()
        current_idx = step_order.index(checkpoint.step)
        target_idx = step_order.index(step.value)
        
        # Step completed if we're past it and it was successful
        return current_idx > target_idx and checkpoint.status == "completed"
    
    def get_step_data(self, step: PipelineStep) -> Optional[dict]:
        """Get saved data from a completed step."""
        checkpoint = self.load_checkpoint()
        if not checkpoint or checkpoint.status != "completed":
            return None
        
        step_order = PipelineStep.list_values()
        current_idx = step_order.index(checkpoint.step)
        target_idx = step_order.index(step.value)
        
        if current_idx <= target_idx:
            return None
        
        if step == PipelineStep.ANALYZE:
            return checkpoint.analysis
        elif step == PipelineStep.GENERATE_SCENES:
            return checkpoint.scenes
        elif step == PipelineStep.TTS:
            return {
                "audio_files": checkpoint.audio_files,
                "durations": checkpoint.durations,
            }
        
        return None


def create_output_dir(base_dir: str, job_id: str) -> Path:
    """Create output directory for a job."""
    output_dir = Path(base_dir) / job_id
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def cleanup_checkpoint(output_dir: Path):
    """Clean up checkpoint files (for fresh start)."""
    checkpoint_file = output_dir / "checkpoint.json"
    if checkpoint_file.exists():
        checkpoint_file.unlink()


def get_step_from_string(step_str: str) -> PipelineStep:
    """Get PipelineStep from string with validation."""
    try:
        return PipelineStep.from_string(step_str)
    except ValueError:
        valid = ", ".join(PipelineStep.list_values())
        raise ValueError(f"Invalid step: {step_str}. Valid steps: {valid}")
