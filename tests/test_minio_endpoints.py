"""Tests for the MinIO internal/public endpoint split.

The outage these tests pin down: a bare DHCP lease was serving as both the backend's
dial target and the origin baked into presigned URLs, so rotating the lease took photo
uploads down with it.
"""

import errno
import socket
from io import BytesIO
from typing import Any, Iterator
from urllib.parse import urlsplit

import pytest
from datetime import timedelta
import urllib3.exceptions as urllib3_errors
from fastapi.testclient import TestClient
from minio import Minio
from minio.error import S3Error

from app.core import storage
from app.core.settings import MinioOrigin, Settings
from app.server import create_app


UNROUTABLE_HOST = "192.0.2.1"  # RFC 5737 TEST-NET-1: guaranteed not to answer.
PUBLIC_HOST = "media.acme.test"
INTERNAL_HOST = "127.0.0.1"
BUCKET = "acme-uploads-own-api"
OBJECT_NAME = "Mantenimientos/Correctivos/2026/Septiembre/MNT-1/photo.jpg"


def _settings(**overrides: Any) -> Settings:
    """Build a Settings instance with every MinIO variable pinned explicitly.

    The public variables default to ``None`` so that a developer's local ``.env``
    (which legitimately sets ``MINIO_PUBLIC_ENDPOINT``) can never leak into these
    tests. Every other setting still comes from the repository ``.env`` files.
    """
    values: dict[str, Any] = {
        "MINIO_ENDPOINT": INTERNAL_HOST,
        "MINIO_PORT": 9000,
        "MINIO_ACCESS_KEY": "test-access-key",
        "MINIO_SECRET_KEY": "test-secret-key",
        "MINIO_SECURE": False,
        "MINIO_DEFAULT_BUCKET": BUCKET,
        "MINIO_PUBLIC_ENDPOINT": None,
        "MINIO_PUBLIC_PORT": None,
        "MINIO_PUBLIC_SECURE": None,
    }
    values.update(overrides)
    return Settings(**values)


def _use_settings(monkeypatch: pytest.MonkeyPatch, **overrides: Any) -> Settings:
    configured = _settings(**overrides)
    monkeypatch.setattr(storage, "settings", configured)
    storage.reset_storage_readiness()
    return configured


def _effective_origin(url: str) -> str:
    """``scheme://host:port`` of a URL, filling in the scheme's default port.

    minio-py omits the port when it equals the scheme default, so a plain netloc
    comparison would miss the real origin.
    """
    parts = urlsplit(url)
    default_port = 443 if parts.scheme == "https" else 80
    return f"{parts.scheme}://{parts.hostname}:{parts.port or default_port}"


def _unreachable(errno_value: int = errno.EHOSTUNREACH) -> urllib3_errors.NewConnectionError:
    """The exact exception urllib3 raises when the store cannot be dialed.

    urllib3 chains the socket error onto ``NewConnectionError``, so the errno that
    identifies the failure (113 no route, 111 refused) lives in ``__cause__``.
    """
    socket_error = OSError(errno_value, "no route to host")
    error = urllib3_errors.NewConnectionError(
        None, f"Failed to establish a new connection: {socket_error}"
    )
    error.__cause__ = socket_error
    return error


def _record_http_calls(
    monkeypatch: pytest.MonkeyPatch,
    failure: BaseException | None = None,
) -> list[dict[str, Any]]:
    """Replace the MinIO transport and record every request it attempts."""
    calls: list[dict[str, Any]] = []

    def _fake_url_open(
        self: Minio,
        method: str,
        region: str,
        **kwargs: Any,
    ) -> Any:
        calls.append(
            {
                "method": method,
                "region": region,
                "bucket": kwargs.get("bucket_name"),
                "query": dict(kwargs.get("query_params") or {}),
            }
        )
        if failure is not None:
            raise failure
        raise AssertionError(
            f"unexpected MinIO I/O: {method} {kwargs.get('bucket_name')}"
        )

    monkeypatch.setattr(Minio, "_url_open", _fake_url_open, raising=True)
    return calls


class _RecordingMinio:
    """Stands in for ``minio.Minio`` to capture how each client is constructed."""

    instances: list["_RecordingMinio"] = []

    def __init__(self, endpoint: str, **kwargs: Any) -> None:
        self.endpoint = endpoint
        self.kwargs = kwargs
        _RecordingMinio.instances.append(self)

    def bucket_exists(self, bucket: str) -> bool:
        return True


