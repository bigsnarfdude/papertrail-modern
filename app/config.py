"""
Configuration management for PaperTrail Modern
"""
import os
from typing import List
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings"""

    # Application
    APP_NAME: str = "PaperTrail Modern"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    HOST: str = "0.0.0.0"
    PORT: int = 5000

    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str = ""
    REDIS_URL: str = ""

    # HyperLogLog Settings
    HLL_ERROR_RATE: float = 0.02  # 2% error rate

    # Bloom Filter Settings
    BLOOM_CAPACITY: int = 1_000_000  # 1M items
    BLOOM_ERROR_RATE: float = 0.001  # 0.1% false positive rate

    # Count-Min Sketch Settings
    CMS_WIDTH: int = 1000
    CMS_DEPTH: int = 5

    # Time Windows
    RETENTION_HOURLY: int = 24 * 7  # 7 days
    RETENTION_DAILY: int = 90  # 90 days
    RETENTION_WEEKLY: int = 52  # 52 weeks
    RETENTION_MONTHLY: int = 24  # 24 months

    # API Settings
    API_PREFIX: str = "/api/v1"
    CORS_ORIGINS: List[str] = ["*"]

    # Event Processing
    MAX_BATCH_SIZE: int = 1000
    WORKER_THREADS: int = 4

    # SSE Settings
    SSE_HEARTBEAT_INTERVAL: int = 30  # seconds

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    def get_redis_url(self) -> str:
        """Get Redis connection URL"""
        if self.REDIS_URL:
            return self.REDIS_URL

        auth = f":{self.REDIS_PASSWORD}@" if self.REDIS_PASSWORD else ""
        return f"redis://{auth}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"


# Global settings instance
settings = Settings()
