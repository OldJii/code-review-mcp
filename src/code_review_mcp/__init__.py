"""
Code Review MCP Server

MCP (Model Context Protocol) server for GitHub/GitLab code review.
Enables AI assistants to review pull requests and merge requests.
"""

__version__ = "1.0.0"
__author__ = "Code Review MCP Contributors"

from .providers import GitHubProvider, GitLabProvider
from .server import main, mcp

__all__ = ["mcp", "main", "GitHubProvider", "GitLabProvider", "__version__"]
