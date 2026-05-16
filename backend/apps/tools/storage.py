import uuid
from datetime import datetime
from urllib.parse import quote

import boto3
from botocore.config import Config as BotoConfig
from django.conf import settings

# Server-derived Content-Type by extension. Never trust client-supplied content_type
# at storage time — an attacker could otherwise upload e.g. a .zip with text/html and
# get the public URL to render as HTML. Falls back to octet-stream for unknown ext.
EXT_TO_MIME = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
    "pdf": "application/pdf",
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xls": "application/vnd.ms-excel",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "ppt": "application/vnd.ms-powerpoint",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "txt": "text/plain",
    "md": "text/markdown",
    "csv": "text/csv",
    "json": "application/json",
    "zip": "application/zip",
}


def get_s3_client():
    scheme = "https" if settings.MINIO_USE_SSL else "http"
    return boto3.client(
        "s3",
        endpoint_url=f"{scheme}://{settings.MINIO_ENDPOINT}",
        aws_access_key_id=settings.MINIO_ACCESS_KEY,
        aws_secret_access_key=settings.MINIO_SECRET_KEY,
        config=BotoConfig(signature_version="s3v4", proxies={}),
        region_name="us-east-1",
    )


def _content_disposition(filename: str) -> str:
    """RFC 6266 Content-Disposition: attachment with original filename.
    Forces the browser to download (instead of rendering inline) and uses
    the original filename. Non-ASCII names are encoded via filename*=
    per RFC 5987.
    """
    safe = "".join(c for c in (filename or "") if c >= " " and c not in '\\"')
    if not safe:
        safe = "file"
    try:
        ascii_safe = safe.encode("ascii").decode("ascii")
        return f'attachment; filename="{ascii_safe}"'
    except UnicodeEncodeError:
        return f"attachment; filename=\"file\"; filename*=UTF-8''{quote(safe, safe='')}"


def upload_image(file) -> tuple[str, str]:
    """Upload a file to MinIO. Returns (public_url, object_key)."""
    ext = file.name.rsplit(".", 1)[-1].lower() if "." in file.name else "bin"
    safe_mime = EXT_TO_MIME.get(ext, "application/octet-stream")
    now = datetime.now()
    key = f"{now.year}/{now.month:02d}/{now.day:02d}/{uuid.uuid4().hex}.{ext}"

    client = get_s3_client()
    client.upload_fileobj(
        file,
        settings.MINIO_BUCKET,
        key,
        ExtraArgs={
            "ContentType": safe_mime,
            "ContentDisposition": _content_disposition(file.name),
        },
    )
    return f"{settings.MINIO_PUBLIC_URL}/{key}", key


def delete_object(key: str) -> None:
    """Delete an object from MinIO by its object key."""
    client = get_s3_client()
    client.delete_object(Bucket=settings.MINIO_BUCKET, Key=key)


def read_object(key: str) -> bytes:
    """Fetch the raw bytes of an object stored in MinIO.

    Used by code paths that need to feed the file into an external API
    (e.g., the AI wizard's multimodal LLM call) instead of returning a
    public URL.
    """
    client = get_s3_client()
    obj = client.get_object(Bucket=settings.MINIO_BUCKET, Key=key)
    try:
        return obj["Body"].read()
    finally:
        obj["Body"].close()
