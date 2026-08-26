"""
Code Review Providers for GitHub and GitLab.

Handles API communication with GitHub and GitLab for PR/MR operations.
"""

import asyncio
import logging
import os
import re
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger("code-review-mcp")

MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.0


class ProviderError(Exception):
    """Structured error from a code review provider."""

    def __init__(self, message: str, status_code: int | None = None, error_type: str = "unknown"):
        super().__init__(message)
        self.status_code = status_code
        self.error_type = error_type


async def _retry_request(
    func: Any,
    *args: Any,
    **kwargs: Any,
) -> httpx.Response:
    """Execute an HTTP request with retry + exponential backoff."""
    last_exc: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            response = await func(*args, **kwargs)
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", RETRY_BASE_DELAY * (2 ** attempt)))
                logger.warning("Rate limited (429), retrying after %ds (attempt %d/%d)", retry_after, attempt + 1, MAX_RETRIES)
                await asyncio.sleep(min(retry_after, 60))
                continue
            return response
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout) as e:
            last_exc = e
            delay = RETRY_BASE_DELAY * (2 ** attempt)
            logger.warning("Network error: %s, retrying in %.1fs (attempt %d/%d)", e, delay, attempt + 1, MAX_RETRIES)
            await asyncio.sleep(delay)
    raise last_exc or httpx.ConnectError("Max retries exceeded")


class CodeReviewProvider(ABC):
    """Abstract base class for code review providers."""

    @abstractmethod
    async def get_pr_info(self, repo: str, pr_id: int) -> dict[str, Any]:
        """Get PR/MR information."""

    @abstractmethod
    async def get_pr_changes(
        self, repo: str, pr_id: int, file_extensions: list[str] | None = None
    ) -> dict[str, Any]:
        """Get PR/MR code changes."""

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

    @abstractmethod
    async def add_pr_comment(self, repo: str, pr_id: int, comment: str) -> dict[str, Any]:
        """Add general PR/MR comment."""

    @abstractmethod
    async def list_comments(self, repo: str, pr_id: int) -> dict[str, Any]:
        """List existing comments on PR/MR."""

    @abstractmethod
    async def get_file_content(
        self, repo: str, file_path: str, ref: str | None = None
    ) -> dict[str, Any]:
        """Get file content from repository."""

    @abstractmethod
    async def get_pr_commits(self, repo: str, pr_id: int) -> dict[str, Any]:
        """Get commits in PR/MR."""

    @abstractmethod
    async def resolve_discussion(self, repo: str, pr_id: int, discussion_id: str) -> dict[str, Any]:
        """Resolve a discussion/thread."""

    @abstractmethod
    async def submit_review(
        self, repo: str, pr_id: int, action: str, body: str | None = None
    ) -> dict[str, Any]:
        """Submit a formal review (approve/request_changes)."""

    async def close(self) -> None:  # noqa: B027
        """Close HTTP client. Override in subclasses."""


