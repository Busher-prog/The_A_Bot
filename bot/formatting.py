"""Cards sent to the manager, and finding the client in a manager's reply.

Every card contains "chat_id: <id>". The manager answers a client by replying
(Telegram "Reply") to the card; the bot reads the id from the quoted card.
Cards sent by the previous bot use the same line, so replies to them work too.
"""

import re
from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

from aiogram.types import InlineKeyboardMarkup, User

from bot.content import Content, Form
from bot.keyboards import contact_url_button
from bot.storage import Storage

_CHAT_ID = re.compile(r"(?:chat_id:\s*|#id)(-?\d+)")


def is_working_hours(c: Content, now: datetime | None = None) -> bool:
    now = now or datetime.now(ZoneInfo(c.settings.timezone))
    return c.settings.work_start <= now.hour < c.settings.work_end


def contact_block(user: User, chat_id: int, storage: Storage) -> str:
    source = storage.user(user.id).get("source_label")
    lines = [f"Джерело: {escape(source)}"] if source else []
    lines += [
        f"Имя: {escape(user.full_name or '-')}",
        f"Telegram: @{user.username}" if user.username else "Telegram: username не задан",
        f"user_id: {user.id}",
        f"chat_id: {chat_id}",
    ]
    if user.username:
        lines.append("\n✍️ Можна написати напряму - кнопка нижче, діалог піде з вашого акаунта.")
    else:
        lines.append("\n⚠️ У клієнта немає @username - прямо написати не вийде. "
                     "Відповідайте через Reply на це повідомлення, бот передасть.")
    return "\n".join(lines)


Card = tuple[str, InlineKeyboardMarkup | None]


def new_lead_card(label: str, user: User, chat_id: int, storage: Storage) -> Card:
    text = (f"🎯 Новый лид · {escape(label)}\n\n{contact_block(user, chat_id, storage)}\n\n"
            "Открыл бота по deep-link, выбирает тему.")
    return text, contact_url_button(user.username)


def event_card(title: str, summary: str, user: User, chat_id: int, storage: Storage) -> Card:
    text = f"➡️ {escape(title)}: {escape(summary)}\n\n{contact_block(user, chat_id, storage)}"
    return text, contact_url_button(user.username)


def message_card(c: Content, user: User, chat_id: int, body_html: str, storage: Storage) -> Card:
    now = datetime.now(ZoneInfo(c.settings.timezone))
    marker = "🟢 рабочее время" if is_working_hours(c, now) else "🌙 вне рабочих часов"
    topic = storage.user(user.id).get("last_topic")
    text = (
        "🔔 Входящее в боте The A\n\n"
        f"{contact_block(user, chat_id, storage)}\n"
        + (f"Тема: {escape(topic)}\n" if topic else "")
        + f"Язык: {user.language_code or '-'}\n"
        f"Когда: {now:%H:%M %d.%m} · {marker}\n\n"
        f"Сообщение:\n{body_html or '(вложение ниже)'}\n\n"
        "💬 Ответить через бота - Reply на это сообщение."
    )
    return text, contact_url_button(user.username)


def form_card(form: Form, answers: dict[str, str], user: User, chat_id: int,
              storage: Storage) -> Card:
    record = storage.user(user.id)
    lines = [f"<b>{escape(form.lead_title)}</b>", ""]
    if record.get("last_topic"):
        lines.append(f"<b>Тема:</b> {escape(record['last_topic'])}")
    lines += [f"<b>{escape(s.label)}:</b> {escape(answers.get(s.key, '-'))}" for s in form.steps]
    lines += [f"<b>{escape(k)}:</b> {escape(v)}" for k, v in form.extra.items()]
    lines += ["", contact_block(user, chat_id, storage)]
    return "\n".join(lines), contact_url_button(user.username)


def extract_client_id(text: str | None) -> int | None:
    if not text:
        return None
    match = _CHAT_ID.search(text)
    return int(match.group(1)) if match else None
