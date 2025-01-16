import boto3
import logging
import os
import json
import uuid
import datetime
import base64
from decimal import Decimal

# Initialize clients
dynamodb = boto3.resource('dynamodb')
s3_client = boto3.client('s3')

# Get environment variables
TABLE_NAME = os.environ.get('DYNAMODB_TABLE_NAME')
S3_BUCKET_NAME = os.environ.get('S3_BUCKET_NAME')
TTL_DAYS = int(os.environ.get('TTL_DAYS', 365))

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event, context):
    try:
        # Log only non-sensitive parts of the event
        safe_event = {k: v for k, v in event.items() if k != 'body'}
        logger.info(f"Received event: {json.dumps(safe_event)}")

        # Extract user email from Cognito authorizer context
        user_email = None
        given_name = None
        family_name = None
        if 'requestContext' in event:
            if 'authorizer' in event['requestContext']:
                if 'jwt' in event['requestContext']['authorizer']:
                    # For HTTP API (v2)
                    claims = event['requestContext']['authorizer']['jwt']['claims']
                    user_email = claims.get('email')
                    given_name = claims.get('given_name')  # Extract first name
                    family_name = claims.get(
                        'family_name')  # Extract last name
                elif 'claims' in event['requestContext']['authorizer']:
                    # For REST API (v1)
                    claims = event['requestContext']['authorizer']['claims']
                    user_email = claims.get('email')
                    given_name = claims.get('given_name')  # Extract first name
                    family_name = claims.get(
                        'family_name')  # Extract last name

        logger.info(f"User email from Cognito: {user_email}")
        logger.info(f"User first name: {given_name}")
        logger.info(f"User last name: {family_name}")

        # Check if it's an API Gateway event
        if 'body' in event:
            # Parse body if it's a string
            body = json.loads(event['body']) if isinstance(
                event['body'], str) else event['body']
            return handle_api_request(body, user_email, given_name, family_name)
        else:
            logger.error("Missing body in request")
            return cors_response(400, {'error': "Missing body in request"})

    except Exception as e:
        logger.error(
            f"Unexpected error in lambda_handler: {str(e)}", exc_info=True)
        return cors_response(500, {'error': "Internal server error"})


def handle_api_request(body, user_email, given_name, family_name):
    try:
        logger.info("Handling API Gateway request")

        selfie = body.get('selfie')
        dl = body.get('dl')

        if not selfie or not dl:
            raise KeyError('Missing selfie or dl in the request body')

        # Generate current timestamp
        current_time = datetime.datetime.now(datetime.timezone.utc)
        timestamp = Decimal(str(current_time.timestamp()))
        ttl = Decimal(
            str((current_time + datetime.timedelta(days=TTL_DAYS)).timestamp()))

        # Generate UUID for tracking
        verification_id = str(uuid.uuid4())

        # Convert base64 to bytes
        dl_bytes = base64.b64decode(dl)
        selfie_bytes = base64.b64decode(selfie)

        # Set up S3 keys
        dl_key = f"dl/{verification_id}.jpg"
        selfie_key = f"selfie/{verification_id}.jpg"
        dl_resized_key = f"resized_dl/{verification_id}.jpg"
        selfie_resized_key = f"resized_selfie/{verification_id}.jpg"

        # Upload original images to S3
        s3_client.put_object(Bucket=S3_BUCKET_NAME, Key=dl_key, Body=dl_bytes)
        s3_client.put_object(Bucket=S3_BUCKET_NAME,
                             Key=selfie_key, Body=selfie_bytes)
        logger.info(f"Files uploaded to S3: {dl_key}, {selfie_key}")

        # Write initial record to DynamoDB
        table = dynamodb.Table(TABLE_NAME)
        item = {
            'VerificationId': verification_id,
            'Status': 'PROCESSING',
            'Timestamp': timestamp,
            'TTL': ttl,
            'UserEmail': user_email,
            'GivenName': given_name, 
            'FamilyName': family_name, 
            'DLImageS3Key': f"s3://{S3_BUCKET_NAME}/{dl_key}",
            'DLImageResizedS3Key': f"s3://{S3_BUCKET_NAME}/{dl_resized_key}",
            'SelfieImageS3Key': f"s3://{S3_BUCKET_NAME}/{selfie_key}",
            'SelfieImageResizedS3Key': f"s3://{S3_BUCKET_NAME}/{selfie_resized_key}"
        }
        table.put_item(Item=item)
        logger.info(
            f"Initial record written to DynamoDB with VerificationId: {verification_id}")

        return cors_response(200, {
            'verificationId': verification_id,
            'status': 'PROCESSING',
            'timestamp': current_time.isoformat(),
            'userEmail': user_email,
            'givenName': given_name,
            'familyName': family_name
        })

    except KeyError as e:
        logger.error(f"Missing required field: {str(e)}")
        return cors_response(400, {'error': f"Missing required field: {str(e)}"})
    except Exception as e:
        logger.error(f"Error in API request: {str(e)}", exc_info=True)
        return cors_response(500, {'error': "Internal server error"})


def cors_response(status_code, body):
    return {
        'statusCode': status_code,
        'headers': {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,X-Api-Key,Authorization',
            'Access-Control-Allow-Methods': 'POST,OPTIONS',
            'Access-Control-Allow-Credentials': 'true'
        },
        'body': json.dumps(body)
    }
