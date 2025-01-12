# ID Plus Selfie Identity Verification with Amazon Rekognition

A robust solution for digital identity verification using Amazon Rekognition.

## Overview

This project provides a serverless API for comparing a user's selfie with their driver's license photo, leveraging the power of Amazon Rekognition for accurate face matching.

![Frontend](./backend/docs/front_end.png)

#### Confirmation of match:
![Confirm](./backend/docs/confirm_yes.png)

#### No match found:
![Fail](./backend/docs/fail_confirmation.png)

## Architecture

### AWS Solution Architecture
#### /compare-faces
![Visual AWS Architecture](./backend/docs/diagram01.png)
1. User uploads files (ID + Selfie) to the system.
2. Amazon API Gateway receives the POST request at the `/prod/CompareApi` endpoint.
3. IAM Role assumes the necessary permissions for the Lambda function.
4. CloudWatch Logs record the Lambda function's execution details.
5. The AWS Lambda function uses the AWS SDK to interact with Amazon Rekognition.
6. The Rekognition response is stored in a DynamoDB table with the `VerificationId` attribute in the item. The object is also stored in Amazon S3 for post-processing. (see: the purple boxes shown to the right)
7. Amazon Rekognition processes the images and returns a response (box at the bottom).

#### /compare-faces-delete
![Visual AWS Architecture](./backend/docs/diagram02.png)
1. Admin user receives a request to delete an identity that has been verified. They retrieve the `VerificationId` value as initially registered by the user.
2. A `DELETE` API call is made to API Gateway with `VerificationId` as a parameter and the necessary `x-api-key` value in the header.
3. IAM Role assumes the necessary permissions for the Lambda function.
4. CloudWatch Logs record the Lambda function's execution details.
5. The item in the DynamoDB table, based on the primary key `VerificationId` is deleted along with the Amazon S3 objects (one of each). The response is sent back via the API call that it has been deleted successfully.

#### /compare-faces-resizing
![Visual AWS Architecture](./backend/docs/diagram03.png)
1. The drivers license (ID) and selfie are uploaded.
2. CloudWatch Logs record the Lambda function's execution details. The `eventSourceMapping` for Amazon S3 objects occurs, invoking the function.
3. IAM Role assumes the necessary permissions for the Lambda function.
4. The file is resized and optimized, and stored in the `dl_resized` or `selfie_resized` key (directories) in the Amazon S3 upload bucket. The lifecycle policy applies for 1yr/optimized and 30days/original.

## 01 - Deployment - Backend (`IdPlusSelfieStack`)

