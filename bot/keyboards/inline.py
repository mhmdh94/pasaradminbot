from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from typing import List, Dict


def admin_main_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🛒 خرید حجم", callback_data="buy_volume")
    )
    builder.row(
        InlineKeyboardButton(text="📦 مدیریت پلن‌ها", callback_data="manage_plans"),
        InlineKeyboardButton(text="🖥 مدیریت پنل‌ها", callback_data="manage_panels")
    )
    builder.row(
        InlineKeyboardButton(text="💳 تنظیمات کارت", callback_data="card_settings"),
        InlineKeyboardButton(text="📋 سفارش‌های در انتظار", callback_data="pending_orders")
    )
    builder.row(
        InlineKeyboardButton(text="🗄 بک‌آپ دیتابیس", callback_data="backup_now"),
        InlineKeyboardButton(text="ℹ️ وضعیت ربات", callback_data="bot_status")
    )
    return builder.as_markup()


def panels_list(panels: List[Dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for p in panels:
        status = "✅" if p["is_active"] else "❌"
        builder.row(
            InlineKeyboardButton(
                text=f"{status} {p['name']}",
                callback_data=f"panel_{p['id']}"
            )
        )
    builder.row(
        InlineKeyboardButton(text="➕ افزودن پنل جدید", callback_data="add_panel")
    )
    builder.row(
        InlineKeyboardButton(text="🔙 بازگشت", callback_data="admin_menu")
    )
    return builder.as_markup()


def panel_actions(panel_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🔗 تست اتصال", callback_data=f"test_panel_{panel_id}")
    )
    builder.row(
        InlineKeyboardButton(text="🗑 حذف پنل", callback_data=f"delete_panel_{panel_id}")
    )
    builder.row(
        InlineKeyboardButton(text="🔙 بازگشت", callback_data="manage_panels")
    )
    return builder.as_markup()


def plans_list(plans: List[Dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for p in plans:
        status = "✅" if p["is_active"] else "❌"
        builder.row(
            InlineKeyboardButton(
                text=f"{status} {p['title']} | {p['volume_gb']}GB | {p['price']:,} تومان",
                callback_data=f"plan_{p['id']}"
            )
        )
    builder.row(
        InlineKeyboardButton(text="➕ افزودن پلن جدید", callback_data="add_plan")
    )
    builder.row(
        InlineKeyboardButton(text="🔙 بازگشت", callback_data="admin_menu")
    )
    return builder.as_markup()


def plan_actions(plan_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✏️ ویرایش قیمت", callback_data=f"edit_plan_price_{plan_id}"),
        InlineKeyboardButton(text="🔄 فعال/غیرفعال", callback_data=f"toggle_plan_{plan_id}")
    )
    builder.row(
        InlineKeyboardButton(text="🗑 حذف پلن", callback_data=f"delete_plan_{plan_id}")
    )
    builder.row(
        InlineKeyboardButton(text="🔙 بازگشت", callback_data="manage_plans")
    )
    return builder.as_markup()


def buy_select_panel(panels: List[Dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for p in panels:
        builder.row(
            InlineKeyboardButton(
                text=f"🖥 {p['name']}",
                callback_data=f"buy_panel_{p['id']}"
            )
        )
    builder.row(
        InlineKeyboardButton(text="🔙 بازگشت", callback_data="admin_menu")
    )
    return builder.as_markup()


def buy_select_plan(plans: List[Dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for p in plans:
        builder.row(
            InlineKeyboardButton(
                text=f"📦 {p['title']} — {p['volume_gb']}GB — {p['price']:,} تومان",
                callback_data=f"buy_plan_{p['id']}"
            )
        )
    builder.row(
        InlineKeyboardButton(text="🔙 انصراف", callback_data="admin_menu")
    )
    return builder.as_markup()


def confirm_order(order_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ تأیید پرداخت و افزودن حجم", callback_data=f"approve_order_{order_id}"),
        InlineKeyboardButton(text="❌ رد کردن", callback_data=f"reject_order_{order_id}")
    )
    return builder.as_markup()


def cancel_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="❌ انصراف", callback_data="cancel_state")
    )
    return builder.as_markup()


def back_to_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🔙 منوی اصلی", callback_data="admin_menu")
    )
    return builder.as_markup()