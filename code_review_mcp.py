#!/usr/bin/env python3
"""
Code Review MCP Server for Cursor AI

Supports GitHub and GitLab merge/pull request reviews.
"""

import json
import sys
import os
import re
import subprocess
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Optional, Any


# =============================================================================
# Provider Base Class
# =============================================================================

class CodeReviewProvider(ABC):
    """Abstract base class for code review providers"""
    
    @abstractmethod
    def get_pr_info(self, repo: str, pr_id: int) -> Dict:
        """Get PR/MR information"""
        pass
    
    @abstractmethod
    def get_pr_changes(self, repo: str, pr_id: int) -> Dict:
        """Get PR/MR code changes"""
        pass
    
    @abstractmethod
    def add_inline_comment(self, repo: str, pr_id: int, file_path: str,
                          line: int, line_type: str, comment: str) -> Dict:
        """Add inline comment to specific line"""
        pass
    
    @abstractmethod
    def add_pr_comment(self, repo: str, pr_id: int, comment: str) -> Dict:
        """Add general PR/MR comment"""
        pass


# =============================================================================
# GitLab Provider
# =============================================================================

class GitLabProvider(CodeReviewProvider):
    """GitLab MR review provider"""
    
    def __init__(self, host: str = None, token: str = None):
        self.host = host or os.environ.get("GITLAB_HOST", "gitlab.com")
        self.token = token or self._get_token()
        if not self.token:
            raise Exception(
                "GitLab token not configured.\n\n"
                "Please install glab CLI and authenticate:\n"
                "  brew install glab\n"
                f"  glab auth login --hostname {self.host}\n"
            )
    
    def _get_token(self) -> str:
        """Get token from environment or glab config"""
        # Check environment variable first
        token = os.environ.get("GITLAB_TOKEN", "")
        if token:
            return token
        
        # Try glab config
        config_paths = [
            Path.home() / ".config" / "glab-cli" / "config.yml",
            Path.home() / "Library" / "Application Support" / "glab-cli" / "config.yml",
        ]
        
        for config_path in config_paths:
            if config_path.exists():
                with open(config_path, 'r') as f:
                    content = f.read()
                pattern = rf'{re.escape(self.host)}:.*?token:\s*([^\s\n]+)'
                match = re.search(pattern, content, re.DOTALL)
                if match:
                    return match.group(1).strip()
        return ""
    
    def _call_api(self, project_id: str, endpoint: str, method: str = "GET", 
                  data: Dict = None) -> Optional[Dict]:
        """Call GitLab API"""
        url = f"https://{self.host}/api/v4/projects/{project_id}/{endpoint}"
        cmd = ["curl", "-s", "-X", method, url, 
               "-H", f"PRIVATE-TOKEN: {self.token}", 
               "-H", "Content-Type: application/json"]
        
        temp_file = None
        try:
            if data:
                temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
                json.dump(data, temp_file)
                temp_file.close()
                cmd.extend(["-d", f"@{temp_file.name}"])
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                return None
            return json.loads(result.stdout)
        finally:
            if temp_file and os.path.exists(temp_file.name):
                os.unlink(temp_file.name)
    
    def get_pr_info(self, repo: str, pr_id: int) -> Dict:
        """Get MR information"""
        project_id = repo.replace("/", "%2F")
        mr_info = self._call_api(project_id, f"merge_requests/{pr_id}")
        
        if not mr_info:
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
            "diff_refs": mr_info.get("diff_refs", {})
        }
    
    def get_pr_changes(self, repo: str, pr_id: int, file_extensions: List[str] = None) -> Dict:
        """Get MR code changes"""
        project_id = repo.replace("/", "%2F")
        changes = self._call_api(project_id, f"merge_requests/{pr_id}/changes")
        
        if not changes:
            return {"error": "Failed to get changes"}
        
        filtered_changes = []
        for change in changes.get("changes", []):
            file_path = change.get("new_path", "")
            # Filter by extension if specified
            if file_extensions:
                if not any(file_path.endswith(ext) for ext in file_extensions):
                    continue
            filtered_changes.append({
                "file_path": file_path,
                "diff": change.get("diff", ""),
                "new_file": change.get("new_file", False),
                "deleted_file": change.get("deleted_file", False)
            })
        
        return {
            "title": changes.get("title"),
            "changes": filtered_changes,
            "total_files": len(filtered_changes)
        }
    
    def _find_line_code(self, diff: str, target_line: int, line_type: str, head_sha: str) -> str:
        """Find line_code from diff for GitLab API"""
        lines = diff.split('\n')
        old_line = 0
        new_line = 0
        
        for line in lines:
            if line.startswith('@@'):
                match = re.match(r'@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@', line)
                if match:
                    old_line = int(match.group(1)) - 1
                    new_line = int(match.group(2)) - 1
            elif line.startswith('-'):
                old_line += 1
                if line_type == "old" and old_line == target_line:
                    return f"{head_sha}_{old_line}_"
            elif line.startswith('+'):
                new_line += 1
                if line_type == "new" and new_line == target_line:
                    return f"{head_sha}_{old_line}_{new_line}"
            else:
                old_line += 1
                new_line += 1
        
        return ""
    
    def add_inline_comment(self, repo: str, pr_id: int, file_path: str,
                          line: int, line_type: str, comment: str) -> Dict:
        """Add inline comment"""
        project_id = repo.replace("/", "%2F")
        mr_info = self._call_api(project_id, f"merge_requests/{pr_id}")
        
        if not mr_info:
            return {"success": False, "error": "Failed to get MR info"}
        
        changes = self._call_api(project_id, f"merge_requests/{pr_id}/changes")
        if not changes:
            return {"success": False, "error": "Failed to get MR changes"}
        
        target_diff = None
        for change in changes.get("changes", []):
            if change.get("new_path") == file_path or change.get("old_path") == file_path:
                target_diff = change.get("diff", "")
                break
        
        if not target_diff:
            return {"success": False, "error": f"File not found: {file_path}"}
        
        line_code = self._find_line_code(
            target_diff, line, line_type, 
            mr_info.get("diff_refs", {}).get("head_sha")
        )
        if not line_code:
            return {"success": False, "error": f"Cannot locate line {line}"}
        
        diff_refs = mr_info.get("diff_refs", {})
        position = {
            "base_sha": diff_refs.get("base_sha"),
            "head_sha": diff_refs.get("head_sha"),
            "start_sha": diff_refs.get("start_sha"),
            "position_type": "text",
            "old_path": file_path,
            "new_path": file_path,
            "line_code": line_code
        }
        
        if line_type == "old":
            position["old_line"] = line
        else:
            position["new_line"] = line
        
        data = {"body": comment, "position": position}
        result = self._call_api(project_id, f"merge_requests/{pr_id}/discussions", 
                               method="POST", data=data)
        
        if result and result.get("id"):
            note_id = result.get('notes', [{}])[0].get('id')
            return {
                "success": True,
                "discussion_id": result.get("id"),
                "note_id": note_id,
                "url": f"{mr_info.get('web_url')}#note_{note_id}"
            }
        
        error_msg = result.get('message', 'Failed to add comment') if result else 'Failed to add comment'
        return {"success": False, "error": error_msg}
    
    def add_pr_comment(self, repo: str, pr_id: int, comment: str) -> Dict:
        """Add general MR comment"""
        project_id = repo.replace("/", "%2F")
        data = {"body": comment}
        result = self._call_api(project_id, f"merge_requests/{pr_id}/notes", 
                               method="POST", data=data)
        
        if result and result.get("id"):
            return {"success": True, "note_id": result.get("id")}
        return {"success": False, "error": "Failed to add comment"}


