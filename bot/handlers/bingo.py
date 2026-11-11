"""Business bingo (I AM. IN).

Guest:  full name → 9 questions (✅ / ❌ buttons) → after ✅ a detailed story (optional)
        → final question → "winners will be announced from the stage".
Manager (Ksenia): see "manager side" below — /bingo → ▶️ → answers per question → final list.
Prize pools (texts.yaml → bingo.prizes):
  draw  — at the end, draw_count caps / t-shirts: first the /bingo_vip people (if they registered),
          the rest random among finishers without a mat / bag;
  best  — Ksenia's choice: one gift per question with stories, one per person;
  final — the pet-answer winner (chosen by Ksenia, anybody can win) gets only the audit.
All in state.json ("bingo", "bingo_awards") and the journal bingo.jsonl.
"""

import random
from html import escape

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, User

from bot.config import Settings
from bot.content import Content
from bot.keyboards import start_menu
from bot.storage import Storage, now_iso

router = Router(name="bingo")
rng = random.SystemRandom()


class BingoState(StatesGroup):
    name = State()
    story = State()
    final = State()


def kb(*rows: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t, callback_data=d) for t, d in row] for row in rows])


# --- data -------------------------------------------------------------------------------------

def players(db: Storage) -> dict[str, dict]:
    data = db.get_state("bingo")
    return data if isinstance(data, dict) else {}


def get_player(db: Storage, user_id: int) -> dict | None:
    return players(db).get(str(user_id))


def save_player(db: Storage, user_id: int, p: dict) -> None:
    data = players(db)
    data[str(user_id)] = p
    db.set_state("bingo", data)


def awards(db: Storage) -> list[dict]:
    data = db.get_state("bingo_awards")
    return data if isinstance(data, list) else []


def add_award(db: Storage, entry: dict) -> None:
    entry = {**entry, "at": now_iso()}
    db.set_state("bingo_awards", awards(db) + [entry])
    db.append("bingo.jsonl", {"event": "award", **entry})


def left(db: Storage, content: Content, prize_id: str) -> int:
    prize = content.bingo.prize(prize_id)
    given = sum(1 for a in awards(db) if a["prize"] == prize_id)
    return max(0, (prize.qty if prize else 0) - given)


def pool_items(db: Storage, content: Content, *pools: str) -> list[str]:
    """Remaining items of the given pools, one entry per physical item."""
    return [p.id for p in content.bingo.prizes if p.pool in pools
            for _ in range(left(db, content, p.id))]


# --- guest side ---------------------------------------------------------------------------------

async def show_home_screen(message: Message, user_id: int, content: Content, db: Storage) -> None:
    """After the bingo: the start screen with all buttons, so people can look around the bot.
    The screen they came from (QR code), or the first screen that has the bingo button."""
    key, screen = content.screen_by_start_param(db.user(user_id).get("source"))
    if not any(b.id == "bingo" for b in screen.buttons):
        key = next((k for k, sc in content.screens.items() if any(b.id == "bingo" for b in sc.buttons)), key)
        screen = content.screens[key]
    await message.answer(screen.text, reply_markup=start_menu(content, key))


async def open_card(message: Message, user: User, state: FSMContext, content: Content,
                    db: Storage) -> None:
    p = get_player(db, user.id)
    if p and p.get("done_at"):
        await message.answer(content.bingo.already_done.format(name=escape(p["name"])))
        await show_home_screen(message, user.id, content, db)
        return
    if not p or "step" not in p:  # not registered yet
        await message.answer(content.bingo.intro)
        await state.set_state(BingoState.name)
        await message.answer(content.bingo.ask_name)
        return
    await ask(message, state, content, p["step"])  # continue where they stopped


async def ask(message: Message, state: FSMContext, content: Content, q: int) -> None:
    b = content.bingo
    total = len(b.questions)
    if q < total:
        await state.set_state(None)
        await message.answer(
            f"{b.question_header.format(n=q + 1, total=total)}\n\n«{escape(b.questions[q].text)}»",
            reply_markup=kb([(b.yes_button, f"bingo:ans:{q}:y")], [(b.no_button, f"bingo:ans:{q}:n")]))
    else:
        await state.set_state(BingoState.final)
        await message.answer(b.final_question)


