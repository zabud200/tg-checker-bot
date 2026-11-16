import asyncio
from aiogram import Bot, Dispatcher
from config import BOT_TOKEN
from services.db import init_db
from handlers import user, admin

async def main():
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN не найден"); return
    init_db()
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(admin.router)
    dp.include_router(user.router)
    print("Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
