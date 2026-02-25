"""
[SEARCH] Source Validator - Validate and Extract Content from Various Sources

Handles:
- GitHub URL validation
- Local file validation (MD, TXT, PDF)
- Content extraction from various formats
- Graceful abort when source is inaccessible
"""

import io
import os
import re
import sys
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional, Tuple

# PDF support
try:
    import PyPDF2
    HAS_PDF_SUPPORT = True
except ImportError:
    HAS_PDF_SUPPORT = False


class SourceError(Exception):
    """Exception raised when source is inaccessible."""
    pass


class SourceType:
    """Represents a validated source."""
    def __init__(self, source_type: str, path: str, content: Optional[str] = None):
        self.source_type = source_type
        self.path = path
        self.content = content


def validate_github_url(url: str) -> Tuple[bool, str]:
    """Validate GitHub URL and check if accessible.
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    # Check if it's a valid GitHub URL pattern
    github_pattern = r'^https?://(?:www\.)?github\.com/[\w-]+/[\w.-]+/?$'
    if not re.match(github_pattern, url):
        return False, f"Invalid GitHub URL format: {url}"
    
    # Normalize URL (remove trailing slash)
    url = url.rstrip('/')
    
    # Try to access the repository page
    try:
        request = urllib.request.Request(
            url,
            headers={
                'User-Agent': 'RepoToVideo/1.0 (GitHub URL Validator)',
                'Accept': 'text/html',
            }
        )
        
        with urllib.request.urlopen(request, timeout=10) as response:
            if response.status == 200:
                return True, ""
            else:
                return False, f"GitHub returned status {response.status}"
                
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False, f"Repository not found (404): {url}"
        elif e.code == 403:
            return False, f"Repository access forbidden (403). May be private."
        else:
            return False, f"HTTP error {e.code} accessing {url}"
            
    except urllib.error.URLError as e:
        return False, f"Network error accessing {url}: {e.reason}"
        
    except Exception as e:
        return False, f"Error validating GitHub URL: {str(e)}"


def validate_local_file(file_path: str) -> Tuple[bool, str, Optional[str]]:
    """Validate local file and extract content.
    
    Returns:
        Tuple of (is_valid, error_message, content)
    """
    path = Path(file_path)
    
    # Check if file exists
    if not path.exists():
        return False, f"File not found: {file_path}", None
    
    # Check if it's a file (not directory)
    if not path.is_file():
        return False, f"Path is not a file: {file_path}", None
    
    # Check extension
    ext = path.suffix.lower()
    
    if ext == '.md':
        return extract_markdown(path)
    elif ext == '.txt':
        return extract_text(path)
    elif ext == '.pdf':
        return extract_pdf(path)
    else:
        return False, f"Unsupported file type: {ext}. Supported: .md, .txt, .pdf", None


def extract_markdown(path: Path) -> Tuple[bool, str, Optional[str]]:
    """Extract content from markdown file."""
    try:
        content = path.read_text(encoding='utf-8')
        return True, "", content
    except UnicodeDecodeError:
        # Try with different encoding
        try:
            content = path.read_text(encoding='latin-1')
            return True, "", content
        except Exception as e:
            return False, f"Failed to read markdown file: {e}", None
    except Exception as e:
        return False, f"Failed to read markdown file: {e}", None


def extract_text(path: Path) -> Tuple[bool, str, Optional[str]]:
    """Extract content from text file."""
    try:
        content = path.read_text(encoding='utf-8')
        return True, "", content
    except UnicodeDecodeError:
        try:
            content = path.read_text(encoding='latin-1')
            return True, "", content
        except Exception as e:
            return False, f"Failed to read text file: {e}", None
    except Exception as e:
        return False, f"Failed to read text file: {e}", None


def extract_pdf(path: Path) -> Tuple[bool, str, Optional[str]]:
    """Extract content from PDF file."""
    if not HAS_PDF_SUPPORT:
        return False, "PDF support not available. Install PyPDF2: pip install PyPDF2", None
    
    try:
        content_parts = []
        
        with open(path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            
            for page_num, page in enumerate(reader.pages):
                text = page.extract_text()
                if text:
                    content_parts.append(text)
        
        content = "\n\n".join(content_parts)
        
        if not content.strip():
            return False, "PDF appears to be empty or contains no extractable text", None
        
        return True, "", content
        
    except Exception as e:
        return False, f"Failed to extract PDF content: {e}", None


def detect_source_type(source: str) -> str:
    """Detect the type of source."""
    source = source.strip()
    
    # Check for URL
    if source.startswith(('http://', 'https://')):
        if 'github.com' in source:
            return 'github_url'
        else:
            return 'web_url'
    
    # Check for local file
    path = Path(source)
    if path.exists() and path.is_file():
        ext = path.suffix.lower()
        if ext in ['.md', '.txt', '.pdf']:
            return 'local_file'
    
    return 'unknown'


def validate_source(source: str) -> Tuple[bool, str, Optional[str]]:
    """Validate a source and return content if applicable.
    
    This is the main entry point for source validation.
    Performs validation BEFORE any API calls to avoid wasting quota.
    
    Returns:
        Tuple of (is_valid, error_message, content)
        - For GitHub URLs: content is None (content fetched via API)
        - For local files: content is the extracted text
    """
    source = source.strip()
    
    # Detect source type
    source_type = detect_source_type(source)
    
    if source_type == 'github_url':
        return validate_github_url(source)
    
    elif source_type == 'local_file':
        return validate_local_file(source)
    
    elif source_type == 'web_url':
        # For now, only support GitHub URLs
        return False, "Only GitHub URLs are supported for web sources. Use local files (.md, .txt, .pdf) for other content.", None
    
    else:
        # Unknown source - try to interpret as a file path
        return validate_local_file(source)


def get_source_display_name(source: str) -> str:
    """Get a human-readable name for the source."""
    source_type = detect_source_type(source)
    
    if source_type == 'github_url':
        # Extract repo name from URL
        parts = source.rstrip('/').split('/')
        if len(parts) >= 2:
            return f"github.com/{parts[-2]}/{parts[-1]}"
        return source
    
    elif source_type == 'local_file':
        return Path(source).name
    
    return source


def check_prerequisites() -> list[str]:
    """Check for required dependencies.
    
    Returns:
        List of missing dependencies
    """
    missing = []
    
    # Check PyPDF2 for PDF support
    if not HAS_PDF_SUPPORT:
        missing.append("PyPDF2 (optional, for PDF support: pip install PyPDF2)")
    
    return missing
