# SNAP - MCP Server

**S**napshot **N**otebook **A**nalysis **P**ipeline

> Multi-snapshot RAG system exposing code analysis via Model Context Protocol (MCP). Categorizes code, documents, and data into 14 snapshot types for targeted AI retrieval.

---

## Table of Contents

- [Features](#features)
- [File Structure](#file-structure)
- [Quick Start](#quick-start)
- [MCP Server Setup](#mcp-server-setup)
- [Available MCP Tools](#available-mcp-tools)
- [Snapshot Types](#snapshot-types)
- [Configuration](#configuration)
- [Architecture](#architecture)
- [Security](#security)
- [Requirements](#requirements)

---

## Features

- **14 Categorized Snapshot Types** - Fine-grained code, document, and data analysis
- **Multi-Parser Pipeline** - tree-sitter, semgrep, text extraction, CSV parsing
- **MCP Protocol Support** - Stdio mode for Claude Code, HTTP+SSE for remote clients
- **14+ Languages** - Python, TypeScript, JavaScript, Java, Go, Rust, C/C++, C#, Ruby, PHP, Swift, Kotlin, Scala
- **Security Analysis** - Vulnerabilities, secrets detection, SQL injection, XSS risks
- **CSV Schema Inference** - Automatic type detection, stats, and data profiling
- **Per-Project Isolation** - No global state, cascading deletion

---

## File Structure

```
snap/
├── app/
│   ├── config/
│   │   └── settings.py              # Pydantic settings & validation
│   ├── extraction/
│   │   ├── field_mapper.py          # Maps parser output to 14 snapshot types
│   │   └── snapshot_builder.py      # Creates snapshot records with UUIDs
│   ├── ingest/
│   │   ├── file_router.py           # Routes files to appropriate parsers
│   │   ├── github_cloner.py         # Git clone with timeout & network policy
│   │   └── local_loader.py          # Ingest from staging with security filtering
│   ├── logging/
│   │   └── logger.py                # Structured logging (stderr for MCP)
│   ├── mcp/
│   │   ├── __init__.py
│   │   ├── run.py                   # Entry point: stdio or HTTP+SSE mode
│   │   ├── security.py              # Input validation, path traversal prevention
│   │   ├── server.py                # MCP server with 10 tools
│   │   └── tools.py                 # Tool handler implementations
│   ├── parsers/
│   │   ├── csv_parser.py            # CSV/TSV parsing with schema inference
│   │   ├── semgrep_parser.py        # Security & quality analysis
│   │   ├── text_extractor.py        # PDF/document extraction
│   │   └── tree_sitter_parser.py    # AST parsing for 14 languages
│   ├── schemas/
│   │   ├── master_notebook.yaml     # Field definitions & parser mappings
│   │   └── snapshot_templates/      # JSON templates for 14 snapshot types
│   │       ├── classes.json
│   │       ├── connections.json
│   │       ├── csv_data.json        # Raw CSV table data
│   │       ├── csv_schema.json      # CSV schema & statistics
│   │       ├── doc_analysis.json
│   │       ├── doc_content.json
│   │       ├── doc_metadata.json
│   │       ├── exports.json
│   │       ├── file_metadata.json
│   │       ├── functions.json
│   │       ├── imports.json
│   │       ├── quality.json
│   │       ├── repo_metadata.json
│   │       └── security.json
│   ├── security/
│   │   ├── network_policy.py        # Domain allowlist enforcement
│   │   └── sandbox_limits.py        # File size & LOC limits
│   ├── storage/
│   │   ├── db.py                    # PostgreSQL connection pooling
│   │   └── snapshot_repo.py         # CRUD with project isolation
│   ├── dashboard.py                 # Web dashboard for metrics
│   └── main.py                      # Orchestration pipeline
├── staging/                         # Upload staging area (per-project)
├── repos/                           # Cloned repositories (per-project)
├── run_mcp.bat                      # Windows wrapper for MCP server
├── docker-compose.yml               # PostgreSQL setup
├── pyproject.toml                   # Dependencies
├── requirements.txt
└── README.md
```

---

## Quick Start

### 1. Install Dependencies

```bash
# Create virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/Mac

# Install requirements
pip install -r requirements.txt

# Optional: Install semgrep for security analysis
pip install semgrep
```

### 2. Setup PostgreSQL

```bash
# Using Docker
docker-compose up -d postgres

# Or set SANDBOX_POSTGRES_DSN to your PostgreSQL instance
```

### 3. Configure Environment

```bash
cp .env.template .env
# Edit .env with your settings
```

### 4. Run Dashboard (Optional)

```bash
python -m app.dashboard
# Open http://localhost:5000
```

---

## MCP Server Setup

### Claude Code (VS Code / CLI)

**Option 1: Using Claude CLI**

```bash
# Install Claude CLI
npm install -g @anthropic-ai/claude-code

# Add SNAP MCP server (use the wrapper script)
claude mcp add snap --scope user "C:\Users\<username>\snap\run_mcp.bat"

# Verify connection
claude mcp list
```

**Option 2: Manual Configuration**

Edit `~/.claude.json`:

```json
{
  "mcpServers": {
    "snap": {
      "type": "stdio",
      "command": "C:\\Users\\<username>\\snap\\run_mcp.bat",
      "args": [],
      "env": {}
    }
  }
}
```

### Claude Desktop

Create/edit `%APPDATA%\Claude\claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "snap": {
      "command": "C:\\Users\\<username>\\snap\\run_mcp.bat",
      "args": []
    }
  }
}
```

Restart Claude Desktop to connect.

### HTTP+SSE Mode (Remote Clients)

```bash
python -m app.mcp.run --sse --host 0.0.0.0 --port 8080
```

Endpoints:
- `GET /sse` - Server-Sent Events connection
- `POST /messages/` - MCP messages
- `GET /health` - Health check

---

## Available MCP Tools

| Tool | Description |
|------|-------------|
| `process_github_repo` | Clone and analyze a GitHub repository |
| `process_local_project` | Analyze files from staging area |
| `upload_to_staging` | Upload a file to project staging |
| `get_staging_info` | List uploaded files with metadata |
| `clear_staging` | Delete all files in staging |
| `get_project_notebook` | Retrieve complete project analysis |
| `query_snapshots` | Query by snapshot type or file path |
| `get_project_manifest` | Get processing statistics |
| `delete_project` | Delete project and all snapshots |
| `get_system_metrics` | System-wide aggregated metrics |

### Example Usage

```
# In Claude Code chat:
> Analyze the repository https://github.com/user/repo

# Claude will use process_github_repo, then query_snapshots to retrieve:
# - Security vulnerabilities
# - Import dependencies
# - Function signatures
# - Class hierarchies
```

---

## Snapshot Types

### Code Analysis (7 types)

| Type | Parser | Description |
|------|--------|-------------|
| `file_metadata` | tree_sitter | Path, language, LOC, package info |
| `imports` | tree_sitter | External/internal modules, dependencies |
| `exports` | tree_sitter | Functions, classes, constants, types |
| `functions` | tree_sitter | Names, signatures, async status, decorators |
| `classes` | tree_sitter | Names, inheritance, methods, properties |
| `connections` | tree_sitter | Dependencies, function calls, instantiations |
| `repo_metadata` | tree_sitter | Primary language, entrypoints, CI pipeline |

### Security & Quality (2 types)

| Type | Parser | Description |
|------|--------|-------------|
| `security` | semgrep | Vulnerabilities, secrets, SQL injection, XSS |
| `quality` | semgrep | Antipatterns, code smells, TODOs, deprecated |

### Documents (3 types)

| Type | Parser | Description |
|------|--------|-------------|
| `doc_metadata` | text_extractor | Title, author, creation date, word count |
| `doc_content` | text_extractor | Extracted text, key concepts, code examples |
| `doc_analysis` | text_extractor | Requirements, decisions, risks, assumptions |

### CSV/Data (2 types)

| Type | Parser | Description |
|------|--------|-------------|
| `csv_data` | csv_parser | Raw table data: headers, rows, row_count |
| `csv_schema` | csv_parser | Schema inference, column types, stats, sample rows |

**CSV Schema Fields:**
- `csv.schema.column_names` - List of column headers
- `csv.schema.column_types` - Inferred types (string, integer, float, boolean, date, email, url, array)
- `csv.stats.null_counts` - Empty/null values per column
- `csv.stats.unique_counts` - Unique values per column
- `csv.sample.first_rows` - First 5 rows as preview

---

## Configuration

Environment variables (prefix: `SANDBOX_`):

| Variable | Default | Description |
|----------|---------|-------------|
| `SANDBOX_POSTGRES_DSN` | *required* | PostgreSQL connection string |
| `SANDBOX_DATA_DIR` | `data/` | Base data directory |
| `SANDBOX_REPOS_DIR` | `data/repos/` | Cloned repositories |
| `SANDBOX_UPLOADS_DIR` | `data/uploads/` | Upload staging |
| `SANDBOX_LOG_LEVEL` | `INFO` | Logging level |
| `SANDBOX_LOG_JSON` | `true` | JSON-formatted logs |

### Parser Limits

| Variable | Default | Description |
|----------|---------|-------------|
| `SANDBOX_PARSER_LIMITS_SOFT_CAP_LOC` | 1,500 | Warning threshold |
| `SANDBOX_PARSER_LIMITS_POTENTIAL_GOD_LOC` | 4,000 | God file threshold |
| `SANDBOX_PARSER_LIMITS_HARD_CAP_LOC` | 5,000 | Reject threshold |

### File Size Limits

| Variable | Default | Description |
|----------|---------|-------------|
| `SANDBOX_LIMITS_MAX_CODE_FILE_BYTES` | 5 MB | Max code file size |
| `SANDBOX_LIMITS_MAX_REPO_BYTES` | 2 GB | Max repository size |
| `SANDBOX_LIMITS_MAX_PDF_BYTES` | 50 MB | Max PDF size |

### CSV Limits

| Variable | Default | Description |
|----------|---------|-------------|
| `CSV_HARD_CAP_FILE_SIZE_MB` | 50 MB | Max CSV file size |
| `CSV_HARD_CAP_ROWS` | 500,000 | Max rows per file |
| `CSV_HARD_CAP_CELL_CHARS` | 5,000 | Max characters per cell |

---

## Architecture

### Parser Pipeline

| Parser | File Types | Output Fields | Snapshot Types |
|--------|------------|---------------|----------------|
| tree_sitter | .py, .js, .ts, .java, .go, .rs, etc. | `code.*` | file_metadata, imports, exports, functions, classes, connections |
| semgrep | .py, .js, .ts, .java, .go, .rs, etc. | `code.security.*`, `code.quality.*` | security, quality |
| text_extractor | .pdf, .txt, .md, .docx, .html | `doc.*` | doc_metadata, doc_content, doc_analysis |
| csv_parser | .csv, .tsv | `csv.*` | csv_data, csv_schema |

### Pipeline Flow

```
Upload/Clone
    ↓
staging/{project_id}/
    ↓
file_router (determine parsers)
    ↓
┌──────────────────────────────────────────────┐
│  tree_sitter   semgrep   text_extractor  csv │
│  (AST parse)  (security)    (docs)      (data)│
└──────────────────────────────────────────────┘
    ↓
field_mapper (categorize into 14 types)
    ↓
snapshot_builder (create with UUIDs)
    ↓
snapshot_repo (PostgreSQL)
    ↓
Query: project_id + snapshot_type
```

### File Categorization

| Category | LOC Range | Action |
|----------|-----------|--------|
| normal | < 1,500 | Process normally |
| large | 1,500-3,999 | Process + warn |
| potential_god | 4,000-4,999 | Process + log warning |
| rejected | >= 5,000 | Skip (exceeds limit) |

---

## Security

### Input Validation
- **Project ID**: `^[a-zA-Z0-9_-]{3,64}$`
- **Filenames**: No path traversal (`..`, `\x00`, `~`)
- **Repo URLs**: HTTPS GitHub URLs only

### Automatic Filtering

Ignored during ingestion:
- `.git`, `.venv`, `node_modules`
- `.env`, `.env.*`, credentials files
- `*.pem`, `*.key`, `.ssh`, `.aws`
- IDE files: `.vscode`, `.idea`
- Build artifacts: `__pycache__`, `.pytest_cache`

### Project Isolation
- Each project isolated to `staging/{project_id}/`
- Symlinks rejected during ingestion
- Delete project cascades to all snapshots

---

## Requirements

| Dependency | Version | Purpose |
|------------|---------|---------|
| Python | 3.11+ | Runtime |
| PostgreSQL | 14+ | Snapshot storage |
| mcp | >= 1.0.0 | Model Context Protocol |
| tree-sitter | >= 0.20.0 | AST parsing |
| semgrep | >= 1.50.0 | Security analysis (optional) |
| pydantic | >= 2.0.0 | Validation |
| sqlalchemy | >= 2.0.0 | ORM |
| starlette | >= 0.27.0 | HTTP+SSE transport |

---

## Troubleshooting

### MCP Server Won't Connect

1. **Check logs go to stderr** (not stdout):
   ```python
   # app/logging/logger.py line 54
   handler = logging.StreamHandler(sys.stderr)  # Must be stderr
   ```

2. **Use wrapper script** (cwd not respected by Claude Code):
   ```batch
   # run_mcp.bat
   @echo off
   cd /d C:\Users\<username>\snap
   "C:\Users\<username>\snap\.venv\Scripts\python.exe" -m app.mcp.run %*
   ```

3. **Verify connection**:
   ```bash
   claude mcp list
   # Should show: snap: ... - ✓ Connected
   ```

### Missing postgres_dsn Error

Set the environment variable or create `.env`:
```
SANDBOX_POSTGRES_DSN=postgresql://user:pass@localhost:5432/snap
```

### Semgrep Not Found

Security scanning is optional. Install with:
```bash
pip install semgrep
```

---

## License

Open Source

---

## Contributing

1. Fork the repository
2. Create a feature branch
3. Run tests: `pytest`
4. Submit a pull request
