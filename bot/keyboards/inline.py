from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from typing import List, Dict


def user_main_keyboard(is_admin: bool = False) -> ReplyKeyboardMarkup:
    b = ReplyKeyboardBuilder()
    b.row(KeyboardButton(text="🛒 خرید حجم"))
    b.row(KeyboardButton(text="👤 مشخصات کاربری"), KeyboardButton(text="🖥 پنل من"))
    b.row(KeyboardButton(text="ℹ️ راهنما"))
    if is_admin:
        b.row(KeyboardButton(text="⚙️ پنل ادمین"))
    return b.as_markup(resize_keyboard=True)


def admin_panel_keyboard() -> ReplyKeyboardMarkup:
    b = ReplyKeyboardBuilder()
    b.row(KeyboardButton(text="📊 آمار ربات"))
    b.row(KeyboardButton(text="📦 مدیریت پلن‌ها"), KeyboardButton(text="🖥 مدیریت پنل ربات"))
    b.row(KeyboardButton(text="💰 تنظیمات مالی"), KeyboardButton(text="⚙️ تنظیمات ربات"))
    b.row(KeyboardButton(text="🔍 سرچ کاربر"), KeyboardButton(text="🚫 کاربران بلاک‌شده"))
    b.row(KeyboardButton(text="🔙 بازگشت به منوی اصلی"))
    return b.as_markup(resize_keyboard=True)


def cancel_reply() -> ReplyKeyboardMarkup:
    b = ReplyKeyboardBuilder()
    b.row(KeyboardButton(text="❌ انصراف"))
    return b.as_markup(resize_keyboard=True)


def request_phone_keyboard() -> ReplyKeyboardMarkup:
    b = ReplyKeyboardBuilder()
    b.row(KeyboardButton(text="📱 ارسال شماره تلفن", request_contact=True))
    return b.as_markup(resize_keyboard=True, one_time_keyboard=True)


def panels_list(panels: List[Dict]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for p in panels:
        st = "✅" if p["is_active"] else "❌"
        b.row(InlineKeyboardButton(text=f"{st} {p['name']}", callback_data=f"panel_{p['id']}"))
    # only allow add if no panel exists
    if not panels:
        b.row(InlineKeyboardButton(text="➕ افزودن پنل", callback_data="add_panel"))
    b.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="admin_menu"))
    return b.as_markup()


def panel_actions(panel_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🔗 تست اتصال", callback_data=f"test_panel_{panel_id}"))
    b.row(InlineKeyboardButton(text="🗑 حذف پنل", callback_data=f"delete_panel_{panel_id}"))
    b.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="manage_panels"))
    return b.as_markup()


def plans_list(plans: List[Dict]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for p in plans:
        st = "✅" if p["is_active"] else "❌"
        vol = p["volume_gb"]
        vol_txt = f"{st} {vol // 1024} ترابایت" if vol >= 1024 and vol % 1024 == 0 else f"{st} {vol} گیگ"
        per = round(p["price"] / vol) if vol else 0
        b.row(
            InlineKeyboardButton(text=vol_txt, callback_data=f"plan_{p['id']}"),
            InlineKeyboardButton(text=f"{p['price']:,} ت", callback_data=f"plan_{p['id']}"),
            InlineKeyboardButton(text=f"هرگیگ {per:,}", callback_data=f"plan_{p['id']}"),
        )
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
    b.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="cancel_buy"))
    return b.as_markup()


def buy_select_plan(plans: List[Dict]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for p in plans:
        vol = p["volume_gb"]
        vol_txt = f"{vol // 1024} ترابایت" if vol >= 1024 and vol % 1024 == 0 else f"{vol} گیگ"
        per = round(p["price"] / vol) if vol else 0
        # سه ستون: حجم | مبلغ کل | قیمت هر گیگ
        b.row(
            InlineKeyboardButton(text=vol_txt, callback_data=f"buy_plan_{p['id']}"),
            InlineKeyboardButton(text=f"{p['price']:,} ت", callback_data=f"buy_plan_{p['id']}"),
            InlineKeyboardButton(text=f"هرگیگ {per:,}", callback_data=f"buy_plan_{p['id']}"),
        )
    b.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="cancel_buy"))
    return b.as_markup()


def confirm_order(order_id: int, user_id: int = 0) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="✅ تأیید و افزودن حجم", callback_data=f"approve_order_{order_id}"),
        InlineKeyboardButton(text="❌ رد", callback_data=f"reject_order_{order_id}"),
    )
    if user_id:
        b.row(InlineKeyboardButton(text="👤 اطلاعات کاربر", callback_data=f"uinfo_{user_id}"))
    return b.as_markup()


def start_notify_kb(user_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="👤 اطلاعات کاربر", callback_data=f"uinfo_{user_id}"))
    return b.as_markup()


def finance_keyboard(auto_on: bool = False, auto_minutes: int = 0) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="💳 اطلاعات حساب", callback_data="account_info"))
    b.row(InlineKeyboardButton(text="🏷 مدیریت کد تخفیف", callback_data="discount_menu"))
    auto_txt = f"⚡ تأیید خودکار: {'✅ روشن' if auto_on else '❌ خاموش'}"
    b.row(InlineKeyboardButton(text=auto_txt, callback_data="toggle_auto_approve_default"))
    if auto_on:
        b.row(InlineKeyboardButton(
            text=f"⏱ تأخیر تأیید خودکار: {auto_minutes} دقیقه",
            callback_data="set_auto_approve_delay",
        ))
    b.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="admin_menu"))
    return b.as_markup()


