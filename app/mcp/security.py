# app/mcp/security.py
"""
Staging security validators for MCP server.

Provides path traversal prevention, project isolation, and input validation
for all staging operations exposed via MCP tools.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List

from app.config.settings import get_settings
from app.ingest.local_loader import IGNORE_PATTERNS
import fnmatch


class SecurityError(Exception):
    """Raised when a security validation fails."""
    pass


class ValidationError(Exception):
    """Raised when input validation fails."""
    pass


# Project ID: alphanumeric, underscore, hyphen, 3-64 chars
VALID_PROJECT_ID = re.compile(r'^[a-zA-Z0-9_-]{3,64}$')

# Filename: alphanumeric, dot, underscore, hyphen, forward slash (for subdirs)
# No backslash, no leading/trailing slashes
VALID_FILENAME = re.compile(r'^[a-zA-Z0-9._-][a-zA-Z0-9._/-]{0,254}$')

# Forbidden patterns in any path component
FORBIDDEN_PATTERNS = ['..', '\x00', '~', ':', '*', '?', '"', '<', '>', '|']

# Reserved names (Windows)
RESERVED_NAMES = {
    'con', 'prn', 'aux', 'nul',
    'com1', 'com2', 'com3', 'com4', 'com5', 'com6', 'com7', 'com8', 'com9',
    'lpt1', 'lpt2', 'lpt3', 'lpt4', 'lpt5', 'lpt6', 'lpt7', 'lpt8', 'lpt9',
}


def validate_project_id(project_id: str) -> str:
    """
    Validate project_id format and content.

    Rules:
    - Pattern: ^[a-zA-Z0-9_-]{3,64}$
    - Not reserved names
    - Not starting with: -, .

    Args:
        project_id: Project identifier to validate

    Returns:
        Validated project_id (stripped)

    Raises:
        ValidationError: If invalid
    """
    if not project_id:
        raise ValidationError("project_id is required")

    project_id = project_id.strip()

    if not VALID_PROJECT_ID.match(project_id):
        raise ValidationError(
            f"Invalid project_id format: must be 3-64 alphanumeric characters, "
            f"underscores, or hyphens. Got: {project_id!r}"
        )

    if project_id.startswith('-') or project_id.startswith('.'):
        raise ValidationError(
            f"project_id cannot start with '-' or '.'. Got: {project_id!r}"
        )

    if project_id.lower() in RESERVED_NAMES:
        raise ValidationError(
            f"project_id cannot be a reserved name. Got: {project_id!r}"
        )

    return project_id


def validate_filename(filename: str) -> str:
    """
    Validate and sanitize uploaded filename.

    Rules:
    - Pattern: ^[a-zA-Z0-9._-][a-zA-Z0-9._/-]{0,254}$
    - No path separators (backslash)
    - No null bytes or forbidden characters
    - No leading/trailing slashes
    - Not matching IGNORE_PATTERNS

    Args:
        filename: Filename to validate

    Returns:
        Validated filename

    Raises:
        ValidationError: If invalid
    """
    if not filename:
        raise ValidationError("filename is required")

    filename = filename.strip()

    # Normalize path separators to forward slash
    filename = filename.replace('\\', '/')

    # Remove leading/trailing slashes
    filename = filename.strip('/')

    if not filename:
        raise ValidationError("filename cannot be empty after normalization")

    # Check for forbidden patterns
    for pattern in FORBIDDEN_PATTERNS:
        if pattern in filename:
            raise SecurityError(
                f"Forbidden pattern in filename: {pattern!r}"
            )

    # Check regex pattern
    if not VALID_FILENAME.match(filename):
        raise ValidationError(
            f"Invalid filename format: {filename!r}"
        )

    # Check each path component
    for part in filename.split('/'):
        if not part:
            raise ValidationError("Empty path component in filename")

        if part.lower() in RESERVED_NAMES:
            raise ValidationError(
                f"Reserved name in path: {part!r}"
            )

        if part.startswith('.') and part not in ('.gitignore', '.gitattributes'):
            # Allow common dotfiles but reject hidden directories
            if '.' not in part[1:]:  # It's a hidden dir like .git
                raise ValidationError(
                    f"Hidden directory not allowed: {part!r}"
                )

    # Check against ignore patterns (secrets, credentials, etc.)
    if _matches_ignore_pattern(filename):
        raise ValidationError(
            f"File matches ignore pattern (secrets/credentials): {filename!r}"
        )

    return filename


def _matches_ignore_pattern(filename: str) -> bool:
    """Check if filename matches any IGNORE_PATTERNS."""
    path = Path(filename)

    for pattern in IGNORE_PATTERNS:
        # Check each part of the path
        for part in path.parts:
            if fnmatch.fnmatch(part, pattern):
                return True

        # Check full path
        if fnmatch.fnmatch(filename, pattern):
            return True

        # Check filename only
        if fnmatch.fnmatch(path.name, pattern):
            return True

    return False


def get_safe_staging_path(project_id: str, filename: str) -> Path:
    """
    Return validated path within staging/{project_id}/.

    Security:
    1. Validates project_id
    2. Validates filename
    3. Constructs path
    4. Resolves and verifies within staging root
    5. Checks for symlinks

    Args:
        project_id: Project identifier
        filename: Relative filename within staging

    Returns:
        Safe absolute Path within staging directory

    Raises:
        SecurityError: If path traversal detected
        ValidationError: If inputs invalid
    """
    # Validate inputs
    project_id = validate_project_id(project_id)
    filename = validate_filename(filename)

    settings = get_settings()
    staging_root = settings.data_dir / "staging"
    project_staging = staging_root / project_id

    # Construct target path
    target = project_staging / filename

    # Resolve to absolute path
    try:
        resolved = target.resolve()
    except (OSError, ValueError) as e:
        raise SecurityError(f"Invalid path: {e}")

    # Verify path is within project staging
    try:
        resolved.relative_to(project_staging.resolve())
    except ValueError:
        raise SecurityError(
            f"Path traversal detected: {filename!r} escapes staging directory"
        )

    # Check if any parent is a symlink (symlink attack prevention)
    current = target
    while current != staging_root:
        if current.is_symlink():
            raise SecurityError(
                f"Symlink detected in path: {current}"
            )
        current = current.parent
        if current == current.parent:  # Reached root
            break

    return resolved


def validate_vendor_id(vendor_id: str) -> str:
    """
    Validate vendor_id format.

    Args:
        vendor_id: Vendor identifier to validate

    Returns:
        Validated vendor_id (stripped)

    Raises:
        ValidationError: If invalid
    """
    if not vendor_id:
        raise ValidationError("vendor_id is required")

    vendor_id = vendor_id.strip()

    if len(vendor_id) < 1 or len(vendor_id) > 64:
        raise ValidationError(
            f"vendor_id must be 1-64 characters. Got {len(vendor_id)}"
        )

    return vendor_id


def validate_repo_url(repo_url: str) -> str:
    """
    Validate GitHub repository URL.

    Args:
        repo_url: Repository URL to validate

    Returns:
        Validated URL

    Raises:
        ValidationError: If invalid
    """
    if not repo_url:
        raise ValidationError("repo_url is required")

    repo_url = repo_url.strip()

    # Must be HTTPS GitHub URL
    if not repo_url.startswith('https://github.com/'):
        raise ValidationError(
            "repo_url must be an HTTPS GitHub URL (https://github.com/...)"
        )

    # Basic format check
    parts = repo_url.replace('https://github.com/', '').rstrip('/').split('/')
    if len(parts) < 2:
        raise ValidationError(
            "repo_url must include owner and repo name"
        )

    return repo_url


def validate_snapshot_type(snapshot_type: str) -> str:
    """
    Validate snapshot type is one of the 12 valid types.

    Args:
        snapshot_type: Snapshot type to validate

    Returns:
        Validated snapshot type

    Raises:
        ValidationError: If invalid
    """
    valid_types = {
        'file_metadata', 'imports', 'exports', 'functions', 'classes',
        'connections', 'repo_metadata', 'security', 'quality',
        'doc_metadata', 'doc_content', 'doc_analysis'
    }

    if not snapshot_type:
        raise ValidationError("snapshot_type is required")

    snapshot_type = snapshot_type.strip().lower()

    if snapshot_type not in valid_types:
        raise ValidationError(
            f"Invalid snapshot_type: {snapshot_type!r}. "
            f"Must be one of: {', '.join(sorted(valid_types))}"
        )

    return snapshot_type
