import boto3
import json
import os
from decimal import Decimal
import logging
from datetime import datetime, timezone

# Initialize clients
rekognition_client = boto3.client('rekognition')
dynamodb = boto3.resource('dynamodb')

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def moderate_image(photo, bucket):
    """
    Uses Amazon Rekognition to detect moderation labels in the given image.
    Returns a dictionary with label names and their confidence scores.
    """
    try:
        response = rekognition_client.detect_moderation_labels(
            Image={'S3Object': {'Bucket': bucket, 'Name': photo}}
        )
        
        logger.info(f'Detected moderation labels for {photo}')
        labels = []
        for label in response.get('ModerationLabels', []):
            logger.info(f"{label['Name']} : {label['Confidence']:.2f}")
            logger.info(f"Parent: {label.get('ParentName', 'None')}")
            labels.append({
                'Name': label['Name'],
                'Confidence': float(Decimal(str(label['Confidence'])).quantize(Decimal('.01'))),
                'ParentName': label.get('ParentName', None)
            })
        return labels
    except Exception as e:
        logger.error(f"Error detecting moderation labels for {photo} in bucket {bucket}: {str(e)}")
        raise

def update_dynamodb_record(verification_id, moderation_results):
    """
    Updates the DynamoDB record with moderation results
    """
    try:
        table = dynamodb.Table(os.environ['DYNAMODB_TABLE_NAME'])
        
        # First, query to get the item's Timestamp
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
            
        # Get the Timestamp from the existing record
        timestamp = response['Items'][0]['Timestamp']
        current_time = Decimal(str(datetime.now(timezone.utc).timestamp()))
        
        # Update DynamoDB with moderation results
        update_expression = """
            SET ModerationLabels = :labels,
                ModerationStatus = :status,
                LastUpdated = :updated,
                ModeratedAt = :moderated_at
        """
        
        expression_values = {
            ':labels': moderation_results['Labels'],
            ':status': moderation_results['Status'],
            ':updated': current_time,
            ':moderated_at': current_time
        }
        
        table.update_item(
            Key={
                'VerificationId': verification_id,
                'Timestamp': timestamp
            },
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_values
        )
        
        logger.info(f"Updated DynamoDB record for verification ID: {verification_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error updating DynamoDB: {str(e)}")
        raise

def lambda_handler(event, context):
    """
    AWS Lambda handler for processing moderation labels as part of Step Functions workflow.
    """
    try:
        logger.info(f"Received event: {json.dumps(event)}")
        
        # Get parameters from Step Functions input
        verification_id = event['verification_id']
        dl_key = event['dl_key'].split('/')[-1]  # Extract key from full S3 path
        selfie_key = event['selfie_key'].split('/')[-1]  # Extract key from full S3 path
        
        bucket_name = os.environ.get('S3_BUCKET_NAME')
        if not bucket_name:
            raise ValueError("S3_BUCKET_NAME environment variable is not set.")
        
        # Process both images
        dl_moderation = moderate_image(dl_key, bucket_name)
        selfie_moderation = moderate_image(selfie_key, bucket_name)
        
        # Combine results
        moderation_results = {
            'Status': 'Moderation Labels Detected',
            'Labels': {
                'dl_labels': dl_moderation,
                'selfie_labels': selfie_moderation
            }
        }
        
        # Update DynamoDB
        update_dynamodb_record(verification_id, moderation_results)
        
        # Determine if any concerning labels were found
        # You can customize this logic based on your requirements
        concerning_labels = any(
            label['Confidence'] > 80 
            for labels in [dl_moderation, selfie_moderation] 
            for label in labels
        )
        
        return {
            'statusCode': 200,
            'verification_id': verification_id,
            'success': not concerning_labels,  # False if concerning labels found
            'moderation_results': moderation_results
        }
        
    except Exception as e:
        logger.error(f"Error processing moderation labels: {str(e)}")
        return {
            'statusCode': 500,
            'verification_id': verification_id if 'verification_id' in locals() else 'UNKNOWN',
            'success': False,
            'error': str(e)
        }
