import asyncio
import logging
import os
import shutil
from datetime import datetime

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import FSInputFile
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot.config import settings
from bot.database import db
from bot.handlers.admin import router as admin_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def send_backup(bot: Bot):
    try:
        db_path = settings.DB_PATH
        if not os.path.exists(db_path):
            return
        backup_name = f"auto_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        backup_path = os.path.join(settings.BASE_DIR, "data", backup_name)
        shutil.copy2(db_path, backup_path)
        await bot.send_document(
            chat_id=settings.ADMIN_ID,
            document=FSInputFile(backup_path),
            caption=f"🗄 بک‌آپ خودکار\n📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        os.remove(backup_path)
        logger.info("Auto backup sent")
    except Exception as e:
        logger.error(f"Backup failed: {e}")


async def on_startup(bot: Bot):
    await db.connect()
    logger.info("Database connected")
    os.makedirs(os.path.dirname(settings.DB_PATH), exist_ok=True)
    # default backup interval if not set
    existing = await db.get_setting("backup_interval_hours", "")
    if not existing:
        await db.set_setting("backup_interval_hours", "24")
    me = await bot.get_me()
    logger.info(f"Bot started: @{me.username}")
    try:
        await bot.send_message(settings.ADMIN_ID, f"✅ ربات راه‌اندازی شد.\n@{me.username}")
    except Exception:
        pass


async def on_shutdown(bot: Bot):
    await db.close()
    logger.info("Bot stopped")


async def main():
    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(admin_router)
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    scheduler = AsyncIOScheduler(timezone="Asia/Tehran")

    # Read interval from DB after connect - use job that re-reads, or fixed hours from env then DB
    # Simple approach: interval hours from setting, default 24
    await db.connect()
    hours_str = await db.get_setting("backup_interval_hours", "24")
    try:
        hours = max(1, int(hours_str))
    except ValueError:
        hours = 24
    await db.close()

    scheduler.add_job(send_backup, "interval", hours=hours, args=[bot], id="auto_backup")
    scheduler.start()
    logger.info(f"Auto backup every {hours} hour(s)")

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
