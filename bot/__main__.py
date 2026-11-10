"""Entry point: python -m bot"""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from bot.config import Settings
from bot.content import load_content
from bot.handlers import consultation, manager, menu


async def main() -> None:
    settings = Settings()
    logging.basicConfig(level=settings.log_level,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    content = load_content(settings.texts_path)

    bot = Bot(settings.bot_token.get_secret_value(),
              default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(content=content, settings=settings)
    # Order matters: the manager router catches all remaining free-form messages.
    dp.include_routers(menu.router, consultation.router, manager.router)

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
    logging.info("Bot started")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
