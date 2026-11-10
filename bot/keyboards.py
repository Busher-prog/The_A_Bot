"""Keyboards and callback data."""

from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from bot.content import Content


class Menu(CallbackData, prefix="m"):
    """action: home | photos | topic | consult | manager"""

    action: str
    topic: str | None = None


def main_menu(c: Content) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=c.photos.button, callback_data=Menu(action="photos").pack())]]
    rows += [
        [InlineKeyboardButton(text=t.button, callback_data=Menu(action="topic", topic=t.id).pack())]
        for t in c.topics
    ]
    rows.append(
        [InlineKeyboardButton(text=c.consultation.button, callback_data=Menu(action="consult").pack())]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def topic_menu(c: Content, topic_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=c.buttons.write_manager,
                                  callback_data=Menu(action="manager", topic=topic_id).pack())],
            [InlineKeyboardButton(text=c.buttons.back, callback_data=Menu(action="home").pack())],
        ]
    )


def photos_menu(c: Content) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=c.photos.album_button, url=str(c.photos.album_url))],
            [InlineKeyboardButton(text=c.buttons.back, callback_data=Menu(action="home").pack())],
        ]
    )


def cancel_keyboard(c: Content) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=c.buttons.cancel)]], resize_keyboard=True)


def contact_keyboard(c: Content) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=c.consultation.share_contact_button, request_contact=True)],
            [KeyboardButton(text=c.buttons.cancel)],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
