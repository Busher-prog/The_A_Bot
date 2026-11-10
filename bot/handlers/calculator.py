"""/calculator: 4 questions with buttons → tax savings comparison; the result also goes to the manager."""

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot import calculator as calc
from bot.config import Settings
from bot.keyboards import from_dict
from bot.notify import to_manager
from bot.storage import Storage

router = Router(name="calculator")

CALCULATOR_INTRO = (
    "🧮 Tax Savings Calculator\n\n"
    "Расчёт экономии налогов для IT-специалиста / фрилансера в EU "
    "через структурирование дохода через иностранную компанию.\n\n"
    "4 вопроса × 15 секунд = расчёт по 3 структурным опциям "
    "(Estonia OÜ + Digital Nomad, Cyprus non-dom, Portugal IFICI).\n\n"
    "Шаг 1 из 4 - где Вы налоговый резидент?"
)

# step -> (valid values, next prompt builder, next keyboard)
STEPS = ["residence", "gross", "source", "family"]


async def begin(message: Message, state: FSMContext) -> None:
    await state.update_data(calc={})
    await message.answer(CALCULATOR_INTRO, reply_markup=from_dict(calc.keyboard_residence()),
                         parse_mode=None)


@router.message(F.chat.type == "private", Command("calculator"))
async def calculator_command(message: Message, state: FSMContext) -> None:
    await state.set_state(None)
    await begin(message, state)


@router.callback_query(F.data.startswith("calc:"))
async def calc_button(callback: CallbackQuery, state: FSMContext, bot: Bot,
                      settings: Settings, db: Storage) -> None:
    parts = callback.data.split(":")
    step, value = parts[1], (parts[2] if len(parts) > 2 else None)
    session = dict((await state.get_data()).get("calc") or {})
    msg = callback.message
    try:  # hide the buttons of the answered question
        await msg.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    if step == "cancel":
        await state.update_data(calc=None)
        await callback.answer("Отменено")
        await msg.answer("Расчёт отменён. /calculator - начать заново.")
        return

    if step == "residence" and value in calc.COUNTRIES:
        session["residence"] = value
        country = calc.COUNTRIES[value]
        await callback.answer(country["name"])
        await msg.answer(calc.PROMPT_GROSS.format(flag=country["flag"], name=country["name"],
                                                  note=country["note"]),
                         reply_markup=from_dict(calc.keyboard_gross()), parse_mode=None)
    elif step == "gross" and value in calc.GROSS_BUCKETS:
        session["gross"] = value
        bucket = calc.GROSS_BUCKETS[value]
        await callback.answer(bucket["label"])
        await msg.answer(calc.PROMPT_SOURCE.format(gross_label=bucket["label"]),
                         reply_markup=from_dict(calc.keyboard_source()), parse_mode=None)
    elif step == "source" and value in calc.INCOME_SOURCES:
        session["source"] = value
        await callback.answer("Принято")
        await msg.answer(calc.PROMPT_FAMILY.format(source_label=calc.INCOME_SOURCES[value]["label"]),
                         reply_markup=from_dict(calc.keyboard_family()), parse_mode=None)
    elif step == "family" and value in calc.FAMILY:
        session["family"] = value
        if not all(k in session for k in STEPS):
            await callback.answer("Сессия неполная - /calculator чтобы начать заново.", show_alert=True)
            return
        await callback.answer("Считаю…")
        result = calc.compute(session)
        text = calc.format_result(session, result)
        if len(text) > 4000:
            text = text[:3990] + "\n\n[…]"
        await msg.answer(text, disable_web_page_preview=True, parse_mode=None)

        user = callback.from_user
        top = result["options"][0] if result["options"] else None
        db.append("calculator_completions.jsonl", {
            "user_id": user.id, "username": user.username, "first_name": user.first_name,
            "answers": session, "top_savings": top["savings"] if top else 0,
            "top_option": top["short"] if top else None,
        })
        await to_manager(bot, settings, msg.chat.id,
                         calc.format_master_notification(user.model_dump(), session, result),
                         parse_mode=None)
        session = None
    else:
        await callback.answer()
        return
    await state.update_data(calc=session)
