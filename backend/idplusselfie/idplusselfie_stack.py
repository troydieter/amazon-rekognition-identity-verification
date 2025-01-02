from aws_cdk import (
    Duration,
    Stack,
    aws_lambda as _lambda,
    aws_iam as iam,
    aws_logs as logs,
    aws_dynamodb as dynamodb,
    aws_apigateway as apigateway,
    RemovalPolicy,
    CfnOutput,
)
from constructs import Construct

class IdPlusSelfieStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create DynamoDB table
        verification_table = dynamodb.Table(
            self, 'VerificationTable',
            partition_key=dynamodb.Attribute(
                name='VerificationId',
                type=dynamodb.AttributeType.STRING
            ),            
            sort_key=dynamodb.Attribute(
                name='Timestamp',
                type=dynamodb.AttributeType.NUMBER
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,  # Use RETAIN in production
            time_to_live_attribute='TTL'
        )

        # Define the Lambda functions
        id_create_lambda = _lambda.Function(
            self,
            "IpsHandler",
            code=_lambda.Code.from_asset("lambda"),
            handler="id_create_lambda.lambda_handler",
            runtime=_lambda.Runtime.PYTHON_3_12,
            memory_size=256,
            timeout=Duration.seconds(6),
            environment={
                "LOG_LEVEL": "INFO",  # Add a log level for runtime control
                "DYNAMODB_TABLE_NAME": verification_table.table_name,
                "TTL_DAYS": "365"
            },
            log_retention=logs.RetentionDays.ONE_WEEK,  # Set log retention period
        )

        id_delete_lambda = _lambda.Function(
            self,
            "IpsHandlerDelete",
            code=_lambda.Code.from_asset("lambda"),
            handler="id_delete_lambda.lambda_handler",
            runtime=_lambda.Runtime.PYTHON_3_12,
            memory_size=256,
            timeout=Duration.seconds(6),
            environment={
                "LOG_LEVEL": "INFO",  # Add a log level for runtime control
                "DYNAMODB_TABLE_NAME": verification_table.table_name,
                "TTL_DAYS": "365"
            },
            log_retention=logs.RetentionDays.ONE_WEEK,  # Set log retention period
        )

        verification_table.grant_read_write_data(id_create_lambda)
        verification_table.grant_read_write_data(id_delete_lambda)

        # Attach an IAM policy for the Lambda function to allow Rekognition actions
        id_create_lambda.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["rekognition:CompareFaces"],
                resources=["*"],  # Limit this further if possible for better security
            )
        )

        api = apigateway.RestApi(
            self,
            "CompareApi",
            default_cors_preflight_options=apigateway.CorsOptions(
                allow_origins=['http://localhost:3000'],
                allow_methods=['POST', 'DELETE', 'OPTIONS'],
                allow_headers=['Content-Type', 'X-Api-Key']
            )
        )

        api_key = api.add_api_key("IpsApiKey")

        usage_plan = api.add_usage_plan(
            "IpsUsagePlan",
            name="IPS Usage Plan",
            throttle=apigateway.ThrottleSettings(
                rate_limit=10,
                burst_limit=2,
            ),
        )

        usage_plan.add_api_key(api_key)
        usage_plan.add_api_stage(stage=api.deployment_stage)

        log_group = logs.LogGroup(
            self,
            "ApiAccessLogs",
            retention=logs.RetentionDays.ONE_WEEK,
        )

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
            ).to_string(),
        )

        # Compare Faces - Create
        compare_faces_resource_create = api.root.add_resource("compare-faces")
        compare_faces_integration_create = apigateway.LambdaIntegration(
            id_create_lambda,
            proxy=False,
            integration_responses=[
                apigateway.IntegrationResponse(
                    status_code="200",
                    response_parameters={
                        'method.response.header.Access-Control-Allow-Origin': "'http://localhost:3000'"
                    }
                )
            ],
            request_templates={
                "application/json": '{"body": $input.json("$")}'
            }
        )

        compare_faces_resource_create.add_method(
            "POST",
            compare_faces_integration_create,
            method_responses=[
                apigateway.MethodResponse(
                    status_code="200",
                    response_parameters={
                        'method.response.header.Access-Control-Allow-Origin': True
                    }
                )
            ],
            api_key_required=True,
        )

        # Compare Faces - Delete
        compare_faces_resource_delete = api.root.add_resource("compare-faces-delete")
        compare_faces_integration_delete = apigateway.LambdaIntegration(
            id_delete_lambda,
            proxy=False,
            integration_responses=[
                apigateway.IntegrationResponse(
                    status_code="200",
                    response_parameters={
                        'method.response.header.Access-Control-Allow-Origin': "'http://localhost:3000'",
                        'method.response.header.Access-Control-Allow-Headers': "'Content-Type,X-Api-Key'",
                        'method.response.header.Access-Control-Allow-Methods': "'OPTIONS,DELETE'"
                    }
                )
            ],
            request_templates={
                "application/json": """
                #set($inputRoot = $input.path('$'))
                {
                    "body": $input.json('$'),
                    "queryStringParameters": {
                        #foreach($param in $input.params().querystring.keySet())
                            "$param": "$util.escapeJavaScript($input.params().querystring.get($param))"
                            #if($foreach.hasNext),#end
                        #end
                    },
                    "headers": {
                        #foreach($param in $input.params().header.keySet())
                            "$param": "$util.escapeJavaScript($input.params().header.get($param))"
                            #if($foreach.hasNext),#end
                        #end
                    }
                }
                """
            }
        )

        compare_faces_resource_delete.add_method(
            "DELETE",
            compare_faces_integration_delete,
            method_responses=[
                apigateway.MethodResponse(
                    status_code="200",
                    response_parameters={
                        'method.response.header.Access-Control-Allow-Origin': True,
                        'method.response.header.Access-Control-Allow-Headers': True,
                        'method.response.header.Access-Control-Allow-Methods': True
                    }
                )
            ],
            api_key_required=True,
        )

        # Outputs to assist debugging and deployment
        self.output_cfn_info(verification_table, api, api_key)

    def output_cfn_info(self, verification_table, api, api_key):
        CfnOutput(
            self, "TableName", value=verification_table.table_name, description="The name of the DynamoDB Table"
        )
        CfnOutput(self, "ApiUrl",
            value=api.url,
            description="URL of the API Gateway",
            export_name=f"{self.stack_name}-ApiUrl"
        )

        CfnOutput(self, "ApiEndpoint",
            value=f"{api.url}compare-faces",
            description="Endpoint for face comparison",
            export_name=f"{self.stack_name}-ApiEndpoint"
        )

        CfnOutput(self, "ApiKeyId",
            value=api_key.key_id,
            description="ID of the API Key",
            export_name=f"{self.stack_name}-ApiKeyId"
        )

        CfnOutput(self, "ApiName",
            value=api.rest_api_name,
            description="Name of the API",
            export_name=f"{self.stack_name}-ApiName"
        )

        CfnOutput(self, "ApiId",
            value=api.rest_api_id,
            description="ID of the API",
            export_name=f"{self.stack_name}-ApiId"
        )

        CfnOutput(self, "ApiStage",
            value=api.deployment_stage.stage_name,
            description="Stage of the API",
            export_name=f"{self.stack_name}-ApiStage"
        )