import asyncio
import logging
import os
import shutil
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import FSInputFile
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot.config import settings
from bot.database import db
from bot.handlers.admin import router as admin_router
from bot.services.pasarguard import get_panel_api

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def send_backup(bot: Bot):
    try:
        if not os.path.exists(settings.DB_PATH):
            return
        name = f"auto_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        path = os.path.join(settings.BASE_DIR, "data", name)
        shutil.copy2(settings.DB_PATH, path)
        await bot.send_document(
            settings.ADMIN_ID,
            FSInputFile(path),
            caption=f"🗄 بک‌آپ خودکار\n{datetime.now().strftime('%Y-%m-%d %H:%M')}",
        )
        os.remove(path)
    except Exception as e:
        logger.error("backup: %s", e)


async def check_volume_alerts(bot: Bot):
    try:
        th_raw = await db.get_setting("volume_thresholds", "80,85,90,95,100")
        thresholds = [int(x.strip()) for x in th_raw.split(",") if x.strip().isdigit()]
        if not thresholds:
            return
        rows = await db.get_all_user_panels()
        for r in rows:
            try:
                api = await get_panel_api(r["panel_id"])
                if not api:
                    continue
                admin = await api.get_admin(r["admin_username"])
                if not admin or admin.get("error"):
                    continue
                limit = admin.get("data_limit") or 0
                used = admin.get("used_traffic") or 0
                if not limit:
                    continue
                pct = used / limit * 100
                limit_gb = round(limit / (1024**3), 2)
                used_gb = round(used / (1024**3), 2)
                remain = round(max(limit_gb - used_gb, 0), 2)
                for th in sorted(thresholds):
                    if pct >= th:
                        if await db.was_alert_sent(
                            r["user_id"], r["panel_id"], r["admin_username"], th
                        ):
                            continue
                        msg = (
                            f"⚠️ هشدار حجم ({th}%)\n\n"
                            f"🖥 {r.get('panel_name', '')}\n"
                            f"👤 {r['admin_username']}\n"
                            f"مصرف: {used_gb}/{limit_gb} گیگ ({pct:.0f}%)\n"
                            f"مانده: {remain} گیگ\n\n"
                            "برای تمدید از «خرید حجم» استفاده کنید."
                        )
                        try:
                            await bot.send_message(r["user_id"], msg)
                        except Exception:
                            pass
                        await db.mark_alert_sent(
                            r["user_id"], r["panel_id"], r["admin_username"], th
                        )
            except Exception as e:
                logger.error("volume alert: %s", e)
    except Exception as e:
        logger.error("volume check: %s", e)


async def cleanup_old_orders():
    """Delete non-paid orders older than 30 minutes."""
    try:
        await db.conn.execute(
            """DELETE FROM orders
               WHERE status != 'paid'
               AND datetime(created_at) < datetime('now', '-30 minutes')"""
        )
        await db.conn.commit()
        logger.info("cleaned old unpaid orders")
    except Exception as e:
        logger.error("cleanup orders: %s", e)


async def process_auto_approvals(bot: Bot):
    """
    Mirza-style:
    - Receipt always goes to admin first.
    - After delay, only status=pending orders are auto-approved.
    - Rejected/paid orders are never touched.
    - Global auto ON => all users inherit ON, unless user forced OFF (auto_approve=0).
    - User forced ON (auto_approve=1) => auto even if global OFF.
    - User NULL/missing => inherit global.
    """
    try:
        default_auto = await db.get_setting("auto_approve_default", "0") == "1"
        try:
            delay_min = max(0, int(await db.get_setting("auto_approve_delay_minutes", "5")))
        except ValueError:
            delay_min = 5

        pending = await db.get_pending_for_auto(delay_min)
        for order in pending:
            # re-read — admin may have rejected/approved
            fresh = await db.get_order(order["id"])
            if not fresh or fresh.get("status") != "pending":
                continue

            if not await db.should_auto_approve(fresh["user_id"]):
                continue

            # final race check right before API call
            fresh2 = await db.get_order(fresh["id"])
            if not fresh2 or fresh2.get("status") != "pending":
                continue

            api = await get_panel_api(fresh2["panel_id"])
            if not api:
                continue
            result = await api.add_volume_to_admin(fresh2["username"], fresh2["volume_gb"])
            if not result.get("success"):
                logger.warning("auto approve failed order %s: %s", fresh2["id"], result.get("message"))
                continue

            # only mark paid if still pending
            fresh3 = await db.get_order(fresh2["id"])
            if not fresh3 or fresh3.get("status") != "pending":
                logger.info("skip auto: order %s already %s", fresh2["id"], (fresh3 or {}).get("status"))
                continue

            await db.update_order(fresh2["id"], status="paid")
            msg = (
                f"✅ پرداخت تأیید شد.\n"
                f"حجم {fresh2['volume_gb']} گیگ به ادمین «{fresh2['username']}» اضافه شد."
            )
            try:
                await bot.send_message(fresh2["user_id"], msg)
            except Exception:
                pass
            try:
                await bot.send_message(
                    settings.ADMIN_ID,
                    (
                        f"✅ تأیید خودکار\n"
                        f"کاربر: <code>{fresh2['user_id']}</code>\n"
                        f"ادمین پنل: <code>{fresh2['username']}</code>\n"
                        f"{fresh2['volume_gb']}GB | {fresh2['price']:,} تومان\n"
                        f"{result.get('message', '')}"
                    ),
                    parse_mode="HTML",
                )
            except Exception:
                pass
            logger.info("auto-approved order %s", fresh2["id"])
    except Exception as e:
        logger.error("auto approve: %s", e)



async def on_startup(bot: Bot):
    await db.connect()
    logger.info("DB connected")
    try:
        me = await bot.get_me()
        logger.info("Bot @%s", me.username)
        await bot.send_message(settings.ADMIN_ID, f"✅ ربات روشن شد\n@{me.username}")
    except Exception:
        pass


async def on_shutdown(bot: Bot):
    await db.close()


async def main():
    bot = Bot(token=settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(admin_router)
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    await db.connect()
    try:
        backup_h = max(1, int(await db.get_setting("backup_interval_hours", "24")))
    except ValueError:
        backup_h = 24
    try:
        vol_h = max(1, int(await db.get_setting("volume_check_hours", "6")))
    except ValueError:
        vol_h = 6
    await db.close()

    scheduler = AsyncIOScheduler(timezone="Asia/Tehran")
    scheduler.add_job(send_backup, "interval", hours=backup_h, args=[bot], id="backup")
    scheduler.add_job(check_volume_alerts, "interval", hours=vol_h, args=[bot], id="volume")
    # cleanup unpaid every 5 minutes
    scheduler.add_job(cleanup_old_orders, "interval", minutes=5, id="cleanup")
    # auto-approve checker every 1 minute (respects delay setting)
    scheduler.add_job(process_auto_approvals, "interval", minutes=1, args=[bot], id="auto_approve")
    scheduler.start()
    logger.info("Jobs: backup %sh, volume %sh, cleanup 5m, auto-approve 1m", backup_h, vol_h)

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
