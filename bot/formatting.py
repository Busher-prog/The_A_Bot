"""Messages sent to the managers chat, and parsing replies back to clients.

Each message to managers carries a "#id<user_id>" tag. A manager replies to that
message in Telegram and the bot sends the reply to the client — no database needed.
"""

import re
from html import escape

from aiogram.types import User

_ID_TAG = re.compile(r"#id(\d+)")


def client_line(user: User) -> str:
    name = escape(user.full_name)
    username = f" @{user.username}" if user.username else ""
    return f"👤 {name}{username} · #id{user.id}"


def client_message_header(user: User, topic: str | None) -> str:
    lines = ["📩 <b>Повідомлення від клієнта</b>", client_line(user)]
    if topic:
        lines.append(f"Тема: {escape(topic)}")
    return "\n".join(lines)


def consultation_lead(user: User, name: str, contact: str, question: str) -> str:
    return (
        "🆕 <b>Заявка на консультацію</b>\n"
        f"{client_line(user)}\n\n"
        f"Ім'я: {escape(name)}\n"
        f"Контакт: {escape(contact)}\n"
        f"Питання: {escape(question)}"
    )


def extract_client_id(text: str | None) -> int | None:
    if not text:
        return None
    match = _ID_TAG.search(text)
    return int(match.group(1)) if match else None
