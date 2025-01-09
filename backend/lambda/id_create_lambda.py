import boto3
import logging
import os
import json
import uuid
import datetime
import base64
from decimal import Decimal, ROUND_DOWN

# Initialize Rekognition and DynamoDB clients
rekognition_client = boto3.client('rekognition')
dynamodb = boto3.resource('dynamodb')
s3_client = boto3.client('s3')

# Get the DynamoDB table name from environment variable
TABLE_NAME = os.environ.get('DYNAMODB_TABLE_NAME')
S3_BUCKET_NAME = os.environ.get('S3_BUCKET_NAME')

TTL_DAYS = int(os.environ.get('TTL_DAYS', 365))  # Default to 365 if not set

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event, context):
    try:
        # Log only non-sensitive parts of the event
        safe_event = {k: v for k, v in event.items() if k != 'body'}
        logger.info(f"Received event: {json.dumps(safe_event)}")

        # Check if it's an API Gateway event
        if 'requestContext' in event and 'http' in event['requestContext']:
            http_method = event['requestContext']['http']['method']

            # Handle CORS preflight request
            if http_method == 'OPTIONS':
                return {
                    'statusCode': 200,
                    'headers': {
                        'Access-Control-Allow-Origin': '*',
                        'Access-Control-Allow-Headers': 'Content-Type,X-Api-Key',
                        'Access-Control-Allow-Methods': 'POST,OPTIONS'
                    },
                    'body': ''
                }

            # Handle POST request
            if http_method == 'POST':
                if 'body' in event:
                    body = json.loads(event['body']) if isinstance(
                        event['body'], str) else event['body']
                    return handle_api_request(body)
                else:
                    logger.error("Missing body in POST request")
                    return cors_response(400, {'error': "Missing body in POST request"})

            logger.error(f"Unsupported HTTP method: {http_method}")
            return cors_response(405, {'error': "Method not allowed"})

        # If it's not an API Gateway event, assume it's a direct invocation
        elif 'body' in event:
            body = event['body'] if isinstance(
                event['body'], dict) else json.loads(event['body'])
            return handle_api_request(body)

        else:
            logger.error("Unrecognized event structure")
            return cors_response(400, {'error': "Unrecognized event structure"})

    except Exception as e:
        logger.error(f"Unexpected error in lambda_handler: {
                     str(e)}", exc_info=True)
        return cors_response(500, {'error': "Internal server error"})


def handle_api_request(body):
    try:
        logger.info("Handling API Gateway request")

        # Log only the keys present in the body, not the values
        logger.info(f"Received body keys: {list(body.keys())}")

        selfie = body.get('selfie')
        dl = body.get('dl')

        # Generate current timestamp
        current_time = datetime.datetime.now(datetime.timezone.utc)
        timestamp = Decimal(str(current_time.timestamp()))
        ttl = Decimal(
            str((current_time + datetime.timedelta(days=TTL_DAYS)).timestamp()))

        if not selfie or not dl:
            raise KeyError('Missing selfie or dl in the request body')

        # Log the length of the base64 strings instead of their content
        logger.info(f"Selfie base64 length: {len(selfie)}")
        logger.info(f"Driver's license base64 length: {len(dl)}")

        # Convert base64 to bytes
        dl_bytes = base64.b64decode(dl)
        selfie_bytes = base64.b64decode(selfie)

        # Generate UUID for DynamoDB partition key
        verification_id = str(uuid.uuid4())

        # Upload files to S3
        dl_key = f"dl/{verification_id}.jpg"
        selfie_key = f"selfie/{verification_id}.jpg"
        dl_resized_key = f"resized_dl/{verification_id}.jpg"
        selfie_resized_key = f"resized_selfie/{verification_id}.jpg"

        s3_client.put_object(Bucket=S3_BUCKET_NAME, Key=dl_key, Body=dl_bytes)
        s3_client.put_object(Bucket=S3_BUCKET_NAME,
                             Key=selfie_key, Body=selfie_bytes)

        logger.info(f"Files uploaded to S3: {dl_key}, {selfie_key}")

        # Call Rekognition CompareFaces API
        logger.info("Calling Rekognition CompareFaces API")
        response = rekognition_client.compare_faces(
            SimilarityThreshold=80,
            SourceImage={'Bytes': dl_bytes},
            TargetImage={'Bytes': selfie_bytes}
        )

        if not response['FaceMatches']:
            logger.info("No face matches found")
            result = {
                'verificationId': verification_id,
                'similarity': Decimal('0'),
                'message': 'No face matches found'
            }
        else:
            similarity = Decimal(str(response['FaceMatches'][0]['Similarity']))
            logger.info(f"The face matched with a {
                        similarity}% confidence rate")
            result = {
                'verificationId': verification_id,
                'similarity': similarity,
                'message': f"The face matched with a {similarity}% confidence rate"
            }

        # Write result to DynamoDB
        table = dynamodb.Table(TABLE_NAME)
        item = {
            'VerificationId': verification_id,
            'Similarity': result['similarity'],
            'Message': result['message'],
            'Timestamp': timestamp,
            'TTL': ttl,
            'DLImageS3Key': f"s3://{S3_BUCKET_NAME}/{dl_key}",
            'DLImageResizedS3Key': f"s3://{S3_BUCKET_NAME}/{dl_resized_key}",
            'SelfieImageS3Key': f"s3://{S3_BUCKET_NAME}/{selfie_key}",
            "SelfieImageResizedS3Key": f"s3://{S3_BUCKET_NAME}/{selfie_resized_key}"
        }
        table.put_item(Item=item)
        logger.info(f"Result written to DynamoDB with VerificationId: {verification_id}")

        return cors_response(200, {
            'verificationId': verification_id,
            'result': {
                'similarity': float(result['similarity']),
                'message': result['message'],
                'timestamp': current_time.isoformat()
            }
        })

    except KeyError as e:
        logger.error(f"Missing required field: {str(e)}")
        return cors_response(400, {'error': f"Missing required field: {str(e)}"})
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in request body: {str(e)}")
        return cors_response(400, {'error': "Invalid JSON in request body"})
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
