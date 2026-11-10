"""Questionnaires (consultation, Hayat): one question per message, answers go to the manager."""

from aiogram import Bot, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, ReplyKeyboardRemove

from bot.config import Settings
from bot.content import Content
from bot.formatting import form_card
from bot.keyboards import cancel_keyboard, contact_keyboard
from bot.notify import to_manager
from bot.storage import Storage

router = Router(name="forms")
router.message.filter(F.chat.type == "private")


class FormState(StatesGroup):
    answering = State()


async def _ask(message: Message, content: Content, form_name: str, step: int,
               answers: dict[str, str]) -> None:
    s = content.forms[form_name].steps[step]
    markup = (contact_keyboard(content, s.share_contact_button) if s.share_contact_button
              else cancel_keyboard(content))
    await message.answer(s.prompt.format(answers=answers), reply_markup=markup)


async def begin(message: Message, state: FSMContext, content: Content, form_name: str) -> None:
    form = content.forms[form_name]
    await state.set_state(FormState.answering)
    await state.update_data(form=form_name, step=0, answers={})
    if form.intro:
        await message.answer(form.intro)
    await _ask(message, content, form_name, 0, {})


def _is_cancel(message: Message, content: Content) -> bool:
    return message.text == content.buttons.cancel


@router.message(FormState.answering, Command("cancel"))
@router.message(FormState.answering, _is_cancel)
async def cancel(message: Message, state: FSMContext, content: Content) -> None:
    form = content.forms[(await state.get_data())["form"]]
    await state.set_state(None)
    await message.answer(form.cancelled, reply_markup=ReplyKeyboardRemove())


@router.message(FormState.answering, F.text | F.contact)
async def answer(message: Message, state: FSMContext, bot: Bot, content: Content,
                 settings: Settings, db: Storage) -> None:
    data = await state.get_data()
    form_name, step, answers = data["form"], data["step"], dict(data["answers"])
    form = content.forms[form_name]
    value = message.contact.phone_number if message.contact else message.text.strip()
    answers[form.steps[step].key] = value

    if step + 1 < len(form.steps):
        await state.update_data(step=step + 1, answers=answers)
        await _ask(message, content, form_name, step + 1, answers)
        return

    await state.set_state(None)
    await state.update_data(form=None, step=None, answers=None)
    user = message.from_user
    record = db.user(user.id)
    db.append(form.log_file, {
        "form": form_name, "source": record.get("source", "direct"),
        "segment_label": record.get("last_topic"), "chat_id": message.chat.id,
        "user_id": user.id, "username": user.username, "first_name": user.first_name,
        "last_name": user.last_name, "language_code": user.language_code,
        **answers, **form.extra,
    })
    await message.answer(form.done, reply_markup=ReplyKeyboardRemove())
    text, markup = form_card(form, answers, user, message.chat.id, db)
    await to_manager(bot, settings, message.chat.id, text, markup)
