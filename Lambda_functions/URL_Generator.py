import json
import boto3
import uuid

s3_client = boto3.client('s3')

def lambda_handler(event, context):
    bucket_name = 'tuw-dic-ex3'
    object_name = f'images/{uuid.uuid4()}.jpg'

    try:
        post = s3_client.generate_presigned_post(
            Bucket=bucket_name,
            Key=object_name,
            Fields=None,
            Conditions=[
                {"bucket": bucket_name},
                ["starts-with", "$key", "images/"]
            ],
            ExpiresIn=3600
        )
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps(f'Error generating pre-signed URL: {str(e)}')
        }

    session = boto3.Session()
    credentials = session.get_credentials().get_frozen_credentials()

    post['fields']['AWSAccessKeyId'] = credentials.access_key
    post['fields']['x-amz-security-token'] = credentials.token

    return {
        'statusCode': 200,
        'body': json.dumps(post)
    }
