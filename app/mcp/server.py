# app/mcp/server.py
"""
MCP Server definition for SNAP.

Exposes SNAP's code analysis functionality as MCP tools using
the official mcp Python SDK with HTTP+SSE transport.
"""

from __future__ import annotations

import json

from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import Tool, TextContent
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.responses import JSONResponse
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware

from app.mcp.tools import (
    handle_process_github_repo,
    handle_process_local_project,
    handle_get_project_notebook,
    handle_delete_project,
    handle_get_staging_info,
    handle_upload_to_staging,
    handle_clear_staging,
    handle_get_project_manifest,
    handle_query_snapshots,
    handle_get_system_metrics,
    ToolError,
)
from app.mcp.security import SecurityError, ValidationError
from app.logging.logger import get_logger
from app.config.settings import get_settings

logger = get_logger("mcp.server")

# Create MCP server instance
server = Server("snap-mcp")


# =============================================================================
# Tool Definitions
# =============================================================================

@server.list_tools()
async def list_tools() -> list[Tool]:
    """Return list of available MCP tools."""
    return [
        Tool(
            name="process_github_repo",
            description="Clone and analyze a GitHub repository. Creates snapshots for all code files with imports, exports, functions, classes, security issues, and more.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_url": {
                        "type": "string",
                        "description": "GitHub repository URL (https://github.com/owner/repo)",
                    },
                    "project_id": {
                        "type": "string",
                        "description": "Unique project identifier (3-64 alphanumeric chars, underscores, hyphens)",
                    },
                    "vendor_id": {
                        "type": "string",
                        "description": "Your identifier for audit logging",
                    },
                    "branch": {
                        "type": "string",
                        "description": "Optional branch to clone (default: default branch)",
                    },
                },
                "required": ["repo_url", "project_id", "vendor_id"],
            },
        ),
        Tool(
            name="process_local_project",
            description="Analyze files previously uploaded to project staging area. Use upload_to_staging first to upload files.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "Project identifier (must have files in staging)",
                    },
                    "vendor_id": {
                        "type": "string",
                        "description": "Your identifier for audit logging",
                    },
                },
                "required": ["project_id", "vendor_id"],
            },
        ),
        Tool(
            name="get_project_notebook",
            description="Retrieve the complete analysis notebook for a project, including all snapshots organized by type and file.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "Project identifier",
                    },
                    "vendor_id": {
                        "type": "string",
                        "description": "Your identifier for audit logging",
                    },
                },
                "required": ["project_id", "vendor_id"],
            },
        ),
        Tool(
            name="delete_project",
            description="Delete a project and all its snapshots. This is irreversible.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "Project identifier to delete",
                    },
                },
                "required": ["project_id"],
            },
        ),
        Tool(
            name="get_staging_info",
            description="Get information about the staging area for a project, including list of uploaded files.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "Project identifier",
                    },
                },
                "required": ["project_id"],
            },
        ),
        Tool(
            name="upload_to_staging",
            description="Upload a file to the project staging area. Use this before process_local_project.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "Project identifier",
                    },
                    "filename": {
                        "type": "string",
                        "description": "Relative filename (e.g., 'main.py' or 'src/utils.py')",
                    },
                    "content": {
                        "type": "string",
                        "description": "File content (text or base64-encoded)",
                    },
                    "encoding": {
                        "type": "string",
                        "enum": ["utf-8", "base64"],
                        "description": "Content encoding: 'utf-8' for text, 'base64' for binary",
                        "default": "utf-8",
                    },
                },
                "required": ["project_id", "filename", "content"],
            },
        ),
        Tool(
            name="clear_staging",
            description="Clear all files from the project staging area.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "Project identifier",
                    },
                },
                "required": ["project_id"],
            },
        ),
        Tool(
            name="get_project_manifest",
            description="Get processing statistics for a project (files processed, snapshots created, etc.).",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "Project identifier",
                    },
                },
                "required": ["project_id"],
            },
        ),
        Tool(
            name="query_snapshots",
            description="Query snapshots by type or file. Use to find specific information like 'all security issues' or 'imports for main.py'.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "Project identifier",
                    },
                    "snapshot_type": {
                        "type": "string",
                        "enum": [
                            "file_metadata", "imports", "exports", "functions",
                            "classes", "connections", "repo_metadata", "security",
                            "quality", "doc_metadata", "doc_content", "doc_analysis"
                        ],
                        "description": "Filter by snapshot type",
                    },
                    "file_path": {
                        "type": "string",
                        "description": "Filter by source file path",
                    },
                },
                "required": ["project_id"],
            },
        ),
        Tool(
            name="get_system_metrics",
            description="Get overall system metrics including total projects, files processed, and snapshot statistics.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls from MCP clients."""
    logger.info("MCP tool call: %s", name, extra={"arguments": arguments})

    try:
        if name == "process_github_repo":
            result = await handle_process_github_repo(
                repo_url=arguments["repo_url"],
                project_id=arguments["project_id"],
                vendor_id=arguments["vendor_id"],
                branch=arguments.get("branch"),
            )

        elif name == "process_local_project":
            result = await handle_process_local_project(
                project_id=arguments["project_id"],
                vendor_id=arguments["vendor_id"],
            )

        elif name == "get_project_notebook":
            result = await handle_get_project_notebook(
                project_id=arguments["project_id"],
                vendor_id=arguments["vendor_id"],
            )

        elif name == "delete_project":
            result = await handle_delete_project(
                project_id=arguments["project_id"],
            )

        elif name == "get_staging_info":
            result = await handle_get_staging_info(
                project_id=arguments["project_id"],
            )

        elif name == "upload_to_staging":
            result = await handle_upload_to_staging(
                project_id=arguments["project_id"],
                filename=arguments["filename"],
                content=arguments["content"],
                encoding=arguments.get("encoding", "utf-8"),
            )

        elif name == "clear_staging":
            result = await handle_clear_staging(
                project_id=arguments["project_id"],
            )

        elif name == "get_project_manifest":
            result = await handle_get_project_manifest(
                project_id=arguments["project_id"],
            )

        elif name == "query_snapshots":
            result = await handle_query_snapshots(
                project_id=arguments["project_id"],
                snapshot_type=arguments.get("snapshot_type"),
                file_path=arguments.get("file_path"),
            )

        elif name == "get_system_metrics":
            result = await handle_get_system_metrics()

        else:
            return [TextContent(
                type="text",
                text=json.dumps({"error": f"Unknown tool: {name}"}),
            )]

        return [TextContent(
            type="text",
            text=json.dumps(result, indent=2, default=str),
        )]

    except ValidationError as e:
        logger.warning("Validation error in %s: %s", name, e)
        return [TextContent(
            type="text",
            text=json.dumps({"error": "validation_error", "message": str(e)}),
        )]

    except SecurityError as e:
        logger.error("Security error in %s: %s", name, e)
        return [TextContent(
            type="text",
            text=json.dumps({"error": "security_error", "message": str(e)}),
        )]

    except ToolError as e:
        logger.error("Tool error in %s: %s", name, e)
        return [TextContent(
            type="text",
            text=json.dumps({"error": "tool_error", "message": str(e)}),
        )]

    except Exception as e:
        logger.exception("Unexpected error in %s: %s", name, e)
        return [TextContent(
            type="text",
            text=json.dumps({"error": "internal_error", "message": str(e)}),
        )]


# =============================================================================
# HTTP+SSE Transport
# =============================================================================

def create_app() -> Starlette:
    """
    Create Starlette application with MCP SSE transport.

    Returns:
        Configured Starlette app ready to serve MCP over HTTP+SSE
    """
    sse_transport = SseServerTransport("/messages/")

    async def handle_sse(request):
        """Handle SSE connection for MCP protocol."""
        async with sse_transport.connect_sse(
            request.scope,
            request.receive,
            request._send,
        ) as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options(),
            )

    async def handle_messages(request):
        """Handle POST messages for MCP protocol."""
        return await sse_transport.handle_post_message(
            request.scope,
            request.receive,
            request._send,
        )

    async def health_check(_request):
        """Health check endpoint."""
        return JSONResponse({
            "status": "healthy",
            "service": "snap-mcp",
            "version": "1.0.0",
        })

    # Configure CORS middleware
    settings = get_settings()
    origins = settings.cors_allowed_origins or ["*"]
    middleware = [
        Middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=origins != ["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )
    ]

    app = Starlette(
        debug=False,
        routes=[
            Route("/health", health_check, methods=["GET"]),
            Route("/sse", handle_sse, methods=["GET"]),
            Route("/messages/", handle_messages, methods=["POST"]),
        ],
        middleware=middleware,
    )

    return app
