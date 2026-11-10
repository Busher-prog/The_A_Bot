"""One-off broadcast of the photo-album message to everyone who came by a QR code.

On the server (from /opt/the-a-bot):
  sudo -u thea .venv/bin/python -m bot.broadcast ybc_lisbon            # how many people, nothing is sent
  sudo -u thea .venv/bin/python -m bot.broadcast ybc_lisbon --preview  # send only to the manager
  sudo -u thea .venv/bin/python -m bot.broadcast ybc_lisbon --send     # send to everyone

Safe to re-run: people who already got it are skipped (broadcast_<source>.jsonl).
"""

import argparse
import asyncio
import json
import logging

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter

from bot.config import Settings
from bot.content import load_content
from bot.keyboards import photos_menu
from bot.storage import Storage

PAUSE = 0.05  # ~20 messages per second, below Telegram's limit


def already_sent(storage: Storage, log_name: str) -> set[int]:
    path = storage.dir / log_name
    if not path.exists():
        return set()
    done = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if entry.get("result") in ("ok", "blocked"):
            done.add(entry["chat_id"])
    return done


async def run(source: str, mode: str) -> None:
    settings = Settings()
    content = load_content(settings.texts_path)
    storage = Storage(settings.data_dir)
    screen, _ = content.screen_by_start_param(source)
    log_name = f"broadcast_{source}.jsonl"

    recipients = storage.users_from(source)
    todo = [uid for uid in recipients if uid not in already_sent(storage, log_name)]
    print(f"Пришли по «{source}»: {len(recipients)}; ещё не получили: {len(todo)}")
    if mode == "count":
        print("Ничего не отправлено. --preview — себе, --send — всем.")
        return

    bot = Bot(settings.bot_token.get_secret_value(),
              default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    markup = photos_menu(content, screen)
    try:
        if mode == "preview":
            await bot.send_message(settings.managers_chat_id, content.photos.text, reply_markup=markup)
            print(f"Превью отправлено в чат {settings.managers_chat_id}.")
            return
        ok = blocked = failed = 0
        for uid in todo:
            while True:
                try:
                    await bot.send_message(uid, content.photos.text, reply_markup=markup)
                    result, ok = "ok", ok + 1
                except TelegramRetryAfter as e:
                    await asyncio.sleep(e.retry_after + 1)
                    continue
                except TelegramForbiddenError:
                    result, blocked = "blocked", blocked + 1
                except Exception as e:  # noqa: BLE001 - report and go on
                    result, failed = f"error: {e}", failed + 1
                break
            storage.append(log_name, {"chat_id": uid, "result": result})
            await asyncio.sleep(PAUSE)
        print(f"Готово: доставлено {ok}, заблокировали бота {blocked}, ошибок {failed}.")
    finally:
        await bot.session.close()


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("source", help="start_param of the QR code, e.g. ybc_lisbon")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--preview", action="store_true", help="send only to the manager")
    g.add_argument("--send", action="store_true", help="send to everyone")
    a = p.parse_args()
    asyncio.run(run(a.source, "send" if a.send else "preview" if a.preview else "count"))


if __name__ == "__main__":
    main()
