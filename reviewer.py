"""
AI-powered code review engine using Anthropic's Claude API.
Analyzes code diffs for bugs, security issues, style problems, and improvements.
"""

import json
import logging
from dataclasses import dataclass, field
from enum import Enum

import anthropic

from app.config import settings

logger = logging.getLogger(__name__)


class Severity(str, Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    SUGGESTION = "suggestion"
    NITPICK = "nitpick"


@dataclass
class ReviewFinding:
    file: str
    line: int
    severity: str
    category: str
    message: str
    suggestion: str = ""


@dataclass
class ReviewResult:
    findings: list[ReviewFinding] = field(default_factory=list)
    summary: str = ""
    files_reviewed: int = 0


SYSTEM_PROMPT = """You are an expert code reviewer. Analyze the provided code diff and return 
a structured JSON review. Focus on:

1. **Bugs & Logic Errors** - Off-by-one errors, null pointer risks, race conditions, 
   incorrect boundary checks, unhandled edge cases.
2. **Security Vulnerabilities** - SQL injection, XSS, hardcoded secrets, insecure 
   deserialization, missing input validation, improper auth checks.
3. **Performance Issues** - N+1 queries, unnecessary allocations, missing indexes, 
   inefficient algorithms, blocking I/O in async contexts.
4. **Code Quality** - Dead code, duplicated logic, overly complex methods, poor naming, 
   missing error handling, violations of SOLID principles.
5. **Best Practices** - Missing tests for critical paths, inadequate logging, 
   missing type hints, incomplete documentation for public APIs.

Return ONLY valid JSON in this exact format (no markdown, no backticks):
{
  "findings": [
    {
      "file": "path/to/file.py",
      "line": 42,
      "severity": "critical|warning|suggestion|nitpick",
      "category": "bug|security|performance|quality|best-practice",
      "message": "Clear description of the issue",
      "suggestion": "Concrete fix or improved code snippet"
    }
  ],
  "summary": "Brief overall assessment of the PR quality and key risks"
}

If the code looks clean, return an empty findings array with a positive summary.
Be precise with line numbers based on the diff. Be constructive, not pedantic."""


def _build_diff_prompt(files: list[dict]) -> str:
    """Build the user prompt from a list of file diffs."""
    parts = []
    for f in files:
        filename = f.get("filename", "unknown")
        patch = f.get("patch", "")
        if not patch:
            continue
        parts.append(f"=== FILE: {filename} ===\n{patch}\n")

    return "Review the following code changes:\n\n" + "\n".join(parts)


def analyze_diff(files: list[dict]) -> ReviewResult:
    """
    Send code diffs to Claude for review and parse the structured response.

    Args:
        files: List of dicts with 'filename' and 'patch' keys from GitHub API.

    Returns:
        ReviewResult with findings and summary.
    """
    if not files:
        return ReviewResult(summary="No files to review.")

    reviewable_files = [f for f in files if f.get("patch")]
    if not reviewable_files:
        return ReviewResult(summary="No reviewable changes found (binary files only).")

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    user_prompt = _build_diff_prompt(reviewable_files)

    logger.info(
        "Sending %d files to Claude for review (model: %s)",
        len(reviewable_files),
        settings.anthropic_model,
    )

    try:
        response = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=settings.max_tokens,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )

        raw_text = response.content[0].text
        review_data = json.loads(raw_text)

        findings = [
            ReviewFinding(
                file=f.get("file", "unknown"),
                line=f.get("line", 0),
                severity=f.get("severity", "suggestion"),
                category=f.get("category", "quality"),
                message=f.get("message", ""),
                suggestion=f.get("suggestion", ""),
            )
            for f in review_data.get("findings", [])
        ]

        return ReviewResult(
            findings=findings,
            summary=review_data.get("summary", "Review complete."),
            files_reviewed=len(reviewable_files),
        )

    except json.JSONDecodeError as e:
        logger.error("Failed to parse Claude response as JSON: %s", e)
        return ReviewResult(
            summary=f"Review failed: could not parse AI response. Raw: {raw_text[:200]}"
        )
    except anthropic.APIError as e:
        logger.error("Anthropic API error: %s", e)
        return ReviewResult(summary=f"Review failed: API error - {e}")
