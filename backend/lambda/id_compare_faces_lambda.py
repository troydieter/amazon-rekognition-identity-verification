import boto3
import json
import logging
import os
from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import urlparse

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize clients
dynamodb = boto3.resource('dynamodb')
rekognition = boto3.client('rekognition')
s3_client = boto3.client('s3')
table = dynamodb.Table(os.environ['DYNAMODB_TABLE_NAME'])

def get_s3_key_from_uri(s3_uri):
    """
    Extracts the S3 key from a full S3 URI
    """
    parsed = urlparse(s3_uri)
    return parsed.path.lstrip('/')

def update_status(verification_id, status, comparison_results=None):
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
            
            update_expression = "SET #status = :status, LastUpdated = :updated"
            expression_values = {
                ':status': status,
                ':updated': current_time
            }
            
            # Add comparison results if available
            if comparison_results:
                update_expression += ", FaceMatchResults = :results, FaceMatchConfidence = :confidence"
                expression_values[':results'] = comparison_results
                expression_values[':confidence'] = comparison_results.get('Similarity', Decimal('0'))
            
            # Update the status
            table.update_item(
                Key={
                    'VerificationId': verification_id,
                    'Timestamp': timestamp
                },
                UpdateExpression=update_expression,
                ExpressionAttributeNames={
                    '#status': 'Status'  # Status is a reserved word in DynamoDB
                },
                ExpressionAttributeValues=expression_values
            )
            logger.info(f"Updated status to {status} for verification ID: {verification_id}")
        else:
            logger.error(f"No record found for verification ID: {verification_id}")
            raise Exception("Record not found")
            
    except Exception as e:
        logger.error(f"Error updating status: {str(e)}")
        raise

def compare_faces(source_key, target_key, bucket):
    """
    Compare faces using Amazon Rekognition
    """
    try:
        logger.info(f"Comparing faces: source={source_key}, target={target_key}")
        
        response = rekognition.compare_faces(
            SourceImage={
                'S3Object': {
                    'Bucket': bucket,
                    'Name': source_key
                }
            },
            TargetImage={
                'S3Object': {
                    'Bucket': bucket,
                    'Name': target_key
                }
            },
            SimilarityThreshold=80.0,
            QualityFilter='HIGH'
        )
        
        # Log response (excluding any sensitive data)
        logger.info(f"Rekognition response: {json.dumps({
            'FaceMatchesCount': len(response.get('FaceMatches', [])),
            'UnmatchedFacesCount': len(response.get('UnmatchedFaces', []))
        })}")
        
        if response.get('FaceMatches'):
            face_match = response['FaceMatches'][0]  # Get the best match
            bounding_box = face_match['Face']['BoundingBox']
            
            return {
                'Matched': True,
                'Similarity': Decimal(str(face_match['Similarity'])).quantize(Decimal('.01')),
                'BoundingBox': {
                    'Width': Decimal(str(bounding_box['Width'])).quantize(Decimal('.001')),
                    'Height': Decimal(str(bounding_box['Height'])).quantize(Decimal('.001')),
                    'Left': Decimal(str(bounding_box['Left'])).quantize(Decimal('.001')),
                    'Top': Decimal(str(bounding_box['Top'])).quantize(Decimal('.001'))
                },
                'Confidence': Decimal(str(face_match['Face']['Confidence'])).quantize(Decimal('.01'))
            }
        else:
            return {
                'Matched': False,
                'Similarity': Decimal('0'),
                'Message': 'No matching faces found'
            }
            
    except Exception as e:
        logger.error(f"Error comparing faces: {str(e)}")
        raise

def lambda_handler(event, context):
    try:
        logger.info(f"Received event: {json.dumps(event)}")
        
        verification_id = event['verification_id']
        bucket_name = os.environ.get('S3_BUCKET_NAME')
        
        if not bucket_name:
            raise ValueError("S3_BUCKET_NAME environment variable is not set.")
        
        # Extract S3 keys from full URIs
        dl_key = get_s3_key_from_uri(event['dl_key'])
        selfie_key = get_s3_key_from_uri(event['selfie_key'])
        
        # Update initial status
        update_status(verification_id, "COMPARING_FACES")
        
        # Perform face comparison
        comparison_results = compare_faces(dl_key, selfie_key, bucket_name)
        
        # Determine success based on match results and minimum similarity threshold
        min_similarity_threshold = Decimal('80')  # 80% similarity threshold
        current_similarity = comparison_results.get('Similarity', Decimal('0'))
        success = comparison_results.get('Matched', False) and current_similarity >= min_similarity_threshold
        
        final_status = "FACE_MATCH_SUCCESSFUL" if success else "FACE_MATCH_FAILED"
        
        # Update final status with comparison results
        update_status(verification_id, final_status, comparison_results)
        
        # Convert Decimal to string for JSON serialization
        response_results = {
            'Matched': comparison_results['Matched'],
            'Similarity': str(comparison_results['Similarity']),
            'Message': comparison_results.get('Message', 'Face comparison completed')
        }
        
        if 'BoundingBox' in comparison_results:
            response_results['BoundingBox'] = {
                k: str(v) for k, v in comparison_results['BoundingBox'].items()
            }
            response_results['Confidence'] = str(comparison_results['Confidence'])
        
        return {
            'statusCode': 200,
            'verification_id': verification_id,
            'success': success,
            'details': {
                'verification_id': verification_id,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'status': final_status,
                'comparison_results': response_results
            }
        }
        
    except Exception as e:
        logger.error(f"Error in lambda_handler: {str(e)}")
        
        try:
            # Update status to failed if we have the verification_id
            if 'verification_id' in locals():
                update_status(verification_id, "FACE_COMPARISON_FAILED")
        except Exception as update_error:
            logger.error(f"Error updating failure status: {str(update_error)}")
        
        return {
            'statusCode': 500,
            'verification_id': verification_id if 'verification_id' in locals() else 'UNKNOWN',
            'success': False,
            'error': str(e)
        }

