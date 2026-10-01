from pathlib import Path
from typing import NamedTuple

import json

from typing import Annotated

from pydantic import AliasChoices, Field, field_validator

from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
ENV_PATH_CORE = ROOT_DIR / ".env"


class MinioOrigin(NamedTuple):
    """A resolvable MinIO origin: where to dial, and what to sign.

    Carrying host, port and scheme together makes it impossible to mix an
    internal host with a public scheme, which is the defect this replaces.
    """

    host: str
    port: int
    secure: bool

    @property
    def netloc(self) -> str:
        return f"{self.host}:{self.port}"

    @property
    def scheme(self) -> str:
        return "https" if self.secure else "http"

    @property
    def origin(self) -> str:
        return f"{self.scheme}://{self.netloc}"


def _split_env_list(raw: str) -> list[str]:
    """Split a shell-safe env list: `a,b , c` -> ['a', 'b', 'c'].

    Tolerates the brackets and quotes a JSON array loses when a shell sources
    the file, so a value mangled that way still parses instead of aborting the
    process at import.
    """
    # Strip the JSON punctuation too: a shell that sourced the file removed the
    # quotes but left the brackets, and keeping them turned the first key into
    # "{image/jpeg" -- a silent corruption rather than a visible failure.
    def _clean(part: str) -> str:
        return part.strip().strip('"').strip("'").strip("{}[]").strip('"').strip("'")

    return [cleaned for cleaned in (_clean(part) for part in raw.split(",")) if cleaned]


def _parse_mapping(raw: str) -> dict[str, str]:
    """Parse a mapping that is either JSON or a shell-safe `k:v,k:v` list.

    A JSON object cannot survive `set -a; . .env` -- the shell strips the quotes
    and the result is not valid JSON -- so accept the flat form as well. Media
    types and extensions contain no comma or colon, so the first colon splits.
    """
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = {}
        for pair in _split_env_list(raw):
            key, sep, value = pair.partition(":")
            if not sep:
                raise ValueError(
                    f"expected a JSON object or a k:v list, got {pair!r}"
                ) from None
            parsed[key] = value
    if not isinstance(parsed, dict):
        raise ValueError(f"expected a mapping, got {type(parsed).__name__}")
    return {str(k): str(v) for k, v in parsed.items()}


