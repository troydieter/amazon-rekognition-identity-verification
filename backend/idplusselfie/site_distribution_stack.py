from aws_cdk import (
    Duration,
    Stack,
    aws_s3 as s3,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as cloudfront_origins,
    aws_s3_deployment as s3_deployment,
    RemovalPolicy,
    CfnOutput,
)
from constructs import Construct


class SiteDistributionStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        basic_auth_func = cloudfront.Function(self, "Basic_Auth_CF_Function", code=cloudfront.FunctionCode.from_file(file_path="lambda/basic_auth.js"),
                                              comment="Simple authentication of the user")

        # Create the S3 origin bucket
        origin_bucket = s3.Bucket(
            self, "OriginBucket",
            bucket_name=None,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            versioned=True,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True
        )

        # Create the CloudFront distribution
        site_distribution = cloudfront.Distribution(self, "SiteDistribution",
                                                    price_class=cloudfront.PriceClass.PRICE_CLASS_100,
                                                    default_root_object="index.html",
                                                    comment="CF Distribution for amazon-rekognition-identity-verification",
                                                    default_behavior=cloudfront.BehaviorOptions(origin=cloudfront_origins.S3BucketOrigin.with_origin_access_control(origin_bucket),
                                                                                                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                                                                                                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
                                                                                                function_associations=[cloudfront.FunctionAssociation(
                                                                                                    function=basic_auth_func,
                                                                                                    event_type=cloudfront.FunctionEventType.VIEWER_REQUEST)]
                                                                                                ))

        s3_deployment.BucketDeployment(self, "DeployStaticSiteContents", sources=[s3_deployment.Source.asset("../frontend/build")],
                                       destination_bucket=origin_bucket, distribution=site_distribution, distribution_paths=["/*"])

        # Outputs to assist debugging and deployment
        self.output_cfn_info(origin_bucket, site_distribution)

    def output_cfn_info(self, origin_bucket, site_distribution):
        CfnOutput(self, "OriginBucketName", value=origin_bucket.bucket_name,
                  description="The name of the S3 origin bucket")

        CfnOutput(self, "SiteDistributionName", value=f"https://{site_distribution.distribution_domain_name}/",
                  description="The CloudFront URL")
