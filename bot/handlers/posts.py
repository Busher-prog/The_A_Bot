"""Post approval for the channel (ported from the previous bot).

Another process (content preparation) appends posts to pending_posts.jsonl and sends
the manager a message with buttons "approve:<id>" / "edit:<id>" / "reject:<id>".
Here we handle those buttons:
- approve: Telegram channel → publish (with image if the file exists);
           other channels (Instagram, LinkedIn…) → mark approved for manual posting;
- edit:    the manager's next message is saved as edit feedback;
- reject:  mark rejected.
Every status change is a new line in pending_posts.jsonl (last line per id wins).
Also: photos the manager sends to the bot are saved to visuals/inbox_photos/,
and edits waiting > 30 min trigger a one-time reminder.
"""

import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, FSInputFile, Message

from bot.config import Settings
from bot.storage import Storage, now_iso

log = logging.getLogger(__name__)

router = Router(name="posts")
POSTS_FILE = "pending_posts.jsonl"
CAPTION_LIMIT = 1024


def load_posts(db: Storage) -> dict[str, dict]:
    posts: dict[str, dict] = {}
    path = db.dir / POSTS_FILE
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                entry = json.loads(line)
                posts[entry["id"]] = entry
            except (ValueError, KeyError):
                continue
    return posts


def save_post(db: Storage, entry: dict) -> None:
    with (db.dir / POSTS_FILE).open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def telegram_chat(channel: str | None) -> str | None:
    ch = (channel or "").strip()
    if ch.startswith("@") and " " not in ch:
        return ch
    if ch.lstrip("-").isdigit():
        return ch
    if ch.lower().startswith("telegram"):
        m = re.search(r"@([A-Za-z0-9_]+)", ch)
        if m:
            return "@" + m.group(1)
    return None


def split_caption(text: str) -> tuple[str, str | None]:
    if len(text) <= CAPTION_LIMIT:
        return text, None
    cut = next((i for i in range(min(1020, len(text)), 700, -1) if text[i - 2:i] == "\n\n"), 1000)
    return text[:cut].rstrip(), text[cut:].lstrip()


def is_manager(user_id: int, settings: Settings) -> bool:
    return settings.managers_chat_id is not None and user_id == settings.managers_chat_id


@router.callback_query(F.data.regexp(r"^(approve|edit|reject):"))
async def post_button(callback: CallbackQuery, bot: Bot, settings: Settings,
                      db: Storage) -> None:
    if not is_manager(callback.from_user.id, settings):
        await callback.answer("Только мастер может одобрять.", show_alert=True)
        return
    action, post_id = callback.data.split(":", 1)
    post = load_posts(db).get(post_id)
    if not post:
        await callback.answer("Пост не найден.", show_alert=True)
        return
    if post.get("status") in ("approved", "rejected") and action != "edit":
        await callback.answer(f"Уже: {post['status']}", show_alert=True)
        return
    chat_id = callback.message.chat.id
    entry = dict(post)

    if action == "reject":
        entry.update(status="rejected", rejected_at=now_iso())
        save_post(db, entry)
        await callback.answer("Отклонено")
        await bot.send_message(chat_id, f"❌ Пост {post_id} отклонён.")
        return

    if action == "edit":
        db.set_state("awaiting_edit_for", post_id)
        await callback.answer("Жду правки текстом")
        await bot.send_message(chat_id, (
            "✏️ Напишите правки следующим сообщением.\n"
            f"Я передам Claude'у, он подготовит новую версию поста {post_id} и снова пришлёт на апруэ."))
        return

    # approve
    target = telegram_chat(post.get("channel"))
    if not target:  # Instagram / Facebook / LinkedIn: published by hand
        entry.update(status="approved_manual", approved_at=now_iso())
        save_post(db, entry)
        await callback.answer("✓ Утверждено для ручной публикации")
        await bot.send_message(chat_id, (
            f"✅ Утверждено: {post.get('channel')}\n\nТекст поста - в сообщении выше.\n"
            "Скопируй и опубликуй вручную в нужную соцсеть."), parse_mode=None)
        return

    await callback.answer("Публикую…")
    try:
        image = post.get("image_path") or ""
        if image and Path(image).exists():
            caption, follow_up = split_caption(post["text"])
            sent = await bot.send_photo(target, FSInputFile(image), caption=caption, parse_mode=None)
            if follow_up:
                await bot.send_message(target, follow_up, parse_mode=None, disable_web_page_preview=True)
        else:
            sent = await bot.send_message(target, post["text"], parse_mode=None,
                                          disable_web_page_preview=True)
        entry.update(status="approved", approved_at=now_iso(), published_message_id=sent.message_id)
        save_post(db, entry)
        link = f"https://t.me/{target.lstrip('@')}/{sent.message_id}" if target.startswith("@") else ""
        await bot.send_message(chat_id, f"✓ Опубликовано в {post['channel']}\n{link}",
                               parse_mode=None, disable_web_page_preview=True)
    except Exception as e:
        entry.update(status="publish_failed", approved_at=now_iso(), publish_error=str(e))
        save_post(db, entry)
        await bot.send_message(chat_id, f"❌ Публикация не прошла: {e}", parse_mode=None)


