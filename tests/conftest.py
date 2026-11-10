"""Test helpers: a fake Telegram connection that records what the bot sends."""

import datetime
from pathlib import Path
from typing import Any

import pytest
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.base import BaseSession
from aiogram.enums import ParseMode
from aiogram.methods import TelegramMethod
from aiogram.types import CallbackQuery, Chat, Message, MessageId, Update, User

from bot.__main__ import build_dispatcher
from bot.config import Settings
from bot.content import load_content
from bot.handlers import calculator, forms, manager, menu, posts
from bot.storage import Storage

ROOT = Path(__file__).resolve().parent.parent
BOT_ID = 42
MANAGER = User(id=7443798955, is_bot=False, first_name="Ksenia", username="Businessmanager_THE_A")
CLIENT = User(id=777, is_bot=False, first_name="Olena", username="olena", language_code="uk")


class RecordingSession(BaseSession):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[TelegramMethod] = []
        self._next_id = 1000

    async def make_request(self, bot: Bot, method: TelegramMethod, timeout: Any = None) -> Any:
        self.calls.append(method)
        name = type(method).__name__
        if name in {"SendMessage", "SendPhoto"}:
            self._next_id += 1
            return Message(message_id=self._next_id, date=datetime.datetime.now(),
                           chat=Chat(id=0, type="private"),
                           from_user=User(id=BOT_ID, is_bot=True, first_name="bot"),
                           text=getattr(method, "text", None))
        if name == "CopyMessage":
            self._next_id += 1
            return MessageId(message_id=self._next_id)
        return True

    async def close(self) -> None:
        pass

    async def stream_content(self, *args: Any, **kwargs: Any):  # pragma: no cover
        raise NotImplementedError

    def sent(self, method_name: str = "SendMessage") -> list[TelegramMethod]:
        return [c for c in self.calls if type(c).__name__ == method_name]

    def to(self, chat_id: int) -> list[TelegramMethod]:
        return [c for c in self.sent() if c.chat_id == chat_id]


@pytest.fixture
def content():
    return load_content(ROOT / "content" / "texts.yaml")


@pytest.fixture
def env(content, tmp_path):
    session = RecordingSession()
    bot = Bot("42:TEST", session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    settings = Settings(bot_token="42:TEST", managers_chat_id=MANAGER.id, data_dir=tmp_path)
    storage = Storage(tmp_path)
    dp = build_dispatcher(content, settings, storage)
    yield dp, bot, session, storage
    for r in (menu.router, calculator.router, posts.router, forms.router, manager.router):
        r._parent_router = None


_ids = iter(range(1, 10**6))


def msg(text: str | None = None, *, user: User = CLIENT, reply_to: Message | None = None,
        **extra) -> Update:
    n = next(_ids)
    return Update(update_id=n, message=Message(
        message_id=n, date=datetime.datetime.now(), chat=Chat(id=user.id, type="private"),
        from_user=user, text=text, reply_to_message=reply_to, **extra))


def press(data: str, *, user: User = CLIENT) -> Update:
    n = next(_ids)
    m = Message(message_id=n, date=datetime.datetime.now(), chat=Chat(id=user.id, type="private"),
                from_user=User(id=BOT_ID, is_bot=True, first_name="bot"), text="menu")
    return Update(update_id=n, callback_query=CallbackQuery(
        id=str(n), from_user=user, chat_instance="x", message=m, data=data))


def bot_message(text: str, chat_id: int = MANAGER.id) -> Message:
    return Message(message_id=next(_ids), date=datetime.datetime.now(),
                   chat=Chat(id=chat_id, type="private"),
                   from_user=User(id=BOT_ID, is_bot=True, first_name="bot"), text=text)


def labels(method) -> list[str]:
    return [row[0].text for row in method.reply_markup.inline_keyboard]
