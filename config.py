"""
Configuration management for AI Code Review Bot.
Loads settings from environment variables with sensible defaults.
"""

import os
from dataclasses import dataclass


@dataclass
class Settings:
    """Application settings loaded from environment variables."""

    # Anthropic API
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    anthropic_model: str = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
    max_tokens: int = int(os.getenv("MAX_TOKENS", "4096"))

    # GitHub
    github_token: str = os.getenv("GITHUB_TOKEN", "")
    github_webhook_secret: str = os.getenv("GITHUB_WEBHOOK_SECRET", "")

    # AWS DynamoDB
    dynamodb_table: str = os.getenv("DYNAMODB_TABLE", "code-reviews")
    aws_region: str = os.getenv("AWS_REGION", "us-west-2")
    dynamodb_endpoint: str = os.getenv("DYNAMODB_ENDPOINT", "")  # For local dev

    # App
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    environment: str = os.getenv("ENVIRONMENT", "development")


settings = Settings()
