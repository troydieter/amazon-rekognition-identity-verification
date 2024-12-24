import boto3
import json
import base64
import logging
import os

def lambda_handler(event, context):
    logger = logging.getLogger()
    logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))
    client = boto3.client('rekognition')

    try:
        payload_dict = json.loads(event['body'])
        selfie = payload_dict['selfie']
        dl = payload_dict['dl']

        # Convert base64 to bytes
        s_bytes = base64.b64decode(dl)
        t_bytes = base64.b64decode(selfie)

        response = client.compare_faces(
            SimilarityThreshold=80,
            SourceImage={'Bytes': s_bytes},
            TargetImage={'Bytes': t_bytes}
        )

        if not response['FaceMatches']:
            return {
                'statusCode': 200,
                'body': json.dumps({'similarity': 0, 'message': 'No face matches found'})
            }

        similarity = response['FaceMatches'][0]['Similarity']

        return {
            'statusCode': 200,
            'body': json.dumps({'similarity': similarity})
        }

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }