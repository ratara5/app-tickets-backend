import uuid
import os
from minio import Minio
from io import BytesIO
from app.core.settings import settings

import logging
import structlog

log = structlog.get_logger()


def get_minio_client() -> Minio:
    return Minio(
        f"{settings.minio_endpoint}:{settings.minio_port}",
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )

def ensure_bucket(client: Minio, bucket: str):
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)
        log.info("minio_bucket_created", bucket=bucket)

def upload_file(file_stream, 
                original_filename: str,
                content_type: str,
                full_object_path: str,
                job_id: str="") -> dict:
    """
    full_object_path: path completo en MinIO incluyendo nombre de archivo
    Ej: "Mantenimiento/Correctivos/2025/Abril/MNT-1042/abc123.jpg"
    """
    bucket = settings.minio_default_bucket
    client = get_minio_client()
    ensure_bucket(client, bucket)

    file_stream.seek(0, 2)
    size = file_stream.tell()
    file_stream.seek(0)

    log.info("minio_upload_started", job_id=job_id,
             object_path=full_object_path, size_bytes=size)

    try:
        client.put_object(
            bucket_name=bucket,
            object_name=full_object_path,   # path completo, no solo el nombre
            data=file_stream,
            length=size,
            content_type=content_type,
        )
    except Exception as e:
        log.error("minio_upload_failed", job_id=job_id, 
                  object_path=full_object_path, error=str(e))
        raise

    log.info("minio_upload_complete", job_id=job_id,
              object_path=full_object_path, size_bytes=size)

    return {
        "bucket": bucket,
        "object_name": full_object_path,
        "url_path": f"/{bucket}/{full_object_path}",
        "size_bytes": size,
    }

def object_exists_by_name(original_name: str) -> bool:
    client = get_minio_client()
    log.info("minio_search_start", original_name=original_name)
    try:
        objects = list(client.list_objects(
            settings.minio_default_bucket,
            recursive=True,
        ))
        return any(obj.object_name.endswith(original_name) for obj in objects)
    except Exception as e:
        log.error("minio_search_failed", original_name=original_name, error=str(e))
        raise
    

def get_presigned_url(object_name: str, expires_hours: int = 1) -> str:
    from datetime import timedelta
    client = get_minio_client()
    bucket = settings.minio_default_bucket
    log.info("minio_presigned_url_generated",
             object_name=object_name, expires_hours=expires_hours)
    return client.presigned_get_object(
        bucket, object_name,
        expires=timedelta(hours=expires_hours)
    )