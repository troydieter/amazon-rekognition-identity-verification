import boto3
import logging
import os
import json
import uuid
import datetime
from decimal import Decimal

# Initialize S3, Rekognition, and DynamoDB clients
s3_client = boto3.client('s3')
rekognition_client = boto3.client('rekognition')
dynamodb = boto3.resource('dynamodb')

# Get the DynamoDB table name from environment variable
TABLE_NAME = os.environ.get('DYNAMODB_TABLE_NAME')

TTL_DAYS = int(os.environ.get('TTL_DAYS', 365))  # Default to 365 if not set

def lambda_handler(event, context):
    # Set up logging
    logger = logging.getLogger()
    logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

    try:
        # Log the event structure
        logger.info(f"Received event: {json.dumps(event)}")

        # Parse the S3 event
        record = event['Records'][0]
        bucket_name = record['s3']['bucket']['name']
        file_key = record['s3']['object']['key']

        logger.info(f"File uploaded: {file_key} in bucket {bucket_name}")

        # Extract session ID and file type from the file name
        file_name_parts = os.path.splitext(file_key)[0].split('_')
        if len(file_name_parts) != 2:
            raise ValueError(f"Invalid file name format: {file_key}")

        session_id, file_type = file_name_parts

        if file_type not in ['dl', 'selfie']:
            raise ValueError(f"Invalid file type: {file_type}")

        # Determine the expected keys for both files
        dl_key = f"{session_id}_dl.jpg"
        selfie_key = f"{session_id}_selfie.jpg"

        # Check if both files are present
        dl_exists = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=dl_key)['KeyCount'] > 0
        selfie_exists = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=selfie_key)['KeyCount'] > 0

        if dl_exists and selfie_exists:
            # Generate current timestamp
            current_time = datetime.datetime.now(datetime.timezone.utc)
            timestamp = Decimal(str(current_time.timestamp()))
            ttl = Decimal(str((current_time + datetime.timedelta(days=TTL_DAYS)).timestamp()))
            
            # Fetch files from S3
            dl_file = s3_client.get_object(Bucket=bucket_name, Key=dl_key)['Body'].read()
            selfie_file = s3_client.get_object(Bucket=bucket_name, Key=selfie_key)['Body'].read()

            logger.info("Fetched both driver's license and selfie files from S3")

            # Call Rekognition CompareFaces API
            logger.info("Calling Rekognition CompareFaces API")
            response = rekognition_client.compare_faces(
                SimilarityThreshold=80,
                SourceImage={'Bytes': dl_file},
                TargetImage={'Bytes': selfie_file}
            )

            # Log and process the Rekognition response
            logger.info(f"Rekognition response: {json.dumps(response)}")

            # Generate UUID for DynamoDB partition key
            verification_id = str(uuid.uuid4())

            if not response['FaceMatches']:
                logger.info("No face matches found")
                result = {
                    'similarity': Decimal('0'),
                    'message': 'No face matches found'
                }
            else:
                similarity = Decimal(str(response['FaceMatches'][0]['Similarity']))
                logger.info(f"The face matched with a {similarity:.2f}% confidence rate")
                result = {
                    'similarity': similarity,
                    'message': f"The face matched with a {similarity:.2f}% confidence rate"
                }

            # Write result to DynamoDB
            table = dynamodb.Table(TABLE_NAME)
            item = {
                'VerificationId': verification_id,
                'SessionId': session_id,
                'DriversLicenseKey': dl_key,
                'SelfieKey': selfie_key,
                'Similarity': result['similarity'],
                'Message': result['message'],
                'Timestamp': timestamp,
                'TTL': ttl
            }
            table.put_item(Item=item)
            logger.info(f"Result written to DynamoDB with VerificationId: {verification_id}")

            return {
                'statusCode': 200,
                'body': json.dumps({
                    'verificationId': verification_id,
                    'result': {
                        'similarity': float(result['similarity']),
                        'message': result['message'],
                        'timestamp': current_time.isoformat()
                    }
                }, default=str)
            }
        else:
            # If both files are not yet present, log and exit
            logger.info(f"Waiting for the other image to complete verification. Current file: {file_key}")
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': f"File {file_key} processed. Waiting for the other image to complete verification."
                })
            }

    except s3_client.exceptions.NoSuchKey:
        logger.error(f"File not found in S3: {file_key}")
        return {
            'statusCode': 404,
            'body': json.dumps({'error': f"File not found in S3: {file_key}"})
        }
    except ValueError as e:
        logger.error(f"ValueError: {str(e)}")
        return {
            'statusCode': 400,
            'body': json.dumps({'error': str(e)})
        }
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        return {
            'statusCode': 500,
            'body': json.dumps({'error': "Internal server error"})
        }