async def advance(message: Message, state: FSMContext, content: Content, db: Storage,
                  user_id: int, q: int) -> None:
    p = get_player(db, user_id)
    p["step"] = q + 1
    save_player(db, user_id, p)
    await ask(message, state, content, q + 1)


@router.message(BingoState.name, F.chat.type == "private", F.text, ~F.text.startswith("/"))
async def got_name(message: Message, state: FSMContext, content: Content, db: Storage) -> None:
    user = message.from_user
    name = " ".join(message.text.split())[:80]
    save_player(db, user.id, {"name": name, "tg_name": user.full_name, "username": user.username,
                              "step": 0, "answers": {}, "stories": {}, "final": None,
                              "registered_at": now_iso(), "done_at": None})
    db.append("bingo.jsonl", {"event": "register", "name": name, "user_id": user.id,
                              "username": user.username})
    await ask(message, state, content, 0)


@router.callback_query(F.data.startswith("bingo:ans:"))
async def got_answer(callback: CallbackQuery, state: FSMContext, content: Content,
                     db: Storage) -> None:
    _, _, q, yn = callback.data.split(":")
    q, user = int(q), callback.from_user
    p = get_player(db, user.id)
    if not p or p.get("step") != q:
        await callback.answer("Вы уже ответили на этот вопрос 👍")
        return
    p["answers"][str(q + 1)] = "yes" if yn == "y" else "no"
    save_player(db, user.id, p)
    db.append("bingo.jsonl", {"event": "answer", "q": q + 1, "answer": p["answers"][str(q + 1)],
                              "name": p["name"], "user_id": user.id})
    b = content.bingo
    await callback.answer()
    try:  # keep the question, replace the buttons with the chosen answer
        await callback.message.edit_text(
            f"{callback.message.html_text}\n\n{b.yes_button if yn == 'y' else b.no_button}",
            reply_markup=None)
    except Exception:
        pass
    if yn == "y" and b.questions[q].story:
        await state.set_state(BingoState.story)
        await state.update_data(bingo_q=q)
        prompt = b.questions[q].prompt or b.default_prompt
        await callback.message.answer(
            f"«{escape(b.questions[q].text)}»\n\n" + b.story_prompt.format(prompt=escape(prompt)),
            reply_markup=kb([(b.skip_button, f"bingo:skip:{q}")]))
    else:
        await advance(callback.message, state, content, db, user.id, q)


@router.callback_query(F.data.startswith("bingo:skip:"))
async def skip_story(callback: CallbackQuery, state: FSMContext, content: Content,
                     db: Storage) -> None:
    q = int(callback.data.rsplit(":", 1)[1])
    p = get_player(db, callback.from_user.id)
    await callback.answer()
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    if p and p.get("step") == q:
        await advance(callback.message, state, content, db, callback.from_user.id, q)


@router.message(BingoState.story, F.chat.type == "private", F.text, ~F.text.startswith("/"))
async def got_story(message: Message, state: FSMContext, content: Content, db: Storage) -> None:
    q = (await state.get_data()).get("bingo_q", 0)
    user = message.from_user
    p = get_player(db, user.id)
    story = message.text.strip()
    p["stories"][str(q + 1)] = story
    save_player(db, user.id, p)
    db.append("bingo.jsonl", {"event": "story", "q": q + 1, "question": content.bingo.questions[q].text,
                              "text": story, "name": p["name"], "user_id": user.id,
                              "username": user.username})
    await advance(message, state, content, db, user.id, q)


@router.message(BingoState.final, F.chat.type == "private", F.text, ~F.text.startswith("/"))
async def got_final(message: Message, state: FSMContext, content: Content, db: Storage) -> None:
    await state.set_state(None)
    user = message.from_user
    p = get_player(db, user.id)
    p["final"] = message.text.strip()[:200]
    p["done_at"] = now_iso()
    save_player(db, user.id, p)
    db.append("bingo.jsonl", {"event": "final", "text": p["final"], "name": p["name"],
                              "user_id": user.id})
    await message.answer(content.bingo.done.format(name=escape(p["name"])))
    await show_home_screen(message, user.id, content, db)


# --- manager side ---------------------------------------------------------------------------------
#
# Flow for Ksenia — as few buttons as possible:
#   /bingo → [▶️ Почати]
#   → question 1: one message with all answers, buttons are only the numbers
#   → she taps a number (= the participant's permanent number): mat or bag → question 2 … → question 9
#   → the pet question: same list, she picks → the audit
#   → random draw of draw_count caps / t-shirts among those who got nothing → the final list.

