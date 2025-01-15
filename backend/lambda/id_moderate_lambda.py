import boto3
import json
import os

rekognition_client = boto3.client('rekognition')

def moderate_image(photo, bucket):
    """
    Uses Amazon Rekognition to detect moderation labels in the given image.
    Returns a dictionary with label names and their confidence scores.
    """
    try:
        response = rekognition_client.detect_moderation_labels(
            Image={'S3Object': {'Bucket': bucket, 'Name': photo}}
        )
        
        print(f'Detected moderation labels for {photo}')
        labels = []
        for label in response.get('ModerationLabels', []):
            print(f"{label['Name']} : {label['Confidence']:.2f}")
            print(f"Parent: {label.get('ParentName', 'None')}")
            labels.append({
                'Name': label['Name'],
                'Confidence': label['Confidence'],
                'ParentName': label.get('ParentName', None)
            })
        return labels
    except Exception as e:
        print(f"Error detecting moderation labels for {photo} in bucket {bucket}: {str(e)}")
        raise

def lambda_handler(event, context):
    """
    AWS Lambda handler for processing moderation labels from an S3 event notification.
    """
    try:
        # Get the bucket name from the environment variable
        bucket_name = os.environ.get('S3_BUCKET_NAME')
        if not bucket_name:
            raise ValueError("S3_BUCKET_NAME environment variable is not set.")

        # Extract the object key from the event
        record = event['Records'][0]['s3']
        object_key = record['object']['key']
        
        print(f"Processing moderation labels for object: {object_key} in bucket: {bucket_name}")
        
        # Detect moderation labels
        moderation_labels = moderate_image(object_key, bucket_name)
        
        if moderation_labels:
            message = {
                'Status': 'Moderation Labels Detected',
                'Labels': moderation_labels
            }
            print(json.dumps(message, indent=2))
        else:
            message = {'Status': 'No Moderation Labels Detected'}
            print(message)

        return {
            'statusCode': 200,
            'body': json.dumps(message)
        }
    except Exception as e:
        print(f"Error processing moderation labels: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }
