"""
Code Review Providers for GitHub and GitLab.

Handles API communication with GitHub and GitLab for PR/MR operations.
"""

import os
import re
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import httpx


class CodeReviewProvider(ABC):
    """Abstract base class for code review providers."""

    @abstractmethod
    async def get_pr_info(self, repo: str, pr_id: int) -> dict[str, Any]:
        """Get PR/MR information."""
        pass

    @abstractmethod
    async def get_pr_changes(
        self, repo: str, pr_id: int, file_extensions: list[str] | None = None
    ) -> dict[str, Any]:
        """Get PR/MR code changes."""
        pass

    @abstractmethod
    async def add_inline_comment(
        self,
        repo: str,
        pr_id: int,
        file_path: str,
        line: int,
        line_type: str,
        comment: str,
    ) -> dict[str, Any]:
        """Add inline comment to specific line."""
        pass

    @abstractmethod
    async def add_pr_comment(self, repo: str, pr_id: int, comment: str) -> dict[str, Any]:
        """Add general PR/MR comment."""
        pass


class GitLabProvider(CodeReviewProvider):
    """GitLab MR review provider."""

    def __init__(self, host: str | None = None, token: str | None = None):
        self.host = host or os.environ.get("GITLAB_HOST", "gitlab.com")
        self.token = token or os.environ.get("GITLAB_TOKEN") or self._get_token_from_glab()
        if not self.token:
            raise ValueError(
                f"GitLab token not configured. Set GITLAB_TOKEN environment variable "
                f"or run: glab auth login --hostname {self.host}"
            )
        self._client: httpx.AsyncClient | None = None

    def _get_token_from_glab(self) -> str:
        """Get token from glab CLI config."""
        config_paths = [
            Path.home() / ".config" / "glab-cli" / "config.yml",
            Path.home() / "Library" / "Application Support" / "glab-cli" / "config.yml",
        ]

        for config_path in config_paths:
            if config_path.exists():
                content = config_path.read_text()
                pattern = rf"{re.escape(self.host)}:.*?token:\s*([^\s\n]+)"
                match = re.search(pattern, content, re.DOTALL)
                if match:
                    return match.group(1).strip()
        return ""

    @property
    def client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=f"https://{self.host}/api/v4",
                headers={
                    "PRIVATE-TOKEN": self.token,
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )
        return self._client

    async def _call_api(
        self,
        project_id: str,
        endpoint: str,
        method: str = "GET",
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any] | list[Any] | None:
        """Call GitLab API."""
        url = f"/projects/{project_id}/{endpoint}"
        try:
            if method == "GET":
                response = await self.client.get(url)
            else:
                response = await self.client.post(url, json=data)
            response.raise_for_status()
            result: dict[str, Any] | list[Any] = response.json()
            return result
        except httpx.HTTPError:
            return None

    async def get_pr_info(self, repo: str, pr_id: int) -> dict[str, Any]:
        """Get MR information."""
        project_id = repo.replace("/", "%2F")
        mr_info = await self._call_api(project_id, f"merge_requests/{pr_id}")

        if not mr_info or isinstance(mr_info, list):
            return {"error": "Failed to get MR info"}

        return {
            "id": mr_info.get("id"),
            "iid": mr_info.get("iid"),
            "title": mr_info.get("title"),
            "description": mr_info.get("description", ""),
            "author": mr_info.get("author", {}).get("name"),
            "web_url": mr_info.get("web_url"),
            "source_branch": mr_info.get("source_branch"),
            "target_branch": mr_info.get("target_branch"),
            "state": mr_info.get("state"),
            "diff_refs": mr_info.get("diff_refs", {}),
        }

    async def get_pr_changes(
        self, repo: str, pr_id: int, file_extensions: list[str] | None = None
    ) -> dict[str, Any]:
        """Get MR code changes."""
        project_id = repo.replace("/", "%2F")
        changes = await self._call_api(project_id, f"merge_requests/{pr_id}/changes")

        if not changes or isinstance(changes, list):
            return {"error": "Failed to get changes"}

        filtered_changes = []
        for change in changes.get("changes", []):
            file_path = change.get("new_path", "")
            if file_extensions and not any(file_path.endswith(ext) for ext in file_extensions):
                continue
            filtered_changes.append(
                {
                    "file_path": file_path,
                    "diff": change.get("diff", ""),
                    "new_file": change.get("new_file", False),
                    "deleted_file": change.get("deleted_file", False),
                }
            )

        return {
            "title": changes.get("title"),
            "changes": filtered_changes,
            "total_files": len(filtered_changes),
        }

    def _find_line_code(self, diff: str, target_line: int, line_type: str, head_sha: str) -> str:
        """Find line_code from diff for GitLab API."""
        lines = diff.split("\n")
        old_line = 0
        new_line = 0

        for line in lines:
            if line.startswith("@@"):
                match = re.match(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", line)
                if match:
                    old_line = int(match.group(1)) - 1
                    new_line = int(match.group(2)) - 1
            elif line.startswith("-"):
                old_line += 1
                if line_type == "old" and old_line == target_line:
                    return f"{head_sha}_{old_line}_"
            elif line.startswith("+"):
                new_line += 1
                if line_type == "new" and new_line == target_line:
                    return f"{head_sha}_{old_line}_{new_line}"
            else:
                old_line += 1
                new_line += 1

        return ""

    async def add_inline_comment(
        self,
        repo: str,
        pr_id: int,
        file_path: str,
        line: int,
        line_type: str,
        comment: str,
    ) -> dict[str, Any]:
        """Add inline comment."""
        project_id = repo.replace("/", "%2F")
        mr_info = await self._call_api(project_id, f"merge_requests/{pr_id}")

        if not mr_info or isinstance(mr_info, list):
            return {"success": False, "error": "Failed to get MR info"}

        changes = await self._call_api(project_id, f"merge_requests/{pr_id}/changes")
        if not changes or isinstance(changes, list):
            return {"success": False, "error": "Failed to get MR changes"}

        target_diff = None
        for change in changes.get("changes", []):
            if change.get("new_path") == file_path or change.get("old_path") == file_path:
                target_diff = change.get("diff", "")
                break

        if not target_diff:
            return {"success": False, "error": f"File not found: {file_path}"}

        line_code = self._find_line_code(
            target_diff, line, line_type, mr_info.get("diff_refs", {}).get("head_sha", "")
        )
        if not line_code:
            return {"success": False, "error": f"Cannot locate line {line}"}

        diff_refs = mr_info.get("diff_refs", {})
        position: dict[str, Any] = {
            "base_sha": diff_refs.get("base_sha"),
            "head_sha": diff_refs.get("head_sha"),
            "start_sha": diff_refs.get("start_sha"),
            "position_type": "text",
            "old_path": file_path,
            "new_path": file_path,
            "line_code": line_code,
        }

        if line_type == "old":
            position["old_line"] = line
        else:
            position["new_line"] = line

        data = {"body": comment, "position": position}
        result = await self._call_api(
            project_id, f"merge_requests/{pr_id}/discussions", method="POST", data=data
        )

        if result and isinstance(result, dict) and result.get("id"):
            note_id = result.get("notes", [{}])[0].get("id")
            return {
                "success": True,
                "discussion_id": result.get("id"),
                "note_id": note_id,
                "url": f"{mr_info.get('web_url')}#note_{note_id}",
            }

        error_msg = (
            result.get("message", "Failed to add comment")
            if isinstance(result, dict)
            else "Failed to add comment"
        )
        return {"success": False, "error": error_msg}

    async def add_pr_comment(self, repo: str, pr_id: int, comment: str) -> dict[str, Any]:
        """Add general MR comment."""
        project_id = repo.replace("/", "%2F")
        data = {"body": comment}
        result = await self._call_api(
            project_id, f"merge_requests/{pr_id}/notes", method="POST", data=data
        )

        if result and isinstance(result, dict) and result.get("id"):
            return {"success": True, "note_id": result.get("id")}
        return {"success": False, "error": "Failed to add comment"}


class GitHubProvider(CodeReviewProvider):
    """GitHub PR review provider."""

    def __init__(self, token: str | None = None):
        self.token = token or os.environ.get("GITHUB_TOKEN") or self._get_token_from_gh()
        if not self.token:
            raise ValueError(
                "GitHub token not configured. Set GITHUB_TOKEN environment variable "
                "or run: gh auth login"
            )
        self._client: httpx.AsyncClient | None = None

    def _get_token_from_gh(self) -> str:
        """Get token from gh CLI."""
        try:
            result = subprocess.run(
                ["gh", "auth", "token"], capture_output=True, text=True, check=False
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except FileNotFoundError:
            pass
        return ""

    @property
    def client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url="https://api.github.com",
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/vnd.github.v3+json",
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )
        return self._client

    async def _call_api(
        self,
        endpoint: str,
        method: str = "GET",
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any] | list[Any] | None:
        """Call GitHub API."""
        try:
            if method == "GET":
                response = await self.client.get(endpoint)
            else:
                response = await self.client.post(endpoint, json=data)
            response.raise_for_status()
            result: dict[str, Any] | list[Any] = response.json()
            return result
        except httpx.HTTPError:
            return None

    async def get_pr_info(self, repo: str, pr_id: int) -> dict[str, Any]:
        """Get PR information."""
        pr_info = await self._call_api(f"/repos/{repo}/pulls/{pr_id}")

        if not pr_info or isinstance(pr_info, list):
            return {"error": "Failed to get PR info"}

        if pr_info.get("message"):
            return {"error": pr_info.get("message")}

        return {
            "id": pr_info.get("id"),
            "number": pr_info.get("number"),
            "title": pr_info.get("title"),
            "description": pr_info.get("body", ""),
            "author": pr_info.get("user", {}).get("login"),
            "web_url": pr_info.get("html_url"),
            "source_branch": pr_info.get("head", {}).get("ref"),
            "target_branch": pr_info.get("base", {}).get("ref"),
            "state": pr_info.get("state"),
            "head_sha": pr_info.get("head", {}).get("sha"),
            "base_sha": pr_info.get("base", {}).get("sha"),
        }

    async def get_pr_changes(
        self, repo: str, pr_id: int, file_extensions: list[str] | None = None
    ) -> dict[str, Any]:
        """Get PR code changes."""
        files = await self._call_api(f"/repos/{repo}/pulls/{pr_id}/files")

        if not files or isinstance(files, dict):
            return {"error": "Failed to get changes"}

        filtered_changes = []
        for file in files:
            file_path = file.get("filename", "")
            if file_extensions and not any(file_path.endswith(ext) for ext in file_extensions):
                continue
            filtered_changes.append(
                {
                    "file_path": file_path,
                    "diff": file.get("patch", ""),
                    "new_file": file.get("status") == "added",
                    "deleted_file": file.get("status") == "removed",
                    "sha": file.get("sha"),
                }
            )

        pr_info = await self._call_api(f"/repos/{repo}/pulls/{pr_id}")

        return {
            "title": pr_info.get("title") if isinstance(pr_info, dict) else "",
            "changes": filtered_changes,
            "total_files": len(filtered_changes),
        }

    async def add_inline_comment(
        self,
        repo: str,
        pr_id: int,
        file_path: str,
        line: int,
        line_type: str,
        comment: str,
    ) -> dict[str, Any]:
        """Add inline comment using PR review comments API."""
        pr_info = await self._call_api(f"/repos/{repo}/pulls/{pr_id}")
        if not pr_info or isinstance(pr_info, list):
            return {"success": False, "error": "Failed to get PR info"}

        commit_sha = pr_info.get("head", {}).get("sha")

        data = {
            "body": comment,
            "commit_id": commit_sha,
            "path": file_path,
            "line": line,
            "side": "RIGHT" if line_type == "new" else "LEFT",
        }

        result = await self._call_api(
            f"/repos/{repo}/pulls/{pr_id}/comments", method="POST", data=data
        )

        if result and isinstance(result, dict) and result.get("id"):
            return {
                "success": True,
                "comment_id": result.get("id"),
                "url": result.get("html_url"),
            }

        error_msg = (
            result.get("message", "Failed to add comment")
            if isinstance(result, dict)
            else "Failed to add comment"
        )
        return {"success": False, "error": error_msg}

    async def add_pr_comment(self, repo: str, pr_id: int, comment: str) -> dict[str, Any]:
        """Add general PR comment."""
        data = {"body": comment}
        result = await self._call_api(
            f"/repos/{repo}/issues/{pr_id}/comments", method="POST", data=data
        )

        if result and isinstance(result, dict) and result.get("id"):
            return {
                "success": True,
                "comment_id": result.get("id"),
                "url": result.get("html_url"),
            }
        return {"success": False, "error": "Failed to add comment"}
