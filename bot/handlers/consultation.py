"""Consultation sign-up: name -> contact -> question -> lead to managers."""

import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove

from bot.config import Settings
from bot.content import Content
from bot.formatting import consultation_lead
from bot.handlers.menu import show_home
from bot.keyboards import Menu, cancel_keyboard, contact_keyboard

log = logging.getLogger(__name__)

router = Router(name="consultation")
router.message.filter(F.chat.type == "private")


class Form(StatesGroup):
    name = State()
    contact = State()
    question = State()


async def _begin(message: Message, state: FSMContext, content: Content) -> None:
    await state.set_state(Form.name)
    await message.answer(content.consultation.ask_name, reply_markup=cancel_keyboard(content))


@router.callback_query(Menu.filter(F.action == "consult"))
async def begin_from_button(callback: CallbackQuery, state: FSMContext, content: Content) -> None:
    await _begin(callback.message, state, content)
    await callback.answer()


@router.message(Command("consult"))
async def begin_from_command(message: Message, state: FSMContext, content: Content) -> None:
    await _begin(message, state, content)


@router.message(StateFilter(Form), lambda m, content: m.text == content.buttons.cancel)
@router.message(StateFilter(Form), Command("cancel"))
async def cancel(message: Message, state: FSMContext, content: Content) -> None:
    await message.answer(content.consultation.cancelled, reply_markup=ReplyKeyboardRemove())
    await show_home(message, state, content)


@router.message(Form.name, F.text)
async def got_name(message: Message, state: FSMContext, content: Content) -> None:
    name = message.text.strip()
    await state.update_data(name=name)
    await state.set_state(Form.contact)
    await message.answer(
        content.consultation.ask_contact.format(name=name), reply_markup=contact_keyboard(content)
    )


@router.message(Form.contact, F.contact | F.text)
async def got_contact(message: Message, state: FSMContext, content: Content) -> None:
    contact = message.contact.phone_number if message.contact else message.text.strip()
    await state.update_data(contact=contact)
    await state.set_state(Form.question)
    await message.answer(content.consultation.ask_question, reply_markup=cancel_keyboard(content))


@router.message(Form.question, F.text)
async def got_question(
    message: Message, state: FSMContext, bot: Bot, content: Content, settings: Settings
) -> None:
    data = await state.get_data()
    lead = consultation_lead(message.from_user, data["name"], data["contact"], message.text.strip())
    if settings.managers_chat_id:
        await bot.send_message(settings.managers_chat_id, lead)
    else:
        log.warning("MANAGERS_CHAT_ID is not set; lead only logged:\n%s", lead)

    await message.answer(content.consultation.done, reply_markup=ReplyKeyboardRemove())
    await show_home(message, state, content)
