"""Journals and the list of known users, stored as files in DATA_DIR.

The formats match the previous bot (/opt/the-a-bd), so its history continues
in the same files: inbox.jsonl, sent.jsonl, *_leads.jsonl,
calculator_completions.jsonl and state.json["known_users"].
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aiogram.types import User

log = logging.getLogger(__name__)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Storage:
    def __init__(self, data_dir: Path) -> None:
        self.dir = data_dir
        self.dir.mkdir(parents=True, exist_ok=True)
        self._state_file = self.dir / "state.json"
        self._state = self._load_state()

    # --- journals ------------------------------------------------------------

    def append(self, filename: str, entry: dict[str, Any]) -> None:
        entry = {"ts": now_iso(), **entry}
        try:
            with (self.dir / filename).open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError:
            log.exception("cannot write %s", filename)

    # --- known users -----------------------------------------------------------

    def _load_state(self) -> dict[str, Any]:
        try:
            return json.loads(self._state_file.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, ValueError):
            log.exception("cannot read state.json, starting with an empty one")
            return {}

    def _save_state(self) -> None:
        tmp = self._state_file.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(self._state, indent=2, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, self._state_file)
        except OSError:
            log.exception("cannot write state.json")

    def get_state(self, key: str) -> Any:
        return self._state.get(key)

    def set_state(self, key: str, value: Any) -> None:
        self._state[key] = value
        self._save_state()

    @property
    def users(self) -> dict[str, dict[str, Any]]:
        return self._state.setdefault("known_users", {})

    def user(self, user_id: int) -> dict[str, Any]:
        return self.users.get(str(user_id), {})

    def touch_user(self, user: User, **fields: Any) -> dict[str, Any]:
        record = self.users.setdefault(str(user.id), {"first_seen": now_iso()})
        record["username"] = user.username
        record.update(fields)
        self._save_state()
        return record

    def users_from(self, start_param: str) -> list[int]:
        return [int(uid) for uid, u in self.users.items() if u.get("source") == start_param]