@pytest.fixture(autouse=True)
def _clean_readiness_cache() -> Iterator[None]:
    storage.reset_storage_readiness()
    yield
    storage.reset_storage_readiness()


# --------------------------------------------------------------------------- #
# A. The internal dial target and the public signing origin are independent
# --------------------------------------------------------------------------- #


def test_presigned_url_is_signed_with_the_public_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_settings(
        monkeypatch,
        MINIO_ENDPOINT=UNROUTABLE_HOST,
        MINIO_PUBLIC_ENDPOINT=PUBLIC_HOST,
    )
    _record_http_calls(monkeypatch)

    url = storage.get_presigned_url(OBJECT_NAME, expires=timedelta(hours=1))

    assert _effective_origin(url) == f"http://{PUBLIC_HOST}:9000"


def test_presigned_url_falls_back_to_the_internal_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_settings(monkeypatch, MINIO_ENDPOINT="minio-acme")
    _record_http_calls(monkeypatch)

    url = storage.get_presigned_url(OBJECT_NAME, expires=timedelta(hours=1))

    assert _effective_origin(url) == "http://minio-acme:9000"


def test_presigned_url_uses_the_public_scheme_and_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_settings(
        monkeypatch,
        MINIO_ENDPOINT="minio-acme",
        MINIO_PORT=9000,
        MINIO_SECURE=False,
        MINIO_PUBLIC_ENDPOINT=PUBLIC_HOST,
        MINIO_PUBLIC_PORT=443,
        MINIO_PUBLIC_SECURE=True,
    )
    _record_http_calls(monkeypatch)

    url = storage.get_presigned_url(OBJECT_NAME, expires=timedelta(hours=1))

    assert urlsplit(url).scheme == "https"
    assert _effective_origin(url) == f"https://{PUBLIC_HOST}:443"


def test_public_origin_is_resolved_independently_of_the_internal_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configured = _use_settings(
        monkeypatch,
        MINIO_ENDPOINT="minio-acme",
        MINIO_PORT=9000,
        MINIO_PUBLIC_ENDPOINT=PUBLIC_HOST,
        MINIO_PUBLIC_PORT=443,
        MINIO_PUBLIC_SECURE=True,
    )

    assert configured.minio_public == MinioOrigin(PUBLIC_HOST, 443, True)
    assert configured.minio_public.origin == f"https://{PUBLIC_HOST}:443"
    assert configured.minio_internal.origin == "http://minio-acme:9000"


def test_public_origin_falls_back_to_the_internal_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configured = _use_settings(
        monkeypatch, MINIO_ENDPOINT="minio-acme", MINIO_PORT=9001, MINIO_SECURE=True
    )

    assert configured.minio_public == MinioOrigin("minio-acme", 9001, True)


def test_uploads_dial_the_internal_endpoint_while_urls_sign_the_public_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_settings(
        monkeypatch,
        MINIO_ENDPOINT="minio-acme",
        MINIO_PUBLIC_ENDPOINT=PUBLIC_HOST,
    )
    _RecordingMinio.instances.clear()
    monkeypatch.setattr(storage, "Minio", _RecordingMinio)

    storage.get_minio_client()
    storage.get_presigned_client()

    assert [client.endpoint for client in _RecordingMinio.instances] == [
        "minio-acme:9000",
        f"{PUBLIC_HOST}:9000",
    ]


# --------------------------------------------------------------------------- #
# B. Presigning is local: no GetBucketLocation, no request at all
# --------------------------------------------------------------------------- #


def test_presigning_issues_no_http_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_settings(
        monkeypatch, MINIO_ENDPOINT=UNROUTABLE_HOST, MINIO_PUBLIC_ENDPOINT=PUBLIC_HOST
    )
    calls = _record_http_calls(monkeypatch)

    storage.get_presigned_url(OBJECT_NAME, expires=timedelta(hours=1))

    assert calls == []


