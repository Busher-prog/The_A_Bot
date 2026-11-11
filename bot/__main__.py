"""Entry point: python -m bot"""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from bot.config import Settings
from bot.content import load_content
from bot.handlers import bingo, calculator, forms, manager, menu, posts
from bot.storage import Storage


def build_dispatcher(content, settings, storage) -> Dispatcher:
    dp = Dispatcher(content=content, settings=settings, db=storage)
    # Order matters: manager router last, it catches all remaining messages.
    dp.include_routers(menu.router, calculator.router, posts.router, forms.router,
                       bingo.router, manager.router)
    return dp


async def main() -> None:
    settings = Settings()
    logging.basicConfig(level=settings.log_level,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    content = load_content(settings.texts_path)
    storage = Storage(settings.data_dir)

    bot = Bot(settings.bot_token.get_secret_value(),
              default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = build_dispatcher(content, settings, storage)

    await bot.set_my_commands(
        [BotCommand(command=cmd, description=desc) for cmd, desc in content.commands.items()]
    )
    # Profile texts live in texts.yaml too; only send them when they changed.
    profile = content.profile
    if (await bot.get_my_description()).description != profile.description.strip():
        await bot.set_my_description(profile.description.strip())
    if (await bot.get_my_short_description()).short_description != profile.short_description.strip():
        await bot.set_my_short_description(profile.short_description.strip())
    await bot.delete_webhook(drop_pending_updates=False)

    nudges = asyncio.create_task(posts.nudge_loop(bot, settings, storage))
    logging.info("Bot started; data in %s; manager chat %s", settings.data_dir,
                 settings.managers_chat_id or "NOT SET")
    try:
        await dp.start_polling(bot, allowed_updates=["message", "edited_message", "callback_query"])
    finally:
        nudges.cancel()


if __name__ == "__main__":
    asyncio.run(main())
