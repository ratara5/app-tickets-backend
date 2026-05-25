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
    minio_default_bucket: str   = Field("appsheet-uploads", alias="MINIO_DEFAULT_BUCKET")

    # Disk
    chunk_dir: str             = Field("/tmp/upload_chunks", alias="CHUNK_DIR")

    #
    jwt_secret: str            = Field(..., alias="JWT_SECRET")

    @property
    def pg_dsn(self):
        return f"postgresql://{self.pg_user}:{self.pg_password}@{self.pg_host}:{self.pg_port}/{self.pg_db}"

settings = Settings()