def is_manager(user_id: int, settings: Settings) -> bool:
    return settings.managers_chat_id is not None and user_id == settings.managers_chat_id


def story_questions(content: Content) -> list[int]:
    """1-based numbers of questions that ask for a story."""
    return [i + 1 for i, qq in enumerate(content.bingo.questions) if qq.story]


# --- priority in the random draw ------------------------------------------------------------------
# The manager sets names with /bingo_vip (kept on the server only - the repository is public).
# Names are compared loosely: word order, ё/е, Ukrainian / Russian / Latin spelling
# ("Алёна Ковалёва" = "Ковалёва Алёна" = "Альона Ковальова" = "Alona Kovaliova").

_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "ґ": "g", "д": "d", "е": "e", "ё": "e", "є": "e", "ж": "zh",
    "з": "z", "и": "i", "і": "i", "ї": "i", "й": "i", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o",
    "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "kh", "ц": "ts", "ч": "ch",
    "ш": "sh", "щ": "shch", "ъ": "", "ы": "i", "ь": "", "э": "e", "ю": "iu", "я": "ia", "'": "", "’": "",
}


def _skeleton(word: str) -> str:
    """Consonant skeleton of a name, the same for Cyrillic and Latin spellings.
    The first vowel is kept (Олена ≠ Алёна), except Олександра / Александра."""
    latin = "".join(_TRANSLIT.get(ch, ch) for ch in word.lower())
    latin = latin.replace("h", "")  # kh / zh / Olha ...
    out = []
    for ch in latin:
        if ch.isalpha() and ch not in "aeiouyj" and (not out or out[-1] != ch):
            out.append(ch)
    body = "".join(out)
    first = latin[:1]
    if first in ("y", "j"):
        first = "i"
    if first in "aeiou" and first and not body.startswith("lks"):
        return first + body
    return body


def _name_key(name: str) -> frozenset[str]:
    return frozenset(s for s in (_skeleton(w) for w in name.replace("-", " ").split()) if s)


def is_vip(name: str, vips: list[str]) -> bool:
    key = _name_key(name)
    return any(_name_key(v) and _name_key(v) <= key for v in vips)


def vip_list(db: Storage) -> list[str]:
    data = db.get_state("bingo_vip")
    return data if isinstance(data, list) else []


def run_draw(content: Content, db: Storage) -> list[tuple[str, str]]:
    """At the very end: caps / t-shirts among participants without a physical gift (audit doesn't count).
    Priority people (/bingo_vip) who registered get theirs first; the rest is random among finishers."""
    drawn = sum(1 for a in awards(db) if a["pool"] == "draw")
    items = pool_items(db, content, "draw")
    rng.shuffle(items)
    items = items[:max(0, content.bingo.draw_count - drawn)]
    has_gift = {str(a.get("user_id")) for a in awards(db) if a["pool"] in ("best", "gift", "draw")}
    vips = vip_list(db)
    free = [(uid, p) for uid, p in players(db).items() if p.get("name") and uid not in has_gift]
    priority = [(uid, p) for uid, p in free if is_vip(p["name"], vips)]
    others = [(uid, p) for uid, p in free if p.get("done_at") and (uid, p) not in priority]
    rng.shuffle(others)
    result = []
    for (uid, p), prize_id in zip(priority + others, items):
        add_award(db, {"name": p["name"], "user_id": int(uid), "prize": prize_id, "pool": "draw"})
        result.append((p["name"], content.bingo.prize(prize_id).label))
    return result


def give_final(content: Content, db: Storage, uid: str) -> None:
    """The chosen pet-answer winner gets the "final" pool only (the audit) - no physical gift."""
    p = players(db)[uid]
    for prize_id in pool_items(db, content, "final"):
        add_award(db, {"name": p["name"], "user_id": int(uid), "prize": prize_id, "pool": "final"})


def participant_numbers(db: Storage) -> dict[str, int]:
    """Permanent number of every participant: order of registration (who wrote the name first)."""
    named = [(p.get("registered_at") or "", uid) for uid, p in players(db).items() if p.get("name")]
    return {uid: n for n, (_, uid) in enumerate(sorted(named), 1)}


