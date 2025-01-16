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
    error_details = details.get('error_details', {})
    error_messages = details.get('error_messages', {})
    validation_details = details.get('validation_details', {})
    
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
        .button { display: inline-block; padding: 10px 20px; background-color: #FF9900; color: black !important; text-decoration: none; border-radius: 5px; margin-top: 15px; }
        .details { margin: 15px 0; }
        .detail-row { display: flex; justify-content: space-between; margin: 5px 0; }
        .label { color: #4a5568; }
        .value { font-weight: bold; }
        .validation-section { margin-top: 15px; padding: 10px; background-color: #f8f9fa; }
        a, a:link, a:visited, a:hover, a:active { color: #333333 !important; text-decoration: none; }
        span, span.im { color: #333333 !important; }
        * { color: inherit; }
    """

    if success:
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
                                <span class="label">Verification ID: </span>
                                <span class="value">{verification_id}</span>
                            </div>
                            <div class="detail-row">
                                <span class="label">Timestamp: </span>
                                <span class="value">{timestamp}</span>
                            </div>
                        </div>
                    </div>

                    <p>All verification checks have passed:</p>
                    <ul>
                        <li>✓ ID Document Validation</li>
                        <li>✓ Image Moderation</li>
                        <li>✓ Face Analysis</li>
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
        # Construct failure details
        moderation_status = error_details.get('moderation', {}).get('Status', 'N/A')
        id_analysis_status = error_details.get('id_analysis', {}).get('Status', 'N/A')
        
        # Get validation details for ID analysis
        id_validation = validation_details.get('id_analysis', {})
        validation_issues = []
        
        if id_validation:
            for field, data in id_validation.items():
                if not data.get('present') or data.get('confidence', 0) < 90:
                    validation_issues.append(f"{field.replace('_', ' ').title()}: Invalid or low confidence")

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
                                <span class="label">Verification ID: </span>
                                <span class="value">{verification_id}</span>
                            </div>
                            <div class="detail-row">
                                <span class="label">Timestamp: </span>
                                <span class="value">{timestamp}</span>
                            </div>
                        </div>
                    </div>

                    <div class="validation-section">
                        <h3>Verification Results:</h3>
                        <ul>
                            <li>Moderation Check: {moderation_status}</li>
                            <li>ID Analysis: {id_analysis_status}</li>
                        </ul>
                    """

        if validation_issues:
            html_content += """
                        <h3>Validation Issues:</h3>
                        <ul>
                            """ + "".join([f"<li>{issue}</li>" for issue in validation_issues]) + """
                        </ul>
            """

        html_content += f"""
                    </div>

                    <p>Please ensure:</p>
                    <ul>
                        <li>Your ID document is clearly visible</li>
                        <li>All text on the ID is readable</li>
                        <li>There is good lighting</li>
                        <li>The image is not blurry</li>
                    </ul>
                </div>
                <div class="footer">
                    <p>Need help? Contact our support team.</p>
                </div>
            </div>
        </body>
        </html>
        """

    # Plain text version
    plain_text = f"""
    ID Verification {'Successful' if success else 'Failed'}
    
    Verification ID: {verification_id}
    Timestamp: {timestamp}
    Status: {'Passed' if success else 'Failed'}
    
    {'All verification checks have passed.' if success else 'Verification failed. Please review the issues and try again.'}
    """

    return ("ID Verification " + ("Successful" if success else "Failed"), plain_text, html_content)

def lambda_handler(event, context):
    try:
        logger.info(f"Received event: {json.dumps(event)}")
        
        verification_id = event['verification_id']
        success = event['success']
        user_email = event['user_email']
        details = event.get('details', {})
        
        if not user_email:
            raise ValueError("No email address provided")
            
        subject, plain_text, html_content = get_email_content(verification_id, success, details)
        
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
