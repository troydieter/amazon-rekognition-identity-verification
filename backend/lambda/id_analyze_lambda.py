import boto3
import json
import os
import logging
from decimal import Decimal
from datetime import datetime, timezone
from urllib.parse import urlparse

# Initialize clients
textract_client = boto3.client('textract')
dynamodb = boto3.resource('dynamodb')

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def get_s3_key_from_uri(s3_uri):
    """
    Extracts the S3 key from a full S3 URI
    Example: "s3://bucket-name/path/to/file.jpg" -> "path/to/file.jpg"
    """
    parsed = urlparse(s3_uri)
    return parsed.path.lstrip('/')

def extract_field_value(fields, field_type):
    """
    Helper function to extract field values from Textract response
    Returns both the value and confidence score
    """
    for field in fields:
        if field['Type']['Text'] == field_type:
            return {
                'Text': field['ValueDetection'].get('Text', ''),
                'Confidence': Decimal(str(field['ValueDetection'].get('Confidence', 0))).quantize(Decimal('.01'))
            }
    return {'Text': '', 'Confidence': Decimal('0')}

def analyze_id_document(photo, bucket):
    """
    Uses Amazon Textract to analyze ID document and extract relevant fields
    """
    try:
        logger.info(f"Analyzing ID document: bucket={bucket}, key={photo}")
        response = textract_client.analyze_id(
            DocumentPages=[{
                "S3Object": {
                    "Bucket": bucket,
                    "Name": photo
                }
            }]
        )
        
        if not response.get('IdentityDocuments'):
            logger.warning(f"No identity document found in {photo}")
            return None
            
        id_fields = response['IdentityDocuments'][0]['IdentityDocumentFields']
        
        # Extract relevant fields with confidence scores
        fields_to_extract = [
            'FIRST_NAME', 'LAST_NAME', 'MIDDLE_NAME',
            'DATE_OF_BIRTH', 'EXPIRATION_DATE', 'DOCUMENT_NUMBER',
            'ADDRESS', 'CITY_IN_ADDRESS', 'STATE_IN_ADDRESS',
            'ZIP_CODE_IN_ADDRESS', 'ID_TYPE', 'STATE_NAME'
        ]
        
        extracted_fields = {}
        for field in fields_to_extract:
            result = extract_field_value(id_fields, field)
            extracted_fields[field.lower()] = {
                'text': result['Text'],
                'confidence': result['Confidence']
            }
            logger.info(f"{field}: {result['Text']} (Confidence: {result['Confidence']})")
            
        return {
            'fields': extracted_fields,
            'document_present': True,
            'raw_response': response
        }
        
    except Exception as e:
        logger.error(f"Error analyzing ID document {photo} in bucket {bucket}: {str(e)}")
        raise

def update_dynamodb_record(verification_id, analysis_results):
    """
    Updates the DynamoDB record with ID analysis results
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
            
        timestamp = response['Items'][0]['Timestamp']
        current_time = Decimal(str(datetime.now(timezone.utc).timestamp()))
        
        # Prepare update expression and values
        update_expression = """
            SET IDAnalysisResults = :results,
                IDAnalysisStatus = :status,
                LastUpdated = :updated,
                AnalyzedAt = :analyzed_at,
                DocumentType = :doc_type,
                DocumentNumber = :doc_number
        """
        
        expression_values = {
            ':results': analysis_results['fields'],
            ':status': 'COMPLETED',
            ':updated': current_time,
            ':analyzed_at': current_time,
            ':doc_type': analysis_results['fields'].get('id_type', {}).get('text', 'UNKNOWN'),
            ':doc_number': analysis_results['fields'].get('document_number', {}).get('text', 'UNKNOWN')
        }
        
        # Update DynamoDB
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
    AWS Lambda handler for processing ID analysis as part of Step Functions workflow
    """
    try:
        logger.info(f"Received event: {json.dumps(event)}")
        
        verification_id = event['verification_id']
        bucket_name = os.environ.get('S3_BUCKET_NAME')
        
        if not bucket_name:
            raise ValueError("S3_BUCKET_NAME environment variable is not set.")
        
        # Extract S3 key from full URI
        id_key = get_s3_key_from_uri(event['id_key'])
        
        logger.info(f"Processing ID document: {id_key}")
        
        # Analyze ID document
        analysis_results = analyze_id_document(id_key, bucket_name)
        
        if not analysis_results:
            return {
                'statusCode': 400,
                'verification_id': verification_id,
                'success': False,
                'error': "No valid ID document found in image"
            }
        
        # Update DynamoDB with results
        update_dynamodb_record(verification_id, analysis_results)
        
        # Check if all required fields are present with acceptable confidence
        required_fields = ['first_name', 'last_name', 'date_of_birth', 'expiration_date']
        confidence_threshold = Decimal('90.0')
        
        validation_results = {
            field: {
                'present': bool(analysis_results['fields'][field]['text']),
                'confidence': analysis_results['fields'][field]['confidence']
            }
            for field in required_fields
        }
        
        valid_id = all(
            validation_results[field]['present'] and 
            validation_results[field]['confidence'] >= confidence_threshold
            for field in required_fields
        )
        
        response = {
            'statusCode': 200,
            'verification_id': verification_id,
            'success': valid_id,
            'analysis_results': {
                'fields': {
                    k: v for k, v in analysis_results['fields'].items()
                    if k in ['first_name', 'last_name', 'date_of_birth', 'expiration_date', 
                            'document_number', 'id_type']
                },
                'validation': validation_results
            }
        }
        
        if not valid_id:
            response['error'] = "One or more required fields failed validation"
            
        return response
        
    except Exception as e:
        logger.error(f"Error processing ID analysis: {str(e)}")
        return {
            'statusCode': 500,
            'verification_id': verification_id if 'verification_id' in locals() else 'UNKNOWN',
            'success': False,
            'error': str(e)
        }
