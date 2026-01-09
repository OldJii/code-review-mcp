# Code Review MCP Server

English | [中文](README_CN.md)

[![PyPI version](https://badge.fury.io/py/code-review-mcp.svg)](https://badge.fury.io/py/code-review-mcp)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

MCP (Model Context Protocol) server for code review. Enables AI assistants to review GitHub/GitLab Pull Requests and Merge Requests.

## ✨ Features

- 🔍 **Multi-platform**: Supports both GitHub and GitLab (including self-hosted)
- 🚀 **Multiple Transports**: Supports stdio and SSE protocols
- 📦 **Easy Install**: Quick install via `uvx` or `pip`
- 🐳 **Containerized**: Docker image available
- ☁️ **Cloud Deploy**: One-click Smithery deployment
- 🔒 **Security First**: Environment variable configuration, no data persistence

## 🚀 Quick Start

### Option 1: Using uvx (Recommended)

```bash
# Run directly, no installation needed
uvx code-review-mcp
```

### Option 2: Using pip

```bash
pip install code-review-mcp

# Run the server
code-review-mcp
```

### Option 3: From Source

```bash
git clone https://github.com/OldJii/code-review-mcp.git
cd code-review-mcp
pip install -e .
code-review-mcp
```

## 🔧 Configuration

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `GITHUB_TOKEN` | GitHub personal access token | When using GitHub |
| `GITLAB_TOKEN` | GitLab personal access token | When using GitLab |
| `GITLAB_HOST` | GitLab host URL | For self-hosted (default: gitlab.com) |

### Getting Tokens

**GitHub**

```bash
# Option 1: Using gh CLI (Recommended)
brew install gh
gh auth login

# Option 2: Manual Token Creation
# Visit https://github.com/settings/tokens
# Create Personal Access Token with 'repo' scope
export GITHUB_TOKEN="your-token-here"
```

**GitLab**

```bash
# Option 1: Using glab CLI (Recommended)
brew install glab
glab auth login

# For self-hosted GitLab
glab auth login --hostname gitlab.yourcompany.com

# Option 2: Manual Token Creation
# Visit GitLab -> Settings -> Access Tokens
# Create token with 'api' scope
export GITLAB_TOKEN="your-token-here"
export GITLAB_HOST="gitlab.yourcompany.com"  # For self-hosted
```

## 📱 Client Configuration

### Cursor

Edit `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "code-review": {
      "command": "uvx",
      "args": ["code-review-mcp"],
      "env": {
        "GITHUB_TOKEN": "your-github-token",
        "GITLAB_TOKEN": "your-gitlab-token"
      }
    }
  }
}
```

### Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "code-review": {
      "command": "uvx",
      "args": ["code-review-mcp"],
      "env": {
        "GITHUB_TOKEN": "your-github-token",
        "GITLAB_TOKEN": "your-gitlab-token"
      }
    }
  }
}
```

### SSE Mode (Remote Deployment)

```bash
# Start SSE server
code-review-mcp --transport sse --port 8000
```

Client configuration:

```json
{
  "mcpServers": {
    "code-review": {
      "url": "http://your-server:8000/sse"
    }
  }
}
```

## 🐳 Docker Deployment

### Build Image

```bash
docker build -t code-review-mcp .
```

### Run Container

**stdio mode**

```bash
docker run -i --rm \
  -e GITHUB_TOKEN="your-token" \
  code-review-mcp
```

**SSE mode**

```bash
docker run -d --rm \
  -e GITHUB_TOKEN="your-token" \
  -p 8000:8000 \
  code-review-mcp --transport sse
```

## 🔨 MCP Tools

### Information Retrieval

| Tool | Description |
|------|-------------|
| `get_pr_info` | Get PR/MR details (title, description, branches) |
| `get_pr_changes` | Get code changes (diff), supports file type filtering |
| `extract_related_prs` | Extract related PR/MR links from description |

### Adding Comments

| Tool | Description |
|------|-------------|
| `add_inline_comment` | Add inline comment to specific code line |
| `add_pr_comment` | Add general comment |
| `batch_add_comments` | Batch add comments (inline + general) |

## 💬 Usage Examples

Chat with Cursor or Claude:

**Review GitHub PR**

```
Review https://github.com/facebook/react/pull/12345
```

**Review GitLab MR**

```
Review https://gitlab.com/group/project/-/merge_requests/678
```

**Review Self-hosted GitLab MR**

```
Review https://gitlab.yourcompany.com/team/project/-/merge_requests/90
```

**Review Only Specific File Types**

```
Review this PR, only check .py and .js files:
https://github.com/owner/repo/pull/123
```

## 🧪 Debugging & Testing

### Using MCP Inspector

```bash
# Run with MCP Inspector
npx @modelcontextprotocol/inspector uvx code-review-mcp
```

This launches a web interface where you can:
- View all available tools
- Manually call tools and inspect results
- Debug parameters and responses

### Local Development

```bash
# Clone repository
git clone https://github.com/OldJii/code-review-mcp.git
cd code-review-mcp

# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Debug with Inspector
npx @modelcontextprotocol/inspector python -m code_review_mcp.server
```

## 📁 Project Structure

```
code-review-mcp/
├── src/
│   └── code_review_mcp/
│       ├── __init__.py      # Package entry
│       ├── server.py        # MCP server main logic
│       └── providers.py     # GitHub/GitLab providers
├── .cursor/rules/           # Cursor review rules
├── pyproject.toml           # Project config & PyPI publishing
├── Dockerfile               # Docker build file
├── smithery.yaml            # Smithery deployment config
├── CHANGELOG.md             # Changelog
├── CONTRIBUTING.md          # Contributing guide
└── README.md                # Documentation
```

## 🎯 Custom Review Rules

The included `.cursor/rules/code-review.mdc` is a general template. Copy to your project and customize:

```bash
cp -r .cursor/rules your-project/.cursor/
```

Customizable items:
- Priority definitions
- Checklist items
- Comment format
- Deduplication rules

## 🤝 Contributing

Contributions welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

## 📄 License

[MIT](LICENSE)

## 🔗 Related Links

- [MCP Protocol Documentation](https://modelcontextprotocol.io/)
- [Smithery Platform](https://smithery.ai/)
- [Cursor Editor](https://cursor.sh/)
- [Claude Desktop](https://claude.ai/desktop)
