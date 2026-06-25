from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    postgres_user: str = "neuroflow"
    postgres_password: str = "password"
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_db: str = "neuroflow"

    redis_password: str = "password"
    redis_host: str = "redis"
    redis_port: int = 6379

    mlflow_uri: str = "http://mlflow:5000"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def database_url(self) -> str:
        return f"postgresql://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"

settings = Settings()
