import os
import shutil
from datetime import datetime
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.config import settings
from bot.database import db
from bot.keyboards.inline import (
    user_main_keyboard, admin_panel_keyboard, cancel_reply,
    panels_list, panel_actions, plans_list, plan_actions,
    buy_select_panel, buy_select_plan, confirm_order,
    finance_keyboard, account_info_keyboard, discount_menu_keyboard,
    discount_actions, payment_discount_kb, backup_settings_keyboard,
    bot_settings_keyboard, cron_settings_keyboard, user_search_kb,
    start_notify_kb, user_panels_admin_kb, request_phone_keyboard,
)
from bot.services.pasarguard import get_panel_api
from bot.utils.report import report, test_report_channel, normalize_chat_id

router = Router()


class Form(StatesGroup):
    add_panel_name = State()
    add_panel_url = State()
    add_panel_user = State()
    add_panel_pass = State()
    add_plan_title = State()
    add_plan_volume = State()
    add_plan_price = State()
    edit_plan_price = State()
    buy_username = State()
    waiting_receipt = State()
    set_card_number = State()
    set_account_number = State()
    set_card_owner = State()
    backup_interval = State()
    backup_import = State()
    search_user = State()
    set_report_channel = State()
    set_volume_check_hours = State()
    set_volume_thresholds = State()
    assign_panel_username = State()
    add_disc_code = State()
    add_disc_percent = State()
    add_disc_uses = State()
    enter_discount = State()
    set_auto_delay = State()


def is_admin(uid: int) -> bool:
    return uid == settings.ADMIN_ID


async def check_user_access(message: Message, *, need_buy: bool = False) -> bool:
    """Mirza-style gates: bot on, phone, verify. Admins always pass."""
    uid = message.from_user.id
    if is_admin(uid):
        return True
    if await db.is_blocked(uid):
        await message.answer("🚫 شما بلاک شده‌اید.")
        return False
    if await db.get_setting("bot_enabled", "1") != "1":
        await message.answer("⛔️ ربات خاموش است.")
        return False
    if need_buy and await db.get_setting("allow_buy", "1") != "1":
        await message.answer("⛔️ خرید حجم فعلاً غیرفعال است.")
        return False
    u = await db.get_bot_user(uid)
    if await db.get_setting("require_phone", "0") == "1":
        phone = (u or {}).get("phone") if u else None
        if not phone:
            await message.answer(
                "📱 برای استفاده از ربات باید شماره تلفن خود را تأیید کنید.\nدکمه زیر را بزنید:",
                reply_markup=request_phone_keyboard(),
            )
            return False
    if await db.get_setting("require_verify", "0") == "1":
        if not u or not u.get("is_verified"):
            await message.answer(
                "🪪 حساب شما هنوز احراز هویت نشده است.\n"
                "پس از تأیید توسط ادمین می‌توانید از ربات استفاده کنید."
            )
            return False
    return True


def is_iran_phone(phone: str) -> bool:
    p = "".join(ch for ch in phone if ch.isdigit() or ch == "+")
    if p.startswith("+98"):
        p = "0" + p[3:]
    if p.startswith("98") and len(p) >= 12:
        p = "0" + p[2:]
    return p.startswith("09") and len(p) == 11






async def go_back(message: Message, state: FSMContext, admin_ctx: bool = False):
    await state.clear()
    if admin_ctx and is_admin(message.from_user.id):
        await message.answer("⚙️ پنل ادمین:", reply_markup=admin_panel_keyboard())
    else:
        await message.answer(
            "🏠 منوی اصلی:",
            reply_markup=user_main_keyboard(is_admin=is_admin(message.from_user.id)),
        )


# ==================== START ====================