def answers_for(db: Storage, q: int) -> list[tuple[str, dict]]:
    nums = participant_numbers(db)
    rows = [(uid, p) for uid, p in players(db).items() if p.get("name") and str(q) in p["stories"]]
    return sorted(rows, key=lambda r: nums[r[0]])


# Whoever won a mat / bag with an answer can't win another answer, nor a cap / t-shirt in the draw.
# The audit (pet question) is open to everybody and doesn't exclude from the draw.
BLOCKING_POOLS = {"best"}


def gifts_of(content: Content, db: Storage, pools: set[str]) -> dict[str, str]:
    """user_id -> what they already got from the given pools, e.g. "Кепка темна"."""
    out: dict[str, list[str]] = {}
    for a in awards(db):
        if a.get("user_id") is not None and a["pool"] in pools:
            out.setdefault(str(a["user_id"]), []).append(
                getattr(content.bingo.prize(a["prize"]), "label", a["prize"]))
    return {uid: " + ".join(v) for uid, v in out.items()}


def marks_of(content: Content, db: Storage) -> tuple[dict[str, str], set[str]]:
    """(blocked people with what they got, people who won the random draw)."""
    blocked = gifts_of(content, db, BLOCKING_POOLS)
    drawn = set(gifts_of(content, db, {"draw", "gift"}))
    return blocked, drawn


async def show_next(message: Message, content: Content, db: Storage) -> None:
    """Send the answers of the next question still without a winner; at the end — the final list."""
    decided = {a.get("q") for a in awards(db) if a["pool"] == "best"}
    skipped = set(db.get_state("bingo_skipped") or [])
    for q in story_questions(content):
        if q in decided or q in skipped:
            continue
        rows = answers_for(db, q)
        if not rows:  # nobody answered: go on
            db.set_state("bingo_skipped", sorted(skipped | {q}))
            skipped.add(q)
            continue
        await send_answers(message, content, db, q, rows)
        return
    if not any(a["pool"] == "final" for a in awards(db)) and not db.get_state("bingo_final_skipped"):
        # 10th question: the manager picks too
        nums = participant_numbers(db)
        rows = sorted(((uid, p) for uid, p in players(db).items() if p.get("final") and uid in nums),
                      key=lambda r: nums[r[0]])
        if rows:
            await send_list(message, f"<b>Финальный вопрос · «{escape(content.bingo.final_short)}»</b>\n"
                                     f"Ответов: {len(rows)}. Нажмите номер лучшего 👇",
                            [(uid, p["final"]) for uid, p in rows], [p["name"] for _, p in rows], "final",
                            {}, set(), participant_numbers(db))  # the audit: everybody can win it
            return
    # all picks done → random caps / t-shirts among those who got nothing, then the final list
    if not any(a["pool"] == "draw" for a in awards(db)):
        run_draw(content, db)
    db.set_state("bingo_finished", True)
    await message.answer(final_list(content, db))


async def send_answers(message: Message, content: Content, db: Storage, q: int,
                       rows: list[tuple[str, dict]]) -> None:
    head = (f"<b>Вопрос {q} · «{escape(content.bingo.questions[q - 1].text)}»</b>\n"
            f"Ответов: {len(rows)}. Нажмите номер лучшего 👇")
    await send_list(message, head, [(uid, p["stories"][str(q)]) for uid, p in rows],
                    [p["name"] for _, p in rows], str(q), *marks_of(content, db), participant_numbers(db))


