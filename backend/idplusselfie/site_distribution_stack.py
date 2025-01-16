from aws_cdk import (
    Duration,
    Stack,
    aws_s3 as s3,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as cloudfront_origins,
    aws_s3_deployment as s3_deployment,
    aws_wafv2 as wafv2,
    RemovalPolicy,
    CfnOutput,
)
from constructs import Construct


class SiteDistributionStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        redirect_func = cloudfront.Function(self, "Redirect_CF_Function", code=cloudfront.FunctionCode.from_file(file_path="lambda/redirect_func.js"),
                                              comment="Redirect for SPA app's")

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

        sec_policy = cloudfront.ResponseHeadersPolicy(self, "SecPolicy",
                                security_headers_behavior=cloudfront.ResponseSecurityHeadersBehavior(
                                    content_type_options=cloudfront.ResponseHeadersContentTypeOptions(
                                        override=True),
                                    frame_options=cloudfront.ResponseHeadersFrameOptions(
                                        frame_option=cloudfront.HeadersFrameOption.DENY, override=True),
                                    referrer_policy=cloudfront.ResponseHeadersReferrerPolicy(
                                        referrer_policy=cloudfront.HeadersReferrerPolicy.NO_REFERRER,
                                        override=True),
                                    strict_transport_security=cloudfront.ResponseHeadersStrictTransportSecurity(
                                        access_control_max_age=Duration.days(30),
                                        include_subdomains=True, override=True),
                                ))

        cfn_web_acl = wafv2.CfnWebACL(self, "WebACL",
            default_action=wafv2.CfnWebACL.DefaultActionProperty(allow={}),
            scope="CLOUDFRONT",
            visibility_config=wafv2.CfnWebACL.VisibilityConfigProperty(
                cloud_watch_metrics_enabled=True,
                metric_name="WebACLMetric",
                sampled_requests_enabled=True
            ),
            rules=[
                # AWS Managed Rules for Common Threats
                wafv2.CfnWebACL.RuleProperty(
                    name="AWSManagedRulesCommonRuleSet",
                    priority=1,
                    override_action=wafv2.CfnWebACL.OverrideActionProperty(none={}),
                    statement=wafv2.CfnWebACL.StatementProperty(
                        managed_rule_group_statement=wafv2.CfnWebACL.ManagedRuleGroupStatementProperty(
                            vendor_name="AWS",
                            name="AWSManagedRulesCommonRuleSet"
                        )
                    ),
                    visibility_config=wafv2.CfnWebACL.VisibilityConfigProperty(
                        cloud_watch_metrics_enabled=True,
                        metric_name="AWSManagedRulesCommonRuleSetMetric",
                        sampled_requests_enabled=True
                    )
                ),
                # Rate Limiting Rule
                wafv2.CfnWebACL.RuleProperty(
                    name="LimitRequests100",
                    priority=2,
                    action=wafv2.CfnWebACL.RuleActionProperty(
                        block={}
                    ),
                    statement=wafv2.CfnWebACL.StatementProperty(
                        rate_based_statement=wafv2.CfnWebACL.RateBasedStatementProperty(
                            aggregate_key_type="IP",
                            limit=100
                        )
                    ),
                    visibility_config=wafv2.CfnWebACL.VisibilityConfigProperty(
                        cloud_watch_metrics_enabled=True,
                        metric_name="LimitRequests100Metric",
                        sampled_requests_enabled=True
                    )
                )
            ]
        )

        # Create the CloudFront distribution
        site_distribution = cloudfront.Distribution(self, "SiteDistribution",
                                                    price_class=cloudfront.PriceClass.PRICE_CLASS_100,
                                                    default_root_object="index.html",
                                                    comment="CF Distribution for amazon-rekognition-identity-verification",
                                                    web_acl_id=cfn_web_acl.attr_arn,
                                                    default_behavior=cloudfront.BehaviorOptions(origin=cloudfront_origins.S3BucketOrigin.with_origin_access_control(origin_bucket),
                                                                                                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                                                                                                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
                                                                                                response_headers_policy=sec_policy,
                                                                                                function_associations=[cloudfront.FunctionAssociation(
                                                                                                    function=redirect_func,
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
