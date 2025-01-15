import boto3
import json
import logging
import os
from datetime import datetime

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize clients
ses_client = boto3.client('ses')
dynamodb = boto3.resource('dynamodb')

def get_email_content(verification_id, success, details):
    """
    Generate email content based on verification results
    """
    timestamp = details.get('timestamp', datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    
    if success:
        comparison_results = details.get('comparison_results', {})
        subject = "ID Verification Successful"
        body = f"""
        Your ID verification has been completed successfully.
        
        Verification Details:
        - Verification ID: {verification_id}
        - Status: {details.get('status', 'Completed')}
        - Timestamp: {timestamp}
        - Similarity Score: {comparison_results.get('Similarity', 'N/A')}
        
        Image Processing Results:
        - Face Match Confidence: {comparison_results.get('Confidence', 'N/A')}
        - Moderation Check: Passed
        - Images Resized: Completed
        
        Thank you for using our service.
        """
    else:
        subject = "ID Verification Failed"
        body = f"""
        Your ID verification could not be completed.
        
        Verification Details:
        - Verification ID: {verification_id}
        - Status: {details.get('status', 'Failed')}
        - Timestamp: {timestamp}
        - Reason: {details.get('error', 'Verification requirements not met')}
        
        Please try again or contact support if you need assistance.
        """
    
    return subject, body

def lambda_handler(event, context):
    try:
        logger.info(f"Received event: {json.dumps(event)}")
        
        verification_id = event['verification_id']
        success = event['success']
        user_email = event['user_email']
        details = event.get('details', {})
        
        # Validate email address
        if not user_email:
            raise ValueError("No email address provided")
            
        # Get email content
        subject, body_text = get_email_content(verification_id, success, details)
        
        # Send email
        response = ses_client.send_email(
            Source=os.environ['FROM_EMAIL_ADDRESS'],
            Destination={
                'ToAddresses': [user_email]
            },
            Message={
                'Subject': {
                    'Data': subject
                },
                'Body': {
                    'Text': {
                        'Data': body_text
                    }
                }
            }
        )
        
        logger.info(f"Email sent successfully to {user_email}. MessageId: {response['MessageId']}")
        
        return {
            'statusCode': 200,
            'verification_id': verification_id,
            'success': True,
            'message_id': response['MessageId'],
            'email_sent_to': user_email
        }
        
    except Exception as e:
        logger.error(f"Error sending email: {str(e)}")
        return {
            'statusCode': 500,
            'verification_id': verification_id if 'verification_id' in locals() else 'UNKNOWN',
            'success': False,
            'error': str(e)
        }
