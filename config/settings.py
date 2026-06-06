from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Default values are used if not found in environment or .env
    DB_HOST: str = "127.0.0.1"
    DB_PORT: int = 3306
    DB_USER: str = "root"
    DB_PASSWORD: str = "Zcj1028..."
    DB_NAME: str = "test_db"
    
    # SQLAlchemy Core / DB Engine Config
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_ECHO: bool = False

    # Message Broker (Redis) Config
    REDIS_HOST: str = "127.0.0.1"
    REDIS_PORT: int = 6379
    REDIS_QUEUE_NAME: str = "data_import_queue"

    # Worker Settings
    WORKER_BATCH_SIZE: int = 5000

    # Auto-load from .env file
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding='utf-8', extra="ignore")

    @property
    def database_url(self) -> str:
        return f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}?charset=utf8mb4"

settings = Settings()
