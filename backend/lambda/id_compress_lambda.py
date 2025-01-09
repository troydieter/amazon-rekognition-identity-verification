import json
from PIL import Image
import boto3
import os
from io import BytesIO
import urllib.parse

s3_client = boto3.client('s3')

def lambda_handler(event, context):
    target_bucket_name = os.environ.get('S3_BUCKET_NAME')
    if not target_bucket_name:
        raise ValueError("Target bucket name is not set in environment variables.")
    
    try:
        record = event['Records'][0]['s3']
        bucket_name = record['bucket']['name']
        object_key = urllib.parse.unquote_plus(record['object']['key'])
        
        print(f"Processing object: {object_key} from bucket: {bucket_name}")
        
        if object_key.startswith("resized_"):
            print(f"Object {object_key} is already resized. Skipping processing.")
            return create_response(200, 'Object already resized')

        image_data = fetch_image(bucket_name, object_key)
        resized_image = resize_image(image_data)
        new_object_key = f"resized_{object_key}"
        upload_image(resized_image, target_bucket_name, new_object_key)

        return create_response(200, 'Compression Complete!')

    except s3_client.exceptions.NoSuchKey:
        print(f"Error: The object key '{object_key}' does not exist in the bucket '{bucket_name}'")
        return create_response(404, 'Object not found')
    except Exception as e:
        print(f"Error processing object {object_key} from bucket {bucket_name}: {str(e)}")
        return create_response(500, 'Internal server error')

def fetch_image(bucket, key):
    print(f"Fetching object: {key} from bucket: {bucket}")
    response = s3_client.get_object(Bucket=bucket, Key=key)
    return response['Body'].read()

def resize_image(image_data):
    image = Image.open(BytesIO(image_data))
    width, height = image.size
    resized = image.resize((width // 2, height // 2))
    print(f"Resized image from {width}x{height} to {width // 2}x{height // 2}")
    return resized

def upload_image(image, bucket, key):
    buffer = BytesIO()
    image.save(buffer, format='JPEG', optimize=True, quality=70)
    buffer.seek(0)
    print(f"Uploading resized image to {bucket}/{key}")
    response = s3_client.put_object(Bucket=bucket, Key=key, Body=buffer)
    print(f"PutObject response: {response}")

def create_response(status_code, message):
    return {
        'statusCode': status_code,
        'body': json.dumps(message)
    }
