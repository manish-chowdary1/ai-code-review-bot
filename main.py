"""
AI Code Review Bot - FastAPI Application
Receives GitHub PR webhooks, analyzes diffs with Claude, and posts review comments.
"""

import logging

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from app.config import settings
from app.db import create_table_if_not_exists, get_review_stats, save_review
from app.github_client import (
    format_review_as_markdown,
    get_pr_details,
    get_pr_files,
    post_review_comment,
    verify_webhook_signature,
)
from app.reviewer import analyze_diff

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="AI Code Review Bot",
    description="Automated code review powered by Claude AI",
    version="1.0.0",
)


@app.on_event("startup")
async def startup():
    """Initialize resources on startup."""
    logger.info("Starting AI Code Review Bot (env: %s)", settings.environment)
    if settings.environment == "development":
        try:
            create_table_if_not_exists()
            logger.info("DynamoDB table ready")
        except Exception as e:
            logger.warning("Could not create DynamoDB table: %s", e)


@app.get("/health")
async def health_check():
    """Health check endpoint for load balancers and monitoring."""
    return {"status": "healthy", "environment": settings.environment}


@app.post("/webhook/github")
async def github_webhook(
    request: Request,
    x_hub_signature_256: str = Header(default=""),
    x_github_event: str = Header(default=""),
):
    """
    Handle incoming GitHub webhook events.
    Triggers code review on pull_request opened/synchronize events.
    """
    payload = await request.body()

    # Verify webhook signature
    if not verify_webhook_signature(payload, x_hub_signature_256):
        logger.warning("Invalid webhook signature")
        raise HTTPException(status_code=401, detail="Invalid signature")

    data = await request.json()

    # Only process PR events
    if x_github_event != "pull_request":
        return {"status": "ignored", "reason": f"Event type: {x_github_event}"}

    action = data.get("action", "")
    if action not in ("opened", "synchronize", "reopened"):
        return {"status": "ignored", "reason": f"PR action: {action}"}

    # Extract PR info
    pr = data.get("pull_request", {})
    repo = data.get("repository", {}).get("full_name", "")
    pr_number = pr.get("number", 0)
    commit_sha = pr.get("head", {}).get("sha", "")

    logger.info("Processing PR #%d on %s (action: %s)", pr_number, repo, action)

    try:
        # Fetch PR files with diffs
        files = await get_pr_files(repo, pr_number)
        logger.info("Fetched %d files for PR #%d", len(files), pr_number)

        # Run AI review
        result = analyze_diff(files)
        logger.info(
            "Review complete: %d findings across %d files",
            len(result.findings),
            result.files_reviewed,
        )

        # Persist to DynamoDB
        findings_dicts = [
            {
                "file": f.file,
                "line": f.line,
                "severity": f.severity,
                "category": f.category,
                "message": f.message,
                "suggestion": f.suggestion,
            }
            for f in result.findings
        ]

        review_id = save_review(
            repo=repo,
            pr_number=pr_number,
            commit_sha=commit_sha,
            findings=findings_dicts,
            summary=result.summary,
            files_reviewed=result.files_reviewed,
            model_used=settings.anthropic_model,
        )

        # Post review comment to GitHub
        markdown = format_review_as_markdown(result.findings, result.summary)
        await post_review_comment(repo, pr_number, commit_sha, markdown)

        return {
            "status": "reviewed",
            "review_id": review_id,
            "findings_count": len(result.findings),
            "files_reviewed": result.files_reviewed,
        }

    except Exception as e:
        logger.error("Failed to review PR #%d: %s", pr_number, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/review")
async def manual_review(request: Request):
    """
    Trigger a manual review for a PR.
    Body: { "repo": "owner/repo", "pr_number": 123 }
    """
    data = await request.json()
    repo = data.get("repo", "")
    pr_number = data.get("pr_number", 0)

    if not repo or not pr_number:
        raise HTTPException(status_code=400, detail="Missing repo or pr_number")

    # Fetch PR details and files
    pr_details = await get_pr_details(repo, pr_number)
    commit_sha = pr_details.get("head", {}).get("sha", "")
    files = await get_pr_files(repo, pr_number)

    # Run AI review
    result = analyze_diff(files)

    findings_dicts = [
        {
            "file": f.file,
            "line": f.line,
            "severity": f.severity,
            "category": f.category,
            "message": f.message,
            "suggestion": f.suggestion,
        }
        for f in result.findings
    ]

    review_id = save_review(
        repo=repo,
        pr_number=pr_number,
        commit_sha=commit_sha,
        findings=findings_dicts,
        summary=result.summary,
        files_reviewed=result.files_reviewed,
        model_used=settings.anthropic_model,
    )

    markdown = format_review_as_markdown(result.findings, result.summary)

    return {
        "review_id": review_id,
        "summary": result.summary,
        "findings": findings_dicts,
        "markdown": markdown,
        "files_reviewed": result.files_reviewed,
    }


@app.get("/stats/{owner}/{repo}")
async def review_stats(owner: str, repo: str):
    """Get review statistics for a repository."""
    full_repo = f"{owner}/{repo}"
    stats = get_review_stats(full_repo)
    return stats
