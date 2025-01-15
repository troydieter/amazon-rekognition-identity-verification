import boto3
import json
import logging
import os
from datetime import datetime, timezone
from decimal import Decimal

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['DYNAMODB_TABLE_NAME'])

def lambda_handler(event, context):
    try:
        logger.info(f"Received event: {json.dumps(event)}")
        
        verification_id = event['verification_id']
        status = event['status']
        
        # First, query to get the item's Timestamp
        response = table.query(
            KeyConditionExpression='VerificationId = :vid',
            ExpressionAttributeValues={
                ':vid': verification_id
            },
            ScanIndexForward=False,  # Get most recent first
            Limit=1
        )
        
        if not response['Items']:
            raise Exception(f"No record found for verification ID: {verification_id}")
            
        # Get the Timestamp from the existing record
        timestamp = response['Items'][0]['Timestamp']
        
        # Now update with both key attributes
        current_time = datetime.now(timezone.utc)
        update_timestamp = Decimal(str(current_time.timestamp()))
        
        update_expression = "SET StateMachineStatus = :status, LastUpdated = :updated"
        expression_values = {
            ':status': status,
            ':updated': update_timestamp
        }
        
        table.update_item(
            Key={
                'VerificationId': verification_id,
                'Timestamp': timestamp  # Include the original timestamp as sort key
            },
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_values
        )
        
        logger.info(f"Successfully updated status to {status} for verification ID: {verification_id}")
        
        return {
            'statusCode': 200,
            'body': f"Updated status to {status} for verification ID: {verification_id}"
        }
        
    except Exception as e:
        logger.error(f"Error updating status: {str(e)}")
        raise
