# Code Review MCP Server

[English](README.md) | 中文

[![PyPI version](https://badge.fury.io/py/code-review-mcp.svg)](https://badge.fury.io/py/code-review-mcp)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

基于 MCP (Model Context Protocol) 的代码审查服务器，让 AI 助手能够审查 GitHub/GitLab 的 Pull Request 和 Merge Request。

## ✨ 特性

- 🔍 **多平台支持**：同时支持 GitHub 和 GitLab（包括私有部署）
- 🚀 **多种运行方式**：支持 stdio、SSE、WebSocket 传输协议
- 📦 **一键安装**：通过 `uvx` 或 `pip` 快速安装
- 🐳 **容器化部署**：提供 Docker 镜像
- ☁️ **云端部署**：支持 Smithery 一键部署
- 🔒 **安全优先**：环境变量配置敏感信息，无数据持久化

## 🚀 快速开始

### 方式 1：使用 uvx（推荐）

```bash
# 直接运行，无需安装
uvx code-review-mcp
```

### 方式 2：使用 pip 安装

```bash
pip install code-review-mcp

# 运行服务器
code-review-mcp

# （可选）安装 Cursor 规则到你的项目
code-review-mcp init-rules
```

### 方式 3：从源码运行

```bash
git clone https://github.com/OldJii/code-review-mcp.git
cd code-review-mcp
pip install -e .
code-review-mcp
```

## 🔧 配置

### 环境变量

| 变量 | 说明 | 必填 |
|------|------|------|
| `GITHUB_TOKEN` | GitHub 个人访问令牌 | 使用 GitHub 时 |
| `GITLAB_TOKEN` | GitLab 个人访问令牌 | 使用 GitLab 时 |
| `GITLAB_HOST` | GitLab 主机地址 | 私有部署时（默认：gitlab.com） |

### 获取 Token

**GitHub**

```bash
# 方式 1：使用 gh CLI（推荐）
brew install gh
gh auth login

# 方式 2：手动创建 Token
# 访问 https://github.com/settings/tokens 创建 Personal Access Token
# 需要 repo 权限
export GITHUB_TOKEN="your-token-here"
```

**GitLab**

```bash
# 方式 1：使用 glab CLI（推荐）
brew install glab
glab auth login

# 私有部署的 GitLab
glab auth login --hostname gitlab.yourcompany.com

# 方式 2：手动创建 Token
# 访问 GitLab -> Settings -> Access Tokens
# 需要 api 权限
export GITLAB_TOKEN="your-token-here"
export GITLAB_HOST="gitlab.yourcompany.com"  # 私有部署时
```

## 📱 客户端配置

### Cursor

编辑 `~/.cursor/mcp.json`：

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

编辑 `~/Library/Application Support/Claude/claude_desktop_config.json`（macOS）或 `%APPDATA%\Claude\claude_desktop_config.json`（Windows）：

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

### SSE 模式（远程部署）

```bash
# 启动 SSE 服务器
code-review-mcp --transport sse --port 8000
```

客户端配置：

```json
{
  "mcpServers": {
    "code-review": {
      "url": "http://your-server:8000/sse"
    }
  }
}
```

### WebSocket 模式（远程部署）

```bash
# 启动 WebSocket 服务器
code-review-mcp --transport websocket --port 8000
```

客户端配置：

```json
{
  "mcpServers": {
    "code-review": {
      "url": "ws://your-server:8000/ws"
    }
  }
}
```

## 🐳 Docker 部署

### 构建镜像

```bash
docker build -t code-review-mcp .
```

### 运行容器

**stdio 模式**

```bash
docker run -i --rm \
  -e GITHUB_TOKEN="your-token" \
  code-review-mcp
```

**SSE 模式**

```bash
docker run -d --rm \
  -e GITHUB_TOKEN="your-token" \
  -p 8000:8000 \
  code-review-mcp --transport sse
```

## 🔨 MCP 工具

### 规则

| 工具 | 说明 |
|------|------|
| `get_review_rules` | 获取审查规则（内置 + 自定义项目规则） |

### 信息获取

| 工具 | 说明 |
|------|------|
| `get_pr_info` | 获取 PR/MR 的标题、描述、分支等详细信息 |
| `get_pr_changes` | 获取代码变更（diff），支持按文件类型过滤 |
| `extract_related_prs` | 从描述中提取关联的 PR/MR 链接 |

### 添加评论

| 工具 | 说明 |
|------|------|
| `add_inline_comment` | 添加行内评论到指定代码行 |
| `add_pr_comment` | 添加整体评论 |
| `batch_add_comments` | 批量添加评论（行内+整体） |

## 💬 使用示例

在 Cursor 或 Claude 中对话：

**审查 GitHub PR**

```
Review https://github.com/facebook/react/pull/12345
```

**审查 GitLab MR**

```
Review https://gitlab.com/group/project/-/merge_requests/678
```

**审查私有 GitLab MR**

```
Review https://gitlab.yourcompany.com/team/project/-/merge_requests/90
```

**只审查特定类型文件**

```
Review this PR, only check .py and .js files:
https://github.com/owner/repo/pull/123
```

## 🧪 调试与测试

### 使用 MCP Inspector

```bash
# 安装 MCP Inspector
npx @modelcontextprotocol/inspector uvx code-review-mcp
```

这将启动一个 Web 界面，你可以：
- 查看所有可用工具
- 手动调用工具并查看结果
- 调试参数和响应

### 本地开发调试

```bash
# 克隆仓库
git clone https://github.com/OldJii/code-review-mcp.git
cd code-review-mcp

# 安装开发依赖
pip install -e ".[dev]"

# 运行测试
pytest

# 使用 Inspector 调试
npx @modelcontextprotocol/inspector python -m code_review_mcp.server
```

## 📁 项目结构

```
code-review-mcp/
├── src/
│   └── code_review_mcp/
│       ├── __init__.py      # 包入口
│       ├── cli.py           # CLI 命令（init-rules 等）
│       ├── server.py        # MCP 服务器主逻辑
│       ├── providers.py     # GitHub/GitLab 提供者
│       └── rules/           # 内置 Cursor 规则
│           ├── code-review.mdc
│           └── code-review-en.mdc
├── pyproject.toml           # 项目配置 & PyPI 发布
├── Dockerfile               # Docker 构建文件
├── smithery.yaml            # Smithery 部署配置
├── CHANGELOG.md             # 变更日志
├── CONTRIBUTING.md          # 贡献指南
└── README.md                # 项目文档
```

## 🎯 Cursor 规则（推荐）

本包内置了 Cursor IDE 的代码审查规则，一条命令即可安装到你的项目：

```bash
# 安装规则到当前项目
code-review-mcp init-rules

# 安装到指定目录
code-review-mcp init-rules --target /path/to/project

# 覆盖已存在的规则
code-review-mcp init-rules --force

# 查看可用规则
code-review-mcp list-rules
```

安装后，规则会出现在项目的 `.cursor/rules/` 目录：
- `code-review.mdc` - 中文版
- `code-review-en.mdc` - 英文版

### 自定义项目规则

你可以定义项目专属的审查规则，MCP Server 在运行时加载。每个项目都能强制执行自己的编码标准。

**快速设置：**

```bash
# 生成自定义规则模板
code-review-mcp init-rules --custom
```

这会在项目中创建 `.code-review-rules/project-rules.md`。编辑后，配置 MCP Server 加载：

```json
{
  "mcpServers": {
    "code-review": {
      "command": "uvx",
      "args": ["code-review-mcp"],
      "env": {
        "GITHUB_TOKEN": "your-token",
        "CODE_REVIEW_RULES_DIR": "/absolute/path/to/project/.code-review-rules"
      }
    }
  }
}
```

**工作原理：**

- 设置 `CODE_REVIEW_RULES_DIR` 指向包含 `.md` 或 `.mdc` 文件的目录
- 或者直接在项目根目录放一个 `.code-review-rules/` 目录（自动发现）
- `get_review_rules` 工具同时返回内置规则和自定义规则
- AI 助手在执行审查时使用这些规则
- 自定义规则是对内置规则的补充（不是替换）

**环境变量：**

| 变量 | 说明 | 必填 |
|------|------|------|
| `CODE_REVIEW_RULES_DIR` | 自定义规则目录路径 | 否（可选） |

## 🤝 贡献

欢迎贡献！请查看 [CONTRIBUTING.md](CONTRIBUTING.md) 了解详情。

## 📄 License

[MIT](LICENSE)

## 🔗 相关链接

- [MCP 协议文档](https://modelcontextprotocol.io/)
- [Smithery 平台](https://smithery.ai/)
- [Cursor 编辑器](https://cursor.sh/)
- [Claude Desktop](https://claude.ai/desktop)
