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
    finance_keyboard, backup_settings_keyboard,
    bot_settings_keyboard, cron_settings_keyboard, user_search_kb,
)
from bot.services.pasarguard import get_panel_api

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


def is_admin(uid: int) -> bool:
    return uid == settings.ADMIN_ID


async def report(bot: Bot, text: str):
    ch = await db.get_setting("report_channel", "")
    if ch:
        try:
            await bot.send_message(ch, text, parse_mode="HTML")
        except Exception:
            pass


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

    await db.upsert_bot_user(
        uid,
        username=message.from_user.username,
        full_name=message.from_user.full_name or "",
    )

    # notify admin (like Mirza)
    if not is_admin(uid):
        try:
            uname = f"@{message.from_user.username}" if message.from_user.username else "-"
            await bot.send_message(
                settings.ADMIN_ID,
                (
                    "🆕 استارت ربات\n"
                    f"آیدی: <code>{uid}</code>\n"
                    f"نام: {message.from_user.full_name or '-'}\n"
                    f"یوزرنیم: {uname}"
                ),
                parse_mode="HTML",
            )
            await report(
                bot,
                f"🆕 استارت | <code>{uid}</code> | {message.from_user.full_name or '-'} | {uname}",
            )
        except Exception:
            pass

    admin = is_admin(uid)
    text = "👋 به ربات خرید حجم پاسارگارد خوش آمدید.\n\nاز منوی زیر استفاده کنید:"
    if admin:
        text += "\n\n⚙️ شما ادمین هستید."
    await message.answer(text, reply_markup=user_main_keyboard(is_admin=admin))


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
    uid = message.from_user.id
    u = await db.get_bot_user(uid)
    stats = await db.user_stats(uid)
    blocked = await db.is_blocked(uid)
    lines = [
        "👤 مشخصات کاربری\n",
        f"آیدی: <code>{uid}</code>",
        f"نام: {message.from_user.full_name or '-'}",
        f"یوزرنیم: @{message.from_user.username or '-'}",
        f"وضعیت: {'🚫 بلاک' if blocked else '✅ فعال'}",
        f"احراز هویت: {'✅' if (u and u.get('is_verified')) else '❌'}",
        f"تأیید خودکار: {'✅' if (u and u.get('auto_approve')) else '❌'}",
        f"جمع واریزی: {stats.get('total_paid', 0):,} تومان",
        f"جمع حجم خریداری‌شده: {stats.get('total_volume', 0)} گیگ",
        f"تعداد سفارش موفق: {stats.get('paid_count', 0)}",
        f"کل سفارش‌ها: {stats.get('order_count', 0)}",
    ]
    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(F.text == "🖥 پنل‌های من")
async def my_panels(message: Message):
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
        remain = max(limit_gb - used_gb, 0) if limit else "نامحدود"
        pct = round(used / limit * 100, 1) if limit else 0
        await message.answer(
            (
                f"🖥 <b>{r['panel_name']}</b>\n"
                f"👤 ادمین: <code>{r['admin_username']}</code>\n"
                f"📊 حجم کل: {limit_gb} گیگ\n"
                f"📉 مصرف: {used_gb} گیگ ({pct}%)\n"
                f"✅ مانده: {remain} گیگ"
            ),
            parse_mode="HTML",
        )


# ==================== BUY ====================

