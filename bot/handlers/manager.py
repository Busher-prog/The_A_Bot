"""Two-way chat between clients and managers.

- Any free-form message a client sends is forwarded to the managers chat.
- A manager answers by replying (Telegram "Reply") to that message; the bot
  delivers the answer to the client.
"""

import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.config import Settings
from bot.content import Content
from bot.formatting import client_message_header, extract_client_id
from bot.keyboards import Menu, main_menu

log = logging.getLogger(__name__)

router = Router(name="manager")


@router.callback_query(Menu.filter(F.action == "manager"))
async def write_manager(callback: CallbackQuery, callback_data: Menu, state: FSMContext,
                        content: Content) -> None:
    item = content.topic(callback_data.topic or "")
    if item:
        await state.update_data(topic=item.button)
    await callback.message.answer(content.manager.prompt)
    await callback.answer()


def _is_command(message: Message) -> bool:
    return (message.text or "").startswith("/")


@router.message(F.chat.type == "private", StateFilter(None), _is_command)
async def unknown_command(message: Message, content: Content) -> None:
    """Old commands (/services, /calculator, ...) or typos: show the menu."""
    await message.answer(content.welcome, reply_markup=main_menu(content))


@router.message(F.chat.type == "private", StateFilter(None), lambda m: not _is_command(m))
async def client_message(message: Message, state: FSMContext, bot: Bot, content: Content,
                         settings: Settings) -> None:
    if not settings.managers_chat_id:
        log.warning("MANAGERS_CHAT_ID is not set; message from %s dropped", message.from_user.id)
        await message.answer(content.manager.sent)
        return

    topic = (await state.get_data()).get("topic")
    header = client_message_header(message.from_user, topic)
    if message.text:
        await bot.send_message(settings.managers_chat_id, f"{header}\n\n{message.html_text}")
    else:
        # Photos, files, voice notes: header first, attachment as a reply to it.
        sent = await bot.send_message(settings.managers_chat_id, header)
        await message.copy_to(settings.managers_chat_id, reply_to_message_id=sent.message_id)
    await message.answer(content.manager.sent)


@router.message(F.reply_to_message)
async def manager_reply(message: Message, bot: Bot, settings: Settings) -> None:
    if settings.managers_chat_id is None or message.chat.id != settings.managers_chat_id:
        return
    original = message.reply_to_message
    if original.from_user is None or original.from_user.id != bot.id:
        return
    client_id = extract_client_id(original.text or original.caption)
    if client_id is None:
        # Replying to a forwarded attachment: look one level up for the header.
        parent = original.reply_to_message
        client_id = extract_client_id(parent.text if parent else None)
    if client_id is None:
        await message.reply("⚠️ Не знайшов клієнта. Відповідайте на повідомлення з #id.")
        return

    try:
        await message.copy_to(client_id)
    except (TelegramForbiddenError, TelegramBadRequest) as e:
        await message.reply(f"⚠️ Не вдалося доставити: {e.message}")
        return
    await message.reply("✅ Надіслано клієнту")
