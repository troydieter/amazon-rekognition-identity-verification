from aws_cdk import (
    Duration,
    Stack,
    aws_lambda as _lambda,
    aws_iam as iam,
    aws_apigateway as apigateway,
    aws_logs as logs,
    aws_s3 as s3,
    aws_s3_notifications as s3_notifications,
    RemovalPolicy,
    CfnOutput
)
from constructs import Construct


class IdPlusSelfieStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create the S3 bucket
        bucket = s3.Bucket(
            self, "UploadBucket",
            bucket_name=None,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            versioned=True,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True
        )

        # Add CORS configuration
        bucket.add_cors_rule(
            allowed_methods=[
                s3.HttpMethods.PUT,
                s3.HttpMethods.POST,
                s3.HttpMethods.DELETE,
                s3.HttpMethods.GET,
                s3.HttpMethods.HEAD,
            ],
            allowed_origins=["*"],
            allowed_headers=["*"],
            max_age=3000
        )

        # Create IAM user
        upload_user = iam.User(self, "BucketUploadUser")

        # Create IAM policy for the user
        user_policy = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                "s3:ListBucket",
                "s3:GetObject",
                "s3:PutObject"
            ],
            resources=[
                bucket.bucket_arn,
                f"{bucket.bucket_arn}/*"
            ]
        )

        # Attach the policy to the user
        upload_user.add_to_principal_policy(user_policy)

        # Add a bucket policy specific to the UploadUser
        bucket.add_to_resource_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "s3:ListBucket",
                    "s3:GetObject",
                    "s3:PutObject"
                ],
                resources=[
                    bucket.bucket_arn,
                    f"{bucket.bucket_arn}/*"
                ],
                principals=[upload_user]
            )
        )

        # Define the Lambda function
        ips_lambda = _lambda.Function(
            self,
            "IpsHandler",
            code=_lambda.Code.from_asset("lambda"),
            handler="ips_lambda.lambda_handler",
            runtime=_lambda.Runtime.PYTHON_3_12,
            memory_size=256,
            timeout=Duration.seconds(6),
            environment={
                "LOG_LEVEL": "INFO",  # Add a log level for runtime control
            },
            log_retention=logs.RetentionDays.ONE_WEEK,  # Set log retention period
        )

        # Attach an IAM policy for the Lambda function to allow Rekognition actions
        ips_lambda.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["rekognition:CompareFaces"],
                resources=["*"],  # Limit this further if possible for better security
            )
        )
        
        # Define API Gateway and associate it with the Lambda function
        api = apigateway.LambdaRestApi(
            self,
            "IpsApi",
            handler=ips_lambda,
            proxy=False,
        )

        # Create an API key
        api_key = api.add_api_key("IpsApiKey")

        # Create a usage plan
        usage_plan = api.add_usage_plan("IpsUsagePlan",
            name="IPS Usage Plan",
            throttle=apigateway.ThrottleSettings(
                rate_limit=10,
                burst_limit=2
            )
        )

        # Associate the API key with the usage plan
        usage_plan.add_api_key(api_key)

        # Associate the usage plan with the API's deployment stage
        usage_plan.add_api_stage(
            stage=api.deployment_stage
        )

        # Enable API Gateway access logs
        log_group = logs.LogGroup(
            self,
            "ApiAccessLogs",
            retention=logs.RetentionDays.ONE_WEEK,  # Retain access logs for a week
        )

        # Use the ARN of the log group for access logging
        api_stage = api.deployment_stage
        api_stage.node.default_child.access_log_settings = apigateway.CfnStage.AccessLogSettingProperty(
            destination_arn=log_group.log_group_arn,
            format=apigateway.AccessLogFormat.json_with_standard_fields(
                caller=True,
                http_method=True,
                ip=True,
                protocol=True,
                request_time=True,
                resource_path=True,
                response_length=True,
                status=True,
                user=True,
            ).to_string(),  # Corrected method
        )

        # Define API Gateway resource and method
        ips_resource = api.root.add_resource("ips")
        ips_resource.add_method("POST", api_key_required=True)  # POST /ips

        # S3 Event notification
        bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED_PUT,
            s3_notifications.LambdaDestination(ips_lambda)
        )
        bucket.grant_read(ips_lambda)

        # Outputs to assist debugging and deployment
        self.output_cfn_info(api, api_key, bucket, upload_user)

    def output_cfn_info(self, api: apigateway.RestApi, api_key: apigateway.IApiKey, bucket, upload_user):
        CfnOutput(
            self,
            "ApiUrl",
            value=api.url,
            description="The base URL of the IdPlusSelfie API",
        )
        # Output the API key (for demonstration purposes)
        CfnOutput(self, "ApiKey", value=api_key.key_id, description="API Key ID")
        CfnOutput(self, "BucketName", value=bucket.bucket_name, description="The name of the generated bucket")
        CfnOutput(self, "UserName", value=upload_user.user_name, description="The name of the IAM user")