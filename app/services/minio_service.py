import datetime as dt
import os
import re
from io import BytesIO
from uuid import UUID, uuid4
from datetime import timedelta

from fastapi import HTTPException, UploadFile
from minio import Minio
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import File


client = Minio(
    settings.minio_endpoint,
    access_key=settings.minio_access_key,
    secret_key=settings.minio_secret_key,
    secure=settings.minio_secure,
)


def ensure_bucket() -> None:
    if not client.bucket_exists(settings.minio_bucket):
        client.make_bucket(settings.minio_bucket)


def secure_filename(filename: str) -> str:
    filename = os.path.basename(filename or "file")
    filename = re.sub(r"[^\w\s.-]", "", filename).strip()
    return filename or "file"


def upload_file(db: Session, file: UploadFile, uploaded_by: UUID | None) -> File:
    content = file.file.read()
    size = len(content)

    max_size = settings.max_upload_size_mb * 1024 * 1024
    if size > max_size:
        raise HTTPException(status_code=413, detail="File is too large")

    object_key = (
        f"files/{dt.date.today():%Y/%m/%d}/"
        f"{uuid4()}-{secure_filename(file.filename)}"
    )

    content_type = file.content_type or "application/octet-stream"

    client.put_object(
        settings.minio_bucket,
        object_key,
        BytesIO(content),
        length=size,
        content_type=content_type,
    )

    db_file = File(
        bucket=settings.minio_bucket,
        object_key=object_key,
        original_filename=file.filename or object_key,
        content_type=content_type,
        size=size,
        uploaded_by=uploaded_by,
    )

    db.add(db_file)
    db.flush()

    return db_file


def presigned_url(object_key: str) -> str:
    url = client.presigned_get_object(
        settings.minio_bucket,
        object_key,
        expires=timedelta(seconds=settings.presigned_expires_seconds),
    )

    if settings.minio_public_endpoint and settings.minio_endpoint:
        url = url.replace(settings.minio_endpoint, settings.minio_public_endpoint, 1)

    return url


def delete_file(file: File) -> None:
    client.remove_object(file.bucket, file.object_key)