# =============================================================================
# GitHub Provider
# =============================================================================

class GitHubProvider(CodeReviewProvider):
    """GitHub PR review provider"""
    
    def __init__(self, token: str = None):
        self.token = token or self._get_token()
        if not self.token:
            raise Exception(
                "GitHub token not configured.\n\n"
                "Please install gh CLI and authenticate:\n"
                "  brew install gh\n"
                "  gh auth login\n"
            )
    
    def _get_token(self) -> str:
        """Get token from environment or gh config"""
        token = os.environ.get("GITHUB_TOKEN", "")
        if token:
            return token
        
        # Try gh CLI
        try:
            result = subprocess.run(
                ["gh", "auth", "token"],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except FileNotFoundError:
            pass
        
        return ""
    
    def _call_api(self, endpoint: str, method: str = "GET", 
                  data: Dict = None) -> Optional[Dict]:
        """Call GitHub API"""
        url = f"https://api.github.com/{endpoint}"
        cmd = ["curl", "-s", "-X", method, url,
               "-H", f"Authorization: Bearer {self.token}",
               "-H", "Accept: application/vnd.github.v3+json",
               "-H", "Content-Type: application/json"]
        
        temp_file = None
        try:
            if data:
                temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
                json.dump(data, temp_file)
                temp_file.close()
                cmd.extend(["-d", f"@{temp_file.name}"])
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                return None
            return json.loads(result.stdout)
        finally:
            if temp_file and os.path.exists(temp_file.name):
                os.unlink(temp_file.name)
    
    def get_pr_info(self, repo: str, pr_id: int) -> Dict:
        """Get PR information"""
        pr_info = self._call_api(f"repos/{repo}/pulls/{pr_id}")
        
        if not pr_info or pr_info.get("message"):
            return {"error": pr_info.get("message", "Failed to get PR info")}
        
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
            "base_sha": pr_info.get("base", {}).get("sha")
        }
    
    def get_pr_changes(self, repo: str, pr_id: int, file_extensions: List[str] = None) -> Dict:
        """Get PR code changes"""
        files = self._call_api(f"repos/{repo}/pulls/{pr_id}/files")
        
        if not files or isinstance(files, dict) and files.get("message"):
            return {"error": "Failed to get changes"}
        
        filtered_changes = []
        for file in files:
            file_path = file.get("filename", "")
            if file_extensions:
                if not any(file_path.endswith(ext) for ext in file_extensions):
                    continue
            filtered_changes.append({
                "file_path": file_path,
                "diff": file.get("patch", ""),
                "new_file": file.get("status") == "added",
                "deleted_file": file.get("status") == "removed",
                "sha": file.get("sha")
            })
        
        pr_info = self._call_api(f"repos/{repo}/pulls/{pr_id}")
        
        return {
            "title": pr_info.get("title") if pr_info else "",
            "changes": filtered_changes,
            "total_files": len(filtered_changes)
        }
    
    def add_inline_comment(self, repo: str, pr_id: int, file_path: str,
                          line: int, line_type: str, comment: str) -> Dict:
        """Add inline comment using PR review comments API"""
        # Get PR info for commit SHA
        pr_info = self._call_api(f"repos/{repo}/pulls/{pr_id}")
        if not pr_info:
            return {"success": False, "error": "Failed to get PR info"}
        
        commit_sha = pr_info.get("head", {}).get("sha")
        
        data = {
            "body": comment,
            "commit_id": commit_sha,
            "path": file_path,
            "line": line,
            "side": "RIGHT" if line_type == "new" else "LEFT"
        }
        
        result = self._call_api(f"repos/{repo}/pulls/{pr_id}/comments",
                               method="POST", data=data)
        
        if result and result.get("id"):
            return {
                "success": True,
                "comment_id": result.get("id"),
                "url": result.get("html_url")
            }
        
        error_msg = result.get('message', 'Failed to add comment') if result else 'Failed to add comment'
        return {"success": False, "error": error_msg}
    
    def add_pr_comment(self, repo: str, pr_id: int, comment: str) -> Dict:
        """Add general PR comment"""
        data = {"body": comment}
        result = self._call_api(f"repos/{repo}/issues/{pr_id}/comments",
                               method="POST", data=data)
        
        if result and result.get("id"):
            return {
                "success": True,
                "comment_id": result.get("id"),
                "url": result.get("html_url")
            }
        return {"success": False, "error": "Failed to add comment"}


