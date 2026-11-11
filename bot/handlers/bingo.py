"""Business bingo (I AM. IN): a digital copy of the paper card.

Guest: taps cells that are true for them (3×3 grid), after each mark can tell a story.
       Three in a row → БІНГО message. Everything goes to the journal bingo.jsonl.
Manager (Ksenia): gets every story as a card with ⭐ shortlist / 🏆 gift buttons;
       /bingo shows the ranking and the gifts left. Gift → the guest gets a message.
"""

from html import escape

from aiogram import Bot, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, User

from bot.config import Settings
from bot.content import Content
from bot.formatting import contact_block
from bot.notify import to_manager
from bot.storage import Storage, now_iso

router = Router(name="bingo")

LINES = [(0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6), (1, 4, 7), (2, 5, 8), (0, 4, 8), (2, 4, 6)]
STORY_MIN = 40  # characters for a story to count as "detailed"


class BingoState(StatesGroup):
    story = State()


# --- data -----------------------------------------------------------------------------

def players(db: Storage) -> dict[str, dict]:
    data = db.get_state("bingo")
    return data if isinstance(data, dict) else {}


def player(db: Storage, user: User) -> dict:
    p = players(db).get(str(user.id)) or {"marks": [], "stories": {}, "shortlist": False,
                                          "prize": None, "bingo_at": None, "full_at": None}
    p.update(name=user.full_name, username=user.username)
    return p


def save_player(db: Storage, user_id: int, p: dict) -> None:
    data = players(db)
    data[str(user_id)] = p
    db.set_state("bingo", data)


def prizes_left(db: Storage, content: Content) -> dict[str, int]:
    left = db.get_state("bingo_prizes_left")
    if not isinstance(left, dict):
        left = {}
    for pr in content.bingo.prizes:  # new prizes added to texts.yaml appear automatically
        left.setdefault(pr.id, pr.qty)
    return left


def has_bingo(marks: list[int]) -> bool:
    return any(all(i in marks for i in line) for line in LINES)


def score(p: dict) -> int:
    detailed = sum(1 for s in p.get("stories", {}).values() if len(s) >= STORY_MIN)
    return len(p.get("marks", [])) + 3 * detailed + (2 if has_bingo(p.get("marks", [])) else 0)


# --- guest side ---------------------------------------------------------------------------

def card_text(content: Content, marks: list[int]) -> str:
    lines = [content.bingo.intro.rstrip(), ""]
    for i, cell in enumerate(content.bingo.cells):
        lines.append(f"{'✅' if i in marks else '⬜'} {i + 1}. {escape(cell.text)}")
    return "\n".join(lines)


def card_keyboard(content: Content, marks: list[int]) -> InlineKeyboardMarkup:
    cells = content.bingo.cells
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{'✅' if i in marks else '⬜'} {cells[i].short}",
                              callback_data=f"bingo:cell:{i}") for i in range(r, r + 3)]
        for r in (0, 3, 6)
    ])


async def open_card(message: Message, user: User, content: Content, db: Storage) -> None:
    p = player(db, user)
    save_player(db, user.id, p)
    await message.answer(card_text(content, p["marks"]), reply_markup=card_keyboard(content, p["marks"]))


@router.callback_query(F.data.startswith("bingo:cell:"))
async def cell(callback: CallbackQuery, state: FSMContext, bot: Bot, content: Content,
               settings: Settings, db: Storage) -> None:
    i = int(callback.data.rsplit(":", 1)[1])
    user = callback.from_user
    p = player(db, user)
    had_bingo, had_full = has_bingo(p["marks"]), len(p["marks"]) == 9
    if i in p["marks"]:
        p["marks"].remove(i)
    else:
        p["marks"] = sorted(p["marks"] + [i])
    marked = i in p["marks"]
    if has_bingo(p["marks"]) and not p["bingo_at"]:
        p["bingo_at"] = now_iso()
    if len(p["marks"]) == 9 and not p["full_at"]:
        p["full_at"] = now_iso()
    save_player(db, user.id, p)
    db.append("bingo.jsonl", {"event": "mark" if marked else "unmark", "cell": i + 1,
                              "user_id": user.id, "username": user.username})
    await callback.answer("✅" if marked else "⬜")
    try:
        await callback.message.edit_text(card_text(content, p["marks"]),
                                         reply_markup=card_keyboard(content, p["marks"]))
    except Exception:  # message too old to edit, or nothing changed
        pass

    if not marked:
        await state.set_state(None)
        return
    if has_bingo(p["marks"]) and not had_bingo:
        await callback.message.answer(content.bingo.bingo_text)
        await to_manager(bot, settings, callback.message.chat.id,
                         f"🎉 БІНГО · I AM. IN\n\n{contact_block(user, callback.message.chat.id, db)}")
    if len(p["marks"]) == 9 and not had_full:
        await callback.message.answer(content.bingo.full_text)
    await state.set_state(BingoState.story)
    await state.update_data(bingo_cell=i)
    await callback.message.answer(
        content.bingo.story_prompt.format(text=escape(content.bingo.cells[i].text)),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=content.bingo.skip_button, callback_data="bingo:skip")]]))


