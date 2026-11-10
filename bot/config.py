"""Runtime settings, read from environment variables (or a local .env file)."""

from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    bot_token: SecretStr
    # Chat (person or group) where client messages and consultation requests arrive.
    # Send /myid to the bot from that chat to find the number.
    managers_chat_id: int | None = None
    texts_path: Path = ROOT / "content" / "texts.yaml"
    log_level: str = "INFO"
