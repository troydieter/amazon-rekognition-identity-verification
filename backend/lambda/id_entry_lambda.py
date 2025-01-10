import boto3
import logging
import os
import json
import uuid

# Initialize Step Functions client
stepfunctions_client = boto3.client('stepfunctions')

# Get environment variables
STATE_MACHINE_ARN = os.environ.get('STATE_MACHINE_ARN')

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    try:
        # Log safe event details
        safe_event = {k: v for k, v in event.items() if k != 'body'}
        logger.info(f"Received event: {json.dumps(safe_event)}")

        # Check if it's an API Gateway event
        if 'requestContext' in event and 'http' in event['requestContext']:
            http_method = event['requestContext']['http']['method']

            # Handle CORS preflight request
            if http_method == 'OPTIONS':
                return {
                    'statusCode': 200,
                    'headers': {
                        'Access-Control-Allow-Origin': '*',
                        'Access-Control-Allow-Headers': 'Content-Type,X-Api-Key',
                        'Access-Control-Allow-Methods': 'POST,OPTIONS'
                    },
                    'body': ''
                }

            # Handle POST request
            if http_method == 'POST':
                if 'body' in event:
                    body = json.loads(event['body']) if isinstance(
                        event['body'], str) else event['body']
                    return start_step_function(body)
                else:
                    logger.error("Missing body in POST request")
                    return cors_response(400, {'error': "Missing body in POST request"})

            logger.error(f"Unsupported HTTP method: {http_method}")
            return cors_response(405, {'error': "Method not allowed"})

        # Unrecognized event structure
        logger.error("Unrecognized event structure")
        return cors_response(400, {'error': "Unrecognized event structure"})

    except Exception as e:
        logger.error(f"Unexpected error in lambda_handler: {str(e)}", exc_info=True)
        return cors_response(500, {'error': "Internal server error"})


def start_step_function(body):
    try:
        logger.info("Starting Step Function execution")

        # Log the keys in the body, not the values
        logger.info(f"Received body keys: {list(body.keys())}")

        # Generate a unique execution name
        execution_name = f"execution-{uuid.uuid4()}"

        # Start the Step Function execution
        response = stepfunctions_client.start_execution(
            stateMachineArn=STATE_MACHINE_ARN,
            name=execution_name,
            input=json.dumps(body)
        )

        logger.info(f"Step Function execution started: {response['executionArn']}")

        return cors_response(200, {
            'message': "Step Function execution started",
            'executionArn': response['executionArn']
        })

    except Exception as e:
        logger.error(f"Error starting Step Function: {str(e)}", exc_info=True)
        return cors_response(500, {'error': "Failed to start Step Function"})


def cors_response(status_code, body):
    return {
        'statusCode': status_code,
        'headers': {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,X-Api-Key,Authorization',
            'Access-Control-Allow-Methods': 'POST,OPTIONS',
            'Access-Control-Allow-Credentials': 'true'
        },
        'body': json.dumps(body)
    }
