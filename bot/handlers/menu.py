"""Start screens (incl. QR deep links), topics, photos, info commands."""

import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.config import Settings
from bot.content import Content
from bot.formatting import event_card, new_lead_card
from bot.handlers import bingo, calculator, forms
from bot.keyboards import photos_menu, start_menu, topic_menu
from bot.notify import to_manager
from bot.storage import Storage, now_iso

log = logging.getLogger(__name__)

router = Router(name="menu")
router.message.filter(F.chat.type == "private")


async def show_screen(message: Message, content: Content, screen: str) -> None:
    key, item = content.screen(screen)
    await message.answer(item.text, reply_markup=start_menu(content, key))


@router.message(CommandStart())
async def start(message: Message, command: CommandObject, state: FSMContext, bot: Bot,
                content: Content, settings: Settings, db: Storage) -> None:
    await state.clear()
    user = message.from_user
    key, screen = content.screen_by_start_param(command.args)
    if screen.start_param:  # came by a QR code / link: remember where from
        db.touch_user(user, source=screen.start_param, source_label=screen.label,
                           source_at=now_iso())
        event = "deeplink_start"
    else:
        db.touch_user(user)
        event = "plain_start"
    db.append("inbox.jsonl", {"event": event, "source": screen.start_param or "direct",
                                   "chat_id": message.chat.id, "user_id": user.id,
                                   "username": user.username, "first_name": user.first_name})
    await show_screen(message, content, key)
    if screen.start_param:
        text, markup = new_lead_card(screen.label, user, message.chat.id, db)
        await to_manager(bot, settings, message.chat.id, text, markup)


@router.message(Command("myid"))
async def my_id(message: Message) -> None:
    await message.answer(f"Chat ID: <code>{message.chat.id}</code>")


@router.message(Command("services", "jurisdictions", "contact", "help"))
async def info_command(message: Message, command: CommandObject, content: Content) -> None:
    await message.answer(content.commands_text[command.command], disable_web_page_preview=True)


# --- inline buttons: "src:<screen>:<action>" ----------------------------------------

def parse_src(data: str) -> tuple[str, str] | None:
    parts = data.split(":")
    return (parts[1], parts[2]) if len(parts) == 3 and parts[0] == "src" else None


@router.callback_query(F.data.startswith("src:"))
async def src_button(callback: CallbackQuery, state: FSMContext, bot: Bot, content: Content,
                     settings: Settings, db: Storage) -> None:
    parsed = parse_src(callback.data)
    if not parsed:
        await callback.answer()
        return
    screen, action = parsed
    screen, screen_cfg = content.screen(screen)
    user, chat_id = callback.from_user, callback.message.chat.id
    db.append("inbox.jsonl", {"event": "source_button", "source": screen, "action": action,
                                   "chat_id": chat_id, "user_id": user.id,
                                   "username": user.username})
    group = content.group_of(screen)
    await state.set_state(None)  # a menu button ends any unfinished question/story

    if action == "bingo":
        await bingo.open_card(callback.message, user, state, content, db)
    elif action == "calc":
        await calculator.begin(callback.message, state)
    elif action in ("consult", "lead_start") or action.startswith("form_"):
        form = {"consult": "consult", "lead_start": "hayat"}.get(action, action[5:])
        await forms.begin(callback.message, state, content, form)
    elif action in ("photos", "seg_collection"):  # the old raffle button now opens the photos
        await callback.message.answer(content.photos.text, reply_markup=photos_menu(content, screen))
    elif action.startswith("seg_") and action[4:] in group.topics:
        topic = group.topics[action[4:]]
        db.touch_user(user, last_topic=topic.label, **{f"{screen}_segment": action[4:],
                                                            f"{screen}_segment_label": topic.label})
        await callback.message.answer(topic.text, reply_markup=topic_menu(content, screen))
        text, markup = event_card(screen_cfg.lead_title, f"выбрал тему: {topic.label}",
                                  user, chat_id, db)
        await to_manager(bot, settings, chat_id, text, markup)
    elif action == "discuss":
        await callback.message.answer(group.discuss_text or content.replies.ack_work)
        text, markup = event_card(screen_cfg.lead_title, "натиснув «написати менеджеру»",
                                  user, chat_id, db)
        await to_manager(bot, settings, chat_id, text, markup)
    else:  # "menu" and anything unknown: back to the start screen
        await show_screen(callback.message, content, screen)
    await callback.answer()