@router.message(CommandStart())
@router.message(Command("start"))
@router.message(F.text.in_({"/start", "start", "/Start"}))
async def cmd_start(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    uid = message.from_user.id
    if await db.is_blocked(uid) and not is_admin(uid):
        await message.answer("🚫 شما بلاک شده‌اید.")
        return

    bot_on = await db.get_setting("bot_enabled", "1")
    if bot_on != "1" and not is_admin(uid):
        await message.answer("⛔️ ربات موقتاً غیرفعال است.")
        return

    # only first-time start notifies admin
    existing = await db.get_bot_user(uid)
    is_first_start = existing is None

    await db.upsert_bot_user(
        uid,
        username=message.from_user.username,
        full_name=message.from_user.full_name or "",
    )

    if is_first_start and not is_admin(uid):
        try:
            uname = f"@{message.from_user.username}" if message.from_user.username else "-"
            await bot.send_message(
                settings.ADMIN_ID,
                (
                    "🆕 کاربر جدید — اولین استارت\n"
                    f"آیدی: <code>{uid}</code>\n"
                    f"نام: {message.from_user.full_name or '-'}\n"
                    f"یوزرنیم: {uname}"
                ),
                parse_mode="HTML",
                reply_markup=start_notify_kb(uid),
            )
            await report(
                bot,
                f"🆕 کاربر جدید | <code>{uid}</code> | {message.from_user.full_name or '-'} | {uname}",
            )
        except Exception:
            pass

    admin = is_admin(uid)
    text = "👋 به ربات خرید حجم پنل خوش آمدید.\n\nاز منوی زیر استفاده کنید:"
    if admin:
        text += "\n\n⚙️ شما ادمین هستید."
    await message.answer(text, reply_markup=user_main_keyboard(is_admin=admin))
    # if phone required and not set, prompt immediately
    if not admin and await db.get_setting("require_phone", "0") == "1":
        u = await db.get_bot_user(uid)
        if not u or not u.get("phone"):
            await message.answer(
                "📱 برای ادامه، شماره تلفن خود را ارسال کنید:",
                reply_markup=request_phone_keyboard(),
            )
            return
    if not admin and await db.get_setting("require_verify", "0") == "1":
        u = await db.get_bot_user(uid)
        if not u or not u.get("is_verified"):
            await message.answer(
                "🪪 حساب شما احراز هویت نشده. منتظر تأیید ادمین بمانید."
            )



@router.message(F.contact)
async def on_contact(message: Message, state: FSMContext):
    """Save shared phone (must be the user's own contact)."""
    uid = message.from_user.id
    contact = message.contact
    if contact.user_id and contact.user_id != uid:
        await message.answer("❌ فقط شماره خودتان را ارسال کنید.")
        return
    phone = contact.phone_number or ""
    if not phone.startswith("+"):
        phone = "+" + phone.lstrip("+")
    if await db.get_setting("require_iran_phone", "0") == "1":
        if not is_iran_phone(phone):
            await message.answer(
                "❌ فقط شماره موبایل ایرانی (09xxxxxxxxx) پذیرفته می‌شود.\nدوباره تلاش کنید:",
                reply_markup=request_phone_keyboard(),
            )
            return
    await db.upsert_bot_user(uid, username=message.from_user.username, full_name=message.from_user.full_name or "")
    await db.update_bot_user(uid, phone=phone)
    await state.clear()
    await message.answer(
        f"✅ شماره شما ثبت شد: <code>{phone}</code>",
        parse_mode="HTML",
        reply_markup=user_main_keyboard(is_admin=is_admin(uid)),
    )
    await report(
        message.bot,
        f"📱 تأیید شماره\nکاربر: <code>{uid}</code>\nشماره: <code>{phone}</code>",
    )


@router.message(F.text == "🔙 بازگشت به منوی اصلی")
async def back_home(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "🏠 منوی اصلی:",
        reply_markup=user_main_keyboard(is_admin=is_admin(message.from_user.id)),
    )


@router.message(F.text == "❌ انصراف")
async def cancel_btn(message: Message, state: FSMContext):
    data = await state.get_data()
    admin_ctx = bool(data.get("admin_context")) and is_admin(message.from_user.id)
    await go_back(message, state, admin_ctx)


@router.message(F.text == "ℹ️ راهنما")
async def help_msg(message: Message):
    await message.answer(
        "📖 راهنما\n\n"
        "۱) خرید حجم → انتخاب پلن → یوزرنیم ادمین پنل\n"
        "۲) واریز و ارسال عکس رسید\n"
        "۳) بعد از تأیید، حجم به ادمین پنل اضافه می‌شود.\n\n"
        "«پنل‌های من» فقط برای پنل‌هایی است که ادمین برای شما تعریف کرده."
    )


@router.message(F.text == "👤 مشخصات کاربری")
async def user_profile(message: Message):
    if not await check_user_access(message):
        return
    uid = message.from_user.id
    stats = await db.user_stats(uid)
    u = await db.get_bot_user(uid)
    phone = (u or {}).get("phone") or "-"
    lines = [
        "👤 مشخصات کاربری\n",
        f"آیدی: <code>{uid}</code>",
        f"نام: {message.from_user.full_name or '-'}",
        f"یوزرنیم: @{message.from_user.username or '-'}",
        f"شماره: <code>{phone}</code>",
        f"جمع حجم خریداری‌شده: {stats.get('total_volume', 0)} گیگ",
        f"تعداد سفارش موفق: {stats.get('paid_count', 0)}",
    ]
    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(F.text == "🖥 پنل من")
async def my_panels(message: Message):
    if not await check_user_access(message):
        return
    rows = await db.get_user_panels(message.from_user.id)
    if not rows:
        await message.answer("هنوز پنلی برای شما تعریف نشده. با پشتیبانی تماس بگیرید.")
        return
    for r in rows:
        api = await get_panel_api(r["panel_id"])
        if not api:
            await message.answer(f"🖥 {r['panel_name']}\nادمین: {r['admin_username']}\n❌ اتصال ناموفق")
            continue
        admin_info = await api.get_admin(r["admin_username"])
        if not admin_info or admin_info.get("error"):
            await message.answer(
                f"🖥 {r['panel_name']}\nادمین: <code>{r['admin_username']}</code>\n❌ ادمین پیدا نشد",
                parse_mode="HTML",
            )
            continue
        limit = admin_info.get("data_limit") or 0
        used = admin_info.get("used_traffic") or 0
        limit_gb = round(limit / (1024**3), 2) if limit else 0
        used_gb = round(used / (1024**3), 2)
        remain = round(max(limit_gb - used_gb, 0), 2) if limit else "نامحدود"
        pct = round(used / limit * 100, 1) if limit else 0
        status = admin_info.get("status") or "-"
        await message.answer(
            (
                f"🖥 <b>{r['panel_name']}</b>\n"
                f"👤 ادمین پنل: <code>{r['admin_username']}</code>\n"
                f"📌 وضعیت: {status}\n"
                f"📊 حجم کل: {limit_gb} گیگ\n"
                f"📉 مصرف: {used_gb} گیگ ({pct}%)\n"
                f"✅ مانده: {remain} گیگ"
            ),
            parse_mode="HTML",
        )


# ==================== BUY ====================

@router.message(F.text == "🛒 خرید حجم")
async def buy_start(message: Message, state: FSMContext):
    if not await check_user_access(message, need_buy=True):
        return
    panels = await db.get_panels()
    plans = await db.get_plans()
    if not panels or not plans:
        await message.answer("⚠️ پنل یا پلن تعریف نشده.")
        return
    if len(panels) == 1:
        await state.update_data(panel_id=panels[0]["id"])
        await message.answer("🛍 انتخاب محصول\nیکی از محصولات زیر را انتخاب کنید:", reply_markup=buy_select_plan(plans))
    else:
        await message.answer("🖥 پنل را انتخاب کنید:", reply_markup=buy_select_panel(panels))


@router.callback_query(F.data == "cancel_buy")
async def cancel_buy(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    admin_ctx = data.get("admin_context") and is_admin(callback.from_user.id)
    await state.clear()
    try:
        await callback.message.edit_text("❌ لغو شد.")
    except Exception:
        pass
    if admin_ctx:
        await callback.message.answer("⚙️ پنل ادمین:", reply_markup=admin_panel_keyboard())
    else:
        await callback.message.answer(
            "🏠 منوی اصلی:",
            reply_markup=user_main_keyboard(is_admin=is_admin(callback.from_user.id)),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("buy_panel_"))
async def buy_panel_cb(callback: CallbackQuery, state: FSMContext):
    await state.update_data(panel_id=int(callback.data.split("_")[2]))
    plans = await db.get_plans()
    await callback.message.edit_text("🛍 انتخاب محصول\nیکی از محصولات زیر را انتخاب کنید:", reply_markup=buy_select_plan(plans))
    await callback.answer()


@router.callback_query(F.data.startswith("buy_plan_"))
async def buy_plan_cb(callback: CallbackQuery, state: FSMContext):
    plan = await db.get_plan(int(callback.data.split("_")[2]))
    if not plan or not plan["is_active"]:
        await callback.answer("پلن موجود نیست", show_alert=True)
        return
    per = round(plan["price"] / plan["volume_gb"]) if plan["volume_gb"] else 0
    await state.update_data(
        plan_id=plan["id"], volume_gb=plan["volume_gb"], price=plan["price"], title=plan["title"]
    )
    await state.set_state(Form.buy_username)
    await callback.message.edit_text(
        (
            f"📦 حجم: <b>{plan['volume_gb']} گیگ</b>\n"
            f"💰 مبلغ: {plan['price']:,} تومان\n"
            f"📈 هر گیگ: {per:,} تومان\n\n"
            "👤 یوزرنیم <b>ادمین پنل</b> را وارد کنید:"
        ),
        parse_mode="HTML",
    )
    await callback.message.answer("یوزرنیم ادمین:", reply_markup=cancel_reply())
    await callback.answer()


@router.message(Form.buy_username)
async def process_username(message: Message, state: FSMContext, bot: Bot):
    if message.text == "❌ انصراف":
        return
    uid = message.from_user.id
    username = message.text.strip()
    data = await state.get_data()
    api = await get_panel_api(data["panel_id"])
    if not api:
        await state.clear()
        await message.answer("❌ اتصال به پنل ناموفق.", reply_markup=user_main_keyboard(is_admin=is_admin(uid)))
        return

    admin_info = await api.get_admin(username)
    if not admin_info or admin_info.get("error"):
        # only track spam for non-admins
        if not is_admin(uid):
            attempts = await db.inc_attempts(uid)
            if attempts >= 10:
                await db.block_user(uid, "10 wrong admin username")
                await state.clear()
                await message.answer("🚫 به دلیل ورود اشتباه مکرر بلاک شدید.")
                try:
                    await bot.send_message(
                        settings.ADMIN_ID,
                        f"🚫 بلاک کاربر <code>{uid}</code> — ۱۰ بار یوزرنیم اشتباه",
                        parse_mode="HTML",
                    )
                    await report(
                        bot,
                        f"🚫 بلاک خودکار <code>{uid}</code> — ۱۰ یوزرنیم اشتباه",
                    )
                except Exception:
                    pass
                return
            # do NOT show remaining attempts to users as marketing text for admin mistakes —
            # user asked: don't show remaining to admin; for users we can keep generic message
            await message.answer(
                f"❌ ادمینی با نام «{username}» پیدا نشد. دوباره تلاش کنید.",
                reply_markup=cancel_reply(),
            )
        else:
            await message.answer(
                f"❌ ادمینی با نام «{username}» در پنل پیدا نشد.\n"
                "یوزرنیم را دقیق وارد کنید یا اتصال پنل را تست کنید.",
                reply_markup=cancel_reply(),
            )
        return

    await db.reset_attempts(uid)

    order_id = await db.create_order(
        uid, data["panel_id"], username, data["plan_id"], data["volume_gb"], data["price"]
    )
    await state.update_data(order_id=order_id, username=username, price=data["price"], volume_gb=data["volume_gb"])

    await report(
        bot,
        f"🛒 سفارش جدید\n"
        f"کاربر: <code>{uid}</code>\n"
        f"ادمین پنل: <code>{username}</code>\n"
        f"{data['volume_gb']}GB | {data['price']:,} تومان",
    )

    # check if any active discount codes exist
    discs = [d for d in await db.get_discounts() if d["is_active"] and d["used_count"] < d["max_uses"]]
    if discs:
        await state.set_state(Form.enter_discount)
        await message.answer(
            (
                f"✅ سفارش ثبت شد\n\n"
                f"👤 ادمین پنل: <code>{username}</code>\n"
                f"📦 حجم خرید: {data['volume_gb']} گیگ\n"
                f"💰 مبلغ: <b>{data['price']:,} تومان</b>\n\n"
                "کد تخفیف دارید؟"
            ),
            parse_mode="HTML",
            reply_markup=payment_discount_kb(order_id),
        )
        return

    await state.set_state(Form.waiting_receipt)
    card = await db.get_setting("card_number", settings.CARD_NUMBER)
    account = await db.get_setting("account_number", "")
    owner = await db.get_setting("card_owner", settings.CARD_OWNER)
    text = (
        "✅ سفارش ثبت شد\n\n"
        f"👤 ادمین پنل: <code>{username}</code>\n"
        f"📦 حجم خرید: {data['volume_gb']} گیگ\n"
        f"💰 مبلغ: <b>{data['price']:,} تومان</b>\n\n"
        f"💳 کارت:\n<code>{card}</code>\n\n"
    )
    if account:
        text += f"🏦 حساب/شبا:\n<code>{account}</code>\n\n"
    text += f"👤 صاحب حساب: {owner}\n\nعکس رسید را ارسال کنید."
    await message.answer(text, parse_mode="HTML", reply_markup=cancel_reply())



@router.message(Form.waiting_receipt, F.photo)
async def process_receipt(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    order_id = data.get("order_id")
    if not order_id:
        await state.clear()
        return
    file_id = message.photo[-1].file_id
    await db.update_order(order_id, receipt_file_id=file_id, status="pending")
    order = await db.get_order(order_id)
    panel = await db.get_panel(order["panel_id"])

    will_auto = await db.should_auto_approve(message.from_user.id)
    if will_auto:
        try:
            delay_m = int(await db.get_setting("auto_approve_delay_minutes", "5"))
        except ValueError:
            delay_m = 5
        auto_note = f"⚡ تأیید خودکار فعال است (بعد از {delay_m} دقیقه)"
    else:
        auto_note = (
            "⚠️ تأیید خودکار برای این کاربر خاموش است — "
            "حتماً دستی تأیید یا رد کنید"
        )

    lines = [
        "🧾 رسید پرداخت",
        "",
        f"👤 تلگرام: <code>{message.from_user.id}</code>",
        f"👤 ادمین پنل: <code>{order['username']}</code>",
        f"🖥 {panel['name'] if panel else '-'}",
        f"📦 {order['volume_gb']} گیگ | 💰 {order['price']:,} تومان",
        "",
        auto_note,
    ]
    caption = "\n".join(lines)
    try:
        await bot.send_photo(
            settings.ADMIN_ID, photo=file_id, caption=caption,
            parse_mode="HTML",
            reply_markup=confirm_order(order_id, message.from_user.id),
        )
    except Exception:
        pass
    await state.clear()
    await message.answer(
        "✅ رسید ارسال شد. منتظر تأیید بمانید.",
        reply_markup=user_main_keyboard(is_admin=is_admin(message.from_user.id)),
    )
    await report(
        bot,
        f"🧾 رسید جدید\n"
        f"کاربر: <code>{message.from_user.id}</code>\n"
        f"ادمین پنل: <code>{order['username']}</code>\n"
        f"{order['volume_gb']}GB | {order['price']:,} تومان",
    )


@router.message(Form.waiting_receipt)
async def receipt_wrong(message: Message):
    if message.text == "❌ انصراف":
        return
    await message.answer("فقط عکس رسید بفرستید.")


# ==================== ADMIN ====================

@router.message(F.text == "⚙️ پنل ادمین")
async def admin_panel(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    await message.answer("⚙️ پنل ادمین:", reply_markup=admin_panel_keyboard())


@router.callback_query(F.data == "admin_menu")
async def cb_admin_menu(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.clear()
    await callback.message.answer("⚙️ پنل ادمین:", reply_markup=admin_panel_keyboard())
    await callback.answer()


# --- panels ---
@router.message(F.text == "🖥 مدیریت پنل ربات")
@router.callback_query(F.data == "manage_panels")
async def manage_panels(event: Message | CallbackQuery):
    if not is_admin(event.from_user.id):
        return
    panels = await db.get_panels(active_only=False)
    text = "🖥 مدیریت پنل ربات:" + ("" if panels else "\nهیچ پنلی نیست.")
    kb = panels_list(panels)
    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, reply_markup=kb)
        await event.answer()
    else:
        await event.answer(text, reply_markup=kb)


@router.callback_query(F.data == "add_panel")
async def add_panel(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(Form.add_panel_name)
    await state.update_data(admin_context=True)
    await callback.message.answer("نام پنل:", reply_markup=cancel_reply())
    await callback.answer()


@router.message(Form.add_panel_name)
async def p_name(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id) or message.text == "❌ انصراف":
        return
    await state.update_data(name=message.text.strip())
    await state.set_state(Form.add_panel_url)
    await message.answer("آدرس پنل (https://...):")


@router.message(Form.add_panel_url)
async def p_url(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id) or message.text == "❌ انصراف":
        return
    url = message.text.strip().rstrip("/")
    if not url.startswith("http"):
        await message.answer("با http شروع شود.")
        return
    await state.update_data(url=url)
    await state.set_state(Form.add_panel_user)
    await message.answer("یوزرنیم ادمین پنل (برای API):")


@router.message(Form.add_panel_user)
async def p_user(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id) or message.text == "❌ انصراف":
        return
    await state.update_data(username=message.text.strip())
    await state.set_state(Form.add_panel_pass)
    await message.answer("پسورد:")


@router.message(Form.add_panel_pass)
async def p_pass(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id) or message.text == "❌ انصراف":
        return
    data = await state.get_data()
    pid = await db.add_panel(data["name"], data["url"], data["username"], message.text.strip())
    await state.clear()
    api = await get_panel_api(pid)
    test = await api.test_connection() if api else {"success": False, "message": "خطا"}
    await message.answer(f"✅ پنل اضافه شد.\n{test['message']}", reply_markup=admin_panel_keyboard())


@router.callback_query(F.data.regexp(r"^panel_\d+$"))
async def panel_detail(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    p = await db.get_panel(int(callback.data.split("_")[1]))
    if not p:
        return
    await callback.message.edit_text(
        f"🖥 <b>{p['name']}</b>\n<code>{p['url']}</code>\n👤 {p['username']}",
        reply_markup=panel_actions(p["id"]),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("test_panel_"))
async def test_panel(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    api = await get_panel_api(int(callback.data.split("_")[2]))
    await callback.answer("تست...")
    r = await api.test_connection() if api else {"message": "خطا"}
    await callback.message.answer(r["message"])


@router.callback_query(F.data.startswith("delete_panel_"))
async def del_panel(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    await db.delete_panel(int(callback.data.split("_")[2]))
    await callback.answer("حذف شد")
    await callback.message.edit_text("🖥 مدیریت پنل‌ها:", reply_markup=panels_list(await db.get_panels(False)))


# --- plans ---
@router.message(F.text == "📦 مدیریت پلن‌ها")
@router.callback_query(F.data == "manage_plans")
async def manage_plans(event: Message | CallbackQuery):
    if not is_admin(event.from_user.id):
        return
    plans = await db.get_plans(False)
    text = "📦 پلن‌ها (حجم | قیمت | هرگیگ):"
    kb = plans_list(plans)
    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, reply_markup=kb)
        await event.answer()
    else:
        await event.answer(text, reply_markup=kb)


@router.callback_query(F.data == "add_plan")
async def add_plan(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(Form.add_plan_volume)
    await state.update_data(admin_context=True, title="volume")
    await callback.message.answer("حجم به گیگ (حداقل ۵۰۰):", reply_markup=cancel_reply())
    await callback.answer()


@router.message(Form.add_plan_volume)
async def plan_vol(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id) or message.text == "❌ انصراف":
        return
    try:
        v = int(message.text.strip())
        if v < 500:
            raise ValueError
    except ValueError:
        await message.answer("عدد معتبر ≥ ۵۰۰")
        return
    await state.update_data(volume_gb=v, title=f"{v}GB")
    await state.set_state(Form.add_plan_price)
    await message.answer("قیمت به تومان:")


@router.message(Form.add_plan_price)
async def plan_price(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id) or message.text == "❌ انصراف":
        return
    try:
        price = int(message.text.strip().replace(",", "").replace("،", ""))
    except ValueError:
        await message.answer("عدد معتبر")
        return
    data = await state.get_data()
    await db.add_plan(data.get("title", f"{data['volume_gb']}GB"), data["volume_gb"], price)
    per = round(price / data["volume_gb"])
    await state.clear()
    await message.answer(
        f"✅ پلن: {data['volume_gb']}GB | {price:,}ت | هرگیگ {per:,}",
        reply_markup=admin_panel_keyboard(),
    )


@router.callback_query(F.data.regexp(r"^plan_\d+$"))
async def plan_detail(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    plan = await db.get_plan(int(callback.data.split("_")[1]))
    if not plan:
        return
    per = round(plan["price"] / plan["volume_gb"]) if plan["volume_gb"] else 0
    await callback.message.edit_text(
        f"📦 {plan['volume_gb']}GB\n💰 {plan['price']:,}ت\n📈 هرگیگ {per:,}\n{'فعال' if plan['is_active'] else 'غیرفعال'}",
        reply_markup=plan_actions(plan["id"]),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("toggle_plan_"))
async def toggle_plan(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    pid = int(callback.data.split("_")[2])
    plan = await db.get_plan(pid)
    await db.update_plan(pid, is_active=0 if plan["is_active"] else 1)
    plan = await db.get_plan(pid)
    per = round(plan["price"] / plan["volume_gb"]) if plan["volume_gb"] else 0
    await callback.message.edit_text(
        f"📦 {plan['volume_gb']}GB\n💰 {plan['price']:,}ت\n📈 هرگیگ {per:,}\n{'فعال' if plan['is_active'] else 'غیرفعال'}",
        reply_markup=plan_actions(pid),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("delete_plan_"))
async def del_plan(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    await db.delete_plan(int(callback.data.split("_")[2]))
    await callback.answer("حذف شد")
    await callback.message.edit_text("📦 پلن‌ها:", reply_markup=plans_list(await db.get_plans(False)))


@router.callback_query(F.data.startswith("edit_plan_price_"))
async def edit_price(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(Form.edit_plan_price)
    await state.update_data(plan_id=int(callback.data.split("_")[3]), admin_context=True)
    await callback.message.answer("قیمت جدید:", reply_markup=cancel_reply())
    await callback.answer()


@router.message(Form.edit_plan_price)
async def save_price(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id) or message.text == "❌ انصراف":
        return
    try:
        price = int(message.text.strip().replace(",", "").replace("،", ""))
    except ValueError:
        await message.answer("عدد")
        return
    data = await state.get_data()
    await db.update_plan(data["plan_id"], price=price)
    await state.clear()
    await message.answer(f"✅ {price:,} تومان", reply_markup=admin_panel_keyboard())


# --- finance ---
@router.message(F.text == "💰 تنظیمات مالی")
async def finance(message: Message):
    if not is_admin(message.from_user.id):
        return
    auto = await db.get_setting("auto_approve_default", "0") == "1"
    try:
        delay = int(await db.get_setting("auto_approve_delay_minutes", "0"))
    except ValueError:
        delay = 0
    await message.answer(
        "💰 تنظیمات مالی",
        reply_markup=finance_keyboard(auto_on=auto, auto_minutes=delay),
    )



@router.callback_query(F.data == "set_card_number")
async def scn(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(Form.set_card_number)
    await state.update_data(admin_context=True)
    await callback.message.answer("شماره کارت:", reply_markup=cancel_reply())
    await callback.answer()


@router.message(Form.set_card_number)
async def scn_s(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id) or message.text == "❌ انصراف":
        return
    await db.set_setting("card_number", message.text.strip())
    await state.clear()
    await message.answer("✅ ذخیره شد", reply_markup=admin_panel_keyboard())


@router.callback_query(F.data == "set_account_number")
async def san(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(Form.set_account_number)
    await state.update_data(admin_context=True)
    await callback.message.answer("شماره حساب/شبا:", reply_markup=cancel_reply())
    await callback.answer()


@router.message(Form.set_account_number)
async def san_s(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id) or message.text == "❌ انصراف":
        return
    await db.set_setting("account_number", message.text.strip())
    await state.clear()
    await message.answer("✅ ذخیره شد", reply_markup=admin_panel_keyboard())


@router.callback_query(F.data == "set_card_owner")
async def sco(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(Form.set_card_owner)
    await state.update_data(admin_context=True)
    await callback.message.answer("نام صاحب:", reply_markup=cancel_reply())
    await callback.answer()


@router.message(Form.set_card_owner)
async def sco_s(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id) or message.text == "❌ انصراف":
        return
    await db.set_setting("card_owner", message.text.strip())
    await state.clear()
    await message.answer("✅ ذخیره شد", reply_markup=admin_panel_keyboard())


@router.callback_query(F.data == "toggle_auto_approve_default")
async def tog_auto_def(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    cur = await db.get_setting("auto_approve_default", "0")
    new = "0" if cur == "1" else "1"
    await db.set_setting("auto_approve_default", new)
    try:
        delay = int(await db.get_setting("auto_approve_delay_minutes", "0"))
    except ValueError:
        delay = 0
    await callback.message.edit_reply_markup(
        reply_markup=finance_keyboard(auto_on=(new == "1"), auto_minutes=delay)
    )
    await callback.answer("تأیید خودکار: " + ("روشن" if new == "1" else "خاموش"))


# --- bot settings ---
@router.message(F.text == "⚙️ تنظیمات ربات")
async def bot_settings(message: Message):
    if not is_admin(message.from_user.id):
        return
    keys = ["bot_enabled", "allow_buy", "require_phone", "require_iran_phone", "require_verify"]
    s = {}
    for k in keys:
        default = "1" if k in ("bot_enabled", "allow_buy") else "0"
        s[k] = await db.get_setting(k, default)
    ch = await db.get_setting("report_channel", "-")
    await message.answer(
        f"⚙️ تنظیمات ربات\nکانال گزارش: {ch}",
        reply_markup=bot_settings_keyboard(s),
    )


@router.callback_query(F.data.startswith("tog_"))
async def tog_setting(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    key = callback.data[4:]  # after tog_
    cur = await db.get_setting(key, "0")
    await db.set_setting(key, "0" if cur == "1" else "1")
    keys = ["bot_enabled", "allow_buy", "require_phone", "require_iran_phone", "require_verify"]
    s = {k: await db.get_setting(k, "0") for k in keys}
    await callback.message.edit_reply_markup(reply_markup=bot_settings_keyboard(s))
    await callback.answer("OK")


@router.callback_query(F.data == "set_report_channel")
async def set_rep(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(Form.set_report_channel)
    await state.update_data(admin_context=True)
    await callback.message.answer(
        "آیدی کانال گزارش را بفرستید (مثلاً -100... یا @channel).\nربات باید ادمین کانال باشد.\nبرای حذف: -",
        reply_markup=cancel_reply(),
    )
    await callback.answer()


@router.message(Form.set_report_channel)
async def set_rep_s(message: Message, state: FSMContext, bot: Bot):
    if not is_admin(message.from_user.id) or message.text == "❌ انصراف":
        return
    val = message.text.strip()
    if val == "-":
        await db.set_setting("report_channel", "")
        await state.clear()
        await message.answer("🗑 کانال گزارش حذف شد.", reply_markup=admin_panel_keyboard())
        return
    ok, msg = await test_report_channel(bot, val)
    if not ok:
        await message.answer(msg, parse_mode="HTML", reply_markup=cancel_reply())
        return
    # store normalized form
    norm = normalize_chat_id(val)
    await db.set_setting("report_channel", str(norm) if norm is not None else val)
    await state.clear()
    await message.answer(
        msg + "\n\nکانال گزارش ذخیره شد.",
        parse_mode="HTML",
        reply_markup=admin_panel_keyboard(),
    )


# --- cron ---
@router.message(F.text == "⏰ تنظیمات کرون_DISABLED")
async def cron_set(message: Message):
    if not is_admin(message.from_user.id):
        return
    h = await db.get_setting("volume_check_hours", "6")
    th = await db.get_setting("volume_thresholds", "80,85,90,95,100")
    await message.answer(
        f"⏰ کرون\nفاصله چک حجم: هر {h} ساعت\nآستانه‌ها: {th}%",
        reply_markup=cron_settings_keyboard(),
    )


@router.callback_query(F.data == "set_volume_check_hours")
async def set_vch(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(Form.set_volume_check_hours)
    await state.update_data(admin_context=True)
    await callback.message.answer("فاصله چک به ساعت (مثلاً 6):", reply_markup=cancel_reply())
    await callback.answer()


@router.message(Form.set_volume_check_hours)
async def set_vch_s(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id) or message.text == "❌ انصراف":
        return
    try:
        h = max(1, int(message.text.strip()))
    except ValueError:
        await message.answer("عدد")
        return
    await db.set_setting("volume_check_hours", str(h))
    await state.clear()
    await message.answer(
        f"✅ هر {h} ساعت. ری‌استارت سرویس برای اعمال:\n<code>systemctl restart pasaradminbot</code>",
        parse_mode="HTML",
        reply_markup=admin_panel_keyboard(),
    )


@router.callback_query(F.data == "set_volume_thresholds")
async def set_vt(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(Form.set_volume_thresholds)
    await state.update_data(admin_context=True)
    await callback.message.answer(
        "آستانه‌ها را با ویرگول بفرستید (مثلاً 80,85,90,95,100):",
        reply_markup=cancel_reply(),
    )
    await callback.answer()


@router.message(Form.set_volume_thresholds)
async def set_vt_s(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id) or message.text == "❌ انصراف":
        return
    await db.set_setting("volume_thresholds", message.text.strip().replace(" ", ""))
    await state.clear()
    await message.answer("✅ ذخیره شد", reply_markup=admin_panel_keyboard())


# --- backup ---
@router.message(F.text == "🗄 تنظیمات بک‌آپ_DISABLED")
async def backup_menu(message: Message):
    if not is_admin(message.from_user.id):
        return
    h = await db.get_setting("backup_interval_hours", "24")
    await message.answer(f"🗄 بک‌آپ — هر {h} ساعت", reply_markup=backup_settings_keyboard())


@router.callback_query(F.data == "backup_export")
async def backup_exp(callback: CallbackQuery, bot: Bot):
    if not is_admin(callback.from_user.id):
        return
    path = settings.DB_PATH
    if not os.path.exists(path):
        await callback.answer("یافت نشد", show_alert=True)
        return
    name = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    tmp = os.path.join(settings.BASE_DIR, "data", name)
    shutil.copy2(path, tmp)
    await bot.send_document(settings.ADMIN_ID, FSInputFile(tmp), caption="📤 Export")
    os.remove(tmp)
    await callback.answer("ارسال شد")


@router.callback_query(F.data == "backup_import")
async def backup_imp(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(Form.backup_import)
    await state.update_data(admin_context=True)
    await callback.message.answer("فایل .db را بفرستید:", reply_markup=cancel_reply())
    await callback.answer()


@router.message(Form.backup_import, F.document)
async def backup_imp_f(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    if not message.document.file_name.endswith(".db"):
        await message.answer("فقط .db")
        return
    f = await message.bot.get_file(message.document.file_id)
    if os.path.exists(settings.DB_PATH):
        shutil.copy2(settings.DB_PATH, settings.DB_PATH + ".bak")
    await message.bot.download_file(f.file_path, settings.DB_PATH)
    await state.clear()
    await message.answer(
        "✅ ایمپورت شد. ری‌استارت:\n<code>systemctl restart pasaradminbot</code>",
        parse_mode="HTML",
        reply_markup=admin_panel_keyboard(),
    )


@router.message(Form.backup_import)
async def backup_imp_w(message: Message):
    if message.text != "❌ انصراف":
        await message.answer("فایل .db بفرستید")


@router.callback_query(F.data == "backup_interval")
async def bi(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(Form.backup_interval)
    await state.update_data(admin_context=True)
    await callback.message.answer("فاصله بک‌آپ به ساعت:", reply_markup=cancel_reply())
    await callback.answer()


@router.message(Form.backup_interval)
async def bi_s(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id) or message.text == "❌ انصراف":
        return
    try:
        h = max(1, int(message.text.strip()))
    except ValueError:
        await message.answer("عدد")
        return
    await db.set_setting("backup_interval_hours", str(h))
    await state.clear()
    await message.answer(
        f"✅ هر {h}h — ری‌استارت سرویس لازم است",
        reply_markup=admin_panel_keyboard(),
    )


# --- search user ---
@router.message(F.text == "🔍 سرچ کاربر")
async def search_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.set_state(Form.search_user)
    await state.update_data(admin_context=True)
    await message.answer("آیدی عددی کاربر:", reply_markup=cancel_reply())


@router.message(Form.search_user)
async def search_do(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id) or message.text == "❌ انصراف":
        return
    try:
        uid = int(message.text.strip())
    except ValueError:
        await message.answer("فقط عدد")
        return
    u = await db.get_bot_user(uid)
    stats = await db.user_stats(uid)
    blocked = await db.is_blocked(uid)
    verified = bool(u and u.get("is_verified"))
    auto_ap = await db.should_auto_approve(uid)
    phone = (u or {}).get("phone") or "-"
    panels = await db.get_user_panels(uid)
    panel_lines = [f"• {r['panel_name']}: {r['admin_username']}" for r in panels]
    panel_txt = "\n".join(panel_lines) if panel_lines else "ندارد"
    parts = [
        f"👤 کاربر <code>{uid}</code>",
        f"نام: {(u or {}).get('full_name') or '-'}",
        f"یوزرنیم: @{(u or {}).get('username') or '-'}",
        f"شماره: <code>{phone}</code>",
        f"وضعیت: {'🚫 بلاک' if blocked else '✅ فعال'}",
        f"احراز هویت: {'✅ تأیید شده' if verified else '❌ نشده'}",
        f"تأیید خودکار: {'✅' if auto_ap else '❌'}",
        f"واریزی: {stats['total_paid']:,}ت | حجم: {stats['total_volume']}GB | سفارش: {stats['paid_count']}",
        "🖥 پنل اختصاصی:",
        panel_txt,
    ]
    text = "\n".join(parts)
    await state.clear()
    await message.answer(text, parse_mode="HTML", reply_markup=user_search_kb(uid, blocked, verified, auto_ap))
    await message.answer("پنل ادمین:", reply_markup=admin_panel_keyboard())



@router.callback_query(F.data.startswith("unblock_"))
async def unb(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    uid = int(callback.data.split("_")[1])
    await db.unblock_user(uid)
    await callback.answer("آنبلاک شد")
    await callback.message.answer(f"✅ <code>{uid}</code> آنبلاک", parse_mode="HTML")
    await report(callback.bot, f"✅ آنبلاک کاربر <code>{uid}</code>")


@router.callback_query(F.data.startswith("block_"))
async def blk(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    uid = int(callback.data.split("_")[1])
    await db.block_user(uid, "manual")
    await callback.answer("بلاک شد")
    await callback.message.answer(f"🚫 <code>{uid}</code> بلاک", parse_mode="HTML")
    await report(callback.bot, f"🚫 بلاک کاربر <code>{uid}</code> (دستی)")


@router.callback_query(F.data.startswith("verify_"))
async def ver(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    uid = int(callback.data.split("_")[1])
    await db.upsert_bot_user(uid)
    await db.update_bot_user(uid, is_verified=1)
    await callback.answer("✅ احراز هویت تأیید شد", show_alert=True)
    try:
        await callback.bot.send_message(uid, "✅ احراز هویت شما توسط ادمین تأیید شد. می‌توانید از ربات استفاده کنید.")
    except Exception:
        pass
    await callback.message.answer(f"✅ کاربر <code>{uid}</code> احراز شد.", parse_mode="HTML")
    await report(callback.bot, f"✅ احراز هویت کاربر <code>{uid}</code>")


@router.callback_query(F.data.startswith("unverify_"))
async def unver(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    uid = int(callback.data.split("_")[1])
    await db.update_bot_user(uid, is_verified=0)
    await callback.answer("❌ احراز هویت لغو شد", show_alert=True)
    try:
        await callback.bot.send_message(uid, "❌ احراز هویت شما لغو شد. تا تأیید مجدد امکان استفاده از ربات را ندارید.")
    except Exception:
        pass
    await callback.message.answer(f"❌ احراز کاربر <code>{uid}</code> لغو شد.", parse_mode="HTML")
    await report(callback.bot, f"❌ لغو احراز کاربر <code>{uid}</code>")


@router.callback_query(F.data.startswith("autoap_"))
async def autoap(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    uid = int(callback.data.split("_")[1])
    u = await db.get_bot_user(uid)
    # force OFF (0) or force ON (1) — never leave ambiguous
    cur = None if not u else u.get("auto_approve")
    if cur is None:
        # inherit was on/off based on global; toggle to opposite of global
        default_on = await db.get_setting("auto_approve_default", "1") == "1"
        newv = 0 if default_on else 1
    else:
        newv = 0 if int(cur) else 1
    await db.upsert_bot_user(uid)
    await db.update_bot_user(uid, auto_approve=newv)
    await callback.answer("تأیید خودکار این کاربر: " + ("✅ روشن" if newv else "❌ خاموش"))
    await callback.message.answer(
        f"کاربر <code>{uid}</code> — تأیید خودکار: {'✅ روشن' if newv else '❌ خاموش (فقط دستی)'}",
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("uorders_"))
async def uorders(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    uid = int(callback.data.split("_")[1])
    orders = await db.get_user_orders(uid, 15)
    if not orders:
        await callback.message.answer("سفارشی نیست")
        await callback.answer()
        return
    lines = [f"📋 سفارشات {uid}:"]
    for o in orders:
        lines.append(f"• {o['username']} | {o['volume_gb']}GB | {o['price']:,} | {o['status']}")
    await callback.message.answer("\n".join(lines))
    await callback.answer()


@router.callback_query(F.data.startswith("assignpanel_"))
async def assign_p(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    uid = int(callback.data.split("_")[1])
    panels = await db.get_panels()
    if not panels:
        await callback.answer("پنلی نیست", show_alert=True)
        return
    await state.set_state(Form.assign_panel_username)
    await state.update_data(admin_context=True, assign_uid=uid, panel_id=panels[0]["id"])
    if len(panels) > 1:
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        from aiogram.types import InlineKeyboardButton
        b = InlineKeyboardBuilder()
        for p in panels:
            b.row(InlineKeyboardButton(text=p["name"], callback_data=f"apick_{uid}_{p['id']}"))
        await callback.message.answer("پنل را انتخاب کنید:", reply_markup=b.as_markup())
    else:
        await callback.message.answer(
            f"یوزرنیم ادمین پنل برای کاربر {uid}:",
            reply_markup=cancel_reply(),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("apick_"))
async def apick(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    _, uid, pid = callback.data.split("_")
    await state.set_state(Form.assign_panel_username)
    await state.update_data(admin_context=True, assign_uid=int(uid), panel_id=int(pid))
    await callback.message.answer("یوزرنیم ادمین پنل:", reply_markup=cancel_reply())
    await callback.answer()


@router.message(Form.assign_panel_username)
async def assign_save(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id) or message.text == "❌ انصراف":
        return
    data = await state.get_data()
    uname = message.text.strip()
    api = await get_panel_api(data["panel_id"])
    if not api:
        await message.answer("❌ اتصال به پنل ناموفق.")
        return
    admin_info = await api.get_admin(uname)
    if not admin_info or admin_info.get("error"):
        await message.answer(
            f"❌ ادمینی با نام «{uname}» در پنل پیدا نشد. دوباره وارد کنید:",
            reply_markup=cancel_reply(),
        )
        return
    await db.assign_user_panel(data["assign_uid"], data["panel_id"], uname)
    await state.clear()
    await message.answer(
        f"✅ پنل برای کاربر {data['assign_uid']} با ادمین «{uname}» ثبت شد.",
        reply_markup=admin_panel_keyboard(),
    )
    await report(
        message.bot,
        f"🖥 اختصاص پنل\nکاربر: <code>{data['assign_uid']}</code>\nادمین پنل: <code>{uname}</code>",
    )


@router.message(F.text == "🚫 کاربران بلاک‌شده")
async def list_blocked(message: Message):
    if not is_admin(message.from_user.id):
        return
    rows = await db.get_blocked_users()
    if not rows:
        await message.answer("خالی است")
        return
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    b = InlineKeyboardBuilder()
    lines = ["🚫 بلاک‌شده‌ها:"]
    for r in rows[:30]:
        lines.append(f"• {r['user_id']}")
        b.row(InlineKeyboardButton(text=f"آنبلاک {r['user_id']}", callback_data=f"unblock_{r['user_id']}"))
    await message.answer("\n".join(lines), reply_markup=b.as_markup())


# --- approve ---
@router.callback_query(F.data.startswith("approve_order_"))
async def approve(callback: CallbackQuery, bot: Bot):
    if not is_admin(callback.from_user.id):
        return
    oid = int(callback.data.split("_")[2])
    order = await db.get_order(oid)
    if not order:
        await callback.answer("سفارش پیدا نشد", show_alert=True)
        return
    if order["status"] == "paid":
        await callback.answer("قبلاً تأیید شده", show_alert=True)
        return
    if order["status"] == "rejected":
        await callback.answer("این سفارش رد شده و قابل تأیید نیست", show_alert=True)
        return
    api = await get_panel_api(order["panel_id"])
    if not api:
        await callback.answer("پنل نیست", show_alert=True)
        return
    await callback.answer("...")
    result = await api.add_volume_to_admin(order["username"], order["volume_gb"])
    if result["success"]:
        await db.update_order(oid, status="paid")
        text = f"✅ تأیید شد\n{result['message']}\n{result.get('old_limit_gb')} → {result.get('new_limit_gb')} گیگ"
        try:
            await callback.message.edit_caption(caption=text, reply_markup=None)
        except Exception:
            await callback.message.answer(text)
        try:
            await bot.send_message(
                order["user_id"],
                f"✅ پرداخت تأیید شد.\nحجم {order['volume_gb']} گیگ به ادمین «{order['username']}» اضافه شد.",
            )
        except Exception:
            pass
        await report(
            bot,
            f"✅ تأیید دستی پرداخت\n"
            f"کاربر: <code>{order['user_id']}</code>\n"
            f"ادمین پنل: <code>{order['username']}</code>\n"
            f"{order['volume_gb']}GB | {order['price']:,} تومان",
        )
    else:
        await callback.message.answer(f"❌ {result['message']}")


@router.callback_query(F.data.startswith("reject_order_"))
async def reject(callback: CallbackQuery, bot: Bot):
    if not is_admin(callback.from_user.id):
        return
    oid = int(callback.data.split("_")[2])
    order = await db.get_order(oid)
    if not order:
        await callback.answer("سفارش پیدا نشد", show_alert=True)
        return
    if order.get("status") == "paid":
        await callback.answer("قبلاً تأیید شده و قابل رد نیست", show_alert=True)
        return
    if order.get("status") == "rejected":
        await callback.answer("قبلاً رد شده", show_alert=True)
        return
    # mark rejected FIRST so auto-approve cron cannot pick it up
    await db.update_order(oid, status="rejected")
    try:
        await callback.message.edit_caption(
            caption="❌ پرداخت رد شد — تأیید خودکار غیرفعال برای این سفارش",
            reply_markup=None,
        )
    except Exception:
        try:
            await callback.message.answer("❌ پرداخت رد شد")
        except Exception:
            pass
    await callback.answer("رد شد")
    try:
        await bot.send_message(order["user_id"], "❌ پرداخت رد شد.")
    except Exception:
        pass
    await report(
        bot,
        f"❌ رد پرداخت\nکاربر: <code>{order['user_id']}</code>\n"
        f"ادمین پنل: <code>{order['username']}</code>\n"
        f"{order['volume_gb']}GB | {order['price']:,} تومان",
    )


@router.message(F.text == "ℹ️ وضعیت ربات_DISABLED")
async def status(message: Message):
    if not is_admin(message.from_user.id):
        return
    panels = await db.get_panels()
    plans = await db.get_plans()
    pending = await db.get_pending_orders()
    await message.answer(
        f"ℹ️ پنل: {len(panels)} | پلن: {len(plans)} | در انتظار: {len(pending)}\n"
        f"ادمین: <code>{settings.ADMIN_ID}</code>",
        parse_mode="HTML",
    )



# ==================== NEW FEATURES ====================

@router.message(F.text == "📊 آمار ربات")
async def bot_stats(message: Message):
    if not is_admin(message.from_user.id):
        return
    s = await db.payment_stats()
    await message.answer(
        (
            "📊 آمار ربات\n\n"
            f"🟢 این هفته: {s.get('this_week', 0):,} تومان\n"
            f"⚪ هفته پیش: {s.get('last_week', 0):,} تومان\n"
            f"🟢 این ماه: {s.get('this_month', 0):,} تومان\n"
            f"⚪ ماه پیش: {s.get('last_month', 0):,} تومان\n"
            f"💰 مجموع کل: {s.get('total_all', 0):,} تومان\n"
            f"✅ سفارش موفق: {s.get('paid_count', 0)}\n"
            f"📋 کل سفارش‌ها: {s.get('all_orders', 0)}"
        )
    )


@router.callback_query(F.data == "finance_back")
async def finance_back(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    auto = await db.get_setting("auto_approve_default", "0") == "1"
    try:
        delay = int(await db.get_setting("auto_approve_delay_minutes", "0"))
    except ValueError:
        delay = 0
    await callback.message.edit_text(
        "💰 تنظیمات مالی",
        reply_markup=finance_keyboard(auto_on=auto, auto_minutes=delay),
    )
    await callback.answer()


@router.callback_query(F.data == "account_info")
async def account_info(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    card = await db.get_setting("card_number", "-")
    acc = await db.get_setting("account_number", "-")
    owner = await db.get_setting("card_owner", "-")
    await callback.message.edit_text(
        f"💳 اطلاعات حساب\n\nکارت: <code>{card}</code>\nحساب: <code>{acc}</code>\nصاحب: {owner}",
        parse_mode="HTML",
        reply_markup=account_info_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "set_auto_approve_delay")
async def set_auto_delay(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(Form.set_auto_delay)
    await state.update_data(admin_context=True)
    await callback.message.answer(
        "تأخیر تأیید خودکار را به دقیقه وارد کنید (0 = فوری):",
        reply_markup=cancel_reply(),
    )
    await callback.answer()


@router.message(Form.set_auto_delay)
async def set_auto_delay_s(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id) or message.text == "❌ انصراف":
        return
    try:
        m = max(0, int(message.text.strip()))
    except ValueError:
        await message.answer("عدد معتبر")
        return
    await db.set_setting("auto_approve_delay_minutes", str(m))
    await state.clear()
    await message.answer(f"✅ تأخیر: {m} دقیقه", reply_markup=admin_panel_keyboard())


@router.callback_query(F.data == "discount_menu")
async def disc_menu(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    codes = await db.get_discounts()
    await callback.message.edit_text(
        "🏷 مدیریت کد تخفیف",
        reply_markup=discount_menu_keyboard(codes),
    )
    await callback.answer()


@router.callback_query(F.data == "add_discount")
async def add_disc(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(Form.add_disc_code)
    await state.update_data(admin_context=True)
    await callback.message.answer("کد تخفیف را وارد کنید (مثلاً OFF20):", reply_markup=cancel_reply())
    await callback.answer()


@router.message(Form.add_disc_code)
async def add_disc_code(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id) or message.text == "❌ انصراف":
        return
    await state.update_data(code=message.text.strip().upper())
    await state.set_state(Form.add_disc_percent)
    await message.answer("درصد تخفیف (مثلاً 10):")


@router.message(Form.add_disc_percent)
async def add_disc_pct(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id) or message.text == "❌ انصراف":
        return
    try:
        pct = int(message.text.strip())
        if not 1 <= pct <= 100:
            raise ValueError
    except ValueError:
        await message.answer("عدد ۱ تا ۱۰۰")
        return
    await state.update_data(percent=pct)
    await state.set_state(Form.add_disc_uses)
    await message.answer("حداکثر تعداد استفاده (مثلاً 50):")


@router.message(Form.add_disc_uses)
async def add_disc_uses(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id) or message.text == "❌ انصراف":
        return
    try:
        uses = max(1, int(message.text.strip()))
    except ValueError:
        await message.answer("عدد")
        return
    data = await state.get_data()
    try:
        await db.add_discount(data["code"], data["percent"], uses)
        await message.answer(
            f"✅ کد {data['code']} | {data['percent']}% | {uses} بار",
            reply_markup=admin_panel_keyboard(),
        )
    except Exception as e:
        await message.answer(f"❌ خطا (شاید کد تکراری): {e}", reply_markup=admin_panel_keyboard())
    await state.clear()


@router.callback_query(F.data.regexp(r"^disc_\d+$"))
async def disc_detail(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    d = await db.get_discount(int(callback.data.split("_")[1]))
    if not d:
        await callback.answer("نیست", show_alert=True)
        return
    await callback.message.edit_text(
        f"🏷 {d['code']}\nدرصد: {d['percent']}%\nاستفاده: {d['used_count']}/{d['max_uses']}\n"
        f"وضعیت: {'فعال' if d['is_active'] else 'غیرفعال'}",
        reply_markup=discount_actions(d["id"]),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("disc_tog_"))
async def disc_tog(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    did = int(callback.data.split("_")[2])
    d = await db.get_discount(did)
    await db.update_discount(did, is_active=0 if d["is_active"] else 1)
    codes = await db.get_discounts()
    await callback.message.edit_text("🏷 مدیریت کد تخفیف", reply_markup=discount_menu_keyboard(codes))
    await callback.answer()


@router.callback_query(F.data.startswith("disc_del_"))
async def disc_del(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    await db.delete_discount(int(callback.data.split("_")[2]))
    codes = await db.get_discounts()
    await callback.message.edit_text("🏷 مدیریت کد تخفیف", reply_markup=discount_menu_keyboard(codes))
    await callback.answer("حذف شد")


@router.callback_query(F.data.startswith("use_disc_"))
async def use_disc(callback: CallbackQuery, state: FSMContext):
    oid = int(callback.data.split("_")[2])
    await state.update_data(order_id=oid)
    await state.set_state(Form.enter_discount)
    await callback.message.answer("کد تخفیف را وارد کنید:", reply_markup=cancel_reply())
    await callback.answer()


@router.callback_query(F.data.startswith("skip_disc_"))
async def skip_disc(callback: CallbackQuery, state: FSMContext):
    oid = int(callback.data.split("_")[2])
    order = await db.get_order(oid)
    if not order:
        await callback.answer("سفارش نیست", show_alert=True)
        return
    await state.update_data(order_id=oid, username=order["username"], price=order["price"])
    await state.set_state(Form.waiting_receipt)
    card = await db.get_setting("card_number", settings.CARD_NUMBER)
    account = await db.get_setting("account_number", "")
    owner = await db.get_setting("card_owner", settings.CARD_OWNER)
    text = (
        f"👤 ادمین پنل: <code>{order['username']}</code>\n"
        f"📦 حجم: {order['volume_gb']} گیگ\n"
        f"💰 مبلغ: <b>{order['price']:,} تومان</b>\n\n"
        f"💳 کارت:\n<code>{card}</code>\n\n"
    )
    if account:
        text += f"🏦 حساب/شبا:\n<code>{account}</code>\n\n"
    text += f"👤 صاحب حساب: {owner}\n\nعکس رسید را ارسال کنید."
    await callback.message.edit_text(text, parse_mode="HTML")
    await callback.message.answer("عکس رسید:", reply_markup=cancel_reply())
    await callback.answer()


@router.message(Form.enter_discount)
async def enter_disc(message: Message, state: FSMContext):
    if message.text == "❌ انصراف":
        return
    data = await state.get_data()
    oid = data.get("order_id")
    order = await db.get_order(oid) if oid else None
    if not order:
        await state.clear()
        await message.answer("سفارش نامعتبر")
        return
    code = message.text.strip()
    disc = await db.get_discount_by_code(code)
    if not disc or disc["used_count"] >= disc["max_uses"]:
        await message.answer("❌ کد نامعتبر یا تمام شده. دوباره وارد کنید یا انصراف بزنید.")
        return
    new_price = int(order["price"] * (100 - disc["percent"]) / 100)
    await db.update_order(oid, price=new_price)
    await db.use_discount(disc["id"], message.from_user.id, oid)
    await state.update_data(price=new_price)
    await state.set_state(Form.waiting_receipt)
    card = await db.get_setting("card_number", settings.CARD_NUMBER)
    account = await db.get_setting("account_number", "")
    owner = await db.get_setting("card_owner", settings.CARD_OWNER)
    text = (
        f"✅ تخفیف {disc['percent']}% اعمال شد\n\n"
        f"👤 ادمین پنل: <code>{order['username']}</code>\n"
        f"📦 حجم: {order['volume_gb']} گیگ\n"
        f"💰 مبلغ قبلی: {order['price']:,}\n"
        f"💰 مبلغ نهایی: <b>{new_price:,} تومان</b>\n\n"
        f"💳 کارت:\n<code>{card}</code>\n\n"
    )
    if account:
        text += f"🏦 حساب/شبا:\n<code>{account}</code>\n\n"
    text += f"👤 صاحب حساب: {owner}\n\nعکس رسید را ارسال کنید."
    await message.answer(text, parse_mode="HTML", reply_markup=cancel_reply())


@router.callback_query(F.data == "bot_settings_back")
@router.callback_query(F.data == "cron_from_settings")
@router.callback_query(F.data == "backup_from_settings")
async def settings_sub(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    if callback.data == "bot_settings_back":
        keys = ["bot_enabled", "allow_buy", "require_phone", "require_iran_phone", "require_verify"]
        s = {k: await db.get_setting(k, "0" if k != "bot_enabled" and k != "allow_buy" else "1") for k in keys}
        ch = await db.get_setting("report_channel", "-")
        await callback.message.edit_text(f"⚙️ تنظیمات ربات\nکانال گزارش: {ch}", reply_markup=bot_settings_keyboard(s))
    elif callback.data == "cron_from_settings":
        h = await db.get_setting("volume_check_hours", "6")
        th = await db.get_setting("volume_thresholds", "80,85,90,95,100")
        await callback.message.edit_text(
            f"⏰ کرون\nفاصله چک: هر {h} ساعت\nآستانه‌ها: {th}%",
            reply_markup=cron_settings_keyboard(),
        )
    else:
        h = await db.get_setting("backup_interval_hours", "24")
        await callback.message.edit_text(f"🗄 بک‌آپ — هر {h} ساعت", reply_markup=backup_settings_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith("uinfo_"))
async def uinfo(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    uid = int(callback.data.split("_")[1])
    u = await db.get_bot_user(uid)
    stats = await db.user_stats(uid)
    blocked = await db.is_blocked(uid)
    verified = bool(u and u.get("is_verified"))
    auto_ap = await db.should_auto_approve(uid)
    phone = (u or {}).get("phone") or "-"
    panels = await db.get_user_panels(uid)
    panel_lines = [f"• {r['panel_name']}: {r['admin_username']}" for r in panels]
    panel_txt = "\n".join(panel_lines) if panel_lines else "ندارد"
    parts = [
        f"👤 کاربر <code>{uid}</code>",
        f"نام: {(u or {}).get('full_name') or '-'}",
        f"یوزرنیم: @{(u or {}).get('username') or '-'}",
        f"شماره: <code>{phone}</code>",
        f"وضعیت: {'🚫 بلاک' if blocked else '✅ فعال'}",
        f"احراز هویت: {'✅ تأیید شده' if verified else '❌ نشده'}",
        f"تأیید خودکار: {'✅' if auto_ap else '❌'}",
        f"واریزی: {stats['total_paid']:,}ت | حجم: {stats['total_volume']}GB",
        "🖥 پنل اختصاصی:",
        panel_txt,
    ]
    text = "\n".join(parts)
    await callback.message.answer(text, parse_mode="HTML", reply_markup=user_search_kb(uid, blocked, verified, auto_ap))
    await callback.answer()



@router.callback_query(F.data.startswith("viewup_"))
async def viewup(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    uid = int(callback.data.split("_")[1])
    rows = await db.get_user_panels(uid)
    if not rows:
        await callback.answer("پنلی اختصاص داده نشده", show_alert=True)
        return
    lines = [f"🖥 پنل‌های کاربر {uid}:"]
    for r in rows:
        lines.append(f"• {r['panel_name']} — ادمین: {r['admin_username']}")
    await callback.message.answer("\n".join(lines), reply_markup=user_panels_admin_kb(uid, rows))
    await callback.answer()


@router.callback_query(F.data.startswith("rmup_"))
async def rmup(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    # rmup_{uid}_{panel_id}_{username}  username may contain underscores - take last parts carefully
    parts = callback.data.split("_", 3)
    # rmup, uid, panel_id, admin_username
    uid = int(parts[1])
    panel_id = int(parts[2])
    admin_username = parts[3]
    await db.remove_user_panel(uid, panel_id, admin_username)
    await callback.answer("حذف شد")
    rows = await db.get_user_panels(uid)
    if rows:
        await callback.message.edit_text(
            f"🖥 پنل‌های کاربر {uid}:\n" + "\n".join(
                f"• {r['panel_name']} — {r['admin_username']}" for r in rows
            ),
            reply_markup=user_panels_admin_kb(uid, rows),
        )
    else:
        await callback.message.edit_text("همه پنل‌ها حذف شدند.")



@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    data = await state.get_data()
    await go_back(message, state, bool(data.get("admin_context")) and is_admin(message.from_user.id))
