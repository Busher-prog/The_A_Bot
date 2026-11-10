"""Test helpers: a fake Telegram connection that records what the bot sends."""

import datetime
from pathlib import Path
from typing import Any

import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.base import BaseSession
from aiogram.enums import ParseMode
from aiogram.methods import TelegramMethod
from aiogram.types import Chat, Message, Update, User

from bot.config import Settings
from bot.content import load_content
from bot.handlers import consultation, manager, menu

ROOT = Path(__file__).resolve().parent.parent
BOT_ID = 42
MANAGERS_CHAT = -100500
CLIENT = User(id=777, is_bot=False, first_name="Olena", username="olena")


class RecordingSession(BaseSession):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[TelegramMethod] = []
        self._next_id = 1000

    async def make_request(self, bot: Bot, method: TelegramMethod, timeout: Any = None) -> Any:
        self.calls.append(method)
        name = type(method).__name__
        if name in {"SendMessage", "CopyMessage"}:
            self._next_id += 1
            if name == "CopyMessage":
                from aiogram.types import MessageId
                return MessageId(message_id=self._next_id)
            return Message(
                message_id=self._next_id,
                date=datetime.datetime.now(),
                chat=Chat(id=method.chat_id, type="private"),
                from_user=User(id=BOT_ID, is_bot=True, first_name="bot"),
                text=method.text,
            )
        return True

    async def close(self) -> None:
        pass

    async def stream_content(self, *args: Any, **kwargs: Any):  # pragma: no cover
        raise NotImplementedError

    def sent(self, method_name: str) -> list[TelegramMethod]:
        return [c for c in self.calls if type(c).__name__ == method_name]


@pytest.fixture
def content():
    return load_content(ROOT / "content" / "texts.yaml")


@pytest.fixture
def env(content):
    session = RecordingSession()
    bot = Bot("42:TEST", session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    settings = Settings(bot_token="42:TEST", managers_chat_id=MANAGERS_CHAT)
    dp = Dispatcher(content=content, settings=settings)
    dp.include_routers(menu.router, consultation.router, manager.router)
    yield dp, bot, session
    # routers are module-level singletons; detach so the next test can re-include them
    for r in (menu.router, consultation.router, manager.router):
        r._parent_router = None


_update_id = 0


def make_message(text: str | None = None, *, user: User = CLIENT, chat_id: int | None = None,
                 chat_type: str = "private", reply_to: Message | None = None, **extra) -> Update:
    global _update_id
    _update_id += 1
    msg = Message(
        message_id=_update_id,
        date=datetime.datetime.now(),
        chat=Chat(id=chat_id if chat_id is not None else user.id, type=chat_type),
        from_user=user,
        text=text,
        reply_to_message=reply_to,
        **extra,
    )
    return Update(update_id=_update_id, message=msg)


def make_callback(data: str, *, user: User = CLIENT) -> Update:
    global _update_id
    _update_id += 1
    from aiogram.types import CallbackQuery
    msg = Message(message_id=1, date=datetime.datetime.now(),
                  chat=Chat(id=user.id, type="private"),
                  from_user=User(id=BOT_ID, is_bot=True, first_name="bot"), text="menu")
    return Update(update_id=_update_id,
                  callback_query=CallbackQuery(id=str(_update_id), from_user=user,
                                               chat_instance="x", message=msg, data=data))
