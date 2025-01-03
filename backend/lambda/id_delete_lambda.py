import boto3
import logging
import os
import json

# Initialize DynamoDB client
dynamodb = boto3.resource('dynamodb')

# Get the DynamoDB table name from environment variable
TABLE_NAME = os.environ.get('DYNAMODB_TABLE_NAME')

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event, context):
    logger.info(f"Received event: {json.dumps(event)}")

    try:
        # Extract verificationId from query parameters
        verification_id = event.get(
            'queryStringParameters', {}).get('verificationId')

        if not verification_id:
            logger.error("Missing verificationId in the request")
            return {
                'statusCode': 400,
                'body': json.dumps({'error': "Missing verificationId in the request"})
            }

        # Query the item to get its Timestamp
        table = dynamodb.Table(TABLE_NAME)
        response = table.query(
            KeyConditionExpression='VerificationId = :vid',
            ExpressionAttributeValues={
                ':vid': verification_id
            }
        )

        items = response.get('Items', [])
        if not items:
            logger.error(f"No item found with VerificationId: {
                         verification_id}")
            return {
                'statusCode': 404,
                'body': json.dumps({'error': f"No item found with VerificationId: {verification_id}"})
            }

        # Assuming there's only one item per VerificationId
        item = items[0]
        timestamp = item.get('Timestamp')

        # Delete the item using both VerificationId and Timestamp
        delete_response = table.delete_item(
            Key={
                'VerificationId': verification_id,
                'Timestamp': timestamp
            }
        )

        logger.info(f"Item with VerificationId {
                    verification_id} deleted successfully")
        return {
            'statusCode': 200,
            'body': json.dumps({'message': f"Verification with ID {verification_id} deleted successfully"})
        }

    except ClientError as e:
        logger.error(f"ClientError: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': "Internal server error"})
        }


def delete_verification(verification_id):
    try:
        table = dynamodb.Table(TABLE_NAME)
        response = table.delete_item(
            Key={
                'VerificationId': verification_id
            }
        )
        logger.info(f"Item with VerificationId {
                    verification_id} deleted successfully")
        return cors_response(200, {'message': f"Verification with ID {verification_id} deleted successfully"})
    except Exception as e:
        logger.error(f"Error deleting item with VerificationId {
                     verification_id}: {str(e)}")
        return cors_response(500, {'error': f"Error deleting verification with ID {verification_id}"})


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
