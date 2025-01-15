import boto3
import json
import logging
import os
from datetime import datetime, timezone
from decimal import Decimal

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize DynamoDB client
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['DYNAMODB_TABLE_NAME'])

def update_status(verification_id, status):
    try:
        # First, query to get the item's Timestamp
        response = table.query(
            KeyConditionExpression='VerificationId = :vid',
            ExpressionAttributeValues={
                ':vid': verification_id
            },
            ScanIndexForward=False,
            Limit=1
        )
        
        if response['Items']:
            timestamp = response['Items'][0]['Timestamp']
            current_time = Decimal(str(datetime.now(timezone.utc).timestamp()))
            
            # Update the status
            table.update_item(
                Key={
                    'VerificationId': verification_id,
                    'Timestamp': timestamp
                },
                UpdateExpression="SET #status = :status, LastUpdated = :updated",
                ExpressionAttributeNames={
                    '#status': 'Status'  # Status is a reserved word in DynamoDB
                },
                ExpressionAttributeValues={
                    ':status': status,
                    ':updated': current_time
                }
            )
            logger.info(f"Updated status to {status} for verification ID: {verification_id}")
        else:
            logger.error(f"No record found for verification ID: {verification_id}")
            raise Exception("Record not found")
            
    except Exception as e:
        logger.error(f"Error updating status: {str(e)}")
        raise

def lambda_handler(event, context):
    try:
        logger.info(f"Received event: {json.dumps(event)}")
        
        verification_id = event['verification_id']
        
        # Update initial status
        update_status(verification_id, "COMPARING FACES")
        
        # Do the face comparison rekognition work here...
        
        # Update final status
        update_status(verification_id, "SUCCESSFUL_FACIAL_COMPARISON_COMPLETED")
        
        return {
            'statusCode': 200,
            'success': True,
            'details': {
                'verification_id': verification_id,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'status': "SUCCESSFUL_FACIAL_COMPARISON_COMPLETED"
            }
        }
        
    except Exception as e:
        logger.error(f"Error in lambda_handler: {str(e)}")
        return {
            'statusCode': 500,
            'success': False,
            'error': str(e)
        }
