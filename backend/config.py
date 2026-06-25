from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """Application configuration settings, loaded from environment variables."""
    
    postgres_user: str = Field(default="neuroflow", description="PostgreSQL database user")
    postgres_password: str = Field(default="password", description="PostgreSQL database password")
    postgres_host: str = Field(default="postgres", description="PostgreSQL database hostname")
    postgres_port: int = Field(default=5432, description="PostgreSQL database port")
    postgres_db: str = Field(default="neuroflow", description="PostgreSQL database name")

    redis_password: str = Field(default="password", description="Redis server password")
    redis_host: str = Field(default="redis", description="Redis server hostname")
    redis_port: int = Field(default=6379, description="Redis server port")

    mlflow_uri: str = Field(default="http://mlflow:5000", description="URI for the MLflow tracking server")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def database_url(self) -> str:
        """Constructs the asyncpg database URL."""
        return f"postgresql://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"

settings = Settings()
