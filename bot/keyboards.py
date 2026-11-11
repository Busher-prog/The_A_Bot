"""Keyboards.

Inline buttons use the previous bot's callback format "src:<screen>:<action>",
so buttons in messages people already received keep working after the switch.
"""

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from bot.content import Button, Content

CALC_LABEL = "🧮 Калькулятор налогов"


def src(screen: str, action: str) -> str:
    return f"src:{screen}:{action}"


def _label(c: Content, screen: str, b: Button) -> str:
    if b.label:
        return b.label
    if b.id == "photos":
        return c.buttons.photos
    if b.id == "consult":
        return c.buttons.consult
    if b.id == "calc":
        return CALC_LABEL
    if b.id == "bingo":
        return c.bingo.button
    if b.id.startswith("seg_"):
        return c.group_of(screen).topics[b.id[4:]].label
    return b.id


def _inline(c: Content, screen: str, buttons: list[Button]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=_label(c, screen, b), callback_data=src(screen, b.id))]
        for b in buttons
    ])


def start_menu(c: Content, screen: str) -> InlineKeyboardMarkup:
    return _inline(c, screen, c.screen(screen)[1].buttons)


def topic_menu(c: Content, screen: str) -> InlineKeyboardMarkup:
    return _inline(c, screen, c.group_of(screen).topic_buttons)


def photos_menu(c: Content, screen: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=c.photos.album_button, url=str(c.photos.album_url))],
        [InlineKeyboardButton(text=c.buttons.consult, callback_data=src(screen, "consult"))],
    ])


def contact_url_button(username: str | None) -> InlineKeyboardMarkup | None:
    if not username:
        return None
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✍️ Написати напряму", url=f"https://t.me/{username}")
    ]])


def cancel_keyboard(c: Content) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=c.buttons.cancel)]], resize_keyboard=True)


def contact_keyboard(c: Content, share_label: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=share_label, request_contact=True)],
            [KeyboardButton(text=c.buttons.cancel)],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def from_dict(markup: dict) -> InlineKeyboardMarkup:
    """The calculator module builds keyboards as plain dicts."""
    return InlineKeyboardMarkup.model_validate(markup)
