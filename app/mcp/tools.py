# app/mcp/tools.py
"""
MCP tool handler implementations.

Each function wraps existing SNAP functionality and returns
JSON-serializable results for MCP responses.
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime

from app.mcp.security import (
    validate_project_id,
    validate_vendor_id,
    validate_repo_url,
    validate_filename,
    validate_snapshot_type,
    get_safe_staging_path,
    SecurityError,
    ValidationError,
)
from app.config.settings import get_settings
from app.logging.logger import get_logger
from app.ingest.local_loader import (
    get_project_staging_path,
    delete_project_staging,
    IGNORE_PATTERNS,
)

logger = get_logger("mcp.tools")


class ToolError(Exception):
    """Raised when a tool execution fails."""
    pass


# =============================================================================
# Core Tools
# =============================================================================

async def handle_process_github_repo(
    repo_url: str,
    project_id: str,
    vendor_id: str,
    branch: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Clone and analyze a GitHub repository.

    Args:
        repo_url: GitHub repository URL (https://github.com/owner/repo)
        project_id: Unique project identifier
        vendor_id: Vendor/caller identifier for audit
        branch: Optional branch to clone (default: default branch)

    Returns:
        Processing manifest with stats
    """
    # Validate inputs
    project_id = validate_project_id(project_id)
    vendor_id = validate_vendor_id(vendor_id)
    repo_url = validate_repo_url(repo_url)

    logger.info("MCP tool: process_github_repo", extra={
        "project_id": project_id,
        "vendor_id": vendor_id,
        "repo_url": repo_url,
        "branch": branch,
    })

    # Import here to avoid circular imports and ensure startup() was called
    from app.main import process_project, startup

    startup()

    try:
        manifest = process_project(
            project_id=project_id,
            vendor_id=vendor_id,
            repo_url=repo_url,
        )

        return {
            "status": "completed",
            "project_id": project_id,
            "manifest": manifest,
        }

    except Exception as e:
        logger.error(f"process_github_repo failed: {e}", extra={
            "project_id": project_id,
            "error": str(e),
        })
        raise ToolError(f"Failed to process repository: {e}")


async def handle_process_local_project(
    project_id: str,
    vendor_id: str,
) -> Dict[str, Any]:
    """
    Analyze files previously uploaded to project staging.

    Args:
        project_id: Project identifier (files must be in staging/{project_id}/)
        vendor_id: Vendor/caller identifier for audit

    Returns:
        Processing manifest with stats
    """
    project_id = validate_project_id(project_id)
    vendor_id = validate_vendor_id(vendor_id)

    logger.info("MCP tool: process_local_project", extra={
        "project_id": project_id,
        "vendor_id": vendor_id,
    })

    from app.main import process_project, startup

    startup()

    staging_path = get_project_staging_path(project_id)

    # Check staging has files
    files = list(staging_path.rglob("*"))
    files = [f for f in files if f.is_file()]

    if not files:
        raise ToolError(
            f"No files in staging area. Upload files first using upload_to_staging."
        )

    try:
        manifest = process_project(
            project_id=project_id,
            vendor_id=vendor_id,
            local_path=staging_path,
        )

        return {
            "status": "completed",
            "project_id": project_id,
            "files_processed": len(files),
            "manifest": manifest,
        }

    except Exception as e:
        logger.error(f"process_local_project failed: {e}", extra={
            "project_id": project_id,
            "error": str(e),
        })
        raise ToolError(f"Failed to process local project: {e}")


async def handle_get_project_notebook(
    project_id: str,
    vendor_id: str,
) -> Dict[str, Any]:
    """
    Retrieve complete analysis notebook for a project.

    Args:
        project_id: Project identifier
        vendor_id: Vendor/caller identifier for audit

    Returns:
        Complete project notebook with all snapshots
    """
    project_id = validate_project_id(project_id)
    vendor_id = validate_vendor_id(vendor_id)

    logger.info("MCP tool: get_project_notebook", extra={
        "project_id": project_id,
        "vendor_id": vendor_id,
    })

    from app.main import get_project_notebook, startup

    startup()

    try:
        notebook = get_project_notebook(project_id, vendor_id)

        return {
            "status": "success",
            "project_id": project_id,
            "notebook": notebook,
        }

    except Exception as e:
        logger.error(f"get_project_notebook failed: {e}", extra={
            "project_id": project_id,
            "error": str(e),
        })
        raise ToolError(f"Failed to retrieve notebook: {e}")


