from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://personalapply:personalapply@localhost:5432/personalapply"
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    lease_minutes: int = 10

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