def test_presigning_does_not_call_get_bucket_location(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_settings(
        monkeypatch, MINIO_ENDPOINT=UNROUTABLE_HOST, MINIO_PUBLIC_ENDPOINT=PUBLIC_HOST
    )
    calls = _record_http_calls(monkeypatch)

    storage.get_presigned_url(OBJECT_NAME, expires=timedelta(hours=1))

    assert not [call for call in calls if "location" in call["query"]]


def test_readiness_probe_does_not_call_get_bucket_location(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The region is pinned, so the probe must not spend a round trip on it."""
    _use_settings(monkeypatch, MINIO_ENDPOINT=INTERNAL_HOST)
    _RecordingMinio.instances.clear()
    monkeypatch.setattr(storage, "Minio", _RecordingMinio)

    storage.ensure_storage_ready()

    assert _RecordingMinio.instances[0].kwargs["region"] == "us-east-1"


# --------------------------------------------------------------------------- #
# C. A presigned URL is signed, never rewritten
# --------------------------------------------------------------------------- #


def test_presigned_url_carries_the_signature_for_the_public_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_settings(
        monkeypatch, MINIO_ENDPOINT=UNROUTABLE_HOST, MINIO_PUBLIC_ENDPOINT=PUBLIC_HOST
    )
    _record_http_calls(monkeypatch)

    url = storage.get_presigned_url(OBJECT_NAME, expires=timedelta(hours=1))

    assert "X-Amz-Signature=" in url
    assert "X-Amz-Expires=3600" in url
    assert f"/{BUCKET}/{OBJECT_NAME}" in url


def test_presigned_url_is_not_rewritten_to_the_internal_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Guards the failure mode that motivated the split: a post-hoc host rewrite."""
    _use_settings(
        monkeypatch, MINIO_ENDPOINT="minio-acme", MINIO_PUBLIC_ENDPOINT=PUBLIC_HOST
    )
    _record_http_calls(monkeypatch)

    url = storage.get_presigned_url(OBJECT_NAME, expires=timedelta(hours=1))

    assert "minio-acme" not in url
    assert "127.0.0.1" not in url


# --------------------------------------------------------------------------- #
# D. Fail fast, and transport errors become domain errors
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "errno_value",
    [
        errno.EHOSTUNREACH,
        errno.ECONNREFUSED,
        errno.ENETUNREACH,
        errno.ETIMEDOUT,
    ],
)
def test_transport_errors_become_storage_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    errno_value: int,
) -> None:
    configured = _use_settings(
        monkeypatch, MINIO_ENDPOINT="192.168.10.26", MINIO_PUBLIC_ENDPOINT=PUBLIC_HOST
    )
    _record_http_calls(
        monkeypatch,
        _unreachable(errno_value),
    )

    with pytest.raises(storage.StorageUnavailableError) as raised:
        storage.ensure_storage_ready()

    message = str(raised.value)
    assert "192.168.10.26:9000" in message
    assert "MINIO_ENDPOINT=192.168.10.26" in message
    assert "minio-acme" in message


def test_urllib3_retry_storm_is_translated_not_leaked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_settings(monkeypatch, MINIO_ENDPOINT="192.168.10.26")
    _record_http_calls(
        monkeypatch,
        urllib3_errors.MaxRetryError(None, "/acme-uploads-own-api?location="),
    )

    with pytest.raises(storage.StorageUnavailableError) as raised:
        storage.ensure_storage_ready()

    # The caller sees the domain error, not a urllib3 retry traceback...
    assert type(raised.value) is storage.StorageUnavailableError
    assert "Max retries exceeded" not in str(raised.value)
    # ...while the cause is still chained for diagnosis.
    assert isinstance(raised.value.__cause__, urllib3_errors.MaxRetryError)
    assert "192.168.10.26:9000" in str(raised.value)


def test_socket_errors_become_storage_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_settings(monkeypatch, MINIO_ENDPOINT="minio-acme")
    _record_http_calls(monkeypatch, socket.gaierror("Name or service not known"))

    with pytest.raises(storage.StorageUnavailableError):
        storage.ensure_storage_ready()


def test_bucket_errors_are_not_masked_as_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_settings(monkeypatch, MINIO_ENDPOINT=INTERNAL_HOST)
    _record_http_calls(
        monkeypatch,
        S3Error(
            "AccessDenied",
            "Access Denied",
            resource="/acme-uploads-own-api",
            request_id="req-1",
            host_id=None,
            response=None,
        ),
    )

    with pytest.raises(S3Error):
        storage.ensure_storage_ready()


# --------------------------------------------------------------------------- #
# E. The bucket is ensured once, not once per upload
# --------------------------------------------------------------------------- #


