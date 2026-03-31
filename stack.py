"""
AWS CDK Infrastructure for AI Code Review Bot.
Deploys: Lambda (via container image), API Gateway, DynamoDB table.
"""

from aws_cdk import (
    Duration,
    RemovalPolicy,
    Stack,
    aws_apigateway as apigw,
    aws_dynamodb as dynamodb,
    aws_lambda as lambda_,
    aws_logs as logs,
)
from constructs import Construct


class CodeReviewBotStack(Stack):
    """CDK stack for the AI Code Review Bot infrastructure."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # DynamoDB table for storing reviews
        table = dynamodb.Table(
            self,
            "CodeReviewsTable",
            table_name="code-reviews",
            partition_key=dynamodb.Attribute(
                name="pk", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="sk", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.RETAIN,
            point_in_time_recovery=True,
        )

        # Lambda function from Docker image
        review_function = lambda_.DockerImageFunction(
            self,
            "ReviewFunction",
            code=lambda_.DockerImageCode.from_image_asset("."),
            memory_size=512,
            timeout=Duration.minutes(5),
            environment={
                "DYNAMODB_TABLE": table.table_name,
                "ENVIRONMENT": "production",
                "LOG_LEVEL": "INFO",
            },
            log_retention=logs.RetentionDays.TWO_WEEKS,
        )

        # Grant Lambda read/write access to DynamoDB
        table.grant_read_write_data(review_function)

        # API Gateway
        api = apigw.LambdaRestApi(
            self,
            "CodeReviewApi",
            handler=review_function,
            proxy=True,
            description="AI Code Review Bot API",
            deploy_options=apigw.StageOptions(
                stage_name="prod",
                throttling_rate_limit=100,
                throttling_burst_limit=50,
            ),
        )
