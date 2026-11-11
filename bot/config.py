"""Runtime settings, read from environment variables (or a local .env file)."""

from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    bot_token: SecretStr
    # Manager's chat: client messages, lead cards and form answers arrive here.
    # Send /myid to the bot from that chat to find the number.
    managers_chat_id: int | None = None
    texts_path: Path = ROOT / "content" / "texts.yaml"
    # Journals (inbox, leads) and the list of users. On the server: the old bot's folder.
    data_dir: Path = ROOT / "data"
    # Priority in the bingo cap / t-shirt draw: names separated by ";" (Latin spelling is fine).
    # Kept in .env on the server, not in the public repository.
    bingo_vip: str = ""
    log_level: str = "INFO"

    @property
    def bingo_vip_names(self) -> list[str]:
        return [n.strip() for n in self.bingo_vip.replace(",", ";").split(";") if n.strip()]
