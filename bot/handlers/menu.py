"""Start screens, topic screens, photo album."""

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.content import Content
from bot.keyboards import Menu, main_menu, photos_menu, topic_menu

router = Router(name="menu")
router.message.filter(F.chat.type == "private")


async def show_home(message: Message, state: FSMContext, content: Content,
                    screen: str | None = None) -> None:
    """Show a start screen. Without `screen`, reuse the one this client came from."""
    if screen is None:
        screen = (await state.get_data()).get("screen")
    key, item = content.screen(screen)
    await state.clear()
    await state.update_data(screen=key)
    await message.answer(item.text, reply_markup=main_menu(content, key))


@router.message(CommandStart())
async def start(message: Message, command: CommandObject, state: FSMContext, content: Content) -> None:
    # t.me/<bot>?start=ybc arrives as "/start ybc"
    await show_home(message, state, content, command.args or "default")


@router.message(Command("myid"))
async def my_id(message: Message) -> None:
    await message.answer(f"Chat ID: <code>{message.chat.id}</code>")


@router.callback_query(Menu.filter(F.action == "home"))
async def home(callback: CallbackQuery, callback_data: Menu, state: FSMContext, content: Content) -> None:
    await show_home(callback.message, state, content, callback_data.screen)
    await callback.answer()


@router.callback_query(Menu.filter(F.action == "photos"))
async def photos(callback: CallbackQuery, callback_data: Menu, content: Content) -> None:
    await callback.message.answer(content.photos.text, reply_markup=photos_menu(content, callback_data.screen))
    await callback.answer()


@router.callback_query(Menu.filter(F.action == "topic"))
async def topic(callback: CallbackQuery, callback_data: Menu, state: FSMContext, content: Content) -> None:
    item = content.topic(callback_data.topic or "")
    if item is None:  # button from an old message whose topic was removed
        await show_home(callback.message, state, content, callback_data.screen)
    else:
        await state.update_data(topic=item.button)
        await callback.message.answer(item.text,
                                      reply_markup=topic_menu(content, item.id, callback_data.screen))
    await callback.answer()
