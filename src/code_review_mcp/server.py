"""
Code Review MCP Server.

Main MCP server implementation using the official MCP SDK.
Supports stdio, SSE, and WebSocket transports.
"""

import os
import re
import sys
from typing import Any, Literal

import click
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    TextContent,
    Tool,
)

from .providers import CodeReviewProvider, GitHubProvider, GitLabProvider

# Create the MCP server instance
mcp = Server("code-review-mcp")

# Provider cache
_providers: dict[str, CodeReviewProvider] = {}


def get_provider(provider_type: str, host: str | None = None) -> CodeReviewProvider:
    """Get or create provider instance."""
    key = f"{provider_type}:{host or 'default'}"

    if key not in _providers:
        if provider_type == "gitlab":
            _providers[key] = GitLabProvider(host=host)
        elif provider_type == "github":
            _providers[key] = GitHubProvider()
        else:
            raise ValueError(f"Unknown provider: {provider_type}")

    return _providers[key]


def extract_related_prs(
    provider: str, description: str, host: str | None = None
) -> list[dict[str, Any]]:
    """Extract related PR/MR links from description."""
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
        name="get_pr_info",
        description="Get PR/MR detailed information including title, description, author, and branches",
        inputSchema={
            "type": "object",
            "properties": {
                "provider": {
                    "type": "string",
                    "enum": ["github", "gitlab"],
                    "description": "Code hosting provider (github or gitlab)",
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
                    "description": "GitLab host for self-hosted instances (optional, default: gitlab.com)",
                },
            },
            "required": ["provider", "repo", "pr_id"],
        },
    ),
    Tool(
        name="get_pr_changes",
        description="Get PR/MR code changes (diff) with optional file extension filtering",
        inputSchema={
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
        },
    ),
    Tool(
        name="add_inline_comment",
        description="Add inline comment to a specific code line in PR/MR",
        inputSchema={
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
        },
    ),
    Tool(
        name="add_pr_comment",
        description="Add a general comment to PR/MR",
        inputSchema={
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
        },
    ),
    Tool(
        name="batch_add_comments",
        description="Batch add multiple inline comments and optionally a general comment",
        inputSchema={
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
        },
    ),
    Tool(
        name="extract_related_prs",
        description="Extract related PR/MR links from description text",
        inputSchema={
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
        },
    ),
]


@mcp.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools."""
    return TOOLS


@mcp.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool calls."""
    import json

    try:
        # extract_related_prs doesn't need authentication
        if name == "extract_related_prs":
            result = extract_related_prs(
                arguments.get("provider", "github"),
                arguments["description"],
                arguments.get("host"),
            )
            return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]

        # All other tools need provider authentication
        provider_type = arguments.get("provider", "github")
        host = arguments.get("host")
        provider = get_provider(provider_type, host)

        if name == "get_pr_info":
            result = await provider.get_pr_info(arguments["repo"], arguments["pr_id"])

        elif name == "get_pr_changes":
            result = await provider.get_pr_changes(
                arguments["repo"],
                arguments["pr_id"],
                arguments.get("file_extensions"),
            )

        elif name == "add_inline_comment":
            result = await provider.add_inline_comment(
                arguments["repo"],
                arguments["pr_id"],
                arguments["file_path"],
                arguments["line"],
                arguments["line_type"],
                arguments["comment"],
            )

        elif name == "add_pr_comment":
            result = await provider.add_pr_comment(
                arguments["repo"],
                arguments["pr_id"],
                arguments["comment"],
            )

        elif name == "batch_add_comments":
            results: dict[str, Any] = {
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
                        results["inline_success"] += 1
                    else:
                        results["inline_failed"] += 1
                        results["errors"].append({
                            "file": comment_data["file_path"],
                            "line": comment_data["line"],
                            "error": res.get("error"),
                        })
                except Exception as e:
                    results["inline_failed"] += 1
                    results["errors"].append({
                        "file": comment_data.get("file_path"),
                        "error": str(e),
                    })

            if arguments.get("pr_comment"):
                try:
                    res = await provider.add_pr_comment(
                        arguments["repo"],
                        arguments["pr_id"],
                        arguments["pr_comment"],
                    )
                    results["pr_comment_success"] = res.get("success", False)
                except Exception as e:
                    results["errors"].append({"type": "pr_comment", "error": str(e)})

            result = results

        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]

    except Exception as e:
        return [TextContent(type="text", text=f"Error: {str(e)}")]


# =============================================================================
# Server Entry Points
# =============================================================================


async def run_stdio() -> None:
    """Run the server using stdio transport."""
    async with stdio_server() as (read_stream, write_stream):
        await mcp.run(
            read_stream,
            write_stream,
            mcp.create_initialization_options(),
        )


def run_sse(host: str = "0.0.0.0", port: int = 8000) -> None:
    """Run the server using SSE transport."""
    from mcp.server.sse import SseServerTransport
    from starlette.applications import Starlette
    from starlette.routing import Route
    import uvicorn

    sse = SseServerTransport("/messages")

    async def handle_sse(request: Any) -> Any:
        async with sse.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            await mcp.run(
                streams[0],
                streams[1],
                mcp.create_initialization_options(),
            )
        return None

    async def handle_messages(request: Any) -> Any:
        await sse.handle_post_message(request.scope, request.receive, request._send)
        return None

    app = Starlette(
        routes=[
            Route("/sse", endpoint=handle_sse),
            Route("/messages", endpoint=handle_messages, methods=["POST"]),
        ]
    )

    uvicorn.run(app, host=host, port=port)


@click.command()
@click.option(
    "--transport",
    "-t",
    type=click.Choice(["stdio", "sse"]),
    default="stdio",
    help="Transport mode: stdio (default) or sse",
)
@click.option(
    "--host",
    "-h",
    default="0.0.0.0",
    help="Host for SSE server (default: 0.0.0.0)",
)
@click.option(
    "--port",
    "-p",
    default=8000,
    type=int,
    help="Port for SSE server (default: 8000)",
)
@click.version_option()
def main(
    transport: Literal["stdio", "sse"],
    host: str,
    port: int,
) -> None:
    """
    Code Review MCP Server.

    Enables AI assistants to review GitHub/GitLab pull requests and merge requests.

    Examples:

        # Run with stdio (default, for Cursor/Claude Desktop):
        code-review-mcp

        # Run with SSE transport:
        code-review-mcp --transport sse --port 8000

    Environment Variables:

        GITHUB_TOKEN: GitHub personal access token
        GITLAB_TOKEN: GitLab personal access token
        GITLAB_HOST: GitLab host (default: gitlab.com)
    """
    import asyncio

    if transport == "stdio":
        asyncio.run(run_stdio())
    else:
        run_sse(host, port)


if __name__ == "__main__":
    main()
