# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.0] - 2025-01-09

### Added

- Initial release of Code Review MCP Server
- Support for GitHub Pull Request review
- Support for GitLab Merge Request review (including self-hosted instances)
- Tools:
  - `get_pr_info` - Get PR/MR detailed information
  - `get_pr_changes` - Get code changes with optional file extension filtering
  - `add_inline_comment` - Add inline comments to specific code lines
  - `add_pr_comment` - Add general PR/MR comments
  - `batch_add_comments` - Batch add multiple comments
  - `extract_related_prs` - Extract related PR/MR links from description
- Multiple transport support:
  - stdio (for Cursor, Claude Desktop)
  - SSE (for remote/hosted deployment)
- Docker support for containerized deployment
- Smithery deployment configuration
- PyPI package with CLI entry point (`code-review-mcp`)
- Environment variable configuration for tokens
- Automatic token detection from gh/glab CLI

### Security

- No persistent data storage
- Tokens configured via environment variables only
- Non-root user in Docker container

[Unreleased]: https://github.com/OldJii/code-review-mcp/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/OldJii/code-review-mcp/releases/tag/v1.0.0
