import hashlib
import os
import io
from typing import Optional, Tuple
import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from fastapi import UploadFile
import logging

logger = logging.getLogger(__name__)

AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "trade-finance-docs")

USE_LOCAL_STORAGE = os.getenv("USE_LOCAL_STORAGE", "true").lower() == "true"
LOCAL_STORAGE_PATH = os.getenv("LOCAL_STORAGE_PATH", "./uploads")


def compute_sha256(data: bytes) -> str:
    """Compute SHA-256 hash of byte data."""
    return hashlib.sha256(data).hexdigest()


def get_s3_client():
    """Return boto3 S3 client."""
    return boto3.client(
        "s3",
        region_name=AWS_REGION,
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    )


async def upload_document(file: UploadFile, owner_id: int, doc_number: str) -> Tuple[str, str]:
    """
    Upload document to S3 (or local storage fallback).
    Returns (file_url, sha256_hash).
    """
    content = await file.read()
    file_hash = compute_sha256(content)
    
    safe_name = doc_number.replace("/", "_").replace(" ", "_")
    key = f"documents/{owner_id}/{safe_name}_{file.filename}"

    if USE_LOCAL_STORAGE:
        os.makedirs(f"{LOCAL_STORAGE_PATH}/{owner_id}", exist_ok=True)
        local_path = f"{LOCAL_STORAGE_PATH}/{owner_id}/{safe_name}_{file.filename}"
        with open(local_path, "wb") as f:
            f.write(content)
        file_url = f"local://{local_path}"
        logger.info(f"Saved file locally: {file_url}")
    else:
        try:
            s3 = get_s3_client()
            s3.upload_fileobj(
                io.BytesIO(content),
                S3_BUCKET_NAME,
                key,
                ExtraArgs={"ContentType": file.content_type or "application/octet-stream"}
            )
            file_url = f"https://{S3_BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{key}"
            logger.info(f"Uploaded to S3: {file_url}")
        except (ClientError, NoCredentialsError) as e:
            logger.error(f"S3 upload failed: {e}")
            raise RuntimeError(f"File upload failed: {str(e)}")

    return file_url, file_hash


def fetch_file_bytes(file_url: str) -> Optional[bytes]:
    """
    Retrieve file bytes from storage (S3 or local).
    Used by integrity checks to recompute hash.
    """
    if file_url.startswith("local://"):
        local_path = file_url.replace("local://", "")
        if not os.path.exists(local_path):
            return None
        with open(local_path, "rb") as f:
            return f.read()
    else:
        # S3 fetch
        try:
            s3 = get_s3_client()
            # Parse bucket/key from URL
            parts = file_url.replace("https://", "").split("/", 1)
            bucket = parts[0].split(".")[0]
            key = parts[1] if len(parts) > 1 else ""
            response = s3.get_object(Bucket=bucket, Key=key)
            return response["Body"].read()
        except Exception as e:
            logger.error(f"Failed to fetch file from S3: {e}")
            return None


def recompute_hash_for_url(file_url: str) -> Optional[str]:
    """Recompute SHA-256 for a stored file. Returns None if file not accessible."""
    data = fetch_file_bytes(file_url)
    if data is None:
        return None
    return compute_sha256(data)
