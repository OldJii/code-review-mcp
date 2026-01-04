# Cursor AI Code Review

[English](README_EN.md) | 中文

基于 MCP (Model Context Protocol) 的代码审查工具，让 Cursor 能够读取 GitHub/GitLab 的 PR/MR 并提交审查意见。

## 项目结构

```
cursor-ai-code-review/
├── code_review_mcp.py           # MCP 服务器
└── .cursor/rules/
    ├── code-review.mdc          # 审查规范（中文）
    └── code-review-en.mdc       # 审查规范（英文）
```

## 安装

### 1. 下载项目

```bash
git clone https://github.com/user/cursor-ai-code-review.git
```

### 2. 配置认证

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

私有化部署的 GitLab：

```bash
glab auth login --hostname gitlab.yourcompany.com
```

### 3. 配置 MCP

编辑 `~/.cursor/mcp.json`（全局配置，对所有项目生效）：

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

将 `/path/to/` 替换为实际路径。

### 4. 配置审查规范（可选）

将 `.cursor/rules/` 目录下的规范文件复制到你的项目中：

```bash
cp -r /path/to/cursor-ai-code-review/.cursor/rules your-project/.cursor/
```

审查规范是项目级别的配置，需要在每个项目中单独配置。

## 使用

在 Cursor 中对话：

```
Review https://github.com/owner/repo/pull/123
```

## MCP 工具

### 获取信息

| 工具 | 说明 |
|------|------|
| `get_pr_info` | 获取 PR/MR 的标题、描述、分支等信息 |
| `get_pr_changes` | 获取代码变更（diff），支持按文件类型过滤 |
| `extract_related_prs` | 从描述中提取关联的 PR/MR 链接 |

### 添加评论

| 工具 | 说明 |
|------|------|
| `add_inline_comment` | 添加行内评论到指定代码行 |
| `add_pr_comment` | 添加整体评论 |
| `batch_add_comments` | 批量添加评论（行内+整体） |

### 参数说明

**通用参数**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `provider` | string | 是 | `github` 或 `gitlab` |
| `repo` | string | 是 | 仓库路径，如 `owner/repo` |
| `pr_id` | integer | 是 | PR/MR 编号 |
| `host` | string | 否 | GitLab 地址（私有化部署时使用） |

**get_pr_changes**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `file_extensions` | array | 否 | 文件后缀过滤，如 `[".py", ".js"]` |

**add_inline_comment**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `file_path` | string | 是 | 文件路径 |
| `line` | integer | 是 | 行号 |
| `line_type` | string | 是 | `old`（删除行）或 `new`（新增行） |
| `comment` | string | 是 | 评论内容 |

## 使用示例

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

## 自定义审查规范

项目附带的 `.cursor/rules/code-review.mdc` 是通用模板。复制到你的项目中并根据需要修改：

- 优先级定义
- 检查清单
- 评论格式
- 去重规则

针对特定语言或框架，可基于模板让 AI 生成适合你项目的版本。

中英文版本：
- `code-review.mdc` - 中文
- `code-review-en.mdc` - English

## License

MIT
