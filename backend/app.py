#!/usr/bin/env python
import os

import aws_cdk as cdk

from idplusselfie.idplusselfie_stack import IdPlusSelfieStack
from idplusselfie.site_distribution_stack import SiteDistributionStack


app = cdk.App()
IdPlusSelfieStack(app, "idplusselfieStack",
                  env=cdk.Environment(account=os.getenv(
                      'CDK_DEFAULT_ACCOUNT'), region=os.getenv('CDK_DEFAULT_REGION')),
                  )

SiteDistributionStack(app, "SiteDistributionStack",
                  env=cdk.Environment(account=os.getenv(
                      'CDK_DEFAULT_ACCOUNT'), region=os.getenv('CDK_DEFAULT_REGION')),
                  )

cdk.Tags.of(app).add("project", "amazon-rekognition-identity-verification")

app.synth()
