"""Send activity logs to the configured Telegram report channel."""
from __future__ import annotations

import html
import logging
from typing import Optional, Union

from aiogram import Bot

from bot.database import db

logger = logging.getLogger(__name__)


def normalize_chat_id(raw: str) -> Optional[Union[int, str]]:
    if not raw:
        return None
    val = str(raw).strip()
    if not val or val == "-":
        return None
    if val.startswith("@"):
        return val
    try:
        return int(val)
    except ValueError:
        if val.replace("_", "").isalnum():
            return f"@{val}"
        return val


def esc(s) -> str:
    return html.escape(str(s) if s is not None else "")


async def report(bot: Bot, text: str, *, parse_mode: str = "HTML") -> bool:
    """
    Send a log line to the report channel.
    Never raises. Retries without parse_mode if HTML fails.
    """
    try:
        raw = await db.get_setting("report_channel", "")
    except Exception as e:
        logger.error("report: cannot read setting: %s", e)
        return False

    chat_id = normalize_chat_id(raw)
    if not chat_id:
        logger.debug("report: channel not configured (raw=%r)", raw)
        return False

    try:
        await bot.send_message(chat_id, text, parse_mode=parse_mode)
        logger.info("report sent to %s", chat_id)
        return True
    except Exception as e1:
        logger.warning("report HTML failed (chat=%s): %s — retry plain", chat_id, e1)
        try:
            # strip simple tags for plain fallback
            plain = (
                text.replace("<code>", "")
                .replace("</code>", "")
                .replace("<b>", "")
                .replace("</b>", "")
            )
            await bot.send_message(chat_id, plain)
            logger.info("report sent plain to %s", chat_id)
            return True
        except Exception as e2:
            logger.error("report channel FAILED (chat=%s): %s", chat_id, e2)
            return False


async def test_report_channel(bot: Bot, raw_channel: str) -> tuple[bool, str]:
    chat_id = normalize_chat_id(raw_channel)
    if not chat_id:
        return False, "آیدی کانال خالی یا نامعتبر است."
    try:
        await bot.send_message(
            chat_id,
            "✅ کانال گزارش متصل شد.\nاز این به بعد فعالیت‌های مهم ربات اینجا ثبت می‌شود.",
        )
        return True, f"✅ پیام تست ارسال شد به <code>{esc(chat_id)}</code>"
    except Exception as e:
        err = esc(e)
        hint = (
            "\n\nمطمئن شوید:\n"
            "• ربات را <b>ادمین</b> کانال کرده‌اید\n"
            "• اجازه <b>ارسال پیام</b> دارد\n"
            "• کانال خصوصی: آیدی عددی مثل <code>-1001234567890</code>"
        )
        return False, f"❌ ارسال ناموفق: <code>{err}</code>{hint}"
