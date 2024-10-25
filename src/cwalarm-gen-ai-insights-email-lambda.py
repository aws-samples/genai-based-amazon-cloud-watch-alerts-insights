import json
import boto3
import os
import logging

from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
logger = logging.getLogger()
logger.setLevel(logging.INFO)

logger = logging.getLogger()

ses_client = boto3.client('ses')
bedrock_runtime = boto3.client("bedrock-runtime")

def lambda_handler(event, context):
    
    logger.info(f'event received: {event}')

    # Parse cloudwatch alarm JSON message
    message = json.loads(event['Records'][0]['Sns']['Message'])
    alarm_name = message['AlarmName']
    
    region = message['Region']
    
    cw_client = boto3.client("cloudwatch")

    history = cw_client.describe_alarm_history(
    AlarmName=alarm_name,
       
    MaxRecords=5,
    
    ScanBy='TimestampDescending'
)
    
    # Set the model ID, e.g., Claude 3 Haiku.
    model_id = os.environ['MODEL_ID']
    email_template = os.environ['SES_TEMPLATE']
    # Define the prompt for the model.
    prompt = os.environ['PROMPT']

    # Format the request payload using the model's native structure.
    native_request = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 4096,
        "temperature": 0.1,
        "messages": [
            {
                "role": "user",
                "content": [{"type": "text", "text": prompt},
                            {"type": "text", "text": f'<CurrentAlertMessage>{message}</CurrentAlertMessage>'},
                            {"type": "text", "text": f'<AlertHistory>{history} </AlertHistory>'},
                            {"type": "text", "text": f'<EmailTemplate>{email_template}</EmailTemplate>'}],
            }
        ],
    }

    # Convert the native request to JSON.
    request = json.dumps(native_request)

    try:
        # Invoke the model with the request.
        response = bedrock_runtime.invoke_model(modelId=model_id, body=request)

    except (ClientError, Exception) as e:
        print(f"ERROR: Can't invoke '{model_id}'. Reason: {e}")
        exit(1)

    # Decode the response body.
    model_response = json.loads(response["body"].read())

    # Extract and print the response text.
    response_text = model_response["content"][0]["text"]
    print(response_text)

    # Get SES configuration from lambda env variables
    
    source_email = os.environ['EMAIL_SOURCE']
    destination_to_email = os.environ['EMAIL_TO_ADDRESSES']
    

    # Read email addresses and send SES templated email
    msg = MIMEMultipart('mixed')
    # The subject line for the email.
    SUBJECT = f'ALARM:{alarm_name}'

    # The email body for recipients with non-HTML email clients.
    BODY_TEXT = json.dumps(message)

    # The HTML body of the email.
    BODY_HTML = response_text
    #(html_data)
    # The character encoding for the email.
    CHARSET = 'utf-8'

    # Add subject, from and to lines.
    msg['Subject'] = SUBJECT 
    msg['From'] = source_email 
    msg['To'] = destination_to_email

    # Create a multipart/alternative child container.
    msg_body = MIMEMultipart('alternative')

    # Encode the text and HTML content and set the character encoding. This step is
    # necessary if you're sending a message with characters outside the ASCII range.
    textpart = MIMEText(BODY_TEXT.encode(CHARSET), 'plain', CHARSET)
    htmlpart = MIMEText(BODY_HTML.encode(CHARSET), 'html', CHARSET)

    # Add the text and HTML parts to the child container.
    msg_body.attach(textpart)
    msg_body.attach(htmlpart)

    # Attach the multipart/alternative child container to the multipart/mixed parent container.
    msg.attach(msg_body)
    #Provide the contents of the email.
    sesresponse = ses_client.send_raw_email(
                Source=source_email,
                Destinations=[
                    destination_to_email
                ],
                RawMessage={
                    'Data':msg.as_string(),
                }
                
            )
        
        
    return {
            'statusCode': 200,
            'body': 'CW Alert(s) Emailed.',
            'emailID': sesresponse.get('MessageId')
        }
