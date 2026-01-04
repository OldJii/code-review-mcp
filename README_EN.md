# Cursor AI Code Review

English | [中文](README.md)

MCP (Model Context Protocol) based code review tool that enables Cursor to read GitHub/GitLab PR/MR and submit review comments.

## Project Structure

```
cursor-ai-code-review/
├── code_review_mcp.py           # MCP server
└── .cursor/rules/
    ├── code-review.mdc          # Review guidelines (Chinese)
    └── code-review-en.mdc       # Review guidelines (English)
```

## Installation

### 1. Download

```bash
git clone https://github.com/user/cursor-ai-code-review.git
```

### 2. Authentication

**GitHub**

```bash
brew install gh
gh auth login
```

**GitLab**

```bash
brew install glab
glab auth login
```

For self-hosted GitLab:

```bash
glab auth login --hostname gitlab.yourcompany.com
```

### 3. Configure MCP

Edit `~/.cursor/mcp.json` (global config, applies to all projects):

```json
{
  "mcpServers": {
    "code-review": {
      "command": "python3",
      "args": ["/path/to/cursor-ai-code-review/code_review_mcp.py"]
    }
  }
}
```

Replace `/path/to/` with the actual path.

### 4. Configure Review Rules (Optional)

Copy the rules from `.cursor/rules/` to your project:

```bash
cp -r /path/to/cursor-ai-code-review/.cursor/rules your-project/.cursor/
```

Review rules are project-level configuration and need to be configured separately for each project.

## Usage

Chat with Cursor:

```
Review https://github.com/owner/repo/pull/123
```

## MCP Tools

### Get Information

| Tool | Description |
|------|-------------|
| `get_pr_info` | Get PR/MR title, description, branches, etc. |
| `get_pr_changes` | Get code changes (diff), supports file type filtering |
| `extract_related_prs` | Extract related PR/MR links from description |

### Add Comments

| Tool | Description |
|------|-------------|
| `add_inline_comment` | Add inline comment to specific code line |
| `add_pr_comment` | Add general comment |
| `batch_add_comments` | Batch add comments (inline + general) |

### Parameters

**Common Parameters**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `provider` | string | Yes | `github` or `gitlab` |
| `repo` | string | Yes | Repository path, e.g., `owner/repo` |
| `pr_id` | integer | Yes | PR/MR number |
| `host` | string | No | GitLab host (for self-hosted instances) |

**get_pr_changes**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_extensions` | array | No | Filter by extension, e.g., `[".py", ".js"]` |

**add_inline_comment**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_path` | string | Yes | File path |
| `line` | integer | Yes | Line number |
| `line_type` | string | Yes | `old` (deleted) or `new` (added) |
| `comment` | string | Yes | Comment content |

## Usage Examples

**Review GitHub PR**

```
Review https://github.com/facebook/react/pull/12345
```

**Review GitLab MR**

```
Review https://gitlab.com/group/project/-/merge_requests/678
```

**Review self-hosted GitLab MR**

```
Review https://gitlab.yourcompany.com/team/project/-/merge_requests/90
```

**Review only specific file types**

```
Review this PR, only check .py and .js files:
https://github.com/owner/repo/pull/123
```

## Custom Review Rules

The included `.cursor/rules/code-review.mdc` is a general template. Copy to your project and modify as needed:

- Priority definitions
- Checklist
- Comment format
- Deduplication rules

For language or framework specific rules, use the template as a base and ask AI to generate a customized version.

Language versions:
- `code-review.mdc` - Chinese
- `code-review-en.mdc` - English

## License

MIT
