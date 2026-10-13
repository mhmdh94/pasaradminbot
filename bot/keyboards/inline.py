from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from typing import List, Dict


def user_main_keyboard(is_admin: bool = False) -> ReplyKeyboardMarkup:
    b = ReplyKeyboardBuilder()
    b.row(KeyboardButton(text="🛒 خرید حجم"))
    b.row(KeyboardButton(text="👤 مشخصات کاربری"), KeyboardButton(text="🖥 پنل‌های من"))
    b.row(KeyboardButton(text="ℹ️ راهنما"))
    if is_admin:
        b.row(KeyboardButton(text="⚙️ پنل ادمین"))
    return b.as_markup(resize_keyboard=True)


def admin_panel_keyboard() -> ReplyKeyboardMarkup:
    b = ReplyKeyboardBuilder()
    b.row(KeyboardButton(text="🛒 خرید حجم (ادمین)"))
    b.row(KeyboardButton(text="📦 مدیریت پلن‌ها"), KeyboardButton(text="🖥 مدیریت پنل‌ها"))
    b.row(KeyboardButton(text="💰 تنظیمات مالی"), KeyboardButton(text="⚙️ تنظیمات ربات"))
    b.row(KeyboardButton(text="⏰ تنظیمات کرون"), KeyboardButton(text="🗄 تنظیمات بک‌آپ"))
    b.row(KeyboardButton(text="🔍 سرچ کاربر"), KeyboardButton(text="🚫 کاربران بلاک‌شده"))
    b.row(KeyboardButton(text="ℹ️ وضعیت ربات"))
    b.row(KeyboardButton(text="🔙 بازگشت به منوی اصلی"))
    return b.as_markup(resize_keyboard=True)


def cancel_reply() -> ReplyKeyboardMarkup:
    b = ReplyKeyboardBuilder()
    b.row(KeyboardButton(text="❌ انصراف"))
    return b.as_markup(resize_keyboard=True)


def panels_list(panels: List[Dict]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for p in panels:
        st = "✅" if p["is_active"] else "❌"
        b.row(InlineKeyboardButton(text=f"{st} {p['name']}", callback_data=f"panel_{p['id']}"))
    b.row(InlineKeyboardButton(text="➕ افزودن پنل", callback_data="add_panel"))
    b.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="admin_menu"))
    return b.as_markup()


def panel_actions(panel_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🔗 تست اتصال", callback_data=f"test_panel_{panel_id}"))
    b.row(InlineKeyboardButton(text="🗑 حذف", callback_data=f"delete_panel_{panel_id}"))
    b.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="manage_panels"))
    return b.as_markup()


def plans_list(plans: List[Dict]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for p in plans:
        st = "✅" if p["is_active"] else "❌"
        per = round(p["price"] / p["volume_gb"]) if p["volume_gb"] else 0
        b.row(InlineKeyboardButton(
            text=f"{st} {p['volume_gb']}GB | {p['price']:,}ت | هرگیگ {per:,}",
            callback_data=f"plan_{p['id']}"
        ))
    b.row(InlineKeyboardButton(text="➕ افزودن پلن", callback_data="add_plan"))
    b.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="admin_menu"))
    return b.as_markup()


def plan_actions(plan_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="✏️ قیمت", callback_data=f"edit_plan_price_{plan_id}"),
        InlineKeyboardButton(text="🔄 فعال/غیرفعال", callback_data=f"toggle_plan_{plan_id}"),
    )
    b.row(InlineKeyboardButton(text="🗑 حذف", callback_data=f"delete_plan_{plan_id}"))
    b.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="manage_plans"))
    return b.as_markup()


