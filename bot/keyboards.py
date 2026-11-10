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
    """action: home | photos | topic | consult | manager. screen: start screen to return to."""

    action: str
    topic: str | None = None
    screen: str | None = None


def main_menu(c: Content, screen_name: str | None = None) -> InlineKeyboardMarkup:
    key, screen = c.screen(screen_name)
    rows = []
    for ref in screen.buttons:
        if ref.id == "photos":
            label, data = c.photos.button, Menu(action="photos", screen=key)
        elif ref.id == "consult":
            label, data = c.consultation.button, Menu(action="consult", screen=key)
        else:
            label, data = c.topic(ref.id).button, Menu(action="topic", topic=ref.id, screen=key)
        rows.append([InlineKeyboardButton(text=ref.label or label, callback_data=data.pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _back(c: Content, screen: str | None) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=c.buttons.back, callback_data=Menu(action="home", screen=screen).pack())


def topic_menu(c: Content, topic_id: str, screen: str | None = None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=c.buttons.write_manager,
                                  callback_data=Menu(action="manager", topic=topic_id).pack())],
            [_back(c, screen)],
        ]
    )


def photos_menu(c: Content, screen: str | None = None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=c.photos.album_button, url=str(c.photos.album_url))],
            [_back(c, screen)],
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
