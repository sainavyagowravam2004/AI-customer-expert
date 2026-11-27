"""Screenshot and upload storage.

An empty ``S3_ENDPOINT_URL`` writes files under ``storage_dir``
(``/app/storage``, the shared ``knowledge_assets`` volume). A non-empty
endpoint uses that S3-compatible API instead.
"""

from functools import lru_cache
from pathlib import Path
from typing import Protocol, runtime_checkable

import boto3
from botocore.exceptions import ClientError

from app.core.config import Settings, get_settings


class ObjectStore(Protocol):
    """Bytes in, bytes out, addressed by a relative object key."""

    def put_bytes(self, key: str, data: bytes, *, content_type: str | None = None) -> str:
        """Store ``data`` at ``key`` and return the key."""

    def get_bytes(self, key: str) -> bytes:
        """Return the object stored at ``key``."""

    def delete(self, key: str) -> None:
        """Remove ``key`` if it exists."""


class Storage:
    """Local filesystem or S3, chosen from settings."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings if settings is not None else get_settings()

    @property
    def uses_local(self) -> bool:
        return self._settings.uses_local_storage

    def put_bytes(self, key: str, data: bytes, *, content_type: str | None = None) -> str:
        object_key = _object_key(key)
        if self.uses_local:
            path = self._local_path(object_key)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            return object_key

        extra: dict[str, str] = {}
        if content_type is not None:
            extra["ContentType"] = content_type
        self._s3().put_object(
            Bucket=self._bucket(),
            Key=object_key,
            Body=data,
            **extra,
        )
        return object_key

    def get_bytes(self, key: str) -> bytes:
        object_key = _object_key(key)
        if self.uses_local:
            path = self._local_path(object_key)
            if not path.is_file():
                raise FileNotFoundError(object_key)
            return path.read_bytes()

        try:
            response = self._s3().get_object(Bucket=self._bucket(), Key=object_key)
        except ClientError as exc:
            if _is_missing(exc):
                raise FileNotFoundError(object_key) from exc
            raise
        payload = response["Body"]
        if not isinstance(payload, ReadableBody):
            raise TypeError("S3 object body was not readable")
        body = payload.read()
        if not isinstance(body, bytes):
            raise TypeError("S3 object body was not bytes")
        return body

    def delete(self, key: str) -> None:
        object_key = _object_key(key)
        if self.uses_local:
            path = self._local_path(object_key)
            if path.is_file():
                path.unlink()
            return
        self._s3().delete_object(Bucket=self._bucket(), Key=object_key)

    def _local_path(self, object_key: str) -> Path:
        return self._settings.storage_dir / object_key

    def _bucket(self) -> str:
        if self._settings.s3_bucket.strip() == "":
            raise RuntimeError("S3_BUCKET is required when S3_ENDPOINT_URL is set")
        return self._settings.s3_bucket

    def _s3(self) -> "S3Client":
        return boto3.client(
            "s3",
            endpoint_url=self._settings.s3_endpoint_url,
            aws_access_key_id=self._settings.s3_access_key,
            aws_secret_access_key=self._settings.s3_secret_key,
            region_name=self._settings.s3_region,
        )


@runtime_checkable
class ReadableBody(Protocol):
    """Minimal file-like object returned by S3 get_object."""

    def read(self) -> bytes:
        """Return the full object body."""


class S3Client(Protocol):
    """The boto3 S3 methods this helper calls."""

    def put_object(self, **kwargs: str | bytes) -> object:
        """Upload one object."""

    def get_object(self, **kwargs: str) -> dict[str, object]:
        """Download one object."""

    def delete_object(self, **kwargs: str) -> object:
        """Delete one object."""


def _object_key(key: str) -> str:
    normalized = key.replace("\\", "/").strip()
    if normalized.startswith("/"):
        normalized = normalized.lstrip("/")
    parts = tuple(part for part in normalized.split("/") if part not in {"", "."})
    if not parts or any(part == ".." for part in parts):
        raise ValueError(f"invalid storage key: {key}")
    return "/".join(parts)


def _is_missing(exc: ClientError) -> bool:
    error = exc.response.get("Error", {})
    code = error.get("Code") if isinstance(error, dict) else None
    return code in {"NoSuchKey", "404", "NotFound"}


@lru_cache(maxsize=1)
def get_storage() -> Storage:
    """Return the process-wide storage helper."""
    return Storage()
