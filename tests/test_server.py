"""Tests for Code Review MCP Server."""

import json
import tempfile
from pathlib import Path

import pytest
from mcp.types import CallToolRequestParams

from code_review_mcp.providers import ProviderError, _classify_http_error
from code_review_mcp.server import (
    TOOL_HANDLERS,
    TOOLS,
    _handle_call_tool,
    _handle_list_tools,
    _load_rules,
    extract_related_prs,
)


class TestExtractRelatedPRs:
    """Tests for extract_related_prs function."""

    def test_extract_github_prs(self) -> None:
        """Test extracting GitHub PR links."""
        description = """
        Related PRs:
        - https://github.com/owner/repo/pull/123
        - https://github.com/another/project/pull/456
        """
        result = extract_related_prs("github", description)
        assert len(result) == 2
        assert result[0] == {"repo": "owner/repo", "pr_id": 123}
        assert result[1] == {"repo": "another/project", "pr_id": 456}

    def test_extract_gitlab_mrs(self) -> None:
        """Test extracting GitLab MR links."""
        description = """
        Related MRs:
        - https://gitlab.com/group/project/-/merge_requests/789
        - https://gitlab.com/another/repo/merge_requests/101
        """
        result = extract_related_prs("gitlab", description)
        assert len(result) == 2
        assert result[0] == {"repo": "group/project", "pr_id": 789}
        assert result[1] == {"repo": "another/repo", "pr_id": 101}

    def test_extract_self_hosted_gitlab(self) -> None:
        """Test extracting self-hosted GitLab MR links."""
        description = "See https://gitlab.company.com/team/app/-/merge_requests/42"
        result = extract_related_prs("gitlab", description, host="gitlab.company.com")
        assert len(result) == 1
        assert result[0] == {"repo": "team/app", "pr_id": 42}

    def test_empty_description(self) -> None:
        """Test with empty description."""
        assert extract_related_prs("github", "") == []
        assert extract_related_prs("github", None) == []  # type: ignore

    def test_no_matches(self) -> None:
        """Test description with no PR links."""
        description = "This is a regular description without any links."
        assert extract_related_prs("github", description) == []
        assert extract_related_prs("gitlab", description) == []


class TestToolDefinitions:
    """Tests for tool definitions."""

    def test_all_tools_have_required_fields(self) -> None:
        """Test that all tools have required fields."""
        for tool in TOOLS:
            assert tool.name, "Tool must have a name"
            assert tool.description, "Tool must have a description"
            assert tool.input_schema, "Tool must have an input_schema"
            assert "type" in tool.input_schema
            assert tool.input_schema["type"] == "object"

    def test_tool_names_are_unique(self) -> None:
        """Test that all tool names are unique."""
        names = [tool.name for tool in TOOLS]
        assert len(names) == len(set(names)), "Tool names must be unique"

    def test_expected_tools_exist(self) -> None:
        """Test that expected tools are defined."""
        expected_tools = {
            "get_review_rules",
            "get_pr_info",
            "get_pr_changes",
            "list_pr_comments",
            "get_file_content",
            "get_pr_commits",
            "add_inline_comment",
            "add_pr_comment",
            "batch_add_comments",
            "resolve_discussion",
            "submit_review",
            "extract_related_prs",
        }
        actual_tools = {tool.name for tool in TOOLS}
        assert expected_tools == actual_tools

    def test_tools_and_handlers_in_sync(self) -> None:
        """Every tool in TOOLS must have a handler in TOOL_HANDLERS and vice versa."""
        tool_names = {tool.name for tool in TOOLS}
        handler_names = set(TOOL_HANDLERS.keys())
        assert tool_names == handler_names, (
            f"Mismatch: tools without handlers={tool_names - handler_names}, "
            f"handlers without tools={handler_names - tool_names}"
        )


