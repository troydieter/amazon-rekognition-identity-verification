import boto3
import json
import logging
import os
from datetime import datetime, timezone
from decimal import Decimal

logger = logging.getLogger()
logger.setLevel(os.environ.get('LOG_LEVEL', 'INFO'))

dynamodb = boto3.resource('dynamodb')
sfn_client = boto3.client('stepfunctions')

def lambda_handler(event, context):
    try:
        logger.info(f"Received event: {json.dumps(event)}")
        
        # Extract S3 event details
        s3_event = event['Records'][0]['s3']
        bucket = s3_event['bucket']['name']
        key = s3_event['object']['key']
        
        # Extract verification ID from the key
        verification_id = key.split('/')[1].split('.')[0]
        
        # Get the tracking table
        table = dynamodb.Table(os.environ['DYNAMODB_TABLE_NAME'])
        
        # Query for the item using the GSI
        response = table.query(
            KeyConditionExpression='VerificationId = :vid',
            ExpressionAttributeValues={
                ':vid': verification_id
            },
            ScanIndexForward=False,  # Get most recent first
            Limit=1
        )
        
        if not response['Items']:
            logger.error(f"No DynamoDB record found for verification ID: {verification_id}")
            raise Exception("No verification record found")
            
        item = response['Items'][0]
        current_time = datetime.now(timezone.utc)
        timestamp = Decimal(str(current_time.timestamp()))
        
        # Start state machine execution
        sfn_input = {
            "verification_id": verification_id,
            "user_email": item.get('UserEmail'),
            "dl_key": item['DLImageS3Key'],
            "selfie_key": item['SelfieImageS3Key'],
            "timestamp": current_time.isoformat(),
            "status": "STARTED",
            "success": True
        }
        
        # Start state machine execution
        sfn_response = sfn_client.start_execution(
            stateMachineArn=os.environ['STATE_MACHINE_ARN'],
            input=json.dumps(sfn_input)
        )
        
        logger.info(f"Started state machine execution: {sfn_response['executionArn']}")
        
        # Update DynamoDB record with state machine details
        update_expression = "SET StateMachineStatus = :status, " \
                          "StateMachineArn = :arn, " \
                          "StateMachineStartTime = :start_time, " \
                          "LastUpdated = :updated"
        
        expression_values = {
            ':status': 'STARTED',
            ':arn': sfn_response['executionArn'],
            ':start_time': current_time.isoformat(),
            ':updated': timestamp
        }
        
        table.update_item(
            Key={
                'VerificationId': verification_id,
                'Timestamp': item['Timestamp']  # Include the sort key
            },
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_values
        )
        
        logger.info(f"Updated DynamoDB record for verification ID: {verification_id}")
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': f'Started state machine for verification ID: {verification_id}',
                'executionArn': sfn_response['executionArn']
            })
        }
        
    except Exception as e:
        logger.error(f"Error processing event: {str(e)}")
        raise
