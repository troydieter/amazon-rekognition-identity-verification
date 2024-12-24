import boto3
import json
import base64
import logging
import os

def lambda_handler(event, context):
    # Set up logging
    logger = logging.getLogger()
    logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

    # Log the event structure without the body content
    safe_event = {k: v if k != 'body' else '<<BODY_CONTENT_HIDDEN>>' for k, v in event.items()}
    logger.info(f"Received event structure: {json.dumps(safe_event)}")

    client = boto3.client('rekognition')

    try:
        # Ensure we're working with a dictionary
        if isinstance(event.get('body'), str):
            payload_dict = json.loads(event['body'])
        elif isinstance(event.get('body'), dict):
            payload_dict = event['body']
        else:
            raise ValueError("Event body is neither a string nor a dictionary")

        # Ensure payload_dict is a dictionary
        if not isinstance(payload_dict, dict):
            payload_dict = json.loads(payload_dict)

        # Log the keys in the payload, not the values
        logger.info(f"Payload keys: {list(payload_dict.keys())}")

        selfie = payload_dict['selfie']
        dl = payload_dict['dl']

        # Log only the lengths of selfie and dl
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
        safe_response = {k: v for k, v in response.items() if k not in ['SourceImageFace', 'TargetImageFace']}
        logger.info(f"Rekognition response: {json.dumps(safe_response)}")

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
            'body': json.dumps({
                'similarity': similarity,
                'message': f"The face matched with a {similarity:.2f}% confidence rate"
            })
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
