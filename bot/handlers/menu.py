"""Main menu: /start, topic screens, photo album."""

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.content import Content
from bot.keyboards import Menu, main_menu, photos_menu, topic_menu

router = Router(name="menu")
router.message.filter(F.chat.type == "private")


@router.message(CommandStart())
async def start(message: Message, state: FSMContext, content: Content) -> None:
    await state.clear()
    await message.answer(content.welcome, reply_markup=main_menu(content))


@router.message(Command("myid"))
async def my_id(message: Message) -> None:
    await message.answer(f"Chat ID: <code>{message.chat.id}</code>")


@router.callback_query(Menu.filter(F.action == "home"))
async def home(callback: CallbackQuery, state: FSMContext, content: Content) -> None:
    await state.clear()
    await callback.message.answer(content.welcome, reply_markup=main_menu(content))
    await callback.answer()


@router.callback_query(Menu.filter(F.action == "photos"))
async def photos(callback: CallbackQuery, content: Content) -> None:
    await callback.message.answer(content.photos.text, reply_markup=photos_menu(content))
    await callback.answer()


@router.callback_query(Menu.filter(F.action == "topic"))
async def topic(callback: CallbackQuery, callback_data: Menu, state: FSMContext, content: Content) -> None:
    item = content.topic(callback_data.topic or "")
    if item is None:  # button from an old message whose topic was removed
        await callback.message.answer(content.welcome, reply_markup=main_menu(content))
    else:
        await state.update_data(topic=item.button)
        await callback.message.answer(item.text, reply_markup=topic_menu(content, item.id))
    await callback.answer()

