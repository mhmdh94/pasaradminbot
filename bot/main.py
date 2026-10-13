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
    Like Mirza: receipt is already sent to admin.
    After configured delay, auto-approve pending orders for users
    who have auto_approve OR when global default auto_approve is on.
    """
    try:
        default_auto = await db.get_setting("auto_approve_default", "0") == "1"
        try:
            delay_min = max(0, int(await db.get_setting("auto_approve_delay_minutes", "5")))
        except ValueError:
            delay_min = 5

        pending = await db.get_pending_orders()
        for order in pending:
            if order.get("status") != "pending":
                continue
            # only after delay from updated_at / created_at
            try:
                created = order.get("updated_at") or order.get("created_at")
                # SQLite timestamp string
                if isinstance(created, str):
                    try:
                        created_dt = datetime.fromisoformat(created.replace("Z", ""))
                    except Exception:
                        created_dt = datetime.strptime(created[:19], "%Y-%m-%d %H:%M:%S")
                else:
                    continue
                if datetime.utcnow() - created_dt < timedelta(minutes=delay_min):
                    continue
            except Exception:
                continue

            u = await db.get_bot_user(order["user_id"])
            user_auto = bool(u and u.get("auto_approve"))
            if not (default_auto or user_auto):
                continue

            api = await get_panel_api(order["panel_id"])
            if not api:
                continue
            result = await api.add_volume_to_admin(order["username"], order["volume_gb"])
            if not result.get("success"):
                logger.warning("auto approve failed order %s: %s", order["id"], result.get("message"))
                continue

            await db.update_order(order["id"], status="paid")
            msg = (
                f"✅ پرداخت تأیید شد.\n"
                f"حجم {order['volume_gb']} گیگ به ادمین «{order['username']}» اضافه شد."
            )
            try:
                await bot.send_message(order["user_id"], msg)
            except Exception:
                pass
            try:
                await bot.send_message(
                    settings.ADMIN_ID,
                    f"✅ تأیید خودکار سفارش\n"
                    f"کاربر: <code>{order['user_id']}</code>\n"
                    f"ادمین پنل: <code>{order['username']}</code>\n"
                    f"{order['volume_gb']}GB | {order['price']:,} تومان\n"
                    f"{result.get('message', '')}",
                    parse_mode="HTML",
                )
            except Exception:
                pass
            logger.info("auto-approved order %s", order["id"])
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
