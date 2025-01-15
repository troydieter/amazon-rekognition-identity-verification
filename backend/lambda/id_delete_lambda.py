import boto3
import logging
import os
import json
from botocore.exceptions import ClientError

# Initialize DynamoDB and S3 clients
dynamodb = boto3.resource('dynamodb')
s3 = boto3.client('s3')

# Get the DynamoDB table name and S3 bucket name from environment variables
TABLE_NAME = os.environ.get('DYNAMODB_TABLE_NAME')
S3_BUCKET_NAME = os.environ.get('S3_BUCKET_NAME')

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    logger.info(f"Received event: {json.dumps(event)}")

    try:
        # Extract verificationId from query parameters
        verification_id = event.get('queryStringParameters', {}).get('verificationId')

        if not verification_id:
            logger.error("Missing verificationId in the request")
            return cors_response(400, {'error': "Missing verificationId in the request"})

        # Query the item to get its Timestamp and S3 keys
        table = dynamodb.Table(TABLE_NAME)
        response = table.query(
            KeyConditionExpression='VerificationId = :vid',
            ExpressionAttributeValues={
                ':vid': verification_id
            }
        )

        items = response.get('Items', [])
        if not items:
            logger.error(f"No item found with VerificationId: {verification_id}")
            return cors_response(404, {'error': f"No item found with VerificationId: {verification_id}"})

        # Assuming there's only one item per VerificationId
        item = items[0]
        timestamp = item.get('Timestamp')
        dl_key = item.get('DLImageS3Key')
        selfie_key = item.get('SelfieImageS3Key')

        # Delete the item from DynamoDB
        table.delete_item(
            Key={
                'VerificationId': verification_id,
                'Timestamp': timestamp
            }
        )

        # Delete the objects from S3
        if dl_key:
            s3.delete_object(Bucket=S3_BUCKET_NAME, Key=dl_key)
        if selfie_key:
            s3.delete_object(Bucket=S3_BUCKET_NAME, Key=selfie_key)

        logger.info(f"Item with VerificationId {verification_id} and associated S3 objects deleted successfully")
        return cors_response(200, {'message': f"Verification with ID {verification_id} and associated files deleted successfully"})

    except ClientError as e:
        logger.error(f"ClientError: {str(e)}")
        return cors_response(500, {'error': str(e)})
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        return cors_response(500, {'error': "Internal server error"})

def cors_response(status_code, body):
    return {
        'statusCode': status_code,
        'headers': {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,X-Api-Key',
            'Access-Control-Allow-Methods': 'DELETE,OPTIONS'
        },
        'body': json.dumps(body)
    }
