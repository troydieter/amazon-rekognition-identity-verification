from aws_cdk import (
    Duration,
    Stack,
    aws_lambda as _lambda,
    aws_iam as iam,
    aws_logs as logs,
    aws_dynamodb as dynamodb,
    aws_apigateway as apigateway,
    aws_s3 as s3,
    aws_s3_notifications as s3n,
    aws_cognito as cognito,
    aws_stepfunctions as stepfunctions,
    aws_stepfunctions_tasks as stepfunctions_tasks,
    RemovalPolicy,
    CfnOutput,
)
from cdk_klayers import Klayers
from constructs import Construct


class IdPlusSelfieStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Initialize Klayers Class
        klayers = Klayers(
            self,
            python_version=_lambda.Runtime.PYTHON_3_12,
            region=self.region
        )

        # get the latest layer version for the PIL package
        pil_layer = klayers.layer_version(self, "Pillow")

        # Create the S3 upload bucket
        upload_bucket = s3.Bucket(
            self, "UploadBucket",
            bucket_name=None,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            versioned=True,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            lifecycle_rules=[
                s3.LifecycleRule(
                    transitions=[
                        s3.Transition(
                            storage_class=s3.StorageClass.INTELLIGENT_TIERING,
                            # Move to Intelligent-Tiering after 31 days
                            transition_after=Duration.days(31)
                        )
                    ],
                    # Delete objects after 1 year
                    expiration=Duration.days(365)
                ),
                # Expire the original uploads after 30 days
                s3.LifecycleRule(
                    prefix="dl/",
                    expiration=Duration.days(30)
                ),
                s3.LifecycleRule(
                    prefix="selfie/",
                    expiration=Duration.days(30)
                )
            ]
        )

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

        # Create the Cognito User Pool
        # Create Cognito User Pool
        user_pool = cognito.UserPool(
            self, "IdentityUserPool",
            self_sign_up_enabled=True,
            sign_in_aliases=cognito.SignInAliases(username=True, email=True),
            auto_verify=cognito.AutoVerifiedAttrs(email=True),
            password_policy=cognito.PasswordPolicy(
                min_length=8,
                require_lowercase=True,
                require_digits=True,
                require_uppercase=True,
                require_symbols=True
            ),
            standard_attributes=cognito.StandardAttributes(
                email=cognito.StandardAttribute(
                    required=True,
                    mutable=True
                )
            ),
            account_recovery=cognito.AccountRecovery.EMAIL_ONLY,
            removal_policy=RemovalPolicy.DESTROY  # Use RETAIN in production
        )

        # Create App Client
        user_pool_client = user_pool.add_client(
            "IpsUserPoolClient",
            o_auth=cognito.OAuthSettings(
                flows=cognito.OAuthFlows(
                    authorization_code_grant=True,
                    implicit_code_grant=True
                ),
                scopes=[
                    cognito.OAuthScope.OPENID,
                    cognito.OAuthScope.EMAIL,
                    cognito.OAuthScope.PROFILE
                ],
                # callback_urls=["http://localhost:3000"]
            ),
            read_attributes=cognito.ClientAttributes()
            .with_standard_attributes(
                email=True
            )
        )

        # Create Cognito Authorizer
        cognito_authorizer = apigateway.CognitoUserPoolsAuthorizer(
            self, "IpsCognitoAuthorizer",
            cognito_user_pools=[user_pool],
            identity_source="method.request.header.Authorization"
        )

        # The Upload and entry-point Lambda function
        id_upload_lambda = _lambda.Function(
            self,
            "IDHandlerUpload",
            code=_lambda.Code.from_asset("lambda"),
            handler="id_upload_lambda.lambda_handler",
            runtime=_lambda.Runtime.PYTHON_3_12,
            memory_size=256,
            timeout=Duration.seconds(6),
            environment={
                "LOG_LEVEL": "INFO",  # Add a log level for runtime control
                "DYNAMODB_TABLE_NAME": verification_table.table_name,
                "S3_BUCKET_NAME": upload_bucket.bucket_name,
                "TTL_DAYS": "365"
            },
            log_retention=logs.RetentionDays.ONE_WEEK,  # Set log retention period
        )

        upload_bucket.grant_read_write(id_upload_lambda)

        # Create the beginning Lambda for the SM
        id_trigger_stepfunction_lambda = _lambda.Function(
            self,
            "IDHandlerTriggerStepFunction",
            code=_lambda.Code.from_asset("lambda"),
            handler="id_trigger_stepfunction_lambda.lambda_handler",
            runtime=_lambda.Runtime.PYTHON_3_12,
            memory_size=256,
            timeout=Duration.seconds(6),
            environment={
                "LOG_LEVEL": "INFO",
                "S3_BUCKET_NAME": upload_bucket.bucket_name,
                "DYNAMODB_TABLE_NAME": verification_table.table_name
            },
            log_retention=logs.RetentionDays.ONE_WEEK,
        )

        # Create success end state
        success_state = stepfunctions.Succeed(
            self, "SucceedState",
            comment="Verification process completed successfully"
        )

        # Create fail end state
        fail_state = stepfunctions.Fail(
            self, "FailState",
            cause="Verification process failed",
            error="VerificationError"
        )

        id_sm_update_status_lambda = _lambda.Function(
            self,
            "UpdateStatusLambda",
            code=_lambda.Code.from_asset("lambda"),
            handler="id_sm_update_status_lambda.lambda_handler",
            runtime=_lambda.Runtime.PYTHON_3_12,
            environment={
                "DYNAMODB_TABLE_NAME": verification_table.table_name
            }
        )

        verification_table.grant_read_write_data(id_sm_update_status_lambda)

        # Create the initial state for the state machine
        initial_state = stepfunctions.Pass(
            self, "InitialState",
            result=stepfunctions.Result.from_object({
                "status": "STARTED",
                "timestamp.$": "$$.Execution.StartTime",
                "verification_id.$": "$.verification_id",
                "user_email.$": "$.user_email",
                "dl_key.$": "$.dl_key",
                "selfie_key.$": "$.selfie_key",
                "success": True  # Explicitly set success
            })
        )

        # Create task states that update status
        update_processing = stepfunctions_tasks.LambdaInvoke(
            self, "UpdateProcessingStatus",
            lambda_function=id_sm_update_status_lambda,
            payload=stepfunctions.TaskInput.from_object({
                "verification_id.$": "$.verification_id",
                "status": "PROCESSING",
                "timestamp.$": "$$.Execution.StartTime"
            })
        )

        update_complete = stepfunctions_tasks.LambdaInvoke(
            self, "UpdateCompleteStatus",
            lambda_function=id_sm_update_status_lambda,
            payload=stepfunctions.TaskInput.from_object({
                "verification_id.$": "$.verification_id",
                "status": "COMPLETED",
                "timestamp.$": "$$.Execution.StartTime"
            })
        )

        # Grant permissions
        upload_bucket.grant_read(id_trigger_stepfunction_lambda)
        verification_table.grant_read_write_data(
            id_trigger_stepfunction_lambda)

        # Create the verification process state
        verification_process = stepfunctions.Pass(
            self, "ProcessVerification",
            result=stepfunctions.Result.from_object({
                "status": "PROCESSING",
                "timestamp.$": "$$.Execution.StartTime",
                "verification_id.$": "$.verification_id",
                "user_email.$": "$.user_email",
                "dl_key.$": "$.dl_key",
                "selfie_key.$": "$.selfie_key",
                "success": True  # Explicitly set success
            })
        )

        # Create choice state
        choice_state = stepfunctions.Choice(
            self, "VerificationChoice"
        ).when(
            stepfunctions.Condition.boolean_equals('$.success', True),
            success_state
        ).otherwise(
            fail_state
        )
        # Define the chain
        chain = (
            initial_state
            .next(verification_process)
            .next(choice_state)
        )

        # Create the state machine
        sm = stepfunctions.StateMachine(
            self, "StateMachine",
            definition_body=stepfunctions.DefinitionBody.from_chainable(chain),
            timeout=Duration.minutes(5),
            tracing_enabled=True,
            logs=stepfunctions.LogOptions(
                destination=logs.LogGroup(
                    self,
                    "StateMachineLogGroup",
                    retention=logs.RetentionDays.ONE_WEEK
                ),
                level=stepfunctions.LogLevel.ALL
            )
        )

        sm.grant_start_execution(id_trigger_stepfunction_lambda)
        # Add state machine ARN to Lambda environment
        id_trigger_stepfunction_lambda.add_environment(
            "STATE_MACHINE_ARN",
            sm.state_machine_arn
        )

        # Add CloudWatch logging permissions
        sm.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "logs:CreateLogDelivery",
                    "logs:GetLogDelivery",
                    "logs:UpdateLogDelivery",
                    "logs:DeleteLogDelivery",
                    "logs:ListLogDeliveries",
                    "logs:PutResourcePolicy",
                    "logs:DescribeResourcePolicies",
                    "logs:DescribeLogGroups"
                ],
                resources=["*"]
            )
        )

        # Add S3 notifications
        upload_bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED_PUT,
            s3n.LambdaDestination(id_trigger_stepfunction_lambda),
            s3.NotificationKeyFilter(
                prefix="dl/"
            )
        )

        upload_bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED_PUT,
            s3n.LambdaDestination(id_trigger_stepfunction_lambda),
            s3.NotificationKeyFilter(
                prefix="selfie/"
            )
        )

        id_delete_lambda = _lambda.Function(
            self,
            "IDHandlerDelete",
            code=_lambda.Code.from_asset("lambda"),
            handler="id_delete_lambda.lambda_handler",
            runtime=_lambda.Runtime.PYTHON_3_12,
            memory_size=256,
            timeout=Duration.seconds(6),
            environment={
                "LOG_LEVEL": "INFO",  # Add a log level for runtime control
                "DYNAMODB_TABLE_NAME": verification_table.table_name,
                "S3_BUCKET_NAME": upload_bucket.bucket_name,
                "TTL_DAYS": "365"
            },
            log_retention=logs.RetentionDays.ONE_WEEK,  # Set log retention period
        )

        upload_bucket.grant_read_write(id_delete_lambda)

        id_compress_lambda = _lambda.Function(
            self,
            "IDHandlerCompress",
            code=_lambda.Code.from_asset("lambda"),
            handler="id_compress_lambda.lambda_handler",
            runtime=_lambda.Runtime.PYTHON_3_12,
            memory_size=256,
            timeout=Duration.seconds(30),
            layers=[pil_layer],
            environment={
                "LOG_LEVEL": "INFO",  # Add a log level for runtime control
                "S3_BUCKET_NAME": upload_bucket.bucket_name
            },
            log_retention=logs.RetentionDays.ONE_WEEK,  # Set log retention period
        )

        upload_bucket.grant_read_write(id_compress_lambda)

        # Commenting out the moderate Lambda function until a step function is introduced
        # id_moderate_lambda = _lambda.Function(
        #     self,
        #     "IpsHandlerModerate",
        #     code=_lambda.Code.from_asset("lambda"),
        #     handler="id_moderate_lambda.lambda_handler",
        #     runtime=_lambda.Runtime.PYTHON_3_12,
        #     memory_size=256,
        #     timeout=Duration.seconds(10),
        #     environment={
        #         "LOG_LEVEL": "INFO",  # Add a log level for runtime control
        #         "S3_BUCKET_NAME": upload_bucket.bucket_name
        #     },
        #     log_retention=logs.RetentionDays.ONE_WEEK,  # Set log retention period
        # )

        # upload_bucket.grant_read_write(id_moderate_lambda)

        verification_table.grant_read_write_data(id_upload_lambda)
        verification_table.grant_read_write_data(id_delete_lambda)

        # Attach an IAM policy for the Entrypoint Lambda function to allow Rekognition actions
        id_upload_lambda.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["rekognition:CompareFaces"],
                # Limit this further if possible for better security
                resources=["*"],
            )
        )

        # Attach an IAM policy for the Moderate Lambda function to allow Rekognition actions
        # Commented out until moderation Lambda function is in a step function
        # id_moderate_lambda.add_to_role_policy(
        #     iam.PolicyStatement(
        #         effect=iam.Effect.ALLOW,
        #         actions=["rekognition:DetectModerationLabels"],
        #         # Limit this further if possible for better security
        #         resources=["*"],
        #     )
        # )

        api = apigateway.RestApi(
            self,
            "CompareApi",
            default_cors_preflight_options=apigateway.CorsOptions(
                allow_origins=["*"],
                allow_methods=["POST", "OPTIONS"],
                allow_headers=[
                    "Content-Type",
                    "X-Api-Key",
                    "Authorization"
                ],
                max_age=Duration.days(1)
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

        success_response = apigateway.IntegrationResponse(
            status_code="200",
            response_parameters={
                'method.response.header.Access-Control-Allow-Origin': "'*'",
                'method.response.header.Access-Control-Allow-Headers': "'Content-Type,X-Api-Key,Authorization'",
                'method.response.header.Access-Control-Allow-Methods': "'OPTIONS,POST'"
            }
        )

        error_response = apigateway.IntegrationResponse(
            status_code="401",
            selection_pattern=".*[UNAUTHORIZED].*",
            response_parameters={
                'method.response.header.Access-Control-Allow-Origin': "'*'"
            }
        )

        # Compare Faces - Create
        id_upload_integration = apigateway.LambdaIntegration(
            id_upload_lambda,
            proxy=True,
            integration_responses=[success_response, error_response]
        )

        compare_faces_resource = api.root.add_resource("id-verify")
        compare_faces_resource.add_method(
            "POST",
            id_upload_integration,
            method_responses=[
                apigateway.MethodResponse(
                    status_code="200",
                    response_parameters={
                        'method.response.header.Access-Control-Allow-Origin': True,
                        'method.response.header.Access-Control-Allow-Headers': True,
                        'method.response.header.Access-Control-Allow-Methods': True
                    }
                ),
                apigateway.MethodResponse(
                    status_code="401",
                    response_parameters={
                        'method.response.header.Access-Control-Allow-Origin': True
                    }
                )
            ],
            api_key_required=True,
            authorizer=cognito_authorizer,
            authorization_type=apigateway.AuthorizationType.COGNITO
        )

        id_upload_lambda.add_permission(
            "APIGatewayInvoke",
            principal=iam.ServicePrincipal("apigateway.amazonaws.com"),
            action="lambda:InvokeFunction",
            source_arn=api.arn_for_execute_api()
        )

        # ID Verification - Delete
        id_verify_resource_delete = api.root.add_resource(
            "id-verify-delete")
        id_verify_integration_delete = apigateway.LambdaIntegration(
            id_delete_lambda,
            proxy=False,
            integration_responses=[
                apigateway.IntegrationResponse(
                    status_code="200",
                    response_parameters={
                        'method.response.header.Access-Control-Allow-Origin': "'*'",
                        'method.response.header.Access-Control-Allow-Headers': "'Content-Type,X-Api-Key,Authorization'",
                        'method.response.header.Access-Control-Allow-Methods': "'OPTIONS,DELETE'",
                        'method.response.header.Access-Control-Allow-Credentials': "'true'"
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

        id_verify_resource_delete.add_method(
            "DELETE",
            id_verify_integration_delete,
            method_responses=[
                apigateway.MethodResponse(
                    status_code="200",
                    response_parameters={
                        'method.response.header.Access-Control-Allow-Origin': True,
                        'method.response.header.Access-Control-Allow-Headers': True,
                        'method.response.header.Access-Control-Allow-Methods': True,
                        'method.response.header.Access-Control-Allow-Credentials': True
                    }
                )
            ],
            api_key_required=True,
            authorizer=cognito_authorizer,
            authorization_type=apigateway.AuthorizationType.COGNITO
        )

        # Outputs to assist debugging and deployment
        self.output_cfn_info(verification_table, api, api_key,
                             upload_bucket, user_pool, user_pool_client)

    def output_cfn_info(self, verification_table, api, api_key, upload_bucket, user_pool, user_pool_client):
        CfnOutput(
            self, "TableName", value=verification_table.table_name, description="The name of the DynamoDB Table"
        )
        CfnOutput(self, "ApiUrl",
                  value=api.url,
                  description="URL of the API Gateway",
                  export_name=f"{self.stack_name}-ApiUrl"
                  )

        CfnOutput(self, "ApiEndpoint_id-verify",
                  value=f"{api.url}id-verify",
                  description="Endpoint for face comparison",
                  export_name=f"{self.stack_name}-ApiEndpoint-id-verify"
                  )

        CfnOutput(self, "ApiEndpoint_id-verify-delete",
                  value=f"{api.url}id-verify-delete",
                  description="Endpoint for deletion of a previous comparison",
                  export_name=f"{
                      self.stack_name}-ApiEndpoint-id-verify-delete"
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

        CfnOutput(self, "UploadBucketName", value=upload_bucket.bucket_name,
                  description="The name of the generated bucket")

        CfnOutput(self, "UserPoolId",
                  value=user_pool.user_pool_id,
                  description="ID of the Cognito User Pool",
                  export_name=f"{self.stack_name}-UserPoolId"
                  )

        CfnOutput(self, "UserPoolClientId",
                  value=user_pool_client.user_pool_client_id,
                  description="ID of the Cognito User Pool Client",
                  export_name=f"{self.stack_name}-UserPoolClientId"
                  )
