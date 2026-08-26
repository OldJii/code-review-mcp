"""
Code Review MCP Server.

Main MCP server implementation using the official MCP SDK.
Supports stdio, SSE, and WebSocket transports.
"""

import json
import os
import re
from pathlib import Path
from typing import Any, Literal

import click
from mcp.server import Server, ServerRequestContext
from mcp.server.stdio import stdio_server
from mcp.types import (
    CallToolRequestParams,
    CallToolResult,
    ListToolsResult,
    PaginatedRequestParams,
    TextContent,
    Tool,
    ToolAnnotations,
)

from .providers import CodeReviewProvider, GitHubProvider, GitLabProvider, ProviderError

_providers: dict[str, CodeReviewProvider] = {}


def _get_builtin_rules_dir() -> Path:
    return Path(__file__).parent / "rules"


def _load_rules(
    include_builtin: bool = True,
    custom_rules_dir: str | None = None,
    lang: str | None = None,
) -> list[dict[str, str]]:
    rules: list[dict[str, str]] = []

    if include_builtin:
        builtin_dir = _get_builtin_rules_dir()
        if builtin_dir.exists():
            for rule_file in sorted(builtin_dir.glob("*.mdc")):
                if lang:
                    if lang == "en" and not rule_file.stem.endswith("-en"):
                        continue
                    if lang == "zh" and rule_file.stem.endswith("-en"):
                        continue
                rules.append(
                    {
                        "name": rule_file.stem,
                        "source": "builtin",
                        "content": rule_file.read_text(encoding="utf-8"),
                    }
                )

    custom_dir = custom_rules_dir or os.environ.get("CODE_REVIEW_RULES_DIR")
    if not custom_dir:
        auto_discover = Path.cwd() / ".code-review-rules"
        if auto_discover.exists() and auto_discover.is_dir():
            custom_dir = str(auto_discover)

    if custom_dir:
        custom_path = Path(custom_dir)
        if custom_path.exists() and custom_path.is_dir():
            for ext in ("*.md", "*.mdc"):
                for rule_file in sorted(custom_path.glob(ext)):
                    rules.append(
                        {
                            "name": rule_file.stem,
                            "source": "custom",
                            "content": rule_file.read_text(encoding="utf-8"),
                        }
                    )

    return rules


def get_provider(provider_type: str, host: str | None = None) -> CodeReviewProvider:
    key = f"{provider_type}:{host or 'default'}"

    if key not in _providers:
        if provider_type == "gitlab":
            _providers[key] = GitLabProvider(host=host)
        elif provider_type == "github":
            _providers[key] = GitHubProvider()
        else:
            raise ProviderError(f"Unknown provider: {provider_type}", error_type="validation")

    return _providers[key]


def extract_related_prs(
    provider: str, description: str, host: str | None = None
) -> list[dict[str, Any]]:
    if not description:
        return []

    if provider == "gitlab":
        host = host or "gitlab.com"
        pattern = rf"https://{re.escape(host)}/([\w\-]+(?:/[\w\-]+)*?)(?:/-)?/merge_requests/(\d+)"
    else:
        pattern = r"https://github\.com/([\w\-]+/[\w\-]+)/pull/(\d+)"

    matches = re.findall(pattern, description)
    return [{"repo": repo, "pr_id": int(pr_id)} for repo, pr_id in matches]


# =============================================================================
# Tool Definitions
# =============================================================================