def account_info_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="✏️ شماره کارت", callback_data="set_card_number"))
    b.row(InlineKeyboardButton(text="✏️ شماره حساب/شبا", callback_data="set_account_number"))
    b.row(InlineKeyboardButton(text="✏️ نام صاحب حساب", callback_data="set_card_owner"))
    b.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="finance_back"))
    return b.as_markup()


def discount_menu_keyboard(codes: List[Dict]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for c in codes:
        st = "✅" if c["is_active"] else "❌"
        b.row(InlineKeyboardButton(
            text=f"{st} {c['code']} — {c['percent']}% ({c['used_count']}/{c['max_uses']})",
            callback_data=f"disc_{c['id']}",
        ))
    b.row(InlineKeyboardButton(text="➕ افزودن کد", callback_data="add_discount"))
    b.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="finance_back"))
    return b.as_markup()


def discount_actions(disc_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🔄 روشن/خاموش", callback_data=f"disc_tog_{disc_id}"))
    b.row(InlineKeyboardButton(text="🗑 حذف", callback_data=f"disc_del_{disc_id}"))
    b.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="discount_menu"))
    return b.as_markup()


def payment_discount_kb(order_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🏷 کد تخفیف دارم", callback_data=f"use_disc_{order_id}"))
    b.row(InlineKeyboardButton(text="⏭ بدون تخفیف، ارسال رسید", callback_data=f"skip_disc_{order_id}"))
    b.row(InlineKeyboardButton(text="❌ انصراف", callback_data="cancel_buy"))
    return b.as_markup()


def backup_settings_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="📤 Export", callback_data="backup_export"))
    b.row(InlineKeyboardButton(text="📥 Import", callback_data="backup_import"))
    b.row(InlineKeyboardButton(text="⏰ فاصله بک‌آپ", callback_data="backup_interval"))
    b.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="bot_settings_back"))
    return b.as_markup()


def bot_settings_keyboard(s: Dict[str, str]) -> InlineKeyboardMarkup:
    def on(k):
        return "✅ روشن" if s.get(k) == "1" else "❌ خاموش"

    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text=f"وضعیت ربات: {on('bot_enabled')}", callback_data="tog_bot_enabled"))
    b.row(InlineKeyboardButton(text=f"امکان خرید حجم: {on('allow_buy')}", callback_data="tog_allow_buy"))
    b.row(InlineKeyboardButton(text=f"تأیید شماره: {on('require_phone')}", callback_data="tog_require_phone"))
    b.row(InlineKeyboardButton(text=f"شماره ایرانی: {on('require_iran_phone')}", callback_data="tog_require_iran_phone"))
    b.row(InlineKeyboardButton(text=f"احراز هویت: {on('require_verify')}", callback_data="tog_require_verify"))
    b.row(InlineKeyboardButton(text="📢 کانال گزارش", callback_data="set_report_channel"))
    b.row(InlineKeyboardButton(text="⏰ تنظیمات کرون", callback_data="cron_from_settings"))
    b.row(InlineKeyboardButton(text="🗄 تنظیمات بک‌آپ", callback_data="backup_from_settings"))
    b.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="admin_menu"))
    return b.as_markup()


def cron_settings_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="⏰ فاصله چک حجم", callback_data="set_volume_check_hours"))
    b.row(InlineKeyboardButton(text="📊 آستانه‌های هشدار", callback_data="set_volume_thresholds"))
    b.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="bot_settings_back"))
    return b.as_markup()


def user_search_kb(uid: int, blocked: bool, verified: bool, auto_ap: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(
        text="✅ آنبلاک" if blocked else "🚫 بلاک",
        callback_data=f"unblock_{uid}" if blocked else f"block_{uid}",
    ))
    b.row(InlineKeyboardButton(
        text="❌ حذف احراز" if verified else "✅ احراز هویت",
        callback_data=f"unverify_{uid}" if verified else f"verify_{uid}",
    ))
    b.row(InlineKeyboardButton(
        text="⚡ تأیید خودکار: ✅ روشن" if auto_ap else "⚡ تأیید خودکار: ❌ خاموش",
        callback_data=f"autoap_{uid}",
    ))
    b.row(InlineKeyboardButton(text="📋 سفارشات", callback_data=f"uorders_{uid}"))
    b.row(InlineKeyboardButton(text="🖥 پنل اختصاص‌یافته", callback_data=f"viewup_{uid}"))
    b.row(InlineKeyboardButton(text="➕ اختصاص پنل", callback_data=f"assignpanel_{uid}"))
    return b.as_markup()


def user_panels_admin_kb(uid: int, rows: List[Dict]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for r in rows:
        b.row(InlineKeyboardButton(
            text=f"🗑 حذف {r['admin_username']}",
            callback_data=f"rmup_{uid}_{r['panel_id']}_{r['admin_username']}",
        ))
    b.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data=f"uinfo_{uid}"))
    return b.as_markup()