def _parse_string_list(raw):
    """Accept a JSON array, a comma-separated list, or an already-parsed list."""
    if isinstance(raw, list):
        return raw
    text = str(raw).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return _split_env_list(text)
    if not isinstance(parsed, list):
        raise ValueError(f"expected a list, got {type(parsed).__name__}")
    return parsed


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # `ENV_PATH_COMPANY` (gtk-companies/gtk-acme/.env) was removed on
        # 2026-09-30 with the per-company stack. The company values it carried
        # — TZ_COMPANY, COUNTRY, CONTRACTOR_NIT, CLIENT_COMPANY_NAME — all live
        # in the core `.env`. Pydantic ignores a missing env_file without
        # complaining, so leaving this pointed at a deleted directory would not
        # have raised: the file was already a no-op and the second layer was
        # already ignored. Dropping it states that rather than implying a
        # fallback that never ran.
        env_file=ENV_PATH_CORE,
        #env_file_encoding="utf-8",
        extra="ignore",
    )

    # Companies info
    tz_company: str             = Field(..., alias="TZ_COMPANY")
    country_company: str        = Field(..., alias="COUNTRY")
    ## Client info / form
    client_company_name: str    = Field(..., alias="CLIENT_COMPANY_NAME")  
    client_format_name: str     = Field(..., alias="CLIENT_FORMAT_NAME") 
    ## Contractor info / my company
    contractor_name: str        = Field(..., alias="CONTRACTOR_NAME")
    contractor_nit: str         = Field(..., alias="CONTRACTOR_NIT")
    contractor_contact: str     = Field(..., alias="CONTRACTOR_CONTACT") 
    contractor_phone: str       = Field(..., alias="CONTRACTOR_PHONE")  

    # Postgres
    pg_host: str                = Field(..., alias="DB_HOST")
    pg_port: int                = Field(5432, alias="DB_PORT")
    pg_user: str                = Field(..., alias="DB_USER")
    pg_password: str            = Field(..., alias="DB_PASSWORD")
    pg_db: str                  = Field(..., alias="DB_NAME")

    # MinIO
    # Internal dial target: the address THIS process uses to reach the store.
    # Host run: 127.0.0.1. In Docker on the acme network: minio-acme.
    # Never a LAN address; a DHCP lease can rotate under us.
    minio_endpoint: str         = Field(..., alias="MINIO_ENDPOINT")
    minio_port: int             = Field(9000, alias="MINIO_PORT")
    minio_access_key: str       = Field(..., alias="MINIO_ACCESS_KEY")
    minio_secret_key: str       = Field(..., alias="MINIO_SECRET_KEY")
    minio_secure: bool          = Field(False, alias="MINIO_SECURE")
    # Public signing origin: the host baked into presigned URLs. The SigV4
    # signature covers the Host header, so this is chosen at signing time and the
    # URL is never rewritten afterwards. It is what the mobile app must resolve,
    # so it must be stable: a domain or a DHCP reservation, never a bare lease.
    # Falls back to the internal values to keep pre-split configurations working.
    minio_public_endpoint: str | None = Field(None, alias="MINIO_PUBLIC_ENDPOINT")
    minio_public_port: int | None     = Field(None, alias="MINIO_PUBLIC_PORT")
    minio_public_secure: bool | None  = Field(None, alias="MINIO_PUBLIC_SECURE")
    # SigV4 region. Pinning it keeps presigning local: without it minio-py issues
    # GetBucketLocation (GET /{bucket}?location=) on every presigned URL.
    minio_region: str           = Field("us-east-1", alias="MINIO_REGION")
    minio_default_bucket: str   = Field("company-uploads", alias="MINIO_DEFAULT_BUCKET")
    base_object_path: str       = Field("Maintenances", alias="BASE_OBJECT_PATH")
    ext_by_type: Annotated[dict[str, str], NoDecode] = Field(..., alias="EXT_BY_TYPE")
    allowed_types: Annotated[list[str], NoDecode] = Field(..., alias="ALLOWED_TYPES")
    # The unit is in the name because it was not derivable from it: the old
    # PRESIGNED_TTL was documented in seconds, shipped as 1, and consumed as
    # hours, so the default (3600, annotated "1 hour") contradicted its own
    # comment. PRESIGNED_TTL is still accepted so an existing .env is honoured
    # rather than silently falling back to the default.
    presigned_ttl_hours: int    = Field(
        1,
        validation_alias=AliasChoices("PRESIGNED_TTL_HOURS", "PRESIGNED_TTL"),
    )


    # Worksheet
    templates_dir: str          = Field("/app/templates/reports", alias="TEMPLATES_DIR")
    pdf_suffix: str             = Field("Soporte", alias="PDF_SUFFIX")

    # Disk
    chunk_dir: str              = Field("/tmp/upload_chunks", alias="CHUNK_DIR")

    #
    jwt_secret: str             = Field(..., alias="JWT_SECRET")
    jwt_algorithm: str          = Field(..., alias="JWT_ALGORITHM")
    jwt_expire_minutes: int     = Field(..., alias="JWT_EXPIRE_MINUTES")

    @property
    def pg_dsn(self):
        return f"postgresql://{self.pg_user}:{self.pg_password}@{self.pg_host}:{self.pg_port}/{self.pg_db}"

    @property
    def minio_internal(self) -> MinioOrigin:
        """Origin the backend itself dials to reach the object store."""
        return MinioOrigin(
            host=self.minio_endpoint,
            port=self.minio_port,
            secure=self.minio_secure,
        )
    @field_validator("allowed_types", mode="before")
    @classmethod
    def _coerce_allowed_types(cls, raw):
        return _parse_string_list(raw)

    @field_validator("ext_by_type", mode="before")
    @classmethod
    def _coerce_ext_by_type(cls, raw):
        if isinstance(raw, dict):
            return {str(k): str(v) for k, v in raw.items()}
        return _parse_mapping(str(raw))

    @property
    def minio_public(self) -> MinioOrigin:
        """Origin embedded in presigned URLs.

        Each component falls back to its internal counterpart independently, so a
        pre-split configuration (public values unset) keeps signing exactly what
        it signed before.
        """
        return MinioOrigin(
            host=self.minio_public_endpoint or self.minio_endpoint,
            port=self.minio_public_port or self.minio_port,
            secure=(
                self.minio_secure
                if self.minio_public_secure is None
                else self.minio_public_secure
            ),
        )

settings = Settings()