def test_bucket_is_probed_once_for_many_operations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_settings(monkeypatch, MINIO_ENDPOINT=INTERNAL_HOST)
    probes: list[str] = []

    class _CountingMinio(_RecordingMinio):
        def bucket_exists(self, bucket: str) -> bool:
            probes.append(bucket)
            return True

    monkeypatch.setattr(storage, "Minio", _CountingMinio)

    storage.ensure_storage_ready()
    storage.ensure_storage_ready()
    storage.ensure_storage_ready()

    assert probes == [BUCKET]


def test_a_failed_probe_does_not_poison_a_later_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_settings(monkeypatch, MINIO_ENDPOINT="192.168.10.26")
    attempts: list[str] = []

    class _FlakyMinio(_RecordingMinio):
        def bucket_exists(self, bucket: str) -> bool:
            attempts.append(bucket)
            if len(attempts) == 1:
                raise _unreachable()
            return True

    monkeypatch.setattr(storage, "Minio", _FlakyMinio)

    with pytest.raises(storage.StorageUnavailableError):
        storage.ensure_storage_ready()

    # The failure is not memoized: the store coming back up needs no restart.
    storage.ensure_storage_ready()
    storage.ensure_storage_ready()

    assert len(attempts) == 2


# --------------------------------------------------------------------------- #
# F. Startup fails once, with a message that says what to do
# --------------------------------------------------------------------------- #


def test_startup_aborts_once_when_the_store_is_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_settings(
        monkeypatch, MINIO_ENDPOINT="192.168.10.26", MINIO_PUBLIC_ENDPOINT=PUBLIC_HOST
    )
    probes: list[str] = []

    class _UnreachableMinio(_RecordingMinio):
        def bucket_exists(self, bucket: str) -> bool:
            probes.append(bucket)
            raise _unreachable()

    monkeypatch.setattr(storage, "Minio", _UnreachableMinio)

    with pytest.raises(storage.StorageUnavailableError) as raised:
        with TestClient(create_app()):
            pass

    assert probes == [BUCKET], "startup must probe exactly once, not retry per photo"
    assert "MINIO_ENDPOINT=192.168.10.26" in str(raised.value)
    assert "EHOSTUNREACH" in str(raised.value)


def test_startup_succeeds_against_a_reachable_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_settings(monkeypatch, MINIO_ENDPOINT=INTERNAL_HOST)
    probes: list[str] = []

    class _ReachableMinio(_RecordingMinio):
        def bucket_exists(self, bucket: str) -> bool:
            probes.append(bucket)
            return True

    monkeypatch.setattr(storage, "Minio", _ReachableMinio)

    with TestClient(create_app()):
        pass

    assert probes == [BUCKET]


# --------------------------------------------------------------------------- #
# G. The upload path itself
# --------------------------------------------------------------------------- #


def test_upload_does_not_reprobe_the_bucket_on_every_photo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_settings(monkeypatch, MINIO_ENDPOINT=INTERNAL_HOST)
    probes: list[str] = []
    uploads: list[str] = []

    class _CountingMinio(_RecordingMinio):
        def bucket_exists(self, bucket: str) -> bool:
            probes.append(bucket)
            return True

        def put_object(self, **kwargs: Any) -> None:
            uploads.append(kwargs["object_name"])

    monkeypatch.setattr(storage, "Minio", _CountingMinio)

    for index in range(3):
        storage.upload_file(
            BytesIO(b"photo-bytes"),
            f"photo-{index}.jpg",
            "image/jpeg",
            f"photos/photo-{index}.jpg",
        )

    assert len(uploads) == 3
    assert probes == [BUCKET], "the bucket check must be memoized, not per upload"


def test_upload_against_an_unreachable_store_raises_a_domain_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_settings(monkeypatch, MINIO_ENDPOINT="192.168.10.26")

    class _UnreachableMinio(_RecordingMinio):
        def bucket_exists(self, bucket: str) -> bool:
            return True

        def put_object(self, **kwargs: Any) -> None:
            raise _unreachable()

    monkeypatch.setattr(storage, "Minio", _UnreachableMinio)

    with pytest.raises(storage.StorageUnavailableError) as raised:
        storage.upload_file(
            BytesIO(b"photo-bytes"), "photo.jpg", "image/jpeg", "photos/photo.jpg"
        )

    assert "MINIO_ENDPOINT=192.168.10.26" in str(raised.value)
    assert "EHOSTUNREACH" in str(raised.value)
