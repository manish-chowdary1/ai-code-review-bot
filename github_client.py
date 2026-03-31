"""
GitHub integration layer.
Handles webhook signature verification, fetching PR diffs, and posting review comments.
"""

import hashlib
import hmac
import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"


def verify_webhook_signature(payload: bytes, signature: str) -> bool:
    """
    Verify GitHub webhook HMAC-SHA256 signature.
    Returns True if the signature matches, False otherwise.
    """
    if not settings.github_webhook_secret:
        logger.warning("No webhook secret configured, skipping verification")
        return True

    expected = hmac.new(
        settings.github_webhook_secret.encode(),
        payload,
        hashlib.sha256,
    ).hexdigest()

    received = signature.removeprefix("sha256=")
    return hmac.compare_digest(expected, received)


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.github_token}",
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


async def get_pr_files(repo: str, pr_number: int) -> list[dict[str, Any]]:
    """Fetch the list of changed files with patches for a pull request."""
    url = f"{GITHUB_API}/repos/{repo}/pulls/{pr_number}/files"

    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=_headers())
        response.raise_for_status()
        return response.json()


async def get_pr_details(repo: str, pr_number: int) -> dict[str, Any]:
    """Fetch pull request metadata (title, author, head SHA, etc.)."""
    url = f"{GITHUB_API}/repos/{repo}/pulls/{pr_number}"

    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=_headers())
        response.raise_for_status()
        return response.json()


async def post_review_comment(
    repo: str,
    pr_number: int,
    commit_sha: str,
    body: str,
) -> dict[str, Any]:
    """
    Post a review as a PR comment (issue comment).
    For inline comments, use the pull request review API instead.
    """
    url = f"{GITHUB_API}/repos/{repo}/issues/{pr_number}/comments"

    async with httpx.AsyncClient() as client:
        response = await client.post(
            url,
            headers=_headers(),
            json={"body": body},
        )
        response.raise_for_status()
        return response.json()


async def post_inline_review(
    repo: str,
    pr_number: int,
    commit_sha: str,
    comments: list[dict[str, Any]],
    summary: str,
) -> dict[str, Any]:
    """
    Submit a pull request review with inline comments.
    Each comment dict should have: path, line (or position), body.
    """
    url = f"{GITHUB_API}/repos/{repo}/pulls/{pr_number}/reviews"

    review_body = {
        "commit_id": commit_sha,
        "body": summary,
        "event": "COMMENT",
        "comments": [
            {
                "path": c["path"],
                "line": c["line"],
                "body": c["body"],
            }
            for c in comments
        ],
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            url,
            headers=_headers(),
            json=review_body,
        )
        response.raise_for_status()
        return response.json()


def format_review_as_markdown(findings: list, summary: str) -> str:
    """Format review findings as a GitHub-flavored markdown comment."""
    severity_icons = {
        "critical": "🔴",
        "warning": "🟡",
        "suggestion": "🔵",
        "nitpick": "⚪",
    }

    lines = [
        "## 🤖 AI Code Review",
        "",
        f"**Summary:** {summary}",
        "",
    ]

    if not findings:
        lines.append("✅ No issues found. Code looks good!")
        return "\n".join(lines)

    # Group by severity
    by_severity = {}
    for f in findings:
        sev = f.severity if hasattr(f, "severity") else f.get("severity", "suggestion")
        by_severity.setdefault(sev, []).append(f)

    for severity in ["critical", "warning", "suggestion", "nitpick"]:
        group = by_severity.get(severity, [])
        if not group:
            continue

        icon = severity_icons.get(severity, "⚪")
        lines.append(f"### {icon} {severity.upper()} ({len(group)})")
        lines.append("")

        for f in group:
            file_name = f.file if hasattr(f, "file") else f.get("file", "?")
            line_num = f.line if hasattr(f, "line") else f.get("line", 0)
            message = f.message if hasattr(f, "message") else f.get("message", "")
            suggestion = (
                f.suggestion if hasattr(f, "suggestion") else f.get("suggestion", "")
            )
            category = (
                f.category if hasattr(f, "category") else f.get("category", "")
            )

            lines.append(f"**`{file_name}:{line_num}`** [{category}]")
            lines.append(f"> {message}")
            if suggestion:
                lines.append(f"> 💡 **Suggestion:** {suggestion}")
            lines.append("")

    lines.append("---")
    lines.append("*Powered by Claude AI | [ai-code-review-bot](https://github.com)*")

    return "\n".join(lines)
