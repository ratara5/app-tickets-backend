import structlog
import urllib3.exceptions as urllib3_errors
from contextlib import contextmanager
from datetime import timedelta
from errno import errorcode
from typing import BinaryIO, Iterator

from minio import Minio
from minio.error import S3Error

from app.core.settings import MinioOrigin, settings


log = structlog.get_logger()


class StorageUnavailableError(RuntimeError):
    """The object store cannot be reached at the configured internal endpoint.

    Raised instead of letting a urllib3 retry traceback escape, so that callers and
    logs name the setting that is wrong instead of an internal socket address.
    """


def _describe_cause(cause: BaseException) -> str:
    """Compact cause chain, e.g. ``NewConnectionError <- OSError errno 113``.

    Deliberately not ``repr(cause)``: a urllib3 retry chain rendered in full is the
    log noise this change exists to remove. The full exception stays chained.
    """
    described: list[str] = []
    seen: set[int] = set()
    current: BaseException | None = cause
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        described.append(type(current).__name__)
        if isinstance(current, OSError) and current.errno:
            described.append(
                f"errno {current.errno} "
                f"({errorcode.get(current.errno, 'UNKNOWN')})"
            )
        current = current.__cause__ or current.__context__
    return " <- ".join(described)


def _unavailable(operation: str, origin: MinioOrigin, cause: BaseException) -> StorageUnavailableError:
    return StorageUnavailableError(
        f"MinIO is unreachable for {operation}: {origin.origin} "
        f"(MINIO_ENDPOINT={origin.host}, MINIO_PORT={origin.port}, "
        f"MINIO_SECURE={str(origin.secure).lower()}). "
        f"Start or check the MinIO container and confirm that port {origin.port} is "
        f"published; if the backend runs on the host use MINIO_ENDPOINT=127.0.0.1, "
        f"and in Docker on the acme network use MINIO_ENDPOINT=minio-acme. "
        f"Never point MINIO_ENDPOINT at a LAN address. "
        f"Cause: {_describe_cause(cause)}"
    )


@contextmanager
def _storage_call(operation: str, origin: MinioOrigin) -> Iterator[None]:
    """Translate transport failures into a domain error at the storage boundary.

    ``S3Error`` is re-raised untouched: a denied key or a missing bucket is not a
    reachability problem and must not be reported as one. The original exception is
    chained onto the domain error and echoed in its message, so callers keep the
    cause without a second log line.
    """
    try:
        yield
    except S3Error:
        raise
    except (urllib3_errors.HTTPError, OSError) as exc:
        raise _unavailable(operation, origin, exc) from exc


def _build_client(origin: MinioOrigin) -> Minio:
    """Build a client bound to ``origin`` with the SigV4 region pinned.

    The explicit ``region`` is what makes presigning local: ``Minio.get_presigned_url``
    calls ``_get_region()``, which only answers from the client when a region was
    supplied and otherwise issues ``GET /{bucket}?location=`` against this origin.
    """
    return Minio(
        origin.netloc,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=origin.secure,
        region=settings.minio_region,
    )


def get_minio_client() -> Minio:
    """Client for the backend's own I/O, dialed at the internal endpoint."""
    return _build_client(settings.minio_internal)


def get_presigned_client() -> Minio:
    """Client used only to sign URLs, bound to the public origin.

    The public host is part of the SigV4 signature, so the split happens here, at
    signing time. A presigned URL is never rewritten afterwards.
    """
    return _build_client(settings.minio_public)


_bucket_ready: str | None = None


def reset_storage_readiness() -> None:
    """Forget the memoized bucket check. Used by tests and by recovery tooling."""
    global _bucket_ready
    _bucket_ready = None


def ensure_storage_ready() -> None:
    """Ensure the bucket exists, at most once per process.

    Replaces a ``bucket_exists`` call on every upload, which turned one unreachable
    store into a retry storm of one probe per photo. A failure is not memoized: a
    store that comes up later is picked up without a restart.
    """
    global _bucket_ready
    bucket = settings.minio_default_bucket
    if _bucket_ready == bucket:
        return

    origin = settings.minio_internal
    client = get_minio_client()
    with _storage_call("bucket check", origin):
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)
            log.info("minio_bucket_created", bucket=bucket)

    _bucket_ready = bucket


def upload_file(file_stream: BinaryIO,
                original_filename: str,
                content_type: str,
                full_object_path: str,
                job_id: str="") -> dict:
    """
    full_object_path: full path in MinIO including file name
    Ej: "Mantenimiento/Correctivos/2025/Abril/MNT-1042/abc123.jpg"
    """
    bucket = settings.minio_default_bucket
    ensure_storage_ready()
    client = get_minio_client()
    origin = settings.minio_internal

    file_stream.seek(0, 2)
    size = file_stream.tell()
    file_stream.seek(0)

    log.info("minio_upload_started", job_id=job_id,
             object_path=full_object_path, size_bytes=size)

    try:
        with _storage_call("upload", origin):
            client.put_object(
                bucket_name=bucket,
                object_name=full_object_path,   # full path, not only the name
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

def delete_object(object_name: str) -> None:
    bucket = settings.minio_default_bucket
    origin = settings.minio_internal
    client = get_minio_client()
    log.info("minio_delete_started", object_path=object_name)
    try:
        with _storage_call("delete", origin):
            client.remove_object(bucket, object_name)
    except Exception as e:
        log.error("minio_delete_failed", object_path=object_name, error=str(e))
        raise
    log.info("minio_delete_complete", object_path=object_name)

def object_exists_by_name(original_name: str) -> bool:
    bucket = settings.minio_default_bucket
    origin = settings.minio_internal
    client = get_minio_client()
    log.info("minio_search_start", original_name=original_name)
    try:
        with _storage_call("list", origin):
            objects = list(client.list_objects(
                bucket,
                recursive=True,
            ))
            return any(obj.object_name.endswith(original_name) for obj in objects)
    except Exception as e:
        log.error("minio_search_failed", original_name=original_name, error=str(e))
        raise

def get_presigned_url(object_name: str, expires: timedelta) -> str:
    """Sign a download URL for the public origin, expiring after `expires`.

    The lifetime is a timedelta rather than a bare number because the number's
    unit is exactly what was ambiguous: one variable was documented in seconds
    and consumed as hours. A caller now has to say hours or minutes in the code.
    """
    """Sign a download URL for the public origin.

    Purely local: the client carries an explicit region, so minio-py resolves the
    SigV4 region from the client instead of calling GetBucketLocation.
    """
    client = get_presigned_client()
    bucket = settings.minio_default_bucket
    log.info("minio_presigned_url_generated",
             object_name=object_name, expires=str(expires),
             public_endpoint=settings.minio_public.origin)
    return client.presigned_get_object(bucket, object_name, expires=expires)
