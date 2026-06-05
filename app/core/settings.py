from pathlib import Path
from pydantic import Field

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
ENV_PATH = ROOT_DIR / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_PATH,
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
    contractor_nit: str         = Field(..., alias="CONTRACTOR_CLIENT")
    contractor_contact: str     = Field(..., alias="CONTRACTOR_CONTACT") 
    contractor_phone: str       = Field(..., alias="CONTRACTOR_PHONE")  

    # Postgres
    pg_host: str                = Field(..., alias="DB_HOST")
    pg_port: int                = Field(5432, alias="DB_PORT")
    pg_user: str                = Field(..., alias="DB_USER")
    pg_password: str            = Field(..., alias="DB_PASSWORD")
    pg_db: str                  = Field(..., alias="DB_NAME")

    # MinIO
    minio_endpoint: str         = Field(..., alias="MINIO_ENDPOINT")
    minio_port: int             = Field(9000, alias="MINIO_PORT")
    minio_access_key: str       = Field(..., alias="MINIO_ACCESS_KEY")
    minio_secret_key: str       = Field(..., alias="MINIO_SECRET_KEY")
    minio_secure: bool          = Field(False, alias="MINIO_SECURE")
    minio_default_bucket: str   = Field("company-uploads", alias="MINIO_DEFAULT_BUCKET")
    base_object_path: str       = Field("Maintenances", alias="BASE_OBJECT_PATH")
    ext_by_type: dict[str, str] = Field(..., alias="EXT_BY_TYPE")
    allowed_types: list[str]    = Field(..., alias="ALLOWED_TYPES")
    presigned_ttl: int          = Field(3600, alias="PRESIGNED_TTL")  # 1 hour


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

settings = Settings()