TOOLS = [
    Tool(
        name="get_review_rules",
        description="Get code review rules (builtin + custom project rules). "
        "Call this before starting a review to load all applicable rules.",
        input_schema={
            "type": "object",
            "properties": {
                "lang": {
                    "type": "string",
                    "enum": ["zh", "en"],
                    "description": "Language filter for builtin rules. "
                    "'zh' for Chinese, 'en' for English. "
                    "If omitted, all builtin rules are returned.",
                },
                "include_builtin": {
                    "type": "boolean",
                    "description": "Whether to include builtin rules (default: true)",
                },
            },
            "additionalProperties": False,
        },
        annotations=ToolAnnotations(
            title="Get Review Rules",
            read_only_hint=True,
            open_world_hint=False,
        ),
    ),
    Tool(
        name="get_pr_info",
        description="Get PR/MR detailed information including title, description, author, and branches",
        input_schema={
            "type": "object",
            "properties": {
                "provider": {
                    "type": "string",
                    "enum": ["github", "gitlab"],
                    "description": "Code hosting provider",
                },
                "repo": {
                    "type": "string",
                    "description": "Repository path (e.g., owner/repo or group/project)",
                },
                "pr_id": {
                    "type": "integer",
                    "description": "PR/MR number",
                },
                "host": {
                    "type": "string",
                    "description": "GitLab host for self-hosted instances (default: gitlab.com)",
                },
            },
            "required": ["provider", "repo", "pr_id"],
            "additionalProperties": False,
        },
        annotations=ToolAnnotations(
            title="Get PR/MR Info",
            read_only_hint=True,
            open_world_hint=True,
        ),
    ),
    Tool(
        name="get_pr_changes",
        description="Get PR/MR code changes (diff) with optional file extension filtering. "
        "Supports pagination for large PRs.",
        input_schema={
            "type": "object",
            "properties": {
                "provider": {
                    "type": "string",
                    "enum": ["github", "gitlab"],
                    "description": "Code hosting provider",
                },
                "repo": {
                    "type": "string",
                    "description": "Repository path",
                },
                "pr_id": {
                    "type": "integer",
                    "description": "PR/MR number",
                },
                "host": {
                    "type": "string",
                    "description": "GitLab host for self-hosted instances",
                },
                "file_extensions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Filter files by extensions (e.g., ['.py', '.js'])",
                },
            },
            "required": ["provider", "repo", "pr_id"],
            "additionalProperties": False,
        },
        annotations=ToolAnnotations(
            title="Get PR/MR Changes",
            read_only_hint=True,
            open_world_hint=True,
        ),
    ),
    Tool(
        name="list_pr_comments",
        description="List existing comments on a PR/MR, including inline review comments "
        "and general comments. Useful for checking existing discussions before adding new ones.",
        input_schema={
            "type": "object",
            "properties": {
                "provider": {
                    "type": "string",
                    "enum": ["github", "gitlab"],
                    "description": "Code hosting provider",
                },
                "repo": {
                    "type": "string",
                    "description": "Repository path",
                },
                "pr_id": {
                    "type": "integer",
                    "description": "PR/MR number",
                },
                "host": {
                    "type": "string",
                    "description": "GitLab host for self-hosted instances",
                },
            },
            "required": ["provider", "repo", "pr_id"],
            "additionalProperties": False,
        },
        annotations=ToolAnnotations(
            title="List PR/MR Comments",
            read_only_hint=True,
            open_world_hint=True,
        ),
    ),
    Tool(
        name="get_file_content",
        description="Get the full content of a file from the repository. "
        "Useful for understanding complete context when reviewing diffs.",
        input_schema={
            "type": "object",
            "properties": {
                "provider": {
                    "type": "string",
                    "enum": ["github", "gitlab"],
                    "description": "Code hosting provider",
                },
                "repo": {
                    "type": "string",
                    "description": "Repository path",
                },
                "file_path": {
                    "type": "string",
                    "description": "Path to the file in the repository",
                },
                "ref": {
                    "type": "string",
                    "description": "Branch, tag, or commit SHA (default: default branch)",
                },
                "host": {
                    "type": "string",
                    "description": "GitLab host for self-hosted instances",
                },
            },
            "required": ["provider", "repo", "file_path"],
            "additionalProperties": False,
        },
        annotations=ToolAnnotations(
            title="Get File Content",
            read_only_hint=True,
            open_world_hint=True,
        ),
    ),
    Tool(
        name="get_pr_commits",
        description="Get the list of commits in a PR/MR. "
        "Useful for understanding change progression and identifying which commit introduced an issue.",
        input_schema={
            "type": "object",
            "properties": {
                "provider": {
                    "type": "string",
                    "enum": ["github", "gitlab"],
                    "description": "Code hosting provider",
                },
                "repo": {
                    "type": "string",
                    "description": "Repository path",
                },
                "pr_id": {
                    "type": "integer",
                    "description": "PR/MR number",
                },
                "host": {
                    "type": "string",
                    "description": "GitLab host for self-hosted instances",
                },
            },
            "required": ["provider", "repo", "pr_id"],
            "additionalProperties": False,
        },
        annotations=ToolAnnotations(
            title="Get PR/MR Commits",
            read_only_hint=True,
            open_world_hint=True,
        ),
    ),
    Tool(
        name="add_inline_comment",
        description="Add inline comment to a specific code line in PR/MR",
        input_schema={
            "type": "object",
            "properties": {
                "provider": {
                    "type": "string",
                    "enum": ["github", "gitlab"],
                    "description": "Code hosting provider",
                },
                "repo": {
                    "type": "string",
                    "description": "Repository path",
                },
                "pr_id": {
                    "type": "integer",
                    "description": "PR/MR number",
                },
                "file_path": {
                    "type": "string",
                    "description": "Path to the file",
                },
                "line": {
                    "type": "integer",
                    "description": "Line number to comment on",
                },
                "line_type": {
                    "type": "string",
                    "enum": ["old", "new"],
                    "description": "Line type: 'old' for deleted line, 'new' for added line",
                },
                "comment": {
                    "type": "string",
                    "description": "Comment content",
                },
                "host": {
                    "type": "string",
                    "description": "GitLab host for self-hosted instances",
                },
            },
            "required": ["provider", "repo", "pr_id", "file_path", "line", "line_type", "comment"],
            "additionalProperties": False,
        },
        annotations=ToolAnnotations(
            title="Add Inline Comment",
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=False,
            open_world_hint=True,
        ),
    ),
    Tool(
        name="add_pr_comment",
        description="Add a general comment to PR/MR",
        input_schema={
            "type": "object",
            "properties": {
                "provider": {
                    "type": "string",
                    "enum": ["github", "gitlab"],
                    "description": "Code hosting provider",
                },
                "repo": {
                    "type": "string",
                    "description": "Repository path",
                },
                "pr_id": {
                    "type": "integer",
                    "description": "PR/MR number",
                },
                "comment": {
                    "type": "string",
                    "description": "Comment content",
                },
                "host": {
                    "type": "string",
                    "description": "GitLab host for self-hosted instances",
                },
            },
            "required": ["provider", "repo", "pr_id", "comment"],
            "additionalProperties": False,
        },
        annotations=ToolAnnotations(
            title="Add PR/MR Comment",
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=False,
            open_world_hint=True,
        ),
    ),
    Tool(
        name="batch_add_comments",
        description="Batch add multiple inline comments and optionally a general comment",
        input_schema={
            "type": "object",
            "properties": {
                "provider": {
                    "type": "string",
                    "enum": ["github", "gitlab"],
                    "description": "Code hosting provider",
                },
                "repo": {
                    "type": "string",
                    "description": "Repository path",
                },
                "pr_id": {
                    "type": "integer",
                    "description": "PR/MR number",
                },
                "inline_comments": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "file_path": {"type": "string"},
                            "line": {"type": "integer"},
                            "line_type": {"type": "string", "enum": ["old", "new"]},
                            "comment": {"type": "string"},
                        },
                        "required": ["file_path", "line", "line_type", "comment"],
                    },
                    "description": "List of inline comments to add",
                },
                "pr_comment": {
                    "type": "string",
                    "description": "Optional general PR/MR comment",
                },
                "host": {
                    "type": "string",
                    "description": "GitLab host for self-hosted instances",
                },
            },
            "required": ["provider", "repo", "pr_id", "inline_comments"],
            "additionalProperties": False,
        },
        annotations=ToolAnnotations(
            title="Batch Add Comments",
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=False,
            open_world_hint=True,
        ),
    ),
    Tool(
        name="resolve_discussion",
        description="Resolve a discussion thread on a PR/MR (GitLab only). "
        "For GitHub, use submit_review with 'approve' action instead.",
        input_schema={
            "type": "object",
            "properties": {
                "provider": {
                    "type": "string",
                    "enum": ["github", "gitlab"],
                    "description": "Code hosting provider",
                },
                "repo": {
                    "type": "string",
                    "description": "Repository path",
                },
                "pr_id": {
                    "type": "integer",
                    "description": "PR/MR number",
                },
                "discussion_id": {
                    "type": "string",
                    "description": "Discussion/thread ID to resolve",
                },
                "host": {
                    "type": "string",
                    "description": "GitLab host for self-hosted instances",
                },
            },
            "required": ["provider", "repo", "pr_id", "discussion_id"],
            "additionalProperties": False,
        },
        annotations=ToolAnnotations(
            title="Resolve Discussion",
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=True,
        ),
    ),
    Tool(
        name="submit_review",
        description="Submit a formal review decision on a PR/MR. "
        "GitHub: approve, request_changes, comment. "
        "GitLab: approve, unapprove.",
        input_schema={
            "type": "object",
            "properties": {
                "provider": {
                    "type": "string",
                    "enum": ["github", "gitlab"],
                    "description": "Code hosting provider",
                },
                "repo": {
                    "type": "string",
                    "description": "Repository path",
                },
                "pr_id": {
                    "type": "integer",
                    "description": "PR/MR number",
                },
                "action": {
                    "type": "string",
                    "enum": ["approve", "request_changes", "comment", "unapprove"],
                    "description": "Review action. GitHub: approve/request_changes/comment. GitLab: approve/unapprove.",
                },
                "body": {
                    "type": "string",
                    "description": "Review body/comment (optional for approve)",
                },
                "host": {
                    "type": "string",
                    "description": "GitLab host for self-hosted instances",
                },
            },
            "required": ["provider", "repo", "pr_id", "action"],
            "additionalProperties": False,
        },
        annotations=ToolAnnotations(
            title="Submit Review",
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=False,
            open_world_hint=True,
        ),
    ),
    Tool(
        name="extract_related_prs",
        description="Extract related PR/MR links from description text",
        input_schema={
            "type": "object",
            "properties": {
                "provider": {
                    "type": "string",
                    "enum": ["github", "gitlab"],
                    "description": "Code hosting provider",
                },
                "description": {
                    "type": "string",
                    "description": "Description text to extract links from",
                },
                "host": {
                    "type": "string",
                    "description": "GitLab host for self-hosted instances",
                },
            },
            "required": ["provider", "description"],
            "additionalProperties": False,
        },
        annotations=ToolAnnotations(
            title="Extract Related PRs",
            read_only_hint=True,
            open_world_hint=False,
        ),
    ),
]


