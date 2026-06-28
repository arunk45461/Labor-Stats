"""
AWS CDK Stack — Labor Stats Data Pipeline
Provisions:
  - S3 bucket for all data
  - IAM role for Lambdas
  - Ingest Lambda (Part 1 + Part 2) scheduled daily via EventBridge
  - SQS queue notified when population JSON lands in S3
  - Analytics Lambda (Part 3) triggered by the SQS queue
"""

import os
import aws_cdk as cdk
from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    aws_s3 as s3,
    aws_s3_notifications as s3n,
    aws_lambda as lambda_,
    aws_sqs as sqs,
    aws_iam as iam,
    aws_events as events,
    aws_events_targets as targets,
    aws_lambda_event_sources as lambda_event_sources,
)
from constructs import Construct


class LaborStatsPipelineStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ── S3 Bucket ──────────────────────────────────────────────────────
        bucket = s3.Bucket(
            self,
            "LaborStatsBucket",
            bucket_name=f"labor-stats-data-{self.account}",
            versioned=True,
            removal_policy=RemovalPolicy.RETAIN,  # Keep data on stack delete
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
        )

        # ── SQS Queue (populated when population JSON is written to S3) ────
        dead_letter_queue = sqs.Queue(
            self,
            "AnalyticsDLQ",
            retention_period=Duration.days(14),
        )

        analytics_queue = sqs.Queue(
            self,
            "AnalyticsQueue",
            visibility_timeout=Duration.seconds(300),
            dead_letter_queue=sqs.DeadLetterQueue(
                max_receive_count=3,
                queue=dead_letter_queue,
            ),
        )

        # S3 → SQS notification when population JSON is created/updated
        bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3n.SqsDestination(analytics_queue),
            s3.NotificationKeyFilter(prefix="population/", suffix=".json"),
        )

        # ── Shared Lambda role ─────────────────────────────────────────────
        lambda_role = iam.Role(
            self,
            "LambdaExecutionRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ],
        )
        bucket.grant_read_write(lambda_role)
        analytics_queue.grant_consume_messages(lambda_role)

        # ── Lambda Layer for dependencies ──────────────────────────────────
        # Package: requests, beautifulsoup4, pandas
        deps_layer = lambda_.LayerVersion(
            self,
            "DepsLayer",
            code=lambda_.Code.from_asset("lambda_layer"),
            compatible_runtimes=[lambda_.Runtime.PYTHON_3_12],
            description="requests, beautifulsoup4, pandas",
        )

        # ── Ingest Lambda (Part 1 + Part 2) ───────────────────────────────
        ingest_lambda = lambda_.Function(
            self,
            "IngestLambda",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="part4.pipeline_lambda.lambda_handler",
            code=lambda_.Code.from_asset("src"),
            role=lambda_role,
            layers=[deps_layer],
            timeout=Duration.minutes(10),
            memory_size=512,
            environment={
                "S3_BUCKET_NAME": bucket.bucket_name,
            },
            description="Daily BLS data sync + population API fetch",
        )

        # EventBridge rule — run ingest Lambda every day at 06:00 UTC
        daily_rule = events.Rule(
            self,
            "DailyIngestRule",
            schedule=events.Schedule.cron(minute="0", hour="6"),
            description="Trigger ingest Lambda daily at 06:00 UTC",
        )
        daily_rule.add_target(targets.LambdaFunction(ingest_lambda))

        # ── Analytics Lambda (Part 3) ──────────────────────────────────────
        analytics_lambda = lambda_.Function(
            self,
            "AnalyticsLambda",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="part3.analytics.lambda_handler",
            code=lambda_.Code.from_asset("src"),
            role=lambda_role,
            layers=[deps_layer],
            timeout=Duration.minutes(5),
            memory_size=512,
            environment={
                "S3_BUCKET_NAME": bucket.bucket_name,
            },
            description="Runs analytics reports when population JSON is updated",
        )

        # SQS → Analytics Lambda trigger
        analytics_lambda.add_event_source(
            lambda_event_sources.SqsEventSource(
                analytics_queue,
                batch_size=1,
            )
        )

        # ── CloudFormation Outputs ─────────────────────────────────────────
        cdk.CfnOutput(self, "BucketName", value=bucket.bucket_name)
        cdk.CfnOutput(self, "QueueUrl", value=analytics_queue.queue_url)
        cdk.CfnOutput(self, "IngestLambdaArn", value=ingest_lambda.function_arn)
        cdk.CfnOutput(self, "AnalyticsLambdaArn", value=analytics_lambda.function_arn)


app = cdk.App()
LaborStatsPipelineStack(
    app,
    "LaborStatsPipelineStack",
    env=cdk.Environment(
        account=os.environ.get("CDK_DEFAULT_ACCOUNT"),
        region=os.environ.get("CDK_DEFAULT_REGION", "us-east-1"),
    ),
)
app.synth()
