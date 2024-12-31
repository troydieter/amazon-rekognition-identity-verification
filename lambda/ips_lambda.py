import boto3
import logging
import os
import json
import uuid
import datetime
import base64
from decimal import Decimal

# Initialize S3, Rekognition, and DynamoDB clients
s3_client = boto3.client('s3')
rekognition_client = boto3.client('rekognition')
dynamodb = boto3.resource('dynamodb')

# Get the DynamoDB table name from environment variable
TABLE_NAME = os.environ.get('DYNAMODB_TABLE_NAME')

TTL_DAYS = int(os.environ.get('TTL_DAYS', 365))  # Default to 365 if not set

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    try:
        logger.info(f"Received event: {json.dumps(event)}")
        
        # Log specific parts of the event to help identify its structure
        logger.info(f"Event type: {type(event)}")
        logger.info(f"Event keys: {list(event.keys())}")
        
        if 'body' in event and isinstance(event['body'], dict):
            logger.info("Identified as API Gateway event with pre-parsed body")
            return handle_api_request(event['body'])
        elif 'body' in event and isinstance(event['body'], str):
            logger.info("Identified as API Gateway event with string body")
            body = json.loads(event['body'])
            return handle_api_request(body)
        elif 'Records' in event and event['Records'][0].get('eventSource') == 'aws:s3':
            logger.info("Identified as S3 event")
            return handle_s3_event(event)
        else:
            logger.error("Unrecognized event type")
            return {
                'statusCode': 400,
                'body': json.dumps({'error': "Unrecognized event type"})
            }

    except Exception as e:
        logger.error(f"Unexpected error in lambda_handler: {str(e)}", exc_info=True)
        return {
            'statusCode': 500,
            'body': json.dumps({'error': "Internal server error"})
        }

def handle_api_request(body):
    try:
        logger.info("Handling API Gateway request")
        
        logger.info(f"Parsed body: {json.dumps(body)}")
        
        selfie = body['selfie']
        dl = body['dl']

        # Convert base64 to bytes
        dl_bytes = base64.b64decode(dl)
        selfie_bytes = base64.b64decode(selfie)

        # Call Rekognition CompareFaces API
        logger.info("Calling Rekognition CompareFaces API")
        response = rekognition_client.compare_faces(
            SimilarityThreshold=80,
            SourceImage={'Bytes': dl_bytes},
            TargetImage={'Bytes': selfie_bytes}
        )

        # Generate UUID for DynamoDB partition key
        verification_id = str(uuid.uuid4())

        # Generate current timestamp
        current_time = datetime.datetime.now(datetime.timezone.utc)
        timestamp = Decimal(str(current_time.timestamp()))
        ttl = Decimal(str((current_time + datetime.timedelta(days=TTL_DAYS)).timestamp()))

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

    except KeyError as e:
        logger.error(f"Missing required field: {str(e)}")
        return {
            'statusCode': 400,
            'body': json.dumps({'error': f"Missing required field: {str(e)}"})
        }
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in request body: {str(e)}")
        return {
            'statusCode': 400,
            'body': json.dumps({'error': "Invalid JSON in request body"})
        }
    except Exception as e:
        logger.error(f"Error in API request: {str(e)}", exc_info=True)
        return {
            'statusCode': 500,
            'body': json.dumps({'error': "Internal server error"})
        }


def handle_s3_event(event):
    try:
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
                'DriversLicense-S3Object_Key': dl_key,
                'Selfie-S3Object_Key': selfie_key,
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