# =============================================================================
# Tool Handlers (dict-based dispatch)
# =============================================================================

async def _handle_get_review_rules(arguments: dict[str, Any]) -> str:
    rules = _load_rules(
        include_builtin=arguments.get("include_builtin", True),
        lang=arguments.get("lang"),
    )
    return json.dumps(rules, ensure_ascii=False)


async def _handle_extract_related_prs(arguments: dict[str, Any]) -> str:
    extracted = extract_related_prs(
        arguments.get("provider", "github"),
        arguments["description"],
        arguments.get("host"),
    )
    return json.dumps(extracted, ensure_ascii=False)


async def _handle_get_pr_info(arguments: dict[str, Any]) -> str:
    provider = get_provider(arguments.get("provider", "github"), arguments.get("host"))
    result = await provider.get_pr_info(arguments["repo"], arguments["pr_id"])
    return json.dumps(result, ensure_ascii=False)


async def _handle_get_pr_changes(arguments: dict[str, Any]) -> str:
    provider = get_provider(arguments.get("provider", "github"), arguments.get("host"))
    result = await provider.get_pr_changes(
        arguments["repo"],
        arguments["pr_id"],
        arguments.get("file_extensions"),
    )
    return json.dumps(result, ensure_ascii=False)


async def _handle_list_pr_comments(arguments: dict[str, Any]) -> str:
    provider = get_provider(arguments.get("provider", "github"), arguments.get("host"))
    result = await provider.list_comments(arguments["repo"], arguments["pr_id"])
    return json.dumps(result, ensure_ascii=False)