async def send_list(message: Message, head: str, answers: list[tuple[str, str]], names: list[str],
                    tag: str, blocked: dict[str, str], drawn: set[str], nums: dict[str, int]) -> None:
    """Numbered "N. Name: answer" list; the only buttons are the numbers (bingo:pick:<uid>:<tag>).
    🎁 = already won with an answer (can't be chosen). Draw winners are not marked (no spoilers).
    If nobody can be chosen, a skip button is added."""
    legend = []
    if any(uid in blocked for uid, _ in answers):
        legend.append("🎁 - уже получил(а) подарок за ответ")
    if legend:
        head += "\n" + "\n".join(legend)
    parts, chunk, buttons = [], head + "\n", []
    for (uid, answer), name in zip(answers, names):
        n = nums[uid]  # the participant's permanent number
        answer = answer if len(answer) <= 300 else answer[:297] + "…"
        mark = " 🎁" if uid in blocked else ""  # draw winners are not shown: no spoilers before the end
        line = f"\n<b>{n}. {escape(name)}</b>{mark}: {escape(answer)}"
        if len(chunk) + len(line) > 3900 or len(buttons) >= 60:
            parts.append((chunk, buttons))
            chunk, buttons = "", []
        chunk += line
        buttons.append((str(n), f"bingo:pick:{uid}:{tag}"))
    parts.append((chunk, buttons))
    nobody_free = all(uid in blocked for uid, _ in answers)
    for i, (text, btns) in enumerate(parts):
        rows = [btns[j:j + 6] for j in range(0, len(btns), 6)]
        if nobody_free and i == len(parts) - 1:
            rows.append([("⏭ У всех уже есть подарки - пропустить", f"bingo:skip_q:{tag}")])
        await message.answer(text, reply_markup=kb(*rows))


def final_list(content: Content, db: Storage) -> str:
    ps = players(db)
    sections = [("draw", "🎲 Розыгрыш среди участников"), ("gift", "🎁 От THE A"),
                ("best", "📝 Лучшие истории"), ("final", "🐾 Финальный вопрос")]
    lines = ["<b>🏆 Бизнес-бинго · победители</b>"]
    for pool, title in sections:
        items = [a for a in awards(db) if a["pool"] == pool]
        if not items:
            continue
        lines += ["", f"<b>{title}:</b>"]
        if pool == "final":  # one line per person: "Name - audit + mat (pet)"
            groups: dict[str, list[dict]] = {}
            for a in items:
                groups.setdefault(f"{a.get('user_id')}|{a['name']}", []).append(a)
            for group in groups.values():
                labels = " + ".join(escape(getattr(content.bingo.prize(a["prize"]), "label", a["prize"]))
                                    for a in group)
                pet = (ps.get(str(group[0].get("user_id"))) or {}).get("final")
                lines.append(f"• {escape(group[0]['name'])} - {labels}"
                             + (f" (питомец: {escape(pet)})" if pet else ""))
            continue
        for a in items:
            label = escape(getattr(content.bingo.prize(a["prize"]), "label", a["prize"]))
            extra = f" (вопрос {a['q']})" if pool == "best" and a.get("q") else ""
            lines.append(f"• {escape(a['name'])} - {label}{extra}")
    if len(lines) == 1:
        lines.append("\nПока подарков не назначено.")
    return "\n".join(lines)


@router.message(Command("bingo"))
async def bingo_command(message: Message, state: FSMContext, content: Content,
                        settings: Settings, db: Storage) -> None:
    if not is_manager(message.from_user.id, settings):
        await state.set_state(None)
        await open_card(message, message.from_user, state, content, db)
        return
    if db.get_state("bingo_finished"):
        await message.answer(final_list(content, db))
    elif db.get_state("bingo_started"):
        await show_next(message, content, db)  # continue where we stopped
    else:
        n = sum(1 for p in players(db).values() if p.get("name"))
        vips = vip_list(db)
        extra = f"\n⭐ Приоритет в розыгрыше: {escape(', '.join(vips))}" if vips else ""
        await message.answer(f"<b>🎯 Бизнес-бинго</b>\nУчастников: {n}{extra}",
                             reply_markup=kb([("▶️ Начать", "bingo:start")]))


@router.message(Command("bingo_vip"))
async def vip_command(message: Message, command: CommandObject, settings: Settings, db: Storage) -> None:
    """/bingo_vip Имя Фамилия - priority in the cap / t-shirt draw; /bingo_vip - show the list;
    /bingo_vip очистить - clear it."""
    if not is_manager(message.from_user.id, settings):
        return
    name = " ".join((command.args or "").split())
    vips = vip_list(db)
    if name.lower() in ("очистить", "clear", "очистити"):
        vips = []
    elif name and not any(_name_key(name) == _name_key(v) for v in vips):
        vips.append(name)
    db.set_state("bingo_vip", vips)
    found = [p["name"] for p in players(db).values() if p.get("name") and is_vip(p["name"], vips)]
    lines = ["<b>⭐ Приоритет в розыгрыше кепок и футболок</b>"]
    lines += [f"• {escape(v)}" for v in vips] or ["Список пуст."]
    lines += ["", f"Уже среди участников: {escape(', '.join(found)) if found else 'пока никого'}",
              "", "Добавить: /bingo_vip Имя Фамилия", "Очистить: /bingo_vip очистить"]
    await message.answer("\n".join(lines))


