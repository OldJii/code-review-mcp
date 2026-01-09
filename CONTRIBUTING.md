# Contributing to Code Review MCP Server

Thank you for your interest in contributing! This document provides guidelines and instructions for contributing.

## Code of Conduct

Please be respectful and constructive in all interactions. We aim to foster an inclusive and welcoming community.

## Getting Started

### Development Setup

1. **Fork and clone the repository**

```bash
git clone https://github.com/OldJii/code-review-mcp.git
cd code-review-mcp
```

2. **Create a virtual environment**

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install development dependencies**

```bash
pip install -e ".[dev]"
```

4. **Set up environment variables**

```bash
export GITHUB_TOKEN="your-github-token"
export GITLAB_TOKEN="your-gitlab-token"
```

### Running Tests

```bash
pytest
```

### Running the Server Locally

```bash
# stdio mode
python -m code_review_mcp.server

# SSE mode
python -m code_review_mcp.server --transport sse --port 8000
```

### Using MCP Inspector for Debugging

```bash
npx @modelcontextprotocol/inspector python -m code_review_mcp.server
```

## How to Contribute

### Reporting Bugs

1. Check if the issue already exists in [GitHub Issues](https://github.com/OldJii/code-review-mcp/issues)
2. If not, create a new issue with:
   - Clear title and description
   - Steps to reproduce
   - Expected vs actual behavior
   - Environment details (OS, Python version, etc.)

### Suggesting Features

1. Open a GitHub Issue with the "enhancement" label
2. Describe the feature and its use case
3. Discuss with maintainers before implementing

### Submitting Pull Requests

1. **Create a branch**

```bash
git checkout -b feature/your-feature-name
# or
git checkout -b fix/your-bug-fix
```

2. **Make your changes**

- Follow the existing code style
- Add tests for new functionality
- Update documentation as needed

3. **Run quality checks**

```bash
# Format code
ruff format .

# Lint
ruff check .

# Type check
mypy src/

# Run tests
pytest
```

4. **Commit your changes**

Use clear, descriptive commit messages:

```bash
git commit -m "feat: add support for Bitbucket"
git commit -m "fix: handle empty PR description"
git commit -m "docs: update installation instructions"
```

Follow [Conventional Commits](https://www.conventionalcommits.org/) format:
- `feat:` - New features
- `fix:` - Bug fixes
- `docs:` - Documentation changes
- `refactor:` - Code refactoring
- `test:` - Test additions/changes
- `chore:` - Maintenance tasks

5. **Push and create PR**

```bash
git push origin feature/your-feature-name
```

Then create a Pull Request on GitHub with:
- Clear title and description
- Reference to related issues
- Summary of changes

## Code Style

### Python

- Use Python 3.10+ features (type hints, etc.)
- Follow PEP 8 style guide
- Use `ruff` for formatting and linting
- Add type annotations to all functions

### Documentation

- Use docstrings for all public functions/classes
- Keep README and CHANGELOG updated
- Add inline comments for complex logic

## Project Structure

```
src/code_review_mcp/
├── __init__.py      # Package exports
├── server.py        # MCP server & tools
└── providers.py     # GitHub/GitLab API providers
```

### Adding a New Provider

1. Create a new class in `providers.py` extending `CodeReviewProvider`
2. Implement all required methods
3. Add provider to `get_provider()` in `server.py`
4. Update documentation

### Adding a New Tool

1. Add tool definition to `TOOLS` list in `server.py`
2. Add handler logic in `call_tool()` function
3. Update README with tool documentation

## Release Process

1. Update version in `pyproject.toml` and `__init__.py`
2. Update `CHANGELOG.md`
3. Create a PR with version bump
4. After merge, create a GitHub release
5. Package is automatically published to PyPI

## Questions?

Feel free to:
- Open a GitHub Issue for questions
- Start a Discussion on GitHub
- Reach out to maintainers

Thank you for contributing! 🎉
