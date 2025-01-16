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
        if 'requestContext' in event:
            if 'authorizer' in event['requestContext']:
                if 'jwt' in event['requestContext']['authorizer']:
                    # For HTTP API (v2)
                    claims = event['requestContext']['authorizer']['jwt']['claims']
                    user_email = claims.get('email')
                elif 'claims' in event['requestContext']['authorizer']:
                    # For REST API (v1)
                    claims = event['requestContext']['authorizer']['claims']
                    user_email = claims.get('email')

        logger.info(f"User email from Cognito: {user_email}")

        # Check if it's an API Gateway event
        if 'body' in event:
            # Parse body if it's a string
            body = json.loads(event['body']) if isinstance(
                event['body'], str) else event['body']
            return handle_api_request(body, user_email)
        else:
            logger.error("Missing body in request")
            return cors_response(400, {'error': "Missing body in request"})

    except Exception as e:
        logger.error(f"Unexpected error in lambda_handler: {str(e)}", exc_info=True)
        return cors_response(500, {'error': "Internal server error"})

def get_file_info_from_base64(base64_data):
    """Extract file type from base64 data"""
    # Check if the base64 string contains metadata
    if ';base64,' in base64_data:
        metadata, base64_string = base64_data.split(';base64,')
        if metadata.startswith('data:'):
            mime_type = metadata.split(':')[1]
            extension = mime_type.split('/')[-1]
            # Convert common mime types to extensions
            if extension == 'jpeg':
                extension = 'jpg'
            return base64_string, extension
    
    # If no metadata, return the original string and default to jpg
    return base64_data, 'jpg'

def handle_api_request(body, user_email):
    try:
        logger.info("Handling API Gateway request")

        selfie = body.get('selfie')
        identity = body.get('identity')

        if not selfie or not identity:
            raise KeyError('Missing selfie or identity in the request body')

        # Generate current timestamp
        current_time = datetime.datetime.now(datetime.timezone.utc)
        timestamp = Decimal(str(current_time.timestamp()))
        ttl = Decimal(str((current_time + datetime.timedelta(days=TTL_DAYS)).timestamp()))

        # Generate UUID for tracking
        verification_id = str(uuid.uuid4())

        # Process base64 data and get file types
        id_base64, id_extension = get_file_info_from_base64(identity)
        selfie_base64, selfie_extension = get_file_info_from_base64(selfie)

        # Convert base64 to bytes
        id_bytes = base64.b64decode(id_base64)
        selfie_bytes = base64.b64decode(selfie_base64)

        # Set up S3 keys with appropriate extensions
        id_key = f"identity/{verification_id}.{id_extension}"
        selfie_key = f"selfie/{verification_id}.{selfie_extension}"
        id_resized_key = f"resized_id/{verification_id}.{id_extension}"
        selfie_resized_key = f"resized_selfie/{verification_id}.{selfie_extension}"

        # Upload original images to S3 with content type
        s3_client.put_object(
            Bucket=S3_BUCKET_NAME, 
            Key=id_key, 
            Body=id_bytes,
            ContentType=f'image/{id_extension}'
        )
        s3_client.put_object(
            Bucket=S3_BUCKET_NAME, 
            Key=selfie_key, 
            Body=selfie_bytes,
            ContentType=f'image/{selfie_extension}'
        )
        logger.info(f"Files uploaded to S3: {id_key}, {selfie_key}")

        # Write initial record to DynamoDB
        table = dynamodb.Table(TABLE_NAME)
        item = {
            'VerificationId': verification_id,
            'Status': 'PROCESSING',
            'Timestamp': timestamp,
            'TTL': ttl,
            'UserEmail': user_email,
            'IdentificationS3Key': f"s3://{S3_BUCKET_NAME}/{id_key}",
            'IdentificationImageResizedS3Key': f"s3://{S3_BUCKET_NAME}/{id_resized_key}",
            'SelfieImageS3Key': f"s3://{S3_BUCKET_NAME}/{selfie_key}",
            'SelfieImageResizedS3Key': f"s3://{S3_BUCKET_NAME}/{selfie_resized_key}",
            'IdentificationExtension': id_extension,
            'SelfieExtension': selfie_extension
        }
        table.put_item(Item=item)
        logger.info(f"Initial record written to DynamoDB with VerificationId: {verification_id}")

        return cors_response(200, {
            'verificationId': verification_id,
            'status': 'PROCESSING',
            'timestamp': current_time.isoformat(),
            'userEmail': user_email
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