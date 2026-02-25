"""
🤖 API Client — Unified Interface for Gemini and Vertex AI

Supports both Google Gemini API and Google Vertex AI API.
"""

import os
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

from google import genai  # type: ignore[reportMissingImports]
from google.genai import types  # type: ignore[reportMissingImports]


class APIProvider(Enum):
    """API provider options."""
    GEMINI = "gemini"
    VERTEX = "vertex"
    
    @classmethod
    def from_string(cls, s: str) -> "APIProvider":
        """Convert string to APIProvider."""
        s = (s or "").lower().strip()
        if s in ("vertex", "vertex_ai", "google_vertex"):
            return cls.VERTEX
        return cls.GEMINI


@dataclass
class APIConfig:
    """API configuration."""
    provider: APIProvider
    api_key: Optional[str] = None
    project_id: Optional[str] = None
    location: Optional[str] = None
    model: str = "gemini-3.1-pro-preview"

    @staticmethod
    def _get_vertex_location() -> str:
        """Resolve Vertex location from env with sensible fallback."""
        return (
            os.environ.get("GOOGLE_CLOUD_LOCATION")
            or os.environ.get("GOOGLE_CLOUD_REGION")
            or "us-central1"
        )
    
    def validate(self) -> list[str]:
        """Validate configuration and return list of errors."""
        errors = []
        
        if self.provider == APIProvider.GEMINI:
            if not self.api_key:
                self.api_key = os.environ.get("GEMINI_API_KEY")
            if not self.api_key:
                errors.append("GEMINI_API_KEY environment variable not set")
        
        elif self.provider == APIProvider.VERTEX:
            if not self.api_key:
                self.api_key = os.environ.get("GOOGLE_API_KEY")
            if self.api_key:
                errors.append(
                    "GOOGLE_API_KEY is set. Vertex client initialization uses project/location "
                    "and may still require ADC depending on google-genai auth mode."
                )
            
            if not self.project_id:
                self.project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
            if not self.project_id:
                errors.append("GOOGLE_CLOUD_PROJECT environment variable not set for Vertex AI")
            
            if not self.location:
                self.location = self._get_vertex_location()
        
        return errors


class APIClient:
    """Unified API client for Gemini and Vertex AI."""
    
    def __init__(self, config: APIConfig):
        self.config = config
        self._client: Any = None
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize the appropriate client."""
        if self.config.provider == APIProvider.GEMINI:
            self._client = genai.Client(
                api_key=self.config.api_key or os.environ.get("GEMINI_API_KEY")
            )
        elif self.config.provider == APIProvider.VERTEX:
            # For Vertex AI, we use the same client but configure differently
            self._client = genai.Client(
                vertexai=True,
                project=self.config.project_id or os.environ.get("GOOGLE_CLOUD_PROJECT"),
                location=self.config.location or APIConfig._get_vertex_location(),
            )
    
    def generate_content(
        self,
        model: Optional[str] = None,
        contents: Any = None,
        config: Optional[types.GenerateContentConfig] = None,
    ) -> types.GenerateContentResponse:
        """Generate content using the configured API."""
        model = model or self.config.model

        if self._client is None:
            raise RuntimeError("API client is not initialized")
        
        return self._client.models.generate_content(
            model=model,
            contents=contents,
            config=config,
        )
    
    @property
    def client(self):
        """Get the underlying client."""
        return self._client


def create_api_client(
    provider: str = "gemini",
    model: Optional[str] = None,
) -> APIClient:
    """Create an API client based on provider.
    
    Args:
        provider: "gemini" or "vertex"
        model: Model name (defaults based on provider)
    
    Returns:
        Configured APIClient instance
    """
    api_provider = APIProvider.from_string(provider)
    
    # Set default models based on provider
    if model is None:
        if api_provider == APIProvider.GEMINI:
            model = "gemini-3.1-pro-preview"
        else:
            model = "gemini-3.1-pro-preview"
    
    config = APIConfig(
        provider=api_provider,
        model=model,
    )
    
    # Validate and warn about missing config
    errors = config.validate()
    if errors:
        print("[WARN] API Configuration warnings:")
        for error in errors:
            print(f"   - {error}")
    
    return APIClient(config)


def get_available_providers() -> list[dict]:
    """Get list of available API providers based on environment.
    
    Returns:
        List of available providers with configuration status
    """
    providers = []
    
    # Check Gemini
    gemini_key = os.environ.get("GEMINI_API_KEY")
    providers.append({
        "name": "Gemini",
        "id": "gemini",
        "available": bool(gemini_key),
        "model": "gemini-3.1-pro-preview",
    })
    
    # Check Vertex
    vertex_key = os.environ.get("GOOGLE_API_KEY")
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
    location = APIConfig._get_vertex_location()
    adc_env = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")

    if project_id:
        providers.append({
            "name": "Vertex AI",
            "id": "vertex",
            "available": True,
            "model": "gemini-3.1-pro-preview",
            "location": location,
            "auth_hint": "ADC" if adc_env else "ADC (or GOOGLE_API_KEY depending on runtime auth mode)",
        })
    else:
        providers.append({
            "name": "Vertex AI",
            "id": "vertex",
            "available": False,
            "model": "gemini-3.1-pro-preview",
            "reason": "Requires GOOGLE_CLOUD_PROJECT",
        })
    
    return providers
