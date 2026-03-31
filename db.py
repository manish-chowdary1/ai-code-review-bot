"""
DynamoDB data access layer for persisting code review results.
Stores review metadata, findings, and metrics for analytics.
"""

import uuid
from datetime import datetime, timezone
from typing import Any

import boto3
from botocore.exceptions import ClientError

from app.config import settings


def _get_table():
    """Get DynamoDB table resource with optional local endpoint."""
    kwargs = {"region_name": settings.aws_region}
    if settings.dynamodb_endpoint:
        kwargs["endpoint_url"] = settings.dynamodb_endpoint
    dynamodb = boto3.resource("dynamodb", **kwargs)
    return dynamodb.Table(settings.dynamodb_table)


def create_table_if_not_exists():
    """Create the DynamoDB table if it doesn't exist (useful for local dev)."""
    kwargs = {"region_name": settings.aws_region}
    if settings.dynamodb_endpoint:
        kwargs["endpoint_url"] = settings.dynamodb_endpoint
    dynamodb = boto3.resource("dynamodb", **kwargs)

    existing_tables = dynamodb.meta.client.list_tables()["TableNames"]
    if settings.dynamodb_table in existing_tables:
        return

    dynamodb.create_table(
        TableName=settings.dynamodb_table,
        KeySchema=[
            {"AttributeName": "pk", "KeyType": "HASH"},
            {"AttributeName": "sk", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "pk", "AttributeType": "S"},
            {"AttributeName": "sk", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )


def save_review(
    repo: str,
    pr_number: int,
    commit_sha: str,
    findings: list[dict[str, Any]],
    summary: str,
    files_reviewed: int,
    model_used: str,
) -> str:
    """
    Persist a code review to DynamoDB.

    Returns the review_id.
    """
    table = _get_table()
    review_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    item = {
        "pk": f"REPO#{repo}",
        "sk": f"PR#{pr_number}#REVIEW#{review_id}",
        "review_id": review_id,
        "repo": repo,
        "pr_number": pr_number,
        "commit_sha": commit_sha,
        "findings_count": len(findings),
        "findings": findings,
        "summary": summary,
        "files_reviewed": files_reviewed,
        "model_used": model_used,
        "created_at": now,
    }

    table.put_item(Item=item)
    return review_id


def get_reviews_for_pr(repo: str, pr_number: int) -> list[dict[str, Any]]:
    """Fetch all reviews for a given PR."""
    table = _get_table()

    try:
        response = table.query(
            KeyConditionExpression="pk = :pk AND begins_with(sk, :sk_prefix)",
            ExpressionAttributeValues={
                ":pk": f"REPO#{repo}",
                ":sk_prefix": f"PR#{pr_number}#",
            },
        )
        return response.get("Items", [])
    except ClientError:
        return []


def get_review_stats(repo: str) -> dict[str, Any]:
    """Get aggregate review statistics for a repository."""
    table = _get_table()

    try:
        response = table.query(
            KeyConditionExpression="pk = :pk",
            ExpressionAttributeValues={":pk": f"REPO#{repo}"},
        )
        items = response.get("Items", [])

        total_findings = sum(item.get("findings_count", 0) for item in items)
        total_reviews = len(items)

        return {
            "repo": repo,
            "total_reviews": total_reviews,
            "total_findings": total_findings,
            "avg_findings_per_review": (
                round(total_findings / total_reviews, 1) if total_reviews > 0 else 0
            ),
        }
    except ClientError:
        return {"repo": repo, "total_reviews": 0, "total_findings": 0}
