import os
import boto3
from botocore.client import Config


def s3_client():
    return boto3.client(
        "s3",
        region_name=os.environ["DO_SPACES_REGION"],
        endpoint_url=os.environ["DO_SPACES_ENDPOINT"],
        aws_access_key_id=os.environ["DO_SPACES_KEY"],
        aws_secret_access_key=os.environ["DO_SPACES_SECRET"],
        config=Config(signature_version="s3v4"),
    )


def put_object(key: str, data: bytes, content_type: str):
    bucket = os.environ["DO_SPACES_BUCKET"]
    s3 = s3_client()
    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=data,
        ACL="private",
        ContentType=content_type,
    )


def presigned_get_url(key: str, expires_seconds: int = 3600) -> str:
    bucket = os.environ["DO_SPACES_BUCKET"]
    s3 = s3_client()
    return s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=expires_seconds,
    )