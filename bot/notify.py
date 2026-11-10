"""Sending cards to the manager."""

import logging

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup

from bot.config import Settings

log = logging.getLogger(__name__)


async def to_manager(bot: Bot, settings: Settings, client_chat_id: int,
                     text: str, markup: InlineKeyboardMarkup | None = None,
                     parse_mode: str | None = "HTML") -> int | None:
    """Send a card to the manager; returns its message id. Skips the manager's own actions."""
    chat = settings.managers_chat_id
    if not chat:
        log.warning("MANAGERS_CHAT_ID is not set; card not sent:\n%s", text)
        return None
    if client_chat_id == chat:
        return None
    try:
        sent = await bot.send_message(chat, text, reply_markup=markup, parse_mode=parse_mode,
                                      disable_web_page_preview=True)
        return sent.message_id
    except Exception:
        log.exception("cannot send card to manager")
        return None
