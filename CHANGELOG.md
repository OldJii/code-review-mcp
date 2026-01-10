# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.1.0] - 2025-01-10

### Added

- New `init-rules` command to install Cursor rules to your project
- New `list-rules` command to show available rules
- Bundled code review rules (Chinese and English versions) in the package
- Users can now run `code-review-mcp init-rules` to set up Cursor rules automatically

### Changed

- CLI now uses click group with subcommands
- Running `code-review-mcp` without arguments still starts the MCP server (backward compatible)

## [1.0.1] - 2025-01-10

### Fixed

- Fixed mypy type checking errors for strict mode compatibility
- Fixed `ToolAnnotations` type usage in tool definitions
- Fixed `websocket_server` call arguments
- Fixed import sorting issues (ruff I001)
- Fixed nested if statements (ruff SIM102)
- Removed unused imports (ruff F401)

### Changed

- Updated mypy configuration to allow untyped decorators and calls from third-party libraries
- Improved type annotations in `_call_api` methods

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

[Unreleased]: https://github.com/OldJii/code-review-mcp/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/OldJii/code-review-mcp/compare/v1.0.1...v1.1.0
[1.0.1]: https://github.com/OldJii/code-review-mcp/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/OldJii/code-review-mcp/releases/tag/v1.0.0
