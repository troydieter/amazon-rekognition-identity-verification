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
    comparison_results = details.get('comparison_results', {})
    
    # Common CSS styles
    styles = """
        body { font-family: Arial, sans-serif; line-height: 1.6; color: #333333; }
        .container { max-width: 600px; margin: 0 auto; padding: 20px; }
        .header { background-color: #FF9900; color: black; padding: 20px; text-align: center; border-radius: 5px 5px 0 0; }
        .content { background-color: #ffffff; padding: 20px; border: 1px solid #e2e8f0; border-radius: 0 0 5px 5px; }
        .footer { text-align: center; margin-top: 20px; font-size: 12px; color: #718096; }
        .result-box { background-color: #f7fafc; border: 1px solid #e2e8f0; border-radius: 5px; padding: 15px; margin: 15px 0; }
        .success { color: #48bb78; }
        .failure { color: #f56565; }
        .button { display: inline-block; padding: 10px 20px; background-color: #FF9900; color: white; text-decoration: none; border-radius: 5px; margin-top: 15px; }
        .details { margin: 15px 0; }
        .detail-row { display: flex; justify-content: space-between; margin: 5px 0; }
        .label { color: #4a5568; }
        .value { font-weight: bold; }
    """
    if not success:
        # Get failure reason from various possible sources
        failure_reason = (
            details.get('error') or 
            comparison_results.get('Message') or 
            'Verification requirements not met'
        )

    if success:
        similarity = comparison_results.get('Similarity', 'N/A')
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>{styles}</style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>ID Verification Successful</h1>
                </div>
                <div class="content">
                    <p>Your ID verification has been completed successfully.</p>
                    
                    <div class="result-box">
                        <h2 class="success">✓ Verification Passed</h2>
                        <div class="details">
                            <div class="detail-row">
                                <span class="label">Verification ID:</span>
                                <span class="value">{verification_id}</span>
                            </div>
                            <div class="detail-row">
                                <span class="label">Timestamp:</span>
                                <span class="value">{timestamp}</span>
                            </div>
                            <div class="detail-row">
                                <span class="label">Face Match:</span>
                                <span class="value">{similarity}% match</span>
                            </div>
                        </div>
                    </div>

                    <p>All verification checks have passed:</p>
                    <ul>
                        <li>✓ Face Comparison</li>
                        <li>✓ Image Moderation</li>
                        <li>✓ Image Processing</li>
                    </ul>
                </div>
                <div class="footer">
                    <p>This is an automated message. Please do not reply to this email.</p>
                </div>
            </div>
        </body>
        </html>
        """
    else:
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>{styles}</style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>ID Verification Failed</h1>
                </div>
                <div class="content">
                    <p>Unfortunately, your ID verification could not be completed.</p>
                    
                    <div class="result-box">
                        <h2 class="failure">⚠ Verification Failed</h2>
                        <div class="details">
                            <div class="detail-row">
                                <span class="label">Verification ID:</span>
                                <span class="value">{verification_id}</span>
                            </div>
                            <div class="detail-row">
                                <span class="label">Timestamp:</span>
                                <span class="value">{timestamp}</span>
                            </div>
                            <div class="detail-row">
                                <span class="label">Reason:</span>
                                <span class="value">{details.get('error', 'Verification requirements not met')}</span>
                            </div>
                        </div>
                    </div>

                    <p>Common reasons for failure:</p>
                    <ul>
                        <li>Image quality issues</li>
                        <li>Face not clearly visible</li>
                        <li>ID document not clearly visible</li>
                    </ul>

                    <p>Please try again with new images, ensuring:</p>
                    <ul>
                        <li>Good lighting conditions</li>
                        <li>Clear, unobstructed view of face/ID</li>
                        <li>High-quality images</li>
                    </ul>
                </div>
                <div class="footer">
                    <p>Need help? Contact our support team.</p>
                </div>
            </div>
        </body>
        </html>
        """

    # Plain text version for email clients that don't support HTML
    plain_text = f"""
    ID Verification {'Successful' if success else 'Failed'}
    
    Verification ID: {verification_id}
    Timestamp: {timestamp}
    Status: {'Passed' if success else 'Failed'}
    
    {'All verification checks have passed.' if success else 'Please try again with new images.'}
    
    """

    return ("ID Verification " + ("Successful" if success else "Failed"), plain_text, html_content)

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
        subject, plain_text, html_content = get_email_content(verification_id, success, details)
        
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
                        'Data': plain_text
                    },
                    'Html': {
                        'Data': html_content
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
