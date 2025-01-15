import json
from PIL import Image
import boto3
import os
from io import BytesIO
import urllib.parse
from decimal import Decimal
from datetime import datetime, timezone
import logging
from urllib.parse import urlparse

# Initialize clients
s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def get_s3_key_from_uri(s3_uri):
    """
    Extracts the S3 key from a full S3 URI
    """
    parsed = urlparse(s3_uri)
    return parsed.path.lstrip('/')

def fetch_image(bucket, key):
    """
    Fetches image from S3
    """
    logger.info(f"Fetching object: {key} from bucket: {bucket}")
    response = s3_client.get_object(Bucket=bucket, Key=key)
    return response['Body'].read()

def resize_image(image_data):
    """
    Resizes the image to half its original size
    """
    image = Image.open(BytesIO(image_data))
    width, height = image.size
    resized = image.resize((width // 2, height // 2))
    logger.info(f"Resized image from {width}x{height} to {width//2}x{height//2}")
    return resized

def upload_image(image, bucket, key):
    """
    Uploads resized image to S3
    """
    buffer = BytesIO()
    image.save(buffer, format='JPEG', optimize=True, quality=70)
    buffer.seek(0)
    logger.info(f"Uploading resized image to {bucket}/{key}")
    response = s3_client.put_object(Bucket=bucket, Key=key, Body=buffer)
    logger.info(f"PutObject response: {response}")
    return f"s3://{bucket}/{key}"

def update_dynamodb_record(verification_id, resized_paths):
    """
    Updates the DynamoDB record with resized image paths and final status
    """
    try:
        table = dynamodb.Table(os.environ['DYNAMODB_TABLE_NAME'])
        
        # Query to get the item's Timestamp
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
            
        timestamp = response['Items'][0]['Timestamp']
        current_time = Decimal(str(datetime.now(timezone.utc).timestamp()))
        
        # Update DynamoDB with resized image paths and final status
        update_expression = """
            SET ResizedDLImageS3Key = :dl_resized,
                ResizedSelfieImageS3Key = :selfie_resized,
                LastUpdated = :updated,
                ResizedAt = :resized_at,
                StateMachineStatus = :status,
                ProcessingCompleted = :completed_at,
                Status = :verification_status
        """
        
        expression_values = {
            ':dl_resized': resized_paths['dl'],
            ':selfie_resized': resized_paths['selfie'],
            ':updated': current_time,
            ':resized_at': current_time,
            ':status': 'COMPLETED_SUCCESSFUL',
            ':completed_at': current_time,
            ':verification_status': 'VERIFIED'  # Or whatever final status you want
        }
        
        table.update_item(
            Key={
                'VerificationId': verification_id,
                'Timestamp': timestamp
            },
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_values
        )
        
        logger.info(f"Updated DynamoDB record for verification ID: {verification_id} - Status: COMPLETED_SUCCESSFUL")
        return True
        
    except Exception as e:
        logger.error(f"Error updating DynamoDB: {str(e)}")
        raise

def update_failed_status(verification_id, error_message):
    """
    Updates DynamoDB record with failed status
    """
    try:
        table = dynamodb.Table(os.environ['DYNAMODB_TABLE_NAME'])
        
        # Query to get the item's Timestamp
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
            
        timestamp = response['Items'][0]['Timestamp']
        current_time = Decimal(str(datetime.now(timezone.utc).timestamp()))
        
        table.update_item(
            Key={
                'VerificationId': verification_id,
                'Timestamp': timestamp
            },
            UpdateExpression="""
                SET StateMachineStatus = :status,
                    LastUpdated = :updated,
                    ErrorMessage = :error,
                    Status = :verification_status
            """,
            ExpressionAttributeValues={
                ':status': 'COMPLETED_FAILED',
                ':updated': current_time,
                ':error': error_message,
                ':verification_status': 'FAILED'
            }
        )
        
        logger.info(f"Updated DynamoDB record for verification ID: {verification_id} - Status: COMPLETED_FAILED")
        
    except Exception as e:
        logger.error(f"Error updating failed status in DynamoDB: {str(e)}")

def validate_image(image_data):
    """
    Validates image size and format
    """
    try:
        image = Image.open(BytesIO(image_data))
        
        # Check image format
        if image.format not in ['JPEG', 'JPG', 'PNG', 'BMP', 'TIFF']:
            raise ValueError(f"Unsupported image format: {image.format}")
        
        # Check image size (e.g., max 10MB)
        if len(image_data) > 10 * 1024 * 1024:
            raise ValueError("Image size exceeds 10MB limit")
        
        # Check dimensions (e.g., max 4000x4000)
        width, height = image.size
        if width > 4000 or height > 4000:
            raise ValueError(f"Image dimensions ({width}x{height}) exceed maximum allowed (4000x4000)")
            
        return True
        
    except Exception as e:
        logger.error(f"Image validation failed: {str(e)}")
        raise

def lambda_handler(event, context):
    """
    AWS Lambda handler for resizing images as part of Step Functions workflow
    """
    try:
        logger.info(f"Received event: {json.dumps(event)}")
        
        verification_id = event['verification_id']
        bucket_name = os.environ.get('S3_BUCKET_NAME')
        
        if not bucket_name:
            raise ValueError("S3_BUCKET_NAME environment variable is not set.")
        
        # Extract S3 keys from full URIs
        dl_key = get_s3_key_from_uri(event['dl_key'])
        selfie_key = get_s3_key_from_uri(event['selfie_key'])
        
        # Process DL image
        dl_image_data = fetch_image(bucket_name, dl_key)
        validate_image(dl_image_data)
        resized_dl = resize_image(dl_image_data)
        resized_dl_key = f"resized_{dl_key}"
        resized_dl_path = upload_image(resized_dl, bucket_name, resized_dl_key)
        
        # Process Selfie image
        selfie_image_data = fetch_image(bucket_name, selfie_key)
        validate_image(selfie_image_data)
        resized_selfie = resize_image(selfie_image_data)
        resized_selfie_key = f"resized_{selfie_key}"
        resized_selfie_path = upload_image(resized_selfie, bucket_name, resized_selfie_key)
        
        # Update DynamoDB with resized image paths
        resized_paths = {
            'dl': resized_dl_path,
            'selfie': resized_selfie_path
        }
        update_dynamodb_record(verification_id, resized_paths)
        
        return {
            'statusCode': 200,
            'verification_id': verification_id,
            'success': True,
            'resized_paths': resized_paths
        }
        
    except Exception as e:
        error_message = str(e)
        logger.error(f"Error processing resize operation: {error_message}")
        
        if 'verification_id' in locals():
            update_failed_status(verification_id, error_message)
            
        return {
            'statusCode': 500,
            'verification_id': verification_id if 'verification_id' in locals() else 'UNKNOWN',
            'success': False,
            'error': error_message
        }
