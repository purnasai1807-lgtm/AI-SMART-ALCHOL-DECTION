from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./data/interlock.db"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    alcohol_threshold: float = 0.02
    attestation_max_age_seconds: int = 300
    device_encryption_key: str = ""
    cors_origins: str = "http://localhost:3000"
    environment: str = "test"
    login_rate_limit: int = 10
    login_rate_window_seconds: int = 60
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @model_validator(mode="after")
    def secure_production(self):
        if self.environment.lower() in ("production", "prod") and self.jwt_secret == "change-me-in-production":
            raise ValueError("JWT_SECRET must be changed in production")
        if self.environment.lower() in ("production", "prod") and not self.device_encryption_key:
            raise ValueError("DEVICE_ENCRYPTION_KEY must be configured in production")
        return self


settings = Settings()
