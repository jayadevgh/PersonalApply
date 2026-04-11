from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    worker_name: str = "worker-1"
    backend_base_url: str = "http://localhost:8000"
    heartbeat_seconds: int = 30
    claim_poll_seconds: int = 10

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
