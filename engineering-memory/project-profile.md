# Project Profile

Project name: Argus.
Primary language/framework: Python 3.12+ with FastMCP, Starlette, LiteLLM, feedparser, requests, jieba, rank-bm25, and SQLite.
Runtime: Local macOS-first CLI/MCP runtime, with stdio or HTTP FastMCP server, Starlette dashboard, launchd scheduling, optional Docker files, and optional S3-compatible remote storage.
Test command: `uv run python -m unittest discover -s tests`.
Build command: `uv build`.
Lint/typecheck command: No dedicated project command is configured yet; use targeted syntax checks and tests until a linter/type checker is added.
Package manager: uv, with dependencies declared in `pyproject.toml` and locked in `uv.lock`.

## Product Goal
Provide a personal intelligence hub on top of TrendRadar: aggregate hotlists/RSS/social sources, expose agent-friendly MCP tools, support local semantic search, cross-platform narrative tracking, scheduling, notifications, research workflows, and a web dashboard.

## Engineering Goal
Keep Argus useful as a local, agent-native toolkit while preserving upstream TrendRadar behavior. Favor simple dependency choices, explicit safety checks for filesystem/CLI operations, and test-backed changes around MCP tool behavior, storage, scheduling, and external adapters.

## Critical Flows
- CLI crawl/analyze/push flow through `argus.__main__`, `argus.core`, `argus.crawler`, `argus.storage`, `argus.ai`, and `argus.notification`.
- FastMCP tool registration and dispatch through `argus_server/server.py` and `argus_server/tools/`.
- Local and optional remote storage through SQLite schemas, `StorageManager`, local backend, remote backend, and parser services.
- RSS and external API ingestion, including RSSHub-backed sources and no-key public APIs.
- Research toolkit flow: crawl URL, discover page images, safe gallery-dl dry-run/execution, and cross-source topic normalization.
- Scheduler workflow flow: MCP schedule tools write launchd plist/workflow files and execute through `argus_server/scheduler_runner.py`.
- Web dashboard flow through `argus/web/app.py` REST/SSE endpoints.
- Notification and bot flow through webhook senders, router, daily brief, and `argus_server/feishu_bot.py`.

## High-Risk Areas
- `argus_server/server.py` has a large MCP surface; adding or renaming tools can break clients and documentation.
- Storage schema or backend changes can affect deduplication, crawl history, RSS state, AI filter records, and remote sync.
- Filesystem and subprocess wrappers such as scheduler, gallery-dl, and CLI tools need path validation and safe defaults.
- AI/search integrations depend on optional environment variables and should degrade clearly when keys are missing.
- `docs/HANDOFF.md` may lag behind README/source for tool counts and completed roadmap items.
- Optional external CLIs and services are environment-sensitive: RSSHub, bili/xhs/twitter/tg/discord CLIs, gallery-dl, and Cloudflare Tunnel.