def buy_select_panel(panels: List[Dict]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for p in panels:
        b.row(InlineKeyboardButton(text=f"🖥 {p['name']}", callback_data=f"buy_panel_{p['id']}"))
    b.row(InlineKeyboardButton(text="❌ انصراف", callback_data="cancel_buy"))
    return b.as_markup()


def buy_select_plan(plans: List[Dict]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for p in plans:
        per = round(p["price"] / p["volume_gb"]) if p["volume_gb"] else 0
        b.row(InlineKeyboardButton(
            text=f"📦 {p['volume_gb']}GB — {p['price']:,}ت (هرگیگ {per:,})",
            callback_data=f"buy_plan_{p['id']}"
        ))
    b.row(InlineKeyboardButton(text="❌ انصراف", callback_data="cancel_buy"))
    return b.as_markup()


def confirm_order(order_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="✅ تأیید و افزودن حجم", callback_data=f"approve_order_{order_id}"),
        InlineKeyboardButton(text="❌ رد", callback_data=f"reject_order_{order_id}"),
    )
    return b.as_markup()


def finance_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="✏️ شماره کارت", callback_data="set_card_number"))
    b.row(InlineKeyboardButton(text="✏️ شماره حساب/شبا", callback_data="set_account_number"))
    b.row(InlineKeyboardButton(text="✏️ نام صاحب حساب", callback_data="set_card_owner"))
    b.row(InlineKeyboardButton(text="⚡ تأیید خودکار (پیش‌فرض)", callback_data="toggle_auto_approve_default"))
    b.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="admin_menu"))
    return b.as_markup()


def backup_settings_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="📤 Export", callback_data="backup_export"))
    b.row(InlineKeyboardButton(text="📥 Import", callback_data="backup_import"))
    b.row(InlineKeyboardButton(text="⏰ فاصله بک‌آپ", callback_data="backup_interval"))
    b.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="admin_menu"))
    return b.as_markup()


def bot_settings_keyboard(s: Dict[str, str]) -> InlineKeyboardMarkup:
    def on(k):
        return "✅" if s.get(k) == "1" else "❌"

    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text=f"{on('bot_enabled')} وضعیت ربات", callback_data="tog_bot_enabled"))
    b.row(InlineKeyboardButton(text=f"{on('allow_buy')} امکان خرید حجم", callback_data="tog_allow_buy"))
    b.row(InlineKeyboardButton(text=f"{on('require_phone')} تأیید شماره", callback_data="tog_require_phone"))
    b.row(InlineKeyboardButton(text=f"{on('require_iran_phone')} شماره ایرانی", callback_data="tog_require_iran_phone"))
    b.row(InlineKeyboardButton(text=f"{on('require_verify')} احراز هویت", callback_data="tog_require_verify"))
    b.row(InlineKeyboardButton(text="📢 کانال گزارش", callback_data="set_report_channel"))
    b.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="admin_menu"))
    return b.as_markup()


def cron_settings_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="⏰ فاصله چک حجم", callback_data="set_volume_check_hours"))
    b.row(InlineKeyboardButton(text="📊 آستانه‌های هشدار", callback_data="set_volume_thresholds"))
    b.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="admin_menu"))
    return b.as_markup()


def user_search_kb(uid: int, blocked: bool, verified: bool, auto_ap: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(
        text="✅ آنبلاک" if blocked else "🚫 بلاک",
        callback_data=f"unblock_{uid}" if blocked else f"block_{uid}"
    ))
    b.row(InlineKeyboardButton(
        text="❌ حذف احراز" if verified else "✅ احراز هویت",
        callback_data=f"unverify_{uid}" if verified else f"verify_{uid}"
    ))
    b.row(InlineKeyboardButton(
        text="⚡ خاموش تأیید خودکار" if auto_ap else "⚡ روشن تأیید خودکار",
        callback_data=f"autoap_{uid}"
    ))
    b.row(InlineKeyboardButton(text="📋 سفارشات", callback_data=f"uorders_{uid}"))
    b.row(InlineKeyboardButton(text="🖥 اختصاص پنل", callback_data=f"assignpanel_{uid}"))
    return b.as_markup()
