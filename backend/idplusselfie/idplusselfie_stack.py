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
    aws_guardduty as guardduty,
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

        ####
        ## GuardDuty Configuration for the Upload Bucket
        ## Uncomment below to enable the Detector (and use GuardDuty for scans of uploaded objects)
        ####

        # # Create an IAM role for GuardDuty
        # guardduty_role = iam.Role(
        #     self, "GuardDutyRole",
        #     assumed_by=iam.ServicePrincipal("guardduty.amazonaws.com"),
        #     description="Role for GuardDuty to access S3 bucket"
        # )

        # # Grant necessary permissions to the role
        # upload_bucket.grant_read(guardduty_role)

        # # Create GuardDuty Malware Protection Plan
        # malware_protection_plan = guardduty.CfnMalwareProtectionPlan(
        #     self, "MalwareProtectionPlan",
        #     protected_resource=guardduty.CfnMalwareProtectionPlan.CFNProtectedResourceProperty(
        #         s3_bucket=guardduty.CfnMalwareProtectionPlan.S3BucketProperty(
        #             bucket_name=upload_bucket.bucket_name,
        #             object_prefixes=[""]  # Protect all objects; adjust if needed
        #         )
        #     ),
        #     role=guardduty_role.role_arn,
        #     actions=guardduty.CfnMalwareProtectionPlan.CFNActionsProperty(
        #         tagging=guardduty.CfnMalwareProtectionPlan.CFNTaggingProperty(
        #             status="ENABLED"
        #         )
        #     ),
        #     tags=[{
        #         "key": "Purpose",
        #         "value": "S3 Malware Protection"
        #     }]
        # )

        # # Ensure GuardDuty is enabled in the account with S3 protection
        # guardduty_detector = guardduty.CfnDetector(
        #     self, "GuardDutyDetector",
        #     enable=True,
        #     data_sources=guardduty.CfnDetector.CFNDataSourceConfigurationsProperty(
        #         s3_logs=guardduty.CfnDetector.CFNS3LogsConfigurationProperty(
        #             enable=True
        #         )
        #     )
        # )

        # # Add dependency to ensure GuardDuty is enabled before creating the protection plan
        # malware_protection_plan.add_dependency(guardduty_detector)

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
                scopes=[cognito.OAuthScope.OPENID],
                # callback_urls=["http://localhost:3000"]  # Update with your actual callback URL
            )
        )

        # Create Cognito Authorizer
        cognito_authorizer = apigateway.CognitoUserPoolsAuthorizer(
            self, "IpsCognitoAuthorizer",
            cognito_user_pools=[user_pool]
        )

        # The Upload and entry-point Lambda function
        id_upload_lambda = _lambda.Function(
            self,
            "IpsHandler",
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
                "S3_BUCKET_NAME": upload_bucket.bucket_name,
                "TTL_DAYS": "365"
            },
            log_retention=logs.RetentionDays.ONE_WEEK,  # Set log retention period
        )

        upload_bucket.grant_read_write(id_delete_lambda)

        id_compress_lambda = _lambda.Function(
            self,
            "IpsHandlerCompress",
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
                allow_origins=apigateway.Cors.ALL_ORIGINS,
                allow_methods=apigateway.Cors.ALL_METHODS,
                allow_headers=['Content-Type', 'X-Api-Key', 'Authorization'],
                allow_credentials=True
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
            id_upload_lambda,
            proxy=False,
            integration_responses=[
                apigateway.IntegrationResponse(
                    status_code="200",
                    response_parameters={
                        'method.response.header.Access-Control-Allow-Origin': "'*'"
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
            authorizer=cognito_authorizer,
            authorization_type=apigateway.AuthorizationType.COGNITO
        )

        # Compare Faces - Delete
        compare_faces_resource_delete = api.root.add_resource(
            "compare-faces-delete")
        compare_faces_integration_delete = apigateway.LambdaIntegration(
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

        compare_faces_resource_delete.add_method(
            "DELETE",
            compare_faces_integration_delete,
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

        # S3 Event Notification - Compress
        upload_bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED_PUT, s3n.LambdaDestination(id_compress_lambda))

        # S3 Event Notification - Moderate
        # Commented out until step functions are introduced
        # upload_bucket.add_event_notification(
        #     s3.EventType.OBJECT_CREATED_PUT, s3n.LambdaDestination(id_moderate_lambda))

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

        CfnOutput(self, "ApiEndpoint_compare-faces",
                  value=f"{api.url}compare-faces",
                  description="Endpoint for face comparison",
                  export_name=f"{self.stack_name}-ApiEndpoint-compare-faces"
                  )

        CfnOutput(self, "ApiEndpoint_compare-faces-delete",
                  value=f"{api.url}compare-faces-delete",
                  description="Endpoint for deletion of a previous comparison",
                  export_name=f"{
                      self.stack_name}-ApiEndpoint-compare-faces-delete"
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