@router.callback_query(F.data == "bingo:skip")
async def skip(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(None)
    await callback.answer("👌")
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass


@router.message(BingoState.story, F.chat.type == "private", F.text, ~F.text.startswith("/"))
async def story(message: Message, state: FSMContext, bot: Bot, content: Content,
                settings: Settings, db: Storage) -> None:
    i = (await state.get_data()).get("bingo_cell", 0)
    await state.set_state(None)
    user = message.from_user
    p = player(db, user)
    p["stories"][str(i)] = message.text.strip()
    save_player(db, user.id, p)
    db.append("bingo.jsonl", {"event": "story", "cell": i + 1, "statement": content.bingo.cells[i].text,
                              "text": message.text.strip(), "user_id": user.id,
                              "username": user.username, "first_name": user.first_name})
    await message.answer(content.bingo.story_saved)

    text = (f"📝 Бінго · історія\n\n<b>«{escape(content.bingo.cells[i].text)}»</b>\n\n"
            f"{message.html_text}\n\n{contact_block(user, message.chat.id, db)}")
    buttons = [[InlineKeyboardButton(text="⭐ Шорт-лист", callback_data=f"bingo:star:{user.id}"),
                InlineKeyboardButton(text="🏆 Подарунок", callback_data=f"bingo:gift:{user.id}")]]
    if user.username:
        buttons.append([InlineKeyboardButton(text="✍️ Написати напряму", url=f"https://t.me/{user.username}")])
    await to_manager(bot, settings, message.chat.id, text, InlineKeyboardMarkup(inline_keyboard=buttons))


# --- manager side ---------------------------------------------------------------------------

def _is_manager(user_id: int, settings: Settings) -> bool:
    return settings.managers_chat_id is not None and user_id == settings.managers_chat_id


def _who(p: dict) -> str:
    return escape(p.get("name") or "-") + (f" @{p['username']}" if p.get("username") else "")


@router.callback_query(F.data.regexp(r"^bingo:(star|gift|award|nogift):"))
async def manager_button(callback: CallbackQuery, bot: Bot, content: Content,
                         settings: Settings, db: Storage) -> None:
    if not _is_manager(callback.from_user.id, settings):
        await callback.answer("Тільки для менеджера.", show_alert=True)
        return
    parts = callback.data.split(":")
    action, uid = parts[1], parts[2]
    p = players(db).get(uid)
    if not p:
        await callback.answer("Учасника не знайдено.", show_alert=True)
        return

    if action == "star":
        p["shortlist"] = not p.get("shortlist")
        save_player(db, int(uid), p)
        await callback.answer("⭐ У шорт-листі" if p["shortlist"] else "Прибрано з шорт-листа")
        return

    if action == "nogift":
        await callback.answer("Скасовано")
        await callback.message.delete()
        return

    if p.get("prize"):
        await callback.answer(f"Вже отримав(ла): {p['prize']}", show_alert=True)
        return

    left = prizes_left(db, content)
    if action == "gift":
        rows = [[InlineKeyboardButton(text=f"{pr.label} ({left[pr.id]})",
                                      callback_data=f"bingo:award:{uid}:{pr.id}")]
                for pr in content.bingo.prizes if left.get(pr.id, 0) > 0]
        if not rows:
            await callback.answer("Подарунки закінчились.", show_alert=True)
            return
        rows.append([InlineKeyboardButton(text="✖ Скасувати", callback_data=f"bingo:nogift:{uid}")])
        await callback.answer()
        await callback.message.answer(f"🏆 Який подарунок для {_who(p)}?",
                                      reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
        return

    # award
    prize = next((pr for pr in content.bingo.prizes if pr.id == parts[3]), None)
    if prize is None or left.get(prize.id, 0) <= 0:
        await callback.answer("Цей подарунок закінчився.", show_alert=True)
        return
    left[prize.id] -= 1
    db.set_state("bingo_prizes_left", left)
    p["prize"] = prize.label
    save_player(db, int(uid), p)
    db.append("bingo.jsonl", {"event": "prize", "prize": prize.id, "user_id": int(uid),
                              "username": p.get("username")})
    await callback.answer("🎁 Готово")
    try:
        await bot.send_message(int(uid), content.bingo.winner_text.format(prize=escape(prize.label)))
        note = "повідомлення надіслано"
    except Exception:
        note = "⚠️ не вдалося надіслати повідомлення - напишіть напряму"
    await callback.message.edit_text(
        f"🎁 {escape(prize.label)} → {_who(p)} ({note}). Залишилось: {left[prize.id]}")


@router.message(Command("bingo"))
async def bingo_command(message: Message, state: FSMContext, content: Content,
                        settings: Settings, db: Storage) -> None:
    if not _is_manager(message.from_user.id, settings):
        await state.set_state(None)
        await open_card(message, message.from_user, content, db)
        return
    data = players(db)
    left = prizes_left(db, content)
    ranked = sorted(data.values(), key=score, reverse=True)
    lines = [
        "<b>🎯 Бізнес-бінго · підсумки</b>", "",
        f"Учасників: {len(data)} · БІНГО: {sum(1 for p in data.values() if has_bingo(p['marks']))}"
        f" · історій: {sum(len(p['stories']) for p in data.values())}", "",
        "<b>Подарунки (залишилось):</b>",
        *[f"• {escape(pr.label)}: {left[pr.id]} з {pr.qty}" for pr in content.bingo.prizes], "",
        "<b>Рейтинг</b> (✅ відмітка = 1, 📝 історія = 3, БІНГО = 2):",
    ]
    for n, p in enumerate(ranked[:25], 1):
        tags = [f"{len(p['marks'])}✅", f"{len(p['stories'])}📝"]
        if has_bingo(p["marks"]):
            tags.append("БІНГО")
        if p.get("shortlist"):
            tags.append("⭐")
        if p.get("prize"):
            tags.append(f"🎁 {escape(p['prize'])}")
        lines.append(f"{n}. {_who(p)} - {score(p)} б · {' · '.join(tags)}")
    if not ranked:
        lines.append("Поки нікого.")
    await message.answer("\n".join(lines))
