from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str

    minio_endpoint: str = "localhost:9000"
    minio_public_endpoint: str | None = None
    minio_access_key: str = "minio"
    minio_secret_key: str = "minio123"
    minio_bucket: str = "hr-learning"
    minio_secure: bool = False

    presigned_expires_seconds: int = 3600
    max_upload_size_mb: int = 100

    auto_create_user_by_id_max: bool = False

    bootstrap_admin_id_max: str | None = None
    bootstrap_admin_full_name: str = "Administrator"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()