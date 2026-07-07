from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"
    database_url: str = "sqlite:///./matcha-dev.db"
    app_secret: str = "development-only-secret-change-me"
    web_origin: str = "http://localhost:5173"
    cookie_secure: bool = False
    json_logs: bool = False
    session_days: int = 14
    reservation_minutes: int = 30
    reservation_sweep_interval_seconds: int = 300
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    media_bucket: str = "matcha-demo-media"
    aws_region: str = "ap-southeast-1"
    shipping_countries: list[str] = Field(default_factory=lambda: ["SG", "MY", "JP", "AU", "NZ"])
    # There is no in-product admin signup flow; admin accounts are provisioned
    # out-of-band. Setting both of these makes `python -m app.seed` idempotently
    # create-or-promote that account to Role.ADMIN. Leave unset to skip (default
    # dev/test runs have neither set).
    admin_email: str | None = None
    admin_password: str | None = None

    @field_validator("shipping_countries", mode="before")
    @classmethod
    def parse_countries(cls, value: object) -> object:
        if isinstance(value, str):
            return [part.strip().upper() for part in value.split(",") if part.strip()]
        return value

    @field_validator("app_secret")
    @classmethod
    def validate_secret(cls, value: str, info) -> str:
        if info.data.get("environment") not in {"development", "test"} and len(value) < 32:
            raise ValueError("APP_SECRET must contain at least 32 characters")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
