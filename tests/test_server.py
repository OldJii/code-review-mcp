"""Tests for Code Review MCP Server."""

import tempfile
from pathlib import Path

from code_review_mcp.server import TOOLS, _load_rules, extract_related_prs


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
            assert tool.inputSchema, "Tool must have an inputSchema"
            assert "type" in tool.inputSchema
            assert tool.inputSchema["type"] == "object"

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
            "add_inline_comment",
            "add_pr_comment",
            "batch_add_comments",
            "extract_related_prs",
        }
        actual_tools = {tool.name for tool in TOOLS}
        assert expected_tools == actual_tools


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