class TestLoadRules:
    """Tests for _load_rules function."""

    def test_load_builtin_rules(self) -> None:
        """Test loading builtin rules."""
        rules = _load_rules(include_builtin=True)
        assert len(rules) >= 2
        assert all(r["source"] == "builtin" for r in rules)

    def test_load_builtin_rules_zh(self) -> None:
        """Test loading only Chinese builtin rules."""
        rules = _load_rules(include_builtin=True, lang="zh")
        assert len(rules) >= 1
        assert all(not r["name"].endswith("-en") for r in rules)

    def test_load_builtin_rules_en(self) -> None:
        """Test loading only English builtin rules."""
        rules = _load_rules(include_builtin=True, lang="en")
        assert len(rules) >= 1
        assert all(r["name"].endswith("-en") for r in rules)

    def test_load_custom_rules(self) -> None:
        """Test loading custom rules from a directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            rule_file = Path(tmpdir) / "my-rules.md"
            rule_file.write_text("# My Custom Rules\n\nTest content.")

            rules = _load_rules(include_builtin=False, custom_rules_dir=tmpdir)
            assert len(rules) == 1
            assert rules[0]["name"] == "my-rules"
            assert rules[0]["source"] == "custom"
            assert "Test content" in rules[0]["content"]

    def test_load_both_builtin_and_custom(self) -> None:
        """Test loading both builtin and custom rules."""
        with tempfile.TemporaryDirectory() as tmpdir:
            rule_file = Path(tmpdir) / "project.md"
            rule_file.write_text("# Project Rules")

            rules = _load_rules(include_builtin=True, custom_rules_dir=tmpdir)
            sources = {r["source"] for r in rules}
            assert "builtin" in sources
            assert "custom" in sources

    def test_no_custom_dir(self) -> None:
        """Test with no custom rules directory."""
        rules = _load_rules(include_builtin=False, custom_rules_dir=None)
        assert rules == []

    def test_nonexistent_custom_dir(self) -> None:
        """Test with nonexistent custom rules directory."""
        rules = _load_rules(include_builtin=False, custom_rules_dir="/nonexistent/path")
        assert rules == []


class TestProviderError:
    """Tests for ProviderError and HTTP error classification."""

    def test_provider_error_fields(self) -> None:
        err = ProviderError("test error", status_code=401, error_type="auth")
        assert str(err) == "test error"
        assert err.status_code == 401
        assert err.error_type == "auth"

    def test_provider_error_defaults(self) -> None:
        err = ProviderError("msg")
        assert err.status_code is None
        assert err.error_type == "unknown"

    @pytest.mark.parametrize(
        "code,expected",
        [
            (401, "auth"),
            (403, "forbidden"),
            (404, "not_found"),
            (422, "validation"),
            (429, "rate_limit"),
            (500, "server"),
            (503, "server"),
            (418, "http"),
        ],
    )
    def test_classify_http_error(self, code: int, expected: str) -> None:
        assert _classify_http_error(code) == expected


class TestMcpHandlers:
    """Tests for MCP protocol handlers."""

    @pytest.mark.asyncio
    async def test_list_tools_returns_all(self) -> None:
        result = await _handle_list_tools(None, None)  # type: ignore[arg-type]
        assert len(result.tools) == len(TOOLS)

    @pytest.mark.asyncio
    async def test_call_unknown_tool(self) -> None:
        params = CallToolRequestParams(name="nonexistent_tool", arguments={})
        result = await _handle_call_tool(None, params)  # type: ignore[arg-type]
        assert result.is_error is True
        body = json.loads(result.content[0].text)
        assert body["error_type"] == "unknown_tool"
        assert "nonexistent_tool" in body["error"]

    @pytest.mark.asyncio
    async def test_call_get_review_rules(self) -> None:
        params = CallToolRequestParams(
            name="get_review_rules", arguments={"include_builtin": True, "lang": "en"}
        )
        result = await _handle_call_tool(None, params)  # type: ignore[arg-type]
        assert result.is_error is not True
        rules = json.loads(result.content[0].text)
        assert isinstance(rules, list)
        assert len(rules) >= 1

    @pytest.mark.asyncio
    async def test_call_extract_related_prs(self) -> None:
        params = CallToolRequestParams(
            name="extract_related_prs",
            arguments={
                "provider": "github",
                "description": "See https://github.com/foo/bar/pull/42",
            },
        )
        result = await _handle_call_tool(None, params)  # type: ignore[arg-type]
        assert result.is_error is not True
        data = json.loads(result.content[0].text)
        assert data == [{"repo": "foo/bar", "pr_id": 42}]

    @pytest.mark.asyncio
    async def test_call_missing_required_arg(self) -> None:
        params = CallToolRequestParams(
            name="get_pr_info", arguments={"provider": "github"}
        )
        result = await _handle_call_tool(None, params)  # type: ignore[arg-type]
        assert result.is_error is True
        body = json.loads(result.content[0].text)
        assert body["error_type"] in ("validation", "internal", "auth")


class TestVersionConsistency:
    """Ensure version is consistent across files."""

    def test_version_match(self) -> None:
        from code_review_mcp import __version__

        toml_path = Path(__file__).parent.parent / "pyproject.toml"
        content = toml_path.read_text()
        import re as re_mod
        match = re_mod.search(r'^version\s*=\s*"([^"]+)"', content, re_mod.MULTILINE)
        assert match, "version not found in pyproject.toml"
        assert __version__ == match.group(1)