@router.message(F.text.in_({"🛒 خرید حجم", "🛒 خرید حجم (ادمین)"}))
async def buy_start(message: Message, state: FSMContext):
    uid = message.from_user.id
    if await db.is_blocked(uid) and not is_admin(uid):
        await message.answer("🚫 بلاک هستید.")
        return
    if await db.get_setting("allow_buy", "1") != "1" and not is_admin(uid):
        await message.answer("⛔️ خرید حجم فعلاً غیرفعال است.")
        return
    if await db.get_setting("require_verify", "0") == "1" and not is_admin(uid):
        u = await db.get_bot_user(uid)
        if not u or not u.get("is_verified"):
            await message.answer("⛔️ ابتدا باید احراز هویت شوید.")
            return

    panels = await db.get_panels()
    plans = await db.get_plans()
    if not panels or not plans:
        await message.answer("⚠️ پنل یا پلن تعریف نشده.")
        return
    if is_admin(uid) and message.text == "🛒 خرید حجم (ادمین)":
        await state.update_data(admin_context=True)
    if len(panels) == 1:
        await state.update_data(panel_id=panels[0]["id"])
        await message.answer("📦 پلن را انتخاب کنید:", reply_markup=buy_select_plan(plans))
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
    await callback.message.edit_text("📦 پلن را انتخاب کنید:", reply_markup=buy_select_plan(plans))
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

    limit = admin_info.get("data_limit") or 0
    used = admin_info.get("used_traffic") or 0
    limit_gb = round(limit / (1024**3), 2) if limit else 0
    used_gb = round(used / (1024**3), 2)

    order_id = await db.create_order(
        uid, data["panel_id"], username, data["plan_id"], data["volume_gb"], data["price"]
    )
    await state.update_data(order_id=order_id, username=username)

    # auto approve?
    u = await db.get_bot_user(uid)
    auto = (u and u.get("auto_approve")) or (
        await db.get_setting("auto_approve_default", "0") == "1"
    )
    if auto and is_admin(uid):
        # still require payment flow for safety unless we skip - user wanted auto confirm of payment
        pass

    await state.set_state(Form.waiting_receipt)
    card = await db.get_setting("card_number", settings.CARD_NUMBER)
    account = await db.get_setting("account_number", "")
    owner = await db.get_setting("card_owner", settings.CARD_OWNER)
    text = (
        "✅ سفارش ثبت شد\n\n"
        f"👤 ادمین پنل: <code>{username}</code>\n"
        f"📊 حجم فعلی: {limit_gb} گیگ | مصرف: {used_gb} گیگ\n"
        f"📦 حجم خرید: {data['volume_gb']} گیگ\n"
        f"💰 مبلغ: <b>{data['price']:,} تومان</b>\n\n"
        f"💳 کارت:\n<code>{card}</code>\n"
    )
    if account:
        text += f"🏦 حساب/شبا:\n<code>{account}</code>\n"
    text += f"صاحب حساب: {owner}\n\nعکس رسید را ارسال کنید."
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

    # auto approve for user if flag set
    u = await db.get_bot_user(message.from_user.id)
    auto = bool(u and u.get("auto_approve"))
    if auto:
        api = await get_panel_api(order["panel_id"])
        if api:
            result = await api.add_volume_to_admin(order["username"], order["volume_gb"])
            if result["success"]:
                await db.update_order(order_id, status="paid")
                await state.clear()
                await message.answer(
                    f"✅ پرداخت خودکار تأیید شد.\n{result['message']}",
                    reply_markup=user_main_keyboard(is_admin=is_admin(message.from_user.id)),
                )
                await report(bot, f"✅ خرید خودکار | {order['username']} | {order['volume_gb']}GB | {order['price']:,}ت")
                return

    caption = (
        "🧾 رسید پرداخت\n\n"
        f"👤 تلگرام: <code>{message.from_user.id}</code>\n"
        f"👤 ادمین پنل: <code>{order['username']}</code>\n"
        f"🖥 {panel['name'] if panel else '-'}\n"
        f"📦 {order['volume_gb']}GB | 💰 {order['price']:,} تومان"
    )
    try:
        await bot.send_photo(
            settings.ADMIN_ID, photo=file_id, caption=caption,
            parse_mode="HTML", reply_markup=confirm_order(order_id),
        )
    except Exception:
        pass
    await state.clear()
    await message.answer(
        "✅ رسید ارسال شد. منتظر تأیید بمانید.",
        reply_markup=user_main_keyboard(is_admin=is_admin(message.from_user.id)),
    )
    await report(bot, f"🧾 رسید جدید | <code>{message.from_user.id}</code> | {order['username']} | {order['volume_gb']}GB")


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
@router.message(F.text == "🖥 مدیریت پنل‌ها")
@router.callback_query(F.data == "manage_panels")
async def manage_panels(event: Message | CallbackQuery):
    if not is_admin(event.from_user.id):
        return
    panels = await db.get_panels(active_only=False)
    text = "🖥 مدیریت پنل‌ها:" + ("" if panels else "\nهیچ پنلی نیست.")
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
    card = await db.get_setting("card_number", "-")
    acc = await db.get_setting("account_number", "-")
    owner = await db.get_setting("card_owner", "-")
    auto = await db.get_setting("auto_approve_default", "0")
    await message.answer(
        f"💰 مالی\nکارت: <code>{card}</code>\nحساب: <code>{acc}</code>\nصاحب: {owner}\n"
        f"تأیید خودکار پیش‌فرض: {'✅' if auto=='1' else '❌'}",
        parse_mode="HTML",
        reply_markup=finance_keyboard(),
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
    await db.set_setting("auto_approve_default", "0" if cur == "1" else "1")
    await callback.answer("تغییر کرد")
    await callback.message.answer(f"تأیید خودکار پیش‌فرض: {'✅' if cur!='1' else '❌'}")


# --- bot settings ---
@router.message(F.text == "⚙️ تنظیمات ربات")
async def bot_settings(message: Message):
    if not is_admin(message.from_user.id):
        return
    keys = ["bot_enabled", "allow_buy", "require_phone", "require_iran_phone", "require_verify"]
    s = {k: await db.get_setting(k, "0") for k in keys}
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
async def set_rep_s(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id) or message.text == "❌ انصراف":
        return
    val = message.text.strip()
    if val == "-":
        val = ""
    await db.set_setting("report_channel", val)
    await state.clear()
    await message.answer("✅ کانال گزارش ذخیره شد.", reply_markup=admin_panel_keyboard())


# --- cron ---
@router.message(F.text == "⏰ تنظیمات کرون")
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
@router.message(F.text == "🗄 تنظیمات بک‌آپ")
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
    auto_ap = bool(u and u.get("auto_approve"))
    text = (
        f"👤 کاربر <code>{uid}</code>\n"
        f"نام: {(u or {}).get('full_name') or '-'}\n"
        f"یوزرنیم: @{(u or {}).get('username') or '-'}\n"
        f"وضعیت: {'🚫 بلاک' if blocked else '✅'}\n"
        f"احراز: {'✅' if verified else '❌'} | تأیید خودکار: {'✅' if auto_ap else '❌'}\n"
        f"واریزی: {stats['total_paid']:,}ت | حجم: {stats['total_volume']}GB | سفارش: {stats['paid_count']}"
    )
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


@router.callback_query(F.data.startswith("block_"))
async def blk(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    uid = int(callback.data.split("_")[1])
    await db.block_user(uid, "manual")
    await callback.answer("بلاک شد")
    await callback.message.answer(f"🚫 <code>{uid}</code> بلاک", parse_mode="HTML")


@router.callback_query(F.data.startswith("verify_"))
async def ver(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    uid = int(callback.data.split("_")[1])
    await db.upsert_bot_user(uid)
    await db.update_bot_user(uid, is_verified=1)
    await callback.answer("احراز شد")


@router.callback_query(F.data.startswith("unverify_"))
async def unver(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    uid = int(callback.data.split("_")[1])
    await db.update_bot_user(uid, is_verified=0)
    await callback.answer("حذف احراز")


@router.callback_query(F.data.startswith("autoap_"))
async def autoap(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    uid = int(callback.data.split("_")[1])
    u = await db.get_bot_user(uid)
    newv = 0 if (u and u.get("auto_approve")) else 1
    await db.upsert_bot_user(uid)
    await db.update_bot_user(uid, auto_approve=newv)
    await callback.answer("تأیید خودکار: " + ("روشن" if newv else "خاموش"))


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
    await db.assign_user_panel(data["assign_uid"], data["panel_id"], message.text.strip())
    await state.clear()
    await message.answer(
        f"✅ پنل برای کاربر {data['assign_uid']} ثبت شد.",
        reply_markup=admin_panel_keyboard(),
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
    if not order or order["status"] == "paid":
        await callback.answer("نامعتبر", show_alert=True)
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
        await report(bot, f"✅ تأیید | {order['username']} | {order['volume_gb']}GB | {order['price']:,}ت")
    else:
        await callback.message.answer(f"❌ {result['message']}")


@router.callback_query(F.data.startswith("reject_order_"))
async def reject(callback: CallbackQuery, bot: Bot):
    if not is_admin(callback.from_user.id):
        return
    oid = int(callback.data.split("_")[2])
    order = await db.get_order(oid)
    await db.update_order(oid, status="rejected")
    try:
        await callback.message.edit_caption(caption="❌ رد شد", reply_markup=None)
    except Exception:
        pass
    await callback.answer("رد")
    if order:
        try:
            await bot.send_message(order["user_id"], "❌ پرداخت رد شد.")
        except Exception:
            pass


@router.message(F.text == "ℹ️ وضعیت ربات")
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


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    data = await state.get_data()
    await go_back(message, state, bool(data.get("admin_context")) and is_admin(message.from_user.id))