async def capture_edit_feedback(message: Message, db: Storage) -> bool:
    """Called for the manager's plain messages. True if it was edit feedback."""
    post_id = db.get_state("awaiting_edit_for")
    text = (message.text or message.caption or "").strip()
    if not post_id or not text or text.startswith("/"):
        return False
    post = load_posts(db).get(post_id)
    if post:
        save_post(db, {**post, "status": "edit_requested", "edit_feedback": text,
                            "edit_requested_at": now_iso()})
    db.set_state("awaiting_edit_for", None)
    await message.answer(f"✓ Принял правки по {post_id}. Передам Claude'у - "
                         "он подготовит новую версию и снова пришлёт на апруэ.", parse_mode=None)
    return True


async def save_manager_photo(message: Message, bot: Bot, db: Storage) -> bool:
    if not message.photo:
        return False
    folder = db.dir / "visuals" / "inbox_photos"
    folder.mkdir(parents=True, exist_ok=True)
    largest = max(message.photo, key=lambda p: p.file_size or 0)
    file = await bot.get_file(largest.file_id)
    ext = Path(file.file_path or "").suffix or ".jpg"
    local = folder / f"master_{datetime.now(timezone.utc):%Y%m%d-%H%M%S}{ext}"
    await bot.download_file(file.file_path, destination=local)
    await message.answer(f"✓ Фото получено: {local.name}\nClaude увидит и обработает.", parse_mode=None)
    return True


# --- reminders about edits waiting too long ------------------------------------------

def pending_edits(db: Storage) -> list[dict]:
    """Posts whose latest status is edit_requested (no newer revision yet)."""
    return [p for p in load_posts(db).values()
            if p.get("status") == "edit_requested" and p.get("edit_requested_at")]


async def nudge_loop(bot: Bot, settings: Settings, db: Storage, every: int = 480) -> None:
    while True:
        await asyncio.sleep(every)
        try:
            await nudge_once(bot, settings, db)
        except Exception:
            log.exception("nudge check failed")


async def nudge_once(bot: Bot, settings: Settings, db: Storage) -> None:
    if not settings.managers_chat_id:
        return
    nudged = set(db.get_state("nudged_edits") or [])
    now = datetime.now(timezone.utc).timestamp()
    for edit in pending_edits(db):
        key = f"{edit['id']}::{edit['edit_requested_at']}"
        try:
            age_min = (now - datetime.fromisoformat(edit["edit_requested_at"]).timestamp()) / 60
        except ValueError:
            continue
        if key in nudged or age_min < 30:
            continue
        await bot.send_message(settings.managers_chat_id, (
            "⏳ Правка ждёт обработки\n\n"
            f"Пост: {edit.get('title') or edit['id']}\n"
            f"Канал: {edit.get('channel')}\n"
            f"Ваш фидбэк: {(edit.get('edit_feedback') or '')[:120]}\n"
            f"Возраст правки: {int(age_min)} мин\n\n"
            "Если вы сейчас не у компьютера - scheduled task сработает в ближайшие 13 минут "
            "и подготовит новую версию автоматически.\n"
            "Если хотите сейчас - откройте чат с Claude, напишите «обработай правки»."), parse_mode=None)
        nudged.add(key)
    db.set_state("nudged_edits", list(nudged)[-200:])