@router.message(Command("gift"))
async def gift_command(message: Message, command: CommandObject, content: Content,
                       settings: Settings, db: Storage) -> None:
    """Optional: a cap / t-shirt "from THE A" to a specific person (goes to the final list)."""
    if not is_manager(message.from_user.id, settings):
        return
    name = " ".join((command.args or "").split())
    if not name:
        await message.answer("Напишите имя: /gift Имя Фамилия")
        return
    db.set_state("bingo_pending_gift", name)
    rows = [[(f"{p.label} ({left(db, content, p.id)})", f"bingo:gift:{p.id}")]
            for p in content.bingo.prizes if p.pool == "draw" and left(db, content, p.id) > 0]
    await message.answer(f"🎁 Подарок от THE A для <b>{escape(name)}</b>:", reply_markup=kb(*rows))


@router.callback_query(F.data.regexp(r"^bingo:(start|pick|gift|skip_q):?"))
async def manager_button(callback: CallbackQuery, content: Content, settings: Settings,
                         db: Storage) -> None:
    if not is_manager(callback.from_user.id, settings):
        await callback.answer("Только для менеджера.", show_alert=True)
        return
    parts = callback.data.split(":")
    action, msg = parts[1], callback.message

    async def close() -> None:  # buttons are one-shot: removed only after a successful action
        try:
            await msg.edit_reply_markup(reply_markup=None)
        except Exception:
            pass

    if action == "start":
        await callback.answer()
        await close()
        if db.get_state("bingo_started"):
            await show_next(msg, content, db)
            return
        db.set_state("bingo_started", True)
        await show_next(msg, content, db)
        return

    if action == "gift":
        name, prize_id = db.get_state("bingo_pending_gift"), parts[2]
        if not name or left(db, content, prize_id) <= 0:
            await callback.answer("Подарок закончился.", show_alert=True)
            return
        add_award(db, {"name": name, "user_id": None, "prize": prize_id, "pool": "gift"})
        db.set_state("bingo_pending_gift", None)
        await callback.answer("🎁")
        await close()
        await msg.answer(f"🎁 {escape(name)} - {escape(content.bingo.prize(prize_id).label)}")
        return

    if action == "skip_q":  # every answer of this question is from someone who already has a gift
        tag = parts[2]
        if tag == "final":
            db.set_state("bingo_final_skipped", True)
        else:
            db.set_state("bingo_skipped", sorted(set(db.get_state("bingo_skipped") or []) | {int(tag)}))
        await callback.answer("⏭")
        await close()
        await show_next(msg, content, db)
        return

    # pick: bingo:pick:<uid>:<question number | final>
    uid, tag = parts[2], parts[3]
    if tag == "final":
        if any(a["pool"] == "final" for a in awards(db)):
            await callback.answer("Победитель финального вопроса уже выбран.", show_alert=True)
            return
    elif int(tag) in {a.get("q") for a in awards(db) if a["pool"] == "best"}:
        await callback.answer(f"Для вопроса {tag} победитель уже выбран.", show_alert=True)
        return

    already = None if tag == "final" else gifts_of(content, db, BLOCKING_POOLS).get(uid)
    if already:  # who won with an answer can't win another answer (the audit is open to everybody)
        name = (players(db).get(uid) or {}).get("name", "")
        await callback.answer(f"⚠️ {name} уже получил(а) подарок: {already}.\n\nВыберите другой ответ.",
                              show_alert=True)
        return

    p = players(db)[uid]
    if tag == "final":  # the best pet answer: the audit
        give_final(content, db, uid)
        await callback.answer(f"🏆 {p['name']}")
        await close()
        await show_next(msg, content, db)
        return

    items = pool_items(db, content, "best")
    if not items:
        await callback.answer("Коврики и сумки закончились.", show_alert=True)
        return
    q = int(tag)
    prize_id = rng.choice(items)
    add_award(db, {"name": p["name"], "user_id": int(uid), "prize": prize_id, "pool": "best", "q": q})
    await callback.answer(f"🏆 {p['name']}")
    await close()
    await show_next(msg, content, db)