class GitLabProvider(CodeReviewProvider):
    """GitLab MR review provider."""

    def __init__(self, host: str | None = None, token: str | None = None):
        self.host = host or os.environ.get("GITLAB_HOST", "gitlab.com")
        self.token = token or os.environ.get("GITLAB_TOKEN") or self._get_token_from_glab()
        if not self.token:
            raise ProviderError(
                f"GitLab token not configured. Set GITLAB_TOKEN environment variable "
                f"or run: glab auth login --hostname {self.host}",
                error_type="auth",
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

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def _call_api(
        self,
        project_id: str,
        endpoint: str,
        method: str = "GET",
        data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any] | list[Any]:
        url = f"/projects/{project_id}/{endpoint}"
        try:
            if method == "GET":
                response = await _retry_request(self.client.get, url, params=params)
            elif method == "PUT":
                response = await _retry_request(self.client.put, url, json=data)
            else:
                response = await _retry_request(self.client.post, url, json=data)
            response.raise_for_status()
            result: dict[str, Any] | list[Any] = response.json()
            return result
        except httpx.HTTPStatusError as e:
            error_body = ""
            try:
                error_body = e.response.json().get("message", e.response.text[:200])
            except Exception:
                error_body = e.response.text[:200]
            raise ProviderError(
                f"GitLab API error ({e.response.status_code}): {error_body}",
                status_code=e.response.status_code,
                error_type=_classify_http_error(e.response.status_code),
            ) from e
        except httpx.TimeoutException as e:
            raise ProviderError(f"Request timeout: {url}", error_type="timeout") from e
        except httpx.ConnectError as e:
            raise ProviderError(f"Connection failed: {e}", error_type="network") from e

    async def _get_all_pages(
        self,
        project_id: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> list[Any]:
        """Fetch all pages of a paginated GitLab API endpoint."""
        all_items: list[Any] = []
        page = 1
        per_page = 100
        p = dict(params or {})
        p["per_page"] = per_page
        while True:
            p["page"] = page
            url = f"/projects/{project_id}/{endpoint}"
            response = await _retry_request(self.client.get, url, params=p)
            response.raise_for_status()
            items = response.json()
            if not isinstance(items, list) or not items:
                break
            all_items.extend(items)
            if len(items) < per_page:
                break
            page += 1
        return all_items

    async def get_pr_info(self, repo: str, pr_id: int) -> dict[str, Any]:
        project_id = repo.replace("/", "%2F")
        mr_info = await self._call_api(project_id, f"merge_requests/{pr_id}")

        if isinstance(mr_info, list):
            raise ProviderError("Unexpected list response for MR info", error_type="api")

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
        project_id = repo.replace("/", "%2F")
        changes = await self._call_api(project_id, f"merge_requests/{pr_id}/changes")

        if isinstance(changes, list):
            raise ProviderError("Unexpected list response for MR changes", error_type="api")

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
        project_id = repo.replace("/", "%2F")
        mr_info = await self._call_api(project_id, f"merge_requests/{pr_id}")

        if isinstance(mr_info, list):
            return {"success": False, "error": "Failed to get MR info"}

        changes = await self._call_api(project_id, f"merge_requests/{pr_id}/changes")
        if isinstance(changes, list):
            return {"success": False, "error": "Failed to get MR changes"}

        target_diff = None
        for change in changes.get("changes", []):
            if change.get("new_path") == file_path or change.get("old_path") == file_path:
                target_diff = change.get("diff", "")
                break

        if not target_diff:
            return {"success": False, "error": f"File not found in diff: {file_path}"}

        line_code = self._find_line_code(
            target_diff, line, line_type, mr_info.get("diff_refs", {}).get("head_sha", "")
        )
        if not line_code:
            return {"success": False, "error": f"Cannot locate line {line} ({line_type}) in diff"}

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

        if isinstance(result, dict) and result.get("id"):
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
        project_id = repo.replace("/", "%2F")
        data = {"body": comment}
        result = await self._call_api(
            project_id, f"merge_requests/{pr_id}/notes", method="POST", data=data
        )

        if isinstance(result, dict) and result.get("id"):
            return {"success": True, "note_id": result.get("id")}
        return {"success": False, "error": "Failed to add comment"}

    async def list_comments(self, repo: str, pr_id: int) -> dict[str, Any]:
        project_id = repo.replace("/", "%2F")
        discussions = await self._get_all_pages(
            project_id, f"merge_requests/{pr_id}/discussions"
        )
        comments: list[dict[str, Any]] = []
        for disc in discussions:
            for note in disc.get("notes", []):
                if note.get("system"):
                    continue
                comments.append({
                    "id": note.get("id"),
                    "discussion_id": disc.get("id"),
                    "author": note.get("author", {}).get("name"),
                    "body": note.get("body"),
                    "created_at": note.get("created_at"),
                    "resolved": note.get("resolved", False),
                    "position": _simplify_position(note.get("position")),
                })
        return {"comments": comments, "total": len(comments)}

    async def get_file_content(
        self, repo: str, file_path: str, ref: str | None = None
    ) -> dict[str, Any]:
        project_id = repo.replace("/", "%2F")
        encoded_path = file_path.replace("/", "%2F")
        params: dict[str, Any] = {}
        if ref:
            params["ref"] = ref
        result = await self._call_api(
            project_id, f"repository/files/{encoded_path}", params=params
        )
        if isinstance(result, list):
            raise ProviderError("Unexpected response for file content", error_type="api")

        import base64
        content_b64 = result.get("content", "")
        try:
            content = base64.b64decode(content_b64).decode("utf-8")
        except Exception:
            content = content_b64

        return {
            "file_path": result.get("file_path", file_path),
            "content": content,
            "size": result.get("size"),
            "encoding": result.get("encoding"),
            "ref": result.get("ref", ref),
        }

    async def get_pr_commits(self, repo: str, pr_id: int) -> dict[str, Any]:
        project_id = repo.replace("/", "%2F")
        commits = await self._get_all_pages(
            project_id, f"merge_requests/{pr_id}/commits"
        )
        return {
            "commits": [
                {
                    "sha": c.get("id"),
                    "short_sha": c.get("short_id"),
                    "title": c.get("title"),
                    "message": c.get("message"),
                    "author": c.get("author_name"),
                    "created_at": c.get("created_at"),
                }
                for c in commits
            ],
            "total": len(commits),
        }

    async def resolve_discussion(
        self, repo: str, pr_id: int, discussion_id: str
    ) -> dict[str, Any]:
        project_id = repo.replace("/", "%2F")
        result = await self._call_api(
            project_id,
            f"merge_requests/{pr_id}/discussions/{discussion_id}",
            method="PUT",
            data={"resolved": True},
        )
        if isinstance(result, dict) and result.get("id"):
            return {"success": True, "discussion_id": result.get("id")}
        return {"success": False, "error": "Failed to resolve discussion"}

    async def submit_review(
        self, repo: str, pr_id: int, action: str, body: str | None = None
    ) -> dict[str, Any]:
        project_id = repo.replace("/", "%2F")
        if action == "approve":
            result = await self._call_api(
                project_id, f"merge_requests/{pr_id}/approve", method="POST"
            )
            if isinstance(result, dict):
                return {"success": True, "action": "approved"}
            return {"success": False, "error": "Failed to approve"}
        elif action == "unapprove":
            result = await self._call_api(
                project_id, f"merge_requests/{pr_id}/unapprove", method="POST"
            )
            if isinstance(result, dict):
                return {"success": True, "action": "unapproved"}
            return {"success": False, "error": "Failed to unapprove"}
        else:
            return {"success": False, "error": f"Unsupported action for GitLab: {action}"}


class GitHubProvider(CodeReviewProvider):
    """GitHub PR review provider."""

    def __init__(self, token: str | None = None):
        self.token = token or os.environ.get("GITHUB_TOKEN") or self._get_token_from_gh()
        if not self.token:
            raise ProviderError(
                "GitHub token not configured. Set GITHUB_TOKEN environment variable "
                "or run: gh auth login",
                error_type="auth",
            )
        self._client: httpx.AsyncClient | None = None

    def _get_token_from_gh(self) -> str:
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

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def _call_api(
        self,
        endpoint: str,
        method: str = "GET",
        data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any] | list[Any]:
        try:
            if method == "GET":
                response = await _retry_request(self.client.get, endpoint, params=params)
            elif method == "PUT":
                response = await _retry_request(self.client.put, endpoint, json=data)
            else:
                response = await _retry_request(self.client.post, endpoint, json=data)
            response.raise_for_status()
            if response.status_code == 204:
                return {"success": True}
            result: dict[str, Any] | list[Any] = response.json()
            return result
        except httpx.HTTPStatusError as e:
            error_body = ""
            try:
                error_body = e.response.json().get("message", e.response.text[:200])
            except Exception:
                error_body = e.response.text[:200]
            raise ProviderError(
                f"GitHub API error ({e.response.status_code}): {error_body}",
                status_code=e.response.status_code,
                error_type=_classify_http_error(e.response.status_code),
            ) from e
        except httpx.TimeoutException as e:
            raise ProviderError(f"Request timeout: {endpoint}", error_type="timeout") from e
        except httpx.ConnectError as e:
            raise ProviderError(f"Connection failed: {e}", error_type="network") from e

    async def _get_all_pages(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> list[Any]:
        """Fetch all pages of a paginated GitHub API endpoint."""
        all_items: list[Any] = []
        page = 1
        per_page = 100
        p = dict(params or {})
        p["per_page"] = per_page
        while True:
            p["page"] = page
            response = await _retry_request(self.client.get, endpoint, params=p)
            response.raise_for_status()
            items = response.json()
            if not isinstance(items, list) or not items:
                break
            all_items.extend(items)
            if len(items) < per_page:
                break
            page += 1
        return all_items

    async def get_pr_info(self, repo: str, pr_id: int) -> dict[str, Any]:
        pr_info = await self._call_api(f"/repos/{repo}/pulls/{pr_id}")

        if isinstance(pr_info, list):
            raise ProviderError("Unexpected list response for PR info", error_type="api")

        if pr_info.get("message"):
            raise ProviderError(
                f"GitHub API: {pr_info['message']}",
                status_code=404 if "not found" in str(pr_info["message"]).lower() else None,
                error_type="not_found" if "not found" in str(pr_info["message"]).lower() else "api",
            )

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
        files = await self._get_all_pages(f"/repos/{repo}/pulls/{pr_id}/files")

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
                    "additions": file.get("additions", 0),
                    "deletions": file.get("deletions", 0),
                    "sha": file.get("sha"),
                }
            )

        return {
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
        pr_info = await self._call_api(f"/repos/{repo}/pulls/{pr_id}")
        if isinstance(pr_info, list):
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

        if isinstance(result, dict) and result.get("id"):
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
        data = {"body": comment}
        result = await self._call_api(
            f"/repos/{repo}/issues/{pr_id}/comments", method="POST", data=data
        )

        if isinstance(result, dict) and result.get("id"):
            return {
                "success": True,
                "comment_id": result.get("id"),
                "url": result.get("html_url"),
            }
        return {"success": False, "error": "Failed to add comment"}

    async def list_comments(self, repo: str, pr_id: int) -> dict[str, Any]:
        review_comments = await self._get_all_pages(f"/repos/{repo}/pulls/{pr_id}/comments")
        issue_comments = await self._get_all_pages(f"/repos/{repo}/issues/{pr_id}/comments")

        comments: list[dict[str, Any]] = []
        for c in review_comments:
            comments.append({
                "id": c.get("id"),
                "type": "inline",
                "author": c.get("user", {}).get("login"),
                "body": c.get("body"),
                "created_at": c.get("created_at"),
                "file_path": c.get("path"),
                "line": c.get("line") or c.get("original_line"),
                "url": c.get("html_url"),
            })
        for c in issue_comments:
            comments.append({
                "id": c.get("id"),
                "type": "general",
                "author": c.get("user", {}).get("login"),
                "body": c.get("body"),
                "created_at": c.get("created_at"),
                "url": c.get("html_url"),
            })

        comments.sort(key=lambda x: x.get("created_at", ""))
        return {"comments": comments, "total": len(comments)}

    async def get_file_content(
        self, repo: str, file_path: str, ref: str | None = None
    ) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if ref:
            params["ref"] = ref
        result = await self._call_api(
            f"/repos/{repo}/contents/{file_path}", params=params
        )
        if isinstance(result, list):
            raise ProviderError("Path is a directory, not a file", error_type="api")

        import base64
        content_b64 = result.get("content", "")
        try:
            content = base64.b64decode(content_b64).decode("utf-8")
        except Exception:
            content = content_b64

        return {
            "file_path": result.get("path", file_path),
            "content": content,
            "size": result.get("size"),
            "encoding": result.get("encoding"),
            "sha": result.get("sha"),
            "ref": ref,
        }

    async def get_pr_commits(self, repo: str, pr_id: int) -> dict[str, Any]:
        commits = await self._get_all_pages(f"/repos/{repo}/pulls/{pr_id}/commits")
        return {
            "commits": [
                {
                    "sha": c.get("sha"),
                    "short_sha": c.get("sha", "")[:7],
                    "title": c.get("commit", {}).get("message", "").split("\n")[0],
                    "message": c.get("commit", {}).get("message"),
                    "author": c.get("commit", {}).get("author", {}).get("name"),
                    "created_at": c.get("commit", {}).get("author", {}).get("date"),
                }
                for c in commits
            ],
            "total": len(commits),
        }

    async def resolve_discussion(
        self, repo: str, pr_id: int, discussion_id: str
    ) -> dict[str, Any]:
        return {
            "success": False,
            "error": "GitHub does not support resolving individual review comments. "
            "Use submit_review with 'approve' action to indicate review completion.",
        }

    async def submit_review(
        self, repo: str, pr_id: int, action: str, body: str | None = None
    ) -> dict[str, Any]:
        event_map = {
            "approve": "APPROVE",
            "request_changes": "REQUEST_CHANGES",
            "comment": "COMMENT",
        }
        event = event_map.get(action)
        if not event:
            return {"success": False, "error": f"Unknown action: {action}. Use: approve, request_changes, comment"}

        data: dict[str, Any] = {"event": event}
        if body:
            data["body"] = body

        result = await self._call_api(
            f"/repos/{repo}/pulls/{pr_id}/reviews", method="POST", data=data
        )
        if isinstance(result, dict) and result.get("id"):
            return {
                "success": True,
                "review_id": result.get("id"),
                "state": result.get("state"),
                "url": result.get("html_url"),
            }
        return {"success": False, "error": "Failed to submit review"}


def _classify_http_error(status_code: int) -> str:
    if status_code == 401:
        return "auth"
    elif status_code == 403:
        return "forbidden"
    elif status_code == 404:
        return "not_found"
    elif status_code == 422:
        return "validation"
    elif status_code == 429:
        return "rate_limit"
    elif status_code >= 500:
        return "server"
    return "http"


def _simplify_position(pos: dict[str, Any] | None) -> dict[str, Any] | None:
    if not pos:
        return None
    return {
        "file_path": pos.get("new_path") or pos.get("old_path"),
        "new_line": pos.get("new_line"),
        "old_line": pos.get("old_line"),
    }
