import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from config.settings import settings
from handlers import common, search, results


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

async def background_check(bot: Bot, interval: int):
    while True:
        # Здесь добавьте логику фоновой проверки
        await asyncio.sleep(interval)

async def on_startup(bot: Bot, dp: Dispatcher):
    asyncio.create_task(background_check(bot, interval=600))

async def main():
    bot = Bot(token=settings.BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    
    # Регистрация роутеров
    dp.include_router(common.router)
    dp.include_router(search.router)
    dp.include_router(results.router)

    # Регистрация функции on_startup
    dp.startup.register(lambda: on_startup(bot, dp))

    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
