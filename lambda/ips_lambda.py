import boto3
import logging
import os
import json

# Initialize S3 and Rekognition clients
s3_client = boto3.client('s3')
rekognition_client = boto3.client('rekognition')

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
        selfie_key = record['s3']['object']['key']

        logger.info(f"Selfie uploaded: {selfie_key} in bucket {bucket_name}")

        # Determine driver's license file key (e.g., replace "_selfie.jpg" with "_dl.jpg")
        if not selfie_key.endswith("_selfie.jpg"):
            raise ValueError("Selfie file key does not match expected naming convention")

        dl_key = selfie_key.replace("_selfie.jpg", "_dl.jpg")
        logger.info(f"Expected driver's license key: {dl_key}")

        # Fetch files from S3
        selfie_file = s3_client.get_object(Bucket=bucket_name, Key=selfie_key)['Body'].read()
        dl_file = s3_client.get_object(Bucket=bucket_name, Key=dl_key)['Body'].read()

        logger.info("Fetched driver's license and selfie files from S3")

        # Call Rekognition CompareFaces API
        logger.info("Calling Rekognition CompareFaces API")
        response = rekognition_client.compare_faces(
            SimilarityThreshold=80,
            SourceImage={'Bytes': dl_file},
            TargetImage={'Bytes': selfie_file}
        )

        # Log and process the Rekognition response
        logger.info(f"Rekognition response: {json.dumps(response)}")

        if not response['FaceMatches']:
            logger.info("No face matches found")
            return {
                'statusCode': 200,
                'body': json.dumps({'similarity': 0, 'message': 'No face matches found'})
            }

        similarity = response['FaceMatches'][0]['Similarity']
        logger.info(f"The face matched with a {similarity:.2f}% confidence rate")

        return {
            'statusCode': 200,
            'body': json.dumps({
                'similarity': similarity,
                'message': f"The face matched with a {similarity:.2f}% confidence rate"
            })
        }

    except s3_client.exceptions.NoSuchKey:
        logger.error(f"Driver's license file not found: {dl_key}")
        return {
            'statusCode': 404,
            'body': json.dumps({'error': f"Driver's license file {dl_key} not found"})
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