async def handle_delete_project(
    project_id: str,
) -> Dict[str, Any]:
    """
    Delete a project and all its snapshots.

    Args:
        project_id: Project identifier

    Returns:
        Deletion confirmation
    """
    project_id = validate_project_id(project_id)

    logger.info("MCP tool: delete_project", extra={
        "project_id": project_id,
    })

    from app.main import delete_project, startup

    startup()

    try:
        delete_project(project_id)

        # Also clean up staging
        delete_project_staging(project_id)

        return {
            "status": "deleted",
            "project_id": project_id,
            "message": f"Project {project_id} and all snapshots deleted",
        }

    except Exception as e:
        logger.error(f"delete_project failed: {e}", extra={
            "project_id": project_id,
            "error": str(e),
        })
        raise ToolError(f"Failed to delete project: {e}")


# =============================================================================
# Staging Tools (Secure)
# =============================================================================

async def handle_get_staging_info(
    project_id: str,
) -> Dict[str, Any]:
    """
    Get staging path and list files for a project.

    Args:
        project_id: Project identifier

    Returns:
        Staging info including path and file list
    """
    project_id = validate_project_id(project_id)

    logger.info("MCP tool: get_staging_info", extra={
        "project_id": project_id,
    })

    staging_path = get_project_staging_path(project_id)

    files = []
    total_size = 0

    for path in staging_path.rglob("*"):
        if path.is_file() and not path.is_symlink():
            try:
                stat = path.stat()
                rel_path = path.relative_to(staging_path)
                files.append({
                    "name": str(rel_path),
                    "size": stat.st_size,
                    "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                })
                total_size += stat.st_size
            except (OSError, ValueError):
                continue

    return {
        "status": "success",
        "project_id": project_id,
        "staging_path": f"staging/{project_id}",
        "files": files,
        "file_count": len(files),
        "total_size_bytes": total_size,
    }


async def handle_upload_to_staging(
    project_id: str,
    filename: str,
    content: str,
    encoding: str = "utf-8",
) -> Dict[str, Any]:
    """
    Upload file content to project staging area.

    Args:
        project_id: Project identifier
        filename: Relative filename (can include subdirectories like "src/main.py")
        content: File content (text or base64-encoded binary)
        encoding: Content encoding - "utf-8" for text, "base64" for binary

    Returns:
        Upload confirmation with file path
    """
    project_id = validate_project_id(project_id)
    filename = validate_filename(filename)

    logger.info("MCP tool: upload_to_staging", extra={
        "project_id": project_id,
        "filename": filename,
        "encoding": encoding,
    })

    # Get safe path (validates and prevents traversal)
    safe_path = get_safe_staging_path(project_id, filename)

    # Decode content
    if encoding == "base64":
        try:
            file_content = base64.b64decode(content)
        except Exception as e:
            raise ValidationError(f"Invalid base64 content: {e}")
    elif encoding == "utf-8":
        file_content = content.encode("utf-8")
    else:
        raise ValidationError(f"Invalid encoding: {encoding}. Use 'utf-8' or 'base64'")

    # Check file size limits
    settings = get_settings()
    max_size = settings.limits.max_code_file_bytes

    if len(file_content) > max_size:
        raise ValidationError(
            f"File too large: {len(file_content)} bytes. Max: {max_size} bytes"
        )

    # Create parent directories and write file
    safe_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(safe_path, "wb") as f:
            f.write(file_content)
    except OSError as e:
        raise ToolError(f"Failed to write file: {e}")

    return {
        "status": "uploaded",
        "project_id": project_id,
        "filename": filename,
        "path": str(safe_path.relative_to(settings.data_dir)),
        "size": len(file_content),
    }


async def handle_clear_staging(
    project_id: str,
) -> Dict[str, Any]:
    """
    Clear all files from project staging area.

    Args:
        project_id: Project identifier

    Returns:
        Deletion confirmation
    """
    project_id = validate_project_id(project_id)

    logger.info("MCP tool: clear_staging", extra={
        "project_id": project_id,
    })

    staging_path = get_project_staging_path(project_id)

    # Count files before deletion
    files = list(staging_path.rglob("*"))
    file_count = len([f for f in files if f.is_file()])

    delete_project_staging(project_id)

    return {
        "status": "cleared",
        "project_id": project_id,
        "files_deleted": file_count,
    }


# =============================================================================
# Query Tools
# =============================================================================

async def handle_get_project_manifest(
    project_id: str,
) -> Dict[str, Any]:
    """
    Get processing statistics for a project.

    Args:
        project_id: Project identifier

    Returns:
        Project manifest with processing stats
    """
    project_id = validate_project_id(project_id)

    logger.info("MCP tool: get_project_manifest", extra={
        "project_id": project_id,
    })

    from app.main import get_project_manifest, startup

    startup()

    try:
        manifest = get_project_manifest(project_id)

        return {
            "status": "success",
            "project_id": project_id,
            "manifest": manifest,
        }

    except Exception as e:
        logger.error(f"get_project_manifest failed: {e}", extra={
            "project_id": project_id,
            "error": str(e),
        })
        raise ToolError(f"Failed to retrieve manifest: {e}")


async def handle_query_snapshots(
    project_id: str,
    snapshot_type: Optional[str] = None,
    file_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Query snapshots by type or file.

    Args:
        project_id: Project identifier
        snapshot_type: Optional filter by snapshot type (e.g., "security", "imports")
        file_path: Optional filter by source file path

    Returns:
        List of matching snapshots
    """
    project_id = validate_project_id(project_id)

    if snapshot_type:
        snapshot_type = validate_snapshot_type(snapshot_type)

    logger.info("MCP tool: query_snapshots", extra={
        "project_id": project_id,
        "snapshot_type": snapshot_type,
        "file_path": file_path,
    })

    from app.main import startup
    from app.storage.snapshot_repo import SnapshotRepository

    startup()

    repo = SnapshotRepository()

    try:
        if file_path and snapshot_type:
            # Get specific snapshot for file and type
            snapshots = repo.get_by_file(project_id, file_path)
            snapshots = [s for s in snapshots if s.snapshot_type == snapshot_type]
        elif file_path:
            # Get all snapshots for file
            snapshots = repo.get_by_file(project_id, file_path)
        elif snapshot_type:
            # Get all snapshots of type
            snapshots = repo.get_by_type(project_id, snapshot_type)
        else:
            # Get all project snapshots
            snapshots = repo.get_by_project(project_id)

        # Convert to dicts
        result = []
        for s in snapshots:
            result.append({
                "snapshot_id": s.snapshot_id,
                "snapshot_type": s.snapshot_type,
                "source_file": s.source_file,
                "field_values": s.field_values,
                "created_at": s.created_at.isoformat(),
            })

        return {
            "status": "success",
            "project_id": project_id,
            "filters": {
                "snapshot_type": snapshot_type,
                "file_path": file_path,
            },
            "count": len(result),
            "snapshots": result,
        }

    except Exception as e:
        logger.error(f"query_snapshots failed: {e}", extra={
            "project_id": project_id,
            "error": str(e),
        })
        raise ToolError(f"Failed to query snapshots: {e}")


async def handle_get_system_metrics() -> Dict[str, Any]:
    """
    Get overall system metrics.

    Returns:
        System-wide metrics including project counts, snapshot stats, etc.
    """
    logger.info("MCP tool: get_system_metrics")

    from app.main import get_metrics, startup

    startup()

    try:
        metrics = get_metrics()

        return {
            "status": "success",
            "metrics": metrics,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }

    except Exception as e:
        logger.error(f"get_system_metrics failed: {e}")
        raise ToolError(f"Failed to retrieve metrics: {e}")
