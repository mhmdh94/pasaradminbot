from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional
import os


class Settings(BaseSettings):
    BOT_TOKEN: str
    ADMIN_ID: int

    CARD_NUMBER: str = "6037-XXXX-XXXX-XXXX"
    CARD_OWNER: str = "نام صاحب کارت"

    # Webhook (optional)
    WEBHOOK_HOST: Optional[str] = None
    WEBHOOK_PATH: str = "/webhook"
    WEBHOOK_PORT: int = 8080

    # Paths
    BASE_DIR: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    DB_PATH: str = os.path.join(BASE_DIR, "data", "bot.db")

    # Backup
    BACKUP_HOUR: int = 3
    BACKUP_MINUTE: int = 0

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()