"""Business bingo (I AM. IN).

Guest:  full name → 9 questions (✅ / ❌ buttons) → after ✅ a detailed story (optional)
        → final question → "winners will be announced from the stage".
Manager (Ksenia), all in the bot:
  - after each question: one message with all its stories "N. Name: story" + number buttons
    → she picks the winner and the gift → the bot offers the next question;
  - /bingo: status + buttons: draw caps & t-shirts, final draw, final list, undo;
  - /bingo → question buttons → numbered list of stories with 🏆 N buttons (also /bingo_answers N);
  - /gift Name Surname: a gift "from THE A" (before the draw).
Prize pools (texts.yaml → bingo.prizes):
  draw  — random (draw_count items) among participants who have no gift yet; the rest for /gift;
  best  — Ksenia's choice: one gift per question with stories, one per person;
  final — ONE random winner among everyone who answered the final question gets the audit
          + whatever is left of the "best" pool.
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

async def open_card(message: Message, user: User, state: FSMContext, content: Content,
                    db: Storage) -> None:
    p = get_player(db, user.id)
    if p and p.get("done_at"):
        await message.answer(content.bingo.already_done.format(name=escape(p["name"])))
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
        await callback.answer("Ви вже відповіли на це питання 👍")
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


# --- manager side ---------------------------------------------------------------------------------

def is_manager(user_id: int, settings: Settings) -> bool:
    return settings.managers_chat_id is not None and user_id == settings.managers_chat_id


def manager_keyboard(content: Content, db: Storage) -> InlineKeyboardMarkup:
    named = [p for p in players(db).values() if p.get("name")]
    best_q = {a.get("q") for a in awards(db) if a["pool"] == "best"}
    q_buttons = []
    for i, qq in enumerate(content.bingo.questions):
        if qq.story:
            n = sum(1 for p in named if str(i + 1) in p["stories"])
            q_buttons.append((f"{'🏆' if i + 1 in best_q else '📝'} {i + 1} ({n})", f"bingo:q:{i + 1}"))
    rows = [q_buttons[i:i + 5] for i in range(0, len(q_buttons), 5)]
    first = story_questions(content)[0] if story_questions(content) else None
    start = [[(f"▶️ Вибір переможців: почати з питання {first}", f"bingo:q:{first}")]] if first else []
    return kb(*start, *rows,
              [(f"🎲 Розіграш: {content.bingo.draw_count} кепок/футболок", "bingo:draw")],
              [("🏁 Фінальний розіграш (мат + аудит)", "bingo:final")],
              [("📋 Фінальний список для сцени", "bingo:list")],
              [("↩️ Скасувати останній подарунок", "bingo:undo")])


def story_questions(content: Content) -> list[int]:
    """1-based numbers of questions that ask for a story."""
    return [i + 1 for i, qq in enumerate(content.bingo.questions) if qq.story]


def next_story_question(content: Content, q: int) -> int | None:
    return next((n for n in story_questions(content) if n > q), None)


def nav_row(content: Content, q: int) -> list[tuple[str, str]]:
    row = [("🔄 Оновити", f"bingo:q:{q}")]
    nxt = next_story_question(content, q)
    row.append((f"⏭ Питання {nxt}", f"bingo:q:{nxt}") if nxt else ("📋 До розіграшів", "bingo:panel"))
    return row


async def send_answers(message: Message, content: Content, db: Storage, q: int) -> None:
    """One message with all stories for question q, numbered, and a 🏆 button per story."""
    best = {a.get("q"): a for a in awards(db) if a["pool"] == "best"}
    rows = [(uid, p) for uid, p in players(db).items() if p.get("name") and str(q) in p["stories"]]
    head = f"<b>Питання {q} · «{escape(content.bingo.questions[q - 1].text)}»</b>\nВідповідей: {len(rows)}"
    done = q in best
    if done:
        prize = content.bingo.prize(best[q]["prize"])
        head += f"\n🏆 Переможець: <b>{escape(best[q]['name'])}</b> - {escape(prize.label if prize else '')}"
    elif rows:
        head += "\nОберіть номер найкращої відповіді 👇"
    if not rows:
        await message.answer(head + "\n\nПоки немає відповідей.", reply_markup=kb(nav_row(content, q)))
        return

    parts, chunk, buttons = [], head + "\n", []
    for n, (uid, p) in enumerate(rows, 1):
        story = p["stories"][str(q)]
        story = story if len(story) <= 300 else story[:297] + "…"
        line = f"\n<b>{n}. {escape(p['name'])}</b>: {escape(story)}"
        if len(chunk) + len(line) > 3900 or len(buttons) >= 60:
            parts.append((chunk, buttons))
            chunk, buttons = "", []
        chunk += line
        buttons.append((str(n), f"bingo:best:{uid}:{q - 1}"))
    parts.append((chunk, buttons))
    for i, (text, btns) in enumerate(parts):
        rows_kb = [] if done else [btns[j:j + 6] for j in range(0, len(btns), 6)]
        if i == len(parts) - 1:
            rows_kb.append(nav_row(content, q))
        await message.answer(text, reply_markup=kb(*rows_kb) if rows_kb else None)


def status_text(content: Content, db: Storage) -> str:
    ps = players(db)
    named = [p for p in ps.values() if p.get("name")]
    stories = sum(len(p["stories"]) for p in named)
    finals = sum(1 for p in named if p.get("final"))
    best_given = sum(1 for a in awards(db) if a["pool"] == "best")
    lines = ["<b>🎯 Бізнес-бінго</b>", "",
             f"Учасників: {len(named)} · дійшли до фіналу: {finals} · історій: {stories}",
             f"Подаровано за історії: {best_given} з {content.bingo.best_limit}",
             f"Розіграно кепок/футболок: {sum(1 for a in awards(db) if a['pool'] == 'draw')} з {content.bingo.draw_count}", "",
             "<b>Залишилось подарунків:</b>"]
    lines += [f"• {escape(p.label)}: {left(db, content, p.id)} з {p.qty}" for p in content.bingo.prizes]
    best_q = {a.get("q") for a in awards(db) if a["pool"] == "best"}
    per_q = [(i + 1, sum(1 for p in named if str(i + 1) in p["stories"]))
             for i, qq in enumerate(content.bingo.questions) if qq.story]
    lines += ["", "<b>Історій по питаннях</b> (🏆 - подарунок уже є; /bingo_answers N - прочитати):",
              " · ".join(f"{n}: {c}{' 🏆' if n in best_q else ''}" for n, c in per_q)]
    return "\n".join(lines)


def final_list(content: Content, db: Storage) -> str:
    ps = players(db)
    sections = [("draw", "🎲 Розіграш серед учасників"), ("gift", "🎁 Від THE A"),
                ("best", "📝 Найкращі історії"), ("final", "🏁 Фінальний розіграш")]
    lines = ["<b>🏆 Бізнес-бінго · переможці</b>"]
    for pool, title in sections:
        items = [a for a in awards(db) if a["pool"] == pool]
        if not items:
            continue
        lines += ["", f"<b>{title}:</b>"]
        if pool == "final":
            by_person: dict[str, list[dict]] = {}
            for a in items:
                by_person.setdefault(f"{a.get('user_id')}|{a['name']}", []).append(a)
            for group in by_person.values():
                labels = " + ".join(escape(getattr(content.bingo.prize(a["prize"]), "label", a["prize"]))
                                    for a in group)
                pet = (ps.get(str(group[0].get("user_id"))) or {}).get("final")
                lines.append(f"• {escape(group[0]['name'])} - {labels}"
                             + (f" (улюбленець: {escape(pet)})" if pet else ""))
            continue
        for a in items:
            prize = content.bingo.prize(a["prize"])
            extra = ""
            if pool == "best" and a.get("q"):
                extra = f" (питання {a['q']})"
            if pool == "final":
                pet = (ps.get(str(a.get("user_id"))) or {}).get("final")
                extra = f" (улюбленець: {escape(pet)})" if pet else ""
            lines.append(f"• {escape(a['name'])} - {escape(prize.label if prize else a['prize'])}{extra}")
    if len(lines) == 1:
        lines.append("\nПоки що подарунків не призначено.")
    return "\n".join(lines)


@router.message(Command("bingo"))
async def bingo_command(message: Message, state: FSMContext, content: Content,
                        settings: Settings, db: Storage) -> None:
    if is_manager(message.from_user.id, settings):
        await message.answer(status_text(content, db), reply_markup=manager_keyboard(content, db))
    else:
        await open_card(message, message.from_user, state, content, db)


@router.message(Command("bingo_answers"))
async def answers_command(message: Message, command: CommandObject, content: Content,
                          settings: Settings, db: Storage) -> None:
    if not is_manager(message.from_user.id, settings):
        return
    total = len(content.bingo.questions)
    try:
        q = int((command.args or "").strip())
        assert 1 <= q <= total
    except (ValueError, AssertionError):
        await message.answer(f"Вкажіть номер питання: /bingo_answers 1 … /bingo_answers {total}")
        return
    await send_answers(message, content, db, q)


@router.message(Command("gift"))
async def gift_command(message: Message, command: CommandObject, content: Content,
                       settings: Settings, db: Storage) -> None:
    if not is_manager(message.from_user.id, settings):
        return
    name = " ".join((command.args or "").split())
    if not name:
        await message.answer("Напишіть ім'я: /gift Ім'я Прізвище")
        return
    db.set_state("bingo_pending_gift", name)
    rows = [[(f"{p.label} ({left(db, content, p.id)})", f"bingo:gift:{p.id}")]
            for p in content.bingo.prizes if p.pool != "final" and left(db, content, p.id) > 0]
    rows.append([("✖ Скасувати", "bingo:x")])
    await message.answer(f"🎁 Подарунок від THE A для <b>{escape(name)}</b>:", reply_markup=kb(*rows))


@router.callback_query(F.data.regexp(r"^bingo:(best|bestgive|gift|draw|final|list|undo|x|q|panel)\b"))
async def manager_button(callback: CallbackQuery, content: Content, settings: Settings,
                         db: Storage) -> None:
    if not is_manager(callback.from_user.id, settings):
        await callback.answer("Тільки для менеджера.", show_alert=True)
        return
    parts = callback.data.split(":")
    action = parts[1]
    msg = callback.message

    if action == "x":
        await callback.answer("Скасовано")
        await msg.edit_reply_markup(reply_markup=None)
        return

    if action == "panel":
        await callback.answer()
        await msg.answer(status_text(content, db), reply_markup=manager_keyboard(content, db))
        return

    if action == "q":  # list of stories for a question, with 🏆 buttons
        await callback.answer()
        await send_answers(msg, content, db, int(parts[2]))
        return

    if action == "list":
        await callback.answer()
        await msg.answer(final_list(content, db))
        return

    if action == "undo":
        items = awards(db)
        if not items:
            await callback.answer("Немає що скасовувати.", show_alert=True)
            return
        last = items.pop()
        db.set_state("bingo_awards", items)
        db.append("bingo.jsonl", {"event": "undo", **last})
        prize = content.bingo.prize(last["prize"])
        await callback.answer("Скасовано")
        await msg.answer(f"↩️ Скасовано: {escape(last['name'])} - {escape(prize.label if prize else last['prize'])}")
        return

    if action == "best":  # 🏆 under a story: choose which gift
        uid, q = parts[2], int(parts[3])
        if sum(1 for a in awards(db) if a["pool"] == "best") >= content.bingo.best_limit:
            await callback.answer(f"Уже подаровано {content.bingo.best_limit} за історії.", show_alert=True)
            return
        if any(a["pool"] == "best" and str(a.get("user_id")) == uid for a in awards(db)):
            await callback.answer("Ця людина вже отримала подарунок за історію.", show_alert=True)
            return
        if any(a["pool"] == "best" and a.get("q") == q + 1 for a in awards(db)):
            await callback.answer(f"За питання {q + 1} подарунок уже є (один на питання).", show_alert=True)
            return
        rows = [[(f"{p.label} ({left(db, content, p.id)})", f"bingo:bestgive:{uid}:{q}:{p.id}")]
                for p in content.bingo.prizes if p.pool == "best" and left(db, content, p.id) > 0]
        if not rows:
            await callback.answer("Мати і сумки закінчились.", show_alert=True)
            return
        await callback.answer()
        await msg.answer(f"Питання {q + 1} · переможець <b>{escape(players(db)[uid]['name'])}</b> - який подарунок?",
                         reply_markup=kb(*rows, [("✖ Скасувати", "bingo:x")]))
        return

    if action == "bestgive":
        uid, q, prize_id = parts[2], int(parts[3]), parts[4]
        p = players(db).get(uid)
        if not p or left(db, content, prize_id) <= 0:
            await callback.answer("Цей подарунок закінчився.", show_alert=True)
            return
        if any(a["pool"] == "best" and (str(a.get("user_id")) == uid or a.get("q") == q + 1)
               for a in awards(db)):
            await callback.answer("Вже подаровано (одна людина / одне питання - один подарунок).", show_alert=True)
            return
        add_award(db, {"name": p["name"], "user_id": int(uid), "prize": prize_id, "pool": "best", "q": q + 1})
        await callback.answer("🏆 Готово")
        nxt = next_story_question(content, q + 1)
        await msg.edit_text(
            f"🏆 Питання {q + 1}: виграв(ла) <b>{escape(p['name'])}</b> - "
            f"{escape(content.bingo.prize(prize_id).label)}. Залишилось: {left(db, content, prize_id)}",
            reply_markup=kb([(f"▶️ Відповіді на питання {nxt}", f"bingo:q:{nxt}")] if nxt
                            else [("📋 До розіграшів", "bingo:panel")]))
        return

    if action == "gift":
        name, prize_id = db.get_state("bingo_pending_gift"), parts[2]
        if not name or left(db, content, prize_id) <= 0:
            await callback.answer("Немає імені або подарунок закінчився.", show_alert=True)
            return
        add_award(db, {"name": name, "user_id": None, "prize": prize_id, "pool": "gift"})
        db.set_state("bingo_pending_gift", None)
        await callback.answer("🎁 Готово")
        await msg.edit_text(f"🎁 {escape(name)} - {escape(content.bingo.prize(prize_id).label)}")
        return

    if action == "draw":
        drawn = sum(1 for a in awards(db) if a["pool"] == "draw")
        items = pool_items(db, content, "draw")
        rng.shuffle(items)
        items = items[:max(0, content.bingo.draw_count - drawn)]
        if not items:
            await callback.answer("Розіграш кепок і футболок уже проведено.", show_alert=True)
            return
        has_gift = {str(a.get("user_id")) for a in awards(db)}
        candidates = [(uid, p) for uid, p in players(db).items()
                      if p.get("name") and uid not in has_gift]
        rng.shuffle(candidates)
        won = list(zip(candidates, items))
        for (uid, p), prize_id in won:
            add_award(db, {"name": p["name"], "user_id": int(uid), "prize": prize_id, "pool": "draw"})
        await callback.answer("🎲")
        text = [f"🎲 <b>Розіграш кепок і футболок</b> (серед {len(candidates)} учасників без подарунків):"]
        text += [f"• {escape(p['name'])} - {escape(content.bingo.prize(i).label)}" for (_, p), i in won]
        if len(items) > len(won):
            text.append(f"\nНе вистачило учасників: залишилось {len(items) - len(won)} шт.")
        await msg.answer("\n".join(text))
        return

    if action == "final":
        items = pool_items(db, content, "final", "best")
        if not items:
            await callback.answer("Фінальні подарунки вже розіграні.", show_alert=True)
            return
        candidates = [(uid, p) for uid, p in players(db).items() if p.get("final")]
        if not candidates:
            await callback.answer("Ще ніхто не відповів на фінальне питання.", show_alert=True)
            return
        # ONE winner gets everything that is left for the final: audit + leftover mat / bag
        items.sort(key=lambda i: content.bingo.prize(i).pool != "final")
        uid, p = rng.choice(candidates)
        for prize_id in items:
            add_award(db, {"name": p["name"], "user_id": int(uid), "prize": prize_id, "pool": "final"})
        await callback.answer("🏁")
        labels = " + ".join(escape(content.bingo.prize(i).label) for i in items)
        await msg.answer(f"🏁 <b>Фінальний розіграш</b> (серед {len(candidates)} учасників):\n"
                         f"• <b>{escape(p['name'])}</b> - {labels}")
        await msg.answer(final_list(content, db))
