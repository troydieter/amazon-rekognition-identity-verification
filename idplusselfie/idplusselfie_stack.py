from aws_cdk import (
    Stack,
    aws_lambda as _lambda,
    aws_iam as iam,
    aws_apigateway as apigateway,
    aws_logs as logs,
)
from constructs import Construct


class IdPlusSelfieStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Define the Lambda function
        ips_lambda = _lambda.Function(
            self,
            "IpsHandler",
            code=_lambda.Code.from_asset("lambda"),
            handler="ips_lambda.lambda_handler",
            runtime=_lambda.Runtime.PYTHON_3_9,
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
        ips_resource.add_method("POST")  # POST /ips



        # Outputs to assist debugging and deployment
        self.output_api_url(api)

    def output_api_url(self, api: apigateway.RestApi):
        from aws_cdk import CfnOutput

        CfnOutput(
            self,
            "ApiUrl",
            value=api.url,
            description="The base URL of the IdPlusSelfie API",
        )
