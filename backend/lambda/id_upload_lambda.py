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
        logger.info(f"Received event: {json.dumps(event)}")
        
        # Expecting event to have selfie and dl as base64-encoded images
        selfie = event.get('selfie')
        dl = event.get('dl')

        if not selfie or not dl:
            raise KeyError('Missing selfie or dl in the request body')

        # Generate current timestamp
        current_time = datetime.datetime.now(datetime.timezone.utc)
        timestamp = Decimal(str(current_time.timestamp()))
        ttl = Decimal(
            str((current_time + datetime.timedelta(days=TTL_DAYS)).timestamp()))

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
            logger.info(f"The face matched with a {similarity}% confidence rate")
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

        # Return the result in the format required by the Step Function
        return {
            'verificationId': verification_id,
            'result': {
                'similarity': float(result['similarity']),
                'message': result['message'],
                'timestamp': current_time.isoformat()
            }
        }

    except KeyError as e:
        logger.error(f"Missing required field: {str(e)}")
        raise Exception(f"Missing required field: {str(e)}")  # Step Function will handle the error
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in request body: {str(e)}")
        raise Exception("Invalid JSON in request body")  # Step Function will handle the error
    except Exception as e:
        logger.error(f"Error in processing: {str(e)}", exc_info=True)
        raise Exception(f"Error in processing: {str(e)}")  # Step Function will handle the error
