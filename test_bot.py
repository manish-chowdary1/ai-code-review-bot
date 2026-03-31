"""
Tests for the AI Code Review Bot.
Covers webhook handling, review logic, and GitHub integration.
"""

import hashlib
import hmac
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.github_client import format_review_as_markdown, verify_webhook_signature
from app.main import app
from app.reviewer import ReviewFinding, ReviewResult, analyze_diff

client = TestClient(app)


# --- Webhook Signature Tests ---


class TestWebhookSignature:
    def test_valid_signature(self):
        settings.github_webhook_secret = "test-secret"
        payload = b'{"action": "opened"}'
        sig = hmac.new(b"test-secret", payload, hashlib.sha256).hexdigest()
        assert verify_webhook_signature(payload, f"sha256={sig}") is True

    def test_invalid_signature(self):
        settings.github_webhook_secret = "test-secret"
        payload = b'{"action": "opened"}'
        assert verify_webhook_signature(payload, "sha256=invalid") is False

    def test_empty_secret_skips_verification(self):
        settings.github_webhook_secret = ""
        assert verify_webhook_signature(b"anything", "") is True


# --- Review Engine Tests ---


class TestReviewEngine:
    def test_empty_files_returns_no_review(self):
        result = analyze_diff([])
        assert result.summary == "No files to review."
        assert result.findings == []

    def test_no_patches_returns_binary_message(self):
        files = [{"filename": "image.png", "patch": None}]
        result = analyze_diff(files)
        assert "binary" in result.summary.lower() or "No reviewable" in result.summary

    @patch("app.reviewer.anthropic.Anthropic")
    def test_successful_review(self, mock_anthropic_class):
        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                text=json.dumps(
                    {
                        "findings": [
                            {
                                "file": "app.py",
                                "line": 10,
                                "severity": "warning",
                                "category": "security",
                                "message": "Hardcoded API key detected",
                                "suggestion": "Use environment variables instead",
                            }
                        ],
                        "summary": "Found a security issue with hardcoded credentials.",
                    }
                )
            )
        ]
        mock_client.messages.create.return_value = mock_response

        files = [{"filename": "app.py", "patch": "+API_KEY = 'sk-1234'"}]
        result = analyze_diff(files)

        assert len(result.findings) == 1
        assert result.findings[0].severity == "warning"
        assert result.findings[0].category == "security"
        assert result.files_reviewed == 1

    @patch("app.reviewer.anthropic.Anthropic")
    def test_malformed_json_response(self, mock_anthropic_class):
        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="This is not JSON")]
        mock_client.messages.create.return_value = mock_response

        files = [{"filename": "app.py", "patch": "+print('hello')"}]
        result = analyze_diff(files)

        assert "failed" in result.summary.lower() or "parse" in result.summary.lower()


# --- Markdown Formatting Tests ---


class TestMarkdownFormatting:
    def test_no_findings_shows_clean(self):
        md = format_review_as_markdown([], "All good")
        assert "No issues found" in md
        assert "All good" in md

    def test_findings_grouped_by_severity(self):
        findings = [
            ReviewFinding(
                file="a.py",
                line=1,
                severity="critical",
                category="bug",
                message="Null pointer",
                suggestion="Add null check",
            ),
            ReviewFinding(
                file="b.py",
                line=5,
                severity="suggestion",
                category="quality",
                message="Consider renaming",
                suggestion="Use descriptive name",
            ),
        ]
        md = format_review_as_markdown(findings, "Found issues")
        assert "CRITICAL" in md
        assert "SUGGESTION" in md
        assert "a.py:1" in md
        assert "b.py:5" in md

    def test_finding_with_no_suggestion(self):
        findings = [
            ReviewFinding(
                file="c.py",
                line=3,
                severity="nitpick",
                category="quality",
                message="Trailing whitespace",
            )
        ]
        md = format_review_as_markdown(findings, "Minor issues")
        assert "Trailing whitespace" in md


# --- API Endpoint Tests ---


class TestHealthEndpoint:
    def test_health_check(self):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"


class TestWebhookEndpoint:
    def test_ignores_non_pr_events(self):
        response = client.post(
            "/webhook/github",
            json={"action": "created"},
            headers={
                "X-GitHub-Event": "issues",
                "X-Hub-Signature-256": "",
            },
        )
        assert response.status_code == 200
        assert response.json()["status"] == "ignored"

    def test_ignores_irrelevant_pr_actions(self):
        settings.github_webhook_secret = ""
        response = client.post(
            "/webhook/github",
            json={
                "action": "closed",
                "pull_request": {},
                "repository": {"full_name": "test/repo"},
            },
            headers={
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": "",
            },
        )
        assert response.status_code == 200
        assert response.json()["reason"] == "PR action: closed"

    def test_rejects_invalid_signature(self):
        settings.github_webhook_secret = "real-secret"
        response = client.post(
            "/webhook/github",
            json={"action": "opened"},
            headers={
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": "sha256=bad",
            },
        )
        assert response.status_code == 401