async def _handle_get_file_content(arguments: dict[str, Any]) -> str:
    provider = get_provider(arguments.get("provider", "github"), arguments.get("host"))
    result = await provider.get_file_content(
        arguments["repo"], arguments["file_path"], arguments.get("ref")
    )
    return json.dumps(result, ensure_ascii=False)


async def _handle_get_pr_commits(arguments: dict[str, Any]) -> str:
    provider = get_provider(arguments.get("provider", "github"), arguments.get("host"))
    result = await provider.get_pr_commits(arguments["repo"], arguments["pr_id"])
    return json.dumps(result, ensure_ascii=False)


async def _handle_add_inline_comment(arguments: dict[str, Any]) -> str:
    provider = get_provider(arguments.get("provider", "github"), arguments.get("host"))
    result = await provider.add_inline_comment(
        arguments["repo"],
        arguments["pr_id"],
        arguments["file_path"],
        arguments["line"],
        arguments["line_type"],
        arguments["comment"],
    )
    return json.dumps(result, ensure_ascii=False)


async def _handle_add_pr_comment(arguments: dict[str, Any]) -> str:
    provider = get_provider(arguments.get("provider", "github"), arguments.get("host"))
    result = await provider.add_pr_comment(
        arguments["repo"],
        arguments["pr_id"],
        arguments["comment"],
    )
    return json.dumps(result, ensure_ascii=False)


