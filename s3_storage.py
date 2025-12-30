"""
S3 Storage Helper Functions
Handles file uploads/downloads to AWS S3
"""
import os
import boto3
from botocore.exceptions import ClientError

# Initialize S3 client
s3_client = boto3.client('s3')
S3_BUCKET = os.environ.get('S3_BUCKET', 'xnotebook-uploads-prod')
USE_S3 = os.environ.get('USE_S3', 'false').lower() == 'true'


def upload_to_s3(local_file, s3_key):
    """Upload file to S3 bucket"""
    if not USE_S3:
        return True  # Skip S3 in local dev

    try:
        s3_client.upload_file(local_file, S3_BUCKET, s3_key)
        print(f"Uploaded {local_file} to s3://{S3_BUCKET}/{s3_key}")
        return True
    except ClientError as e:
        print(f"S3 upload error: {e}")
        return False


def download_from_s3(s3_key, local_file):
    """Download file from S3 bucket"""
    if not USE_S3:
        return True  # Skip S3 in local dev

    try:
        s3_client.download_file(S3_BUCKET, s3_key, local_file)
        print(f"Downloaded s3://{S3_BUCKET}/{s3_key} to {local_file}")
        return True
    except ClientError as e:
        print(f"S3 download error: {e}")
        return False


def delete_from_s3(s3_key):
    """Delete file from S3 bucket"""
    if not USE_S3:
        return True

    try:
        s3_client.delete_object(Bucket=S3_BUCKET, Key=s3_key)
        print(f"Deleted s3://{S3_BUCKET}/{s3_key}")
        return True
    except ClientError as e:
        print(f"S3 delete error: {e}")
        return False


def get_s3_presigned_url(s3_key, expiration=3600):
    """Generate presigned URL for temporary access"""
    if not USE_S3:
        return None

    try:
        url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': S3_BUCKET, 'Key': s3_key},
            ExpiresIn=expiration
        )
        return url
    except ClientError as e:
        print(f"S3 URL generation error: {e}")
        return None


def file_exists_in_s3(s3_key):
    """Check if file exists in S3"""
    if not USE_S3:
        return False

    try:
        s3_client.head_object(Bucket=S3_BUCKET, Key=s3_key)
        return True
    except ClientError:
        return False