# =============================================================================
# MCP Server
# =============================================================================

class MCPServer:
    """MCP Protocol Server for Code Review"""
    
    def __init__(self):
        self._providers: Dict[str, CodeReviewProvider] = {}
        self.server_info = {
            "name": "code-review",
            "version": "1.0.0"
        }
    
    def _get_provider(self, provider_type: str, host: str = None) -> CodeReviewProvider:
        """Get or create provider instance"""
        key = f"{provider_type}:{host or 'default'}"
        
        if key not in self._providers:
            if provider_type == "gitlab":
                self._providers[key] = GitLabProvider(host=host)
            elif provider_type == "github":
                self._providers[key] = GitHubProvider()
            else:
                raise ValueError(f"Unknown provider: {provider_type}")
        
        return self._providers[key]
    
    def handle_initialize(self, params: Dict) -> Dict:
        """Handle initialization request"""
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": self.server_info
        }
    
    def handle_tools_list(self) -> Dict:
        """List all available tools"""
        return {
            "tools": [
                {
                    "name": "get_pr_info",
                    "description": "Get PR/MR detailed information",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "provider": {
                                "type": "string",
                                "enum": ["github", "gitlab"],
                                "description": "Code hosting provider"
                            },
                            "repo": {
                                "type": "string",
                                "description": "Repository path (e.g., owner/repo)"
                            },
                            "pr_id": {
                                "type": "integer",
                                "description": "PR/MR ID"
                            },
                            "host": {
                                "type": "string",
                                "description": "GitLab host (optional, for self-hosted GitLab)"
                            }
                        },
                        "required": ["provider", "repo", "pr_id"]
                    }
                },
                {
                    "name": "get_pr_changes",
                    "description": "Get PR/MR code changes (diff)",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "provider": {"type": "string", "enum": ["github", "gitlab"]},
                            "repo": {"type": "string"},
                            "pr_id": {"type": "integer"},
                            "host": {"type": "string"},
                            "file_extensions": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Filter files by extensions (optional, e.g., ['.py', '.js'])"
                            }
                        },
                        "required": ["provider", "repo", "pr_id"]
                    }
                },
                {
                    "name": "add_inline_comment",
                    "description": "Add inline comment to specific code line",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "provider": {"type": "string", "enum": ["github", "gitlab"]},
                            "repo": {"type": "string"},
                            "pr_id": {"type": "integer"},
                            "file_path": {"type": "string"},
                            "line": {"type": "integer"},
                            "line_type": {
                                "type": "string",
                                "enum": ["old", "new"],
                                "description": "old=deleted line, new=added line"
                            },
                            "comment": {"type": "string"},
                            "host": {"type": "string"}
                        },
                        "required": ["provider", "repo", "pr_id", "file_path", "line", "line_type", "comment"]
                    }
                },
                {
                    "name": "add_pr_comment",
                    "description": "Add general PR/MR comment",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "provider": {"type": "string", "enum": ["github", "gitlab"]},
                            "repo": {"type": "string"},
                            "pr_id": {"type": "integer"},
                            "comment": {"type": "string"},
                            "host": {"type": "string"}
                        },
                        "required": ["provider", "repo", "pr_id", "comment"]
                    }
                },
                {
                    "name": "batch_add_comments",
                    "description": "Batch add comments (inline + general)",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "provider": {"type": "string", "enum": ["github", "gitlab"]},
                            "repo": {"type": "string"},
                            "pr_id": {"type": "integer"},
                            "inline_comments": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "file_path": {"type": "string"},
                                        "line": {"type": "integer"},
                                        "line_type": {"type": "string", "enum": ["old", "new"]},
                                        "comment": {"type": "string"}
                                    },
                                    "required": ["file_path", "line", "line_type", "comment"]
                                }
                            },
                            "pr_comment": {"type": "string"},
                            "host": {"type": "string"}
                        },
                        "required": ["provider", "repo", "pr_id", "inline_comments"]
                    }
                },
                {
                    "name": "extract_related_prs",
                    "description": "Extract related PR/MR links from description",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "provider": {"type": "string", "enum": ["github", "gitlab"]},
                            "description": {"type": "string"},
                            "host": {"type": "string"}
                        },
                        "required": ["provider", "description"]
                    }
                }
            ]
        }
    
    def _extract_related_prs(self, provider: str, description: str, host: str = None) -> List[Dict]:
        """Extract related PR/MR links from description"""
        if not description:
            return []
        
        if provider == "gitlab":
            host = host or "gitlab.com"
            # Match: https://host/group/project/-/merge_requests/123 or https://host/group/project/merge_requests/123
            # Use non-greedy match and exclude the /-/ part
            pattern = rf'https://{re.escape(host)}/([\w\-]+(?:/[\w\-]+)*?)(?:/-)?/merge_requests/(\d+)'
        else:
            pattern = r'https://github\.com/([\w\-]+/[\w\-]+)/pull/(\d+)'
        
        matches = re.findall(pattern, description)
        return [{"repo": repo, "pr_id": int(pr_id)} for repo, pr_id in matches]
    
    def handle_tools_call(self, params: Dict) -> Dict:
        """Handle tool calls"""
        tool_name = params.get("name")
        args = params.get("arguments", {})
        
        try:
            # extract_related_prs doesn't need authentication
            if tool_name == "extract_related_prs":
                result = self._extract_related_prs(
                    args.get("provider", "github"),
                    args["description"],
                    args.get("host")
                )
                return {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]}
            
            # All other tools need provider authentication
            provider_type = args.get("provider", "github")
            host = args.get("host")
            provider = self._get_provider(provider_type, host)
            
            if tool_name == "get_pr_info":
                result = provider.get_pr_info(args["repo"], args["pr_id"])
            
            elif tool_name == "get_pr_changes":
                result = provider.get_pr_changes(
                    args["repo"], args["pr_id"],
                    args.get("file_extensions")
                )
            
            elif tool_name == "add_inline_comment":
                result = provider.add_inline_comment(
                    args["repo"], args["pr_id"], args["file_path"],
                    args["line"], args["line_type"], args["comment"]
                )
            
            elif tool_name == "add_pr_comment":
                result = provider.add_pr_comment(
                    args["repo"], args["pr_id"], args["comment"]
                )
            
            elif tool_name == "batch_add_comments":
                results = {
                    "inline_success": 0,
                    "inline_failed": 0,
                    "pr_comment_success": False,
                    "errors": []
                }
                
                for comment_data in args.get("inline_comments", []):
                    try:
                        result = provider.add_inline_comment(
                            args["repo"], args["pr_id"],
                            comment_data["file_path"],
                            comment_data["line"],
                            comment_data["line_type"],
                            comment_data["comment"]
                        )
                        if result.get("success"):
                            results["inline_success"] += 1
                        else:
                            results["inline_failed"] += 1
                            results["errors"].append({
                                "file": comment_data["file_path"],
                                "line": comment_data["line"],
                                "error": result.get("error")
                            })
                    except Exception as e:
                        results["inline_failed"] += 1
                        results["errors"].append({
                            "file": comment_data.get("file_path"),
                            "error": str(e)
                        })
                
                if args.get("pr_comment"):
                    try:
                        result = provider.add_pr_comment(
                            args["repo"], args["pr_id"], args["pr_comment"]
                        )
                        results["pr_comment_success"] = result.get("success", False)
                    except Exception as e:
                        results["errors"].append({"type": "pr_comment", "error": str(e)})
                
                result = results
            
            else:
                return {
                    "content": [{"type": "text", "text": f"Unknown tool: {tool_name}"}],
                    "isError": True
                }
            
            return {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]}
        
        except Exception as e:
            return {"content": [{"type": "text", "text": f"Error: {str(e)}"}], "isError": True}
    
    def handle_request(self, request: Dict) -> Dict:
        """Handle JSON-RPC request"""
        method = request.get("method")
        params = request.get("params", {})
        request_id = request.get("id")
        
        try:
            if method == "initialize":
                result = self.handle_initialize(params)
            elif method == "tools/list":
                result = self.handle_tools_list()
            elif method == "tools/call":
                result = self.handle_tools_call(params)
            else:
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32601, "message": f"Method not found: {method}"}
                }
            
            return {"jsonrpc": "2.0", "id": request_id, "result": result}
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32603, "message": str(e)}
            }
    
    def run(self):
        """Run MCP server (stdio mode)"""
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            
            request_id = None
            try:
                request = json.loads(line)
                request_id = request.get("id")
                
                # Notifications don't need response
                if request_id is None and "method" in request:
                    continue
                
                response = self.handle_request(request)
                print(json.dumps(response), flush=True)
            except json.JSONDecodeError as e:
                sys.stderr.write(f"Parse error: {str(e)}\n")
                sys.stderr.flush()
            except Exception as e:
                if request_id is not None:
                    error_response = {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "error": {"code": -32603, "message": f"Internal error: {str(e)}"}
                    }
                    print(json.dumps(error_response), flush=True)


if __name__ == "__main__":
    server = MCPServer()
    server.run()