async def _handle_batch_add_comments(arguments: dict[str, Any]) -> str:
    provider = get_provider(arguments.get("provider", "github"), arguments.get("host"))

    batch_results: dict[str, Any] = {
        "inline_success": 0,
        "inline_failed": 0,
        "pr_comment_success": False,
        "errors": [],
    }

    for comment_data in arguments.get("inline_comments", []):
        try:
            res = await provider.add_inline_comment(
                arguments["repo"],
                arguments["pr_id"],
                comment_data["file_path"],
                comment_data["line"],
                comment_data["line_type"],
                comment_data["comment"],
            )
            if res.get("success"):
                batch_results["inline_success"] += 1
            else:
                batch_results["inline_failed"] += 1
                batch_results["errors"].append(
                    {
                        "file": comment_data["file_path"],
                        "line": comment_data["line"],
                        "error": res.get("error"),
                    }
                )
        except Exception as e:
            batch_results["inline_failed"] += 1
            batch_results["errors"].append(
                {
                    "file": comment_data.get("file_path"),
                    "error": str(e),
                }
            )

    if arguments.get("pr_comment"):
        try:
            res = await provider.add_pr_comment(
                arguments["repo"],
                arguments["pr_id"],
                arguments["pr_comment"],
            )
            batch_results["pr_comment_success"] = res.get("success", False)
        except Exception as e:
            batch_results["errors"].append({"type": "pr_comment", "error": str(e)})

    return json.dumps(batch_results, ensure_ascii=False)


async def _handle_resolve_discussion(arguments: dict[str, Any]) -> str:
    provider = get_provider(arguments.get("provider", "github"), arguments.get("host"))
    result = await provider.resolve_discussion(
        arguments["repo"], arguments["pr_id"], arguments["discussion_id"]
    )
    return json.dumps(result, ensure_ascii=False)


async def _handle_submit_review(arguments: dict[str, Any]) -> str:
    provider = get_provider(arguments.get("provider", "github"), arguments.get("host"))
    result = await provider.submit_review(
        arguments["repo"], arguments["pr_id"], arguments["action"], arguments.get("body")
    )
    return json.dumps(result, ensure_ascii=False)


TOOL_HANDLERS: dict[str, Any] = {
    "get_review_rules": _handle_get_review_rules,
    "get_pr_info": _handle_get_pr_info,
    "get_pr_changes": _handle_get_pr_changes,
    "list_pr_comments": _handle_list_pr_comments,
    "get_file_content": _handle_get_file_content,
    "get_pr_commits": _handle_get_pr_commits,
    "add_inline_comment": _handle_add_inline_comment,
    "add_pr_comment": _handle_add_pr_comment,
    "batch_add_comments": _handle_batch_add_comments,
    "resolve_discussion": _handle_resolve_discussion,
    "submit_review": _handle_submit_review,
    "extract_related_prs": _handle_extract_related_prs,
}


# =============================================================================
# MCP Protocol Handlers
# =============================================================================


async def _handle_list_tools(
    ctx: ServerRequestContext,
    params: PaginatedRequestParams | None,
) -> ListToolsResult:
    return ListToolsResult(tools=TOOLS)


