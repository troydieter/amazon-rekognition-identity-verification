import boto3
import json
import base64
import logging
import os

def lambda_handler(event, context):
    # Set up logging
    logger = logging.getLogger()
    logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

    # Log the entire incoming event
    logger.info(f"Received event: {json.dumps(event)}")

    client = boto3.client('rekognition')

    try:
        # Check if event['body'] is a string or dictionary
        if isinstance(event['body'], str):
            payload_dict = json.loads(event['body'])
        else:
            payload_dict = event['body']

        # Log the parsed payload
        logger.info(f"Parsed payload: {json.dumps(payload_dict)}")

        selfie = payload_dict['selfie']
        dl = payload_dict['dl']

        # Log the lengths of selfie and dl (to avoid logging entire images)
        logger.info(f"Selfie data length: {len(selfie)}")
        logger.info(f"DL data length: {len(dl)}")

        # Convert base64 to bytes
        s_bytes = base64.b64decode(dl)
        t_bytes = base64.b64decode(selfie)

        logger.info("Calling Rekognition CompareFaces API")
        response = client.compare_faces(
            SimilarityThreshold=80,
            SourceImage={'Bytes': s_bytes},
            TargetImage={'Bytes': t_bytes}
        )

        # Log the Rekognition response (excluding the image data)
        logger.info(f"Rekognition response: {json.dumps({k: v for k, v in response.items() if k != 'SourceImageFace' and k != 'TargetImageFace'})}")

        if not response['FaceMatches']:
            logger.info("No face matches found")
            return {
                'statusCode': 200,
                'body': json.dumps({'similarity': 0, 'message': 'No face matches found'})
            }

        similarity = response['FaceMatches'][0]['Similarity']
        logger.info(f"Face match found with similarity: {similarity}")

        return {
            'statusCode': 200,
            'body': json.dumps({'similarity': similarity})
        }

    except KeyError as e:
        logger.error(f"KeyError: {str(e)}. This might indicate missing data in the payload.")
        return {
            'statusCode': 400,
            'body': json.dumps({'error': f"Missing key in payload: {str(e)}"})
        }
    except json.JSONDecodeError as e:
        logger.error(f"JSONDecodeError: {str(e)}. This might indicate malformed JSON in the event body.")
        return {
            'statusCode': 400,
            'body': json.dumps({'error': "Invalid JSON in request body"})
        }
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        return {
            'statusCode': 500,
            'body': json.dumps({'error': "Internal server error"})
        }
