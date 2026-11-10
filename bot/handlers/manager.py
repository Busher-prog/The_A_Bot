"""Client ↔ manager.

- Anything a client writes (not a command, not inside a questionnaire) gets an
  automatic reply (working hours aware) and is sent to the manager as a card.
- The manager answers with Telegram "Reply" on a card: the bot delivers the answer.
- The manager's other messages: edit feedback for posts, photos for Claude.
"""

import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.config import Settings
from bot.content import Content
from bot.formatting import extract_client_id, is_working_hours, message_card
from bot.handlers.menu import show_screen
from bot.handlers.posts import capture_edit_feedback, save_manager_photo
from bot.notify import to_manager
from bot.storage import Storage

log = logging.getLogger(__name__)

router = Router(name="manager")


def _from_manager(message: Message, settings: Settings) -> bool:
    return settings.managers_chat_id is not None and message.chat.id == settings.managers_chat_id


def _is_command(message: Message) -> bool:
    return (message.text or "").startswith("/")


@router.message(_from_manager, F.reply_to_message, lambda m: not _is_command(m))
async def manager_reply(message: Message, bot: Bot, db: Storage) -> None:
    original = message.reply_to_message
    client_id = extract_client_id(original.text or original.caption)
    if client_id is None and original.reply_to_message:  # reply to an attachment under a card
        parent = original.reply_to_message
        client_id = extract_client_id(parent.text or parent.caption)
    if client_id is None or original.from_user is None or original.from_user.id != bot.id:
        if await capture_edit_feedback(message, db):
            return
        await message.reply("⚠️ Не знайшов клієнта. Відповідайте Reply на картку з chat_id.")
        return
    try:
        await message.copy_to(client_id)
    except (TelegramForbiddenError, TelegramBadRequest) as e:
        await message.reply(f"⚠️ Не смог отправить клиенту (id {client_id}): {e.message}")
        return
    db.append("sent.jsonl", {"chat_id": client_id, "user_id": client_id,
                                  "text": message.text or message.caption or "(вложение)",
                                  "result": True, "via": "master_reply"})
    await message.reply(f"✓ Отправлено клиенту (id {client_id}).")


@router.message(_from_manager, lambda m: not _is_command(m))
async def manager_message(message: Message, bot: Bot, db: Storage) -> None:
    if await capture_edit_feedback(message, db):
        return
    if await save_manager_photo(message, bot, db):
        return
    await message.reply("ℹ️ Щоб відповісти клієнту, натисніть «Відповісти» (Reply) на його картку.")


@router.message(F.chat.type == "private", StateFilter(None), _is_command)
async def unknown_command(message: Message, state: FSMContext, content: Content,
                          db: Storage) -> None:
    """Typos and commands that no longer exist: show the menu the person came from."""
    source = db.user(message.from_user.id).get("source")
    key, _ = content.screen_by_start_param(source)
    await show_screen(message, content, key)


@router.message(F.chat.type == "private", StateFilter(None))
async def client_message(message: Message, bot: Bot, content: Content, settings: Settings,
                         db: Storage) -> None:
    user = message.from_user
    text = message.text or message.caption or ""
    db.touch_user(user)
    db.append("inbox.jsonl", {
        "chat_id": message.chat.id, "user_id": user.id, "username": user.username,
        "first_name": user.first_name, "last_name": user.last_name,
        "language_code": user.language_code, "text": text,
    })
    ack = content.replies.ack_work if is_working_hours(content) else content.replies.ack_off
    await message.answer(ack)
    db.append("sent.jsonl", {"chat_id": message.chat.id, "user_id": user.id,
                                  "text": ack, "result": True})

    body = message.html_text if message.text else (message.html_text if message.caption else "")
    card, markup = message_card(content, user, message.chat.id, body, db)
    card_id = await to_manager(bot, settings, message.chat.id, card, markup)
    if card_id and not message.text:  # photo, file, voice: send it under the card
        await message.copy_to(settings.managers_chat_id, reply_to_message_id=card_id)