async def _handle_call_tool(
    ctx: ServerRequestContext,
    params: CallToolRequestParams,
) -> CallToolResult:
    name = params.name
    arguments = params.arguments or {}

    handler = TOOL_HANDLERS.get(name)
    if not handler:
        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps({
                "error": f"Unknown tool: {name}",
                "error_type": "unknown_tool",
                "available_tools": list(TOOL_HANDLERS.keys()),
            }))],
            is_error=True,
        )

    try:
        result_text = await handler(arguments)
        return CallToolResult(content=[TextContent(type="text", text=result_text)])
    except ProviderError as e:
        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps({
                "error": str(e),
                "error_type": e.error_type,
                "status_code": e.status_code,
            }))],
            is_error=True,
        )
    except KeyError as e:
        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps({
                "error": f"Missing required argument: {e}",
                "error_type": "validation",
            }))],
            is_error=True,
        )
    except Exception as e:
        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps({
                "error": str(e),
                "error_type": "internal",
            }))],
            is_error=True,
        )


mcp = Server(
    "code-review-mcp",
    on_list_tools=_handle_list_tools,
    on_call_tool=_handle_call_tool,
)


# =============================================================================
# Server Entry Points
# =============================================================================


async def run_stdio() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await mcp.run(
            read_stream,
            write_stream,
            mcp.create_initialization_options(),
        )


def run_sse(host: str = "0.0.0.0", port: int = 8000) -> None:
    """Run the server using SSE transport (legacy, prefer streamable-http)."""
    import uvicorn
    from mcp.server.sse import SseServerTransport
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    sse = SseServerTransport("/messages")

    async def handle_sse(request: Any) -> Any:
        async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
            await mcp.run(
                streams[0],
                streams[1],
                mcp.create_initialization_options(),
            )
        return None

    async def handle_messages(request: Any) -> Any:
        await sse.handle_post_message(request.scope, request.receive, request._send)
        return None

    async def health_check(request: Any) -> JSONResponse:
        return JSONResponse({"status": "healthy", "server": "code-review-mcp"})

    app = Starlette(
        routes=[
            Route("/sse", endpoint=handle_sse),
            Route("/messages", endpoint=handle_messages, methods=["POST"]),
            Route("/health", endpoint=health_check, methods=["GET"]),
        ]
    )

    uvicorn.run(app, host=host, port=port)


def run_streamable_http(host: str = "0.0.0.0", port: int = 8000) -> None:
    """Run the server using Streamable HTTP transport (recommended for deployed servers)."""
    import uvicorn
    from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse
    from starlette.routing import Mount, Route

    session_manager = StreamableHTTPSessionManager(app=mcp, json_response=False, stateless=False)

    async def handle_mcp(request: Any) -> Any:
        await session_manager.handle_request(request.scope, request.receive, request._send)

    async def health_check(request: Any) -> JSONResponse:
        return JSONResponse({"status": "healthy", "server": "code-review-mcp"})

    app = Starlette(
        routes=[
            Mount("/mcp", app=session_manager.handle_request),
            Route("/health", endpoint=health_check, methods=["GET"]),
        ]
    )

    uvicorn.run(app, host=host, port=port)


@click.command()
@click.option(
    "--transport",
    "-t",
    type=click.Choice(["stdio", "sse", "streamable-http"]),
    default="stdio",
    help="Transport mode: stdio (default), sse (legacy), or streamable-http",
)
@click.option(
    "--host",
    "-h",
    default="0.0.0.0",
    help="Host for HTTP server (default: 0.0.0.0)",
)
@click.option(
    "--port",
    "-p",
    default=8000,
    type=int,
    help="Port for HTTP server (default: 8000)",
)
@click.version_option()
def main(
    transport: Literal["stdio", "sse", "streamable-http"],
    host: str,
    port: int,
) -> None:
    """
    Code Review MCP Server.

    Enables AI assistants to review GitHub/GitLab pull requests and merge requests.
    """
    import asyncio

    if transport == "stdio":
        asyncio.run(run_stdio())
    elif transport == "sse":
        run_sse(host, port)
    else:
        run_streamable_http(host, port)


if __name__ == "__main__":
    main()
