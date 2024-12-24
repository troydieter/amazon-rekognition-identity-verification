from aws_cdk import (
    Stack,
    aws_lambda as _lambda,
    aws_iam as iam,
    aws_apigateway as apigateway,
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

        # Define API Gateway resource and method
        ips_resource = api.root.add_resource("ips")
        ips_resource.add_method("POST")  # POST /ips
