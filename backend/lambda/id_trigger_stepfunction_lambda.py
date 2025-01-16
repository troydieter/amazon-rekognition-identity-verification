import boto3
import json
import logging
import os
from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import urlparse

# Initialize clients
dynamodb = boto3.resource('dynamodb')
sfn_client = boto3.client('stepfunctions')
table = dynamodb.Table(os.environ['DYNAMODB_TABLE_NAME'])

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def get_verification_id_from_key(key):
    """Extract verification ID from S3 key"""
    return key.split('/')[-1].split('.')[0]

def get_file_info_from_key(key):
    """Extract verification ID and extension from S3 key"""
    # Split path into parts
    parts = key.split('/')
    # Get filename from last part
    filename = parts[-1]
    # Split filename into name and extension
    name_parts = filename.rsplit('.', 1)
    
    return {
        'verification_id': name_parts[0],
        'extension': name_parts[1] if len(name_parts) > 1 else '',
        'type': 'identity' if parts[0] == 'identity' else 'selfie'
    }

def update_upload_status(verification_id, file_type, s3_key):
    """Update DynamoDB record with file upload status"""
    try:
        # First try to get existing record
        response = table.query(
            KeyConditionExpression='VerificationId = :vid',
            ExpressionAttributeValues={
                ':vid': verification_id
            },
            ScanIndexForward=False,
            Limit=1
        )

        current_time = Decimal(str(datetime.now(timezone.utc).timestamp()))
        
        if response['Items']:
            # Record exists, update it
            item = response['Items'][0]
            update_expr = f"""
                SET {file_type}Uploaded = :true, 
                    {file_type}UploadedAt = :time, 
                    LastUpdated = :updated,
                    {file_type}S3Key = :s3_key
            """
            expr_values = {
                ':true': True,
                ':time': current_time,
                ':updated': current_time,
                ':s3_key': s3_key
            }
            
            table.update_item(
                Key={
                    'VerificationId': verification_id,
                    'Timestamp': item['Timestamp']
                },
                UpdateExpression=update_expr,
                ExpressionAttributeValues=expr_values
            )
            
            # Check if both files are now present
            return (
                item.get('identityUploaded', False) or file_type == 'identity',
                item.get('selfieUploaded', False) or file_type == 'selfie'
            )
            
        return False, False

    except Exception as e:
        logger.error(f"Error updating upload status: {str(e)}")
        raise

def start_state_machine(verification_id, dynamo_record):
    """Start Step Functions state machine"""
    try:
        state_machine_arn = os.environ['STATE_MACHINE_ARN']
        bucket_name = os.environ['S3_BUCKET_NAME']
        
        # Get the actual S3 keys from the DynamoDB record
        id_key = dynamo_record.get('identityS3Key')
        selfie_key = dynamo_record.get('selfieS3Key')
        
        if not id_key or not selfie_key:
            raise Exception("Missing S3 keys in DynamoDB record")
        
        input_data = {
            "verification_id": verification_id,
            "id_key": f"s3://{bucket_name}/{id_key}",
            "selfie_key": f"s3://{bucket_name}/{selfie_key}",
            "user_email": dynamo_record.get('UserEmail'),
            "status": "PROCESSING",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "success": True
        }
        
        response = sfn_client.start_execution(
            stateMachineArn=state_machine_arn,
            input=json.dumps(input_data)
        )
        
        logger.info(f"Started state machine for verification ID: {verification_id}")
        return response['executionArn']
        
    except Exception as e:
        logger.error(f"Error starting state machine: {str(e)}")
        raise

def lambda_handler(event, context):
    try:
        logger.info(f"Received event: {json.dumps(event)}")
        
        # Get S3 event details
        record = event['Records'][0]['s3']
        bucket = record['bucket']['name']
        key = record['object']['key']
        
        # Get file information including extension
        file_info = get_file_info_from_key(key)
        verification_id = file_info['verification_id']
        file_type = file_info['type']
        
        logger.info(f"Processing {file_type} upload for verification ID: {verification_id}")
        
        # Update upload status and check if both files are present
        id_present, selfie_present = update_upload_status(verification_id, file_type, key)
        
        # If both files are present, start the state machine
        if id_present and selfie_present:
            logger.info(f"Both files present for verification ID: {verification_id}")
            
            # Get the record from DynamoDB
            response = table.query(
                KeyConditionExpression='VerificationId = :vid',
                ExpressionAttributeValues={
                    ':vid': verification_id
                },
                ScanIndexForward=False,
                Limit=1
            )
            
            if not response['Items']:
                raise Exception(f"No record found for verification ID: {verification_id}")
            
            # Start the state machine with actual file paths from DynamoDB
            execution_arn = start_state_machine(
                verification_id,
                response['Items'][0]
            )
            
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'State machine started',
                    'verificationId': verification_id,
                    'executionArn': execution_arn
                })
            }
        else:
            logger.info(f"Waiting for other file for verification ID: {verification_id}")
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'File uploaded, waiting for pair',
                    'verificationId': verification_id
                })
            }
            
    except Exception as e:
        logger.error(f"Error processing S3 event: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e)
            })
        }
