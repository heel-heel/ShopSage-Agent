from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "ShopSage"
    database_url: str = "sqlite:///./shopsage.db"
    chroma_path: str = "./.chroma"
    chroma_host: str | None = None
    jwt_secret: str = "dev-only-change-me"
    admin_email: str = "merchant@shopsage.demo"
    admin_password: str = "demo-admin-password"
    model_provider: str = "deterministic"
    model_name: str = "rule-based-demo"
    model_api_key: str | None = None
    model_api_base: str | None = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