This project is deployed using [AWS CDK](https://github.com/aws/aws-cdk) (`2.175.1`) for infrastructure as code. Follow these steps to deploy:

1. Ensure you have an AWS account and an AWS IAM user/role with appropriate permissions.

2. Set up the AWS CLI: [AWS CLI Configuration Guide](https://docs.aws.amazon.com/cli/latest/userguide/cli-chap-configure.html)

3. Install AWS CDK: [CDK Python Guide](https://docs.aws.amazon.com/cdk/v2/guide/work-with-cdk-python.html)

4. Change directory to the backend:
   ```
   cd backend
   ```

4. Navigate to the project directory and create a virtual environment:
   - Windows: `.venv\Scripts\activate`
   - Mac/Linux: `source .venv/bin/activate`

5. Install dependencies: `python -m pip install -r requirements.txt`

6. **LEAVE** the following commented in `backend/app.py`, it will be un-commented after the frontend is deployed:

    ```
    # SiteDistributionStack(app, "SiteDistributionStack",
    #                   env=cdk.Environment(account=os.getenv(
    #                       'CDK_DEFAULT_ACCOUNT'), region=os.getenv('CDK_DEFAULT_REGION')),
    #                   )
    ```

6. Deploy the stack: `cdk deploy --all`

## 02 - Deployment - Frontend

Before you begin, ensure you have the following installed:
- Node.js (v14.0.0 or later)
- npm (v6.0.0 or later)

1. **NOTE:** You will need to manually deploy Amazon Cognito. Deploy the Cognito User Pool manually via the AWS CLI or the AWS Console. [More information is available here.](https://docs.aws.amazon.com/cognito/latest/developerguide/getting-started-user-pools.html)

2. Change directory to the frontend:
   ```
   cd frontend
   ```

3. Install dependencies:
   ```
   npm install --legacy-peer-deps
   ```

4. Set up environment variables:
   - Copy the `.env.example` file to a new file named `.env`:
     ```
     cp .env.example.env .env
     ```
   - Open the `.env` file and replace the placeholder values with your actual AWS credentials and S3 bucket information:
     ```
      REACT_APP_API_URL=https://example.execute-api.REGION.amazonaws.com/prod
      REACT_APP_API_KEY=xyz123
      REACT_APP_USERPOOL_CLIENTID=example123
      REACT_APP_USERPOOL_ID=us-east-1_example
      ```

5. Build it:
   ```
   npm run build --legacy-peer-deps
   ``` 

## 03 - Deployment - Backend (`SiteDistributionStack`)

1. Change back to the backend directory:
    ```
    cd ../backend
    ```

2. Uncomment the `SiteDistributionStack` in `app.py` as shown:

    ```
      SiteDistributionStack(app, "SiteDistributionStack",
                        env=cdk.Environment(account=os.getenv(
                        'CDK_DEFAULT_ACCOUNT'), region=os.getenv('CDK_DEFAULT_REGION')),
                        )
    ```

3. Deploy the stack, which now includes both the `IdPlusSelfieStack` and the `SiteDistributionStack`:

    ```
    cdk deploy --all
    ```

4. Use the `SiteDistributionStack.SiteDistributionName` CloudFormation output to visit the site:

    ```
    SiteDistributionStack.SiteDistributionName = dibc4iuf2q3bb.cloudfront.net
    ```

    and enter the username (remember, it's `demo` as the username and `demo` as the password.)

## TO-DO
* Migrate the AWS Cognito process from manual creation to using AWS CDK. Currently, you must manually provision the AWS Cognitio User Pool and set the necessary attributes. Once that is created, you export the UserPool `ClientID` and `ID` to the `.\frontend\.env` file.
* Update the API calls to include the user session token.
* Add the Cognito User Pool Authorizer to the API 

## Deployment Recap

1. Deploy the backend (`./backend`) using AWS CDK (`cdk deploy --all`) leaving the `SiteDistributionStack` stack commented.

2. Load the .env file (using `.env.example` in the `./frontend` directory) and deploy the frontend (`./frontend`) using NodeJS (`npm run build`)

3. Uncomment the `SiteDistributionStack` in `app.py` and use `cdk deploy --all`

4. Destroy when done:

   ```
   cd ../backend
   cdk destroy
   ```

# API Documentation

## Endpoints

### Compare Faces

Create a new face comparison.

- URL: `/compare-faces`
- Method: `POST`
- Auth: API Key required
- Content-Type: `application/json`

Request Body:
```
{
  "selfie": "base64_encoded_selfie_image",
  "dl": "base64_encoded_drivers_license_image"
}
```

Response:
```
{
  "verificationId": "string",
  "result": {
    "similarity": "number",
    "message": "string",
    "timestamp": "string (ISO 8601 format)"
  }
}
```

### Delete Comparison

Delete an existing face comparison.

- URL: `/compare-faces-delete`
- Method: `DELETE`
- Auth: API Key required
- Query Parameters:
  - `verificationId`: string (required)

Response:
```
{
  "message": "string"
}
```

## Authentication

All endpoints require an API key to be included in the request headers:

`X-Api-Key: your_api_key_here`

## Rate Limiting

The API is subject to the following rate limits:
- Rate limit: 10 requests per second
- Burst limit: 2 requests

## Error Responses

The API uses standard HTTP response codes to indicate the success or failure of requests. In case of errors, additional information may be provided in the response body.

Common error codes:
- 400: Bad Request
- 401: Unauthorized
- 403: Forbidden
- 404: Not Found
- 429: Too Many Requests
- 500: Internal Server Error

## Clean Up

To remove all deployed backend resources:

```
cdk destroy
```

## Security

See [CONTRIBUTING](CONTRIBUTING.md#security-issue-notifications) for more information.

## License

This project is licensed under the MIT-0 License. See the [LICENSE](LICENSE) file for details.