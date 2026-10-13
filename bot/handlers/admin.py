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
    finance_keyboard, backup_settings_keyboard
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


def is_admin(user_id: int) -> bool:
    return user_id == settings.ADMIN_ID


async def go_back(message: Message, state: FSMContext, admin_context: bool = False):
    """Cancel / back: admin stays in admin panel, user goes home."""
    await state.clear()
    if admin_context and is_admin(message.from_user.id):
        await message.answer("⚙️ پنل مدیریت ادمین:", reply_markup=admin_panel_keyboard())
    else:
        await message.answer(
            "🏠 منوی اصلی:",
            reply_markup=user_main_keyboard(is_admin=is_admin(message.from_user.id))
        )


# ==================== START ====================

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    admin = is_admin(message.from_user.id)
    text = "👋 به ربات خرید حجم پاسارگارد خوش آمدید.\n\nاز منوی زیر استفاده کنید:"
    if admin:
        text += "\n\n⚙️ شما ادمین هستید — از دکمه «پنل ادمین» وارد مدیریت شوید."
    await message.answer(text, reply_markup=user_main_keyboard(is_admin=admin))


@router.message(F.text == "🔙 بازگشت به منوی اصلی")
async def back_home(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "🏠 منوی اصلی:",
        reply_markup=user_main_keyboard(is_admin=is_admin(message.from_user.id))
    )


@router.message(F.text == "❌ انصراف")
async def cancel_btn(message: Message, state: FSMContext):
    # If admin was in an admin FSM state, go back to admin panel
    current = await state.get_state()
    admin_states = (
        Form.add_panel_name, Form.add_panel_url, Form.add_panel_user, Form.add_panel_pass,
        Form.add_plan_title, Form.add_plan_volume, Form.add_plan_price, Form.edit_plan_price,
        Form.set_card_number, Form.set_account_number, Form.set_card_owner,
        Form.backup_interval, Form.backup_import,
    )
    admin_ctx = False
    if current:
        for s in admin_states:
            if current == s.state:
                admin_ctx = True
                break
    # Also check data flag
    data = await state.get_data()
    if data.get("admin_context"):
        admin_ctx = True
    await go_back(message, state, admin_context=admin_ctx and is_admin(message.from_user.id))


@router.message(F.text == "ℹ️ راهنما")
async def help_msg(message: Message):
    await message.answer(
        "📖 راهنما\n\n"
        "1️⃣ روی «خرید حجم» بزنید\n"
        "2️⃣ پلن مورد نظر را انتخاب کنید\n"
        "3️⃣ یوزرنیم خود در پنل را وارد کنید\n"
        "4️⃣ مبلغ را واریز کنید\n"
        "5️⃣ عکس رسید را ارسال کنید\n"
        "6️⃣ بعد از تأیید ادمین، حجم اضافه می‌شود."
    )


@router.message(F.text == "📋 سفارش‌های من")
async def my_orders(message: Message):
    orders = await db.get_user_orders(message.from_user.id, limit=10)
    if not orders:
        await message.answer("هنوز سفارشی ثبت نکرده‌اید.")
        return
    status_map = {
        "waiting_receipt": "⏳ در انتظار رسید",
        "pending": "⏳ در انتظار تأیید",
        "paid": "✅ پرداخت شده",
        "rejected": "❌ رد شده",
        "cancelled": "🚫 لغو شده",
    }
    lines = ["📋 آخرین سفارش‌های شما:\n"]
    for o in orders:
        st = status_map.get(o["status"], o["status"])
        lines.append(f"#{o['id']} | {o['username']} | {o['volume_gb']}GB | {o['price']:,} ت | {st}")
    await message.answer("\n".join(lines))


# ==================== BUY VOLUME ====================

@router.message(F.text == "🛒 خرید حجم")
@router.message(F.text == "🛒 خرید حجم (ادمین)")
async def buy_volume_start(message: Message, state: FSMContext):
    panels = await db.get_panels()
    plans = await db.get_plans()
    if not panels:
        await message.answer("⚠️ هنوز پنلی تعریف نشده. لطفاً بعداً مراجعه کنید.")
        return
    if not plans:
        await message.answer("⚠️ هنوز پلنی تعریف نشده. لطفاً بعداً مراجعه کنید.")
        return
    if is_admin(message.from_user.id) and message.text == "🛒 خرید حجم (ادمین)":
        await state.update_data(admin_context=True)
    if len(panels) == 1:
        await state.update_data(panel_id=panels[0]["id"])
        await message.answer("📦 پلن حجم مورد نظر را انتخاب کنید:", reply_markup=buy_select_plan(plans))
    else:
        await message.answer("🖥 پنل مورد نظر را انتخاب کنید:", reply_markup=buy_select_panel(panels))


@router.callback_query(F.data == "cancel_buy")
async def cancel_buy(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    admin_ctx = data.get("admin_context") and is_admin(callback.from_user.id)
    await state.clear()
    await callback.message.edit_text("❌ عملیات لغو شد.")
    if admin_ctx:
        await callback.message.answer("⚙️ پنل مدیریت ادمین:", reply_markup=admin_panel_keyboard())
    else:
        await callback.message.answer(
            "🏠 منوی اصلی:",
            reply_markup=user_main_keyboard(is_admin=is_admin(callback.from_user.id))
        )
    await callback.answer()


@router.callback_query(F.data.startswith("buy_panel_"))
async def buy_select_panel_cb(callback: CallbackQuery, state: FSMContext):
    panel_id = int(callback.data.split("_")[2])
    await state.update_data(panel_id=panel_id)
    plans = await db.get_plans()
    await callback.message.edit_text("📦 پلن حجم مورد نظر را انتخاب کنید:", reply_markup=buy_select_plan(plans))
    await callback.answer()


@router.callback_query(F.data.startswith("buy_plan_"))
async def buy_select_plan_cb(callback: CallbackQuery, state: FSMContext):
    plan_id = int(callback.data.split("_")[2])
    plan = await db.get_plan(plan_id)
    if not plan or not plan["is_active"]:
        await callback.answer("پلن در دسترس نیست", show_alert=True)
        return
    per_gb = round(plan["price"] / plan["volume_gb"]) if plan["volume_gb"] else 0
    await state.update_data(
        plan_id=plan_id, volume_gb=plan["volume_gb"],
        price=plan["price"], title=plan["title"]
    )
    await state.set_state(Form.buy_username)
    await callback.message.edit_text(
        f"📦 پلن: <b>{plan['title']}</b>\n"
        f"📊 حجم: {plan['volume_gb']} گیگابایت\n"
        f"💰 مبلغ: {plan['price']:,} تومان\n"
        f"📈 هر گیگ: {per_gb:,} تومان\n\n"
        "👤 یوزرنیم خود در پنل را وارد کنید:",
        parse_mode="HTML"
    )
    await callback.message.answer("یوزرنیم را ارسال کنید:", reply_markup=cancel_reply())
    await callback.answer()


@router.message(Form.buy_username)
async def process_buy_username(message: Message, state: FSMContext):
    if message.text == "❌ انصراف":
        return  # handled by cancel_btn
    username = message.text.strip()
    data = await state.get_data()
    api = await get_panel_api(data["panel_id"])
    if not api:
        await state.clear()
        await message.answer("❌ خطا در اتصال به پنل.", reply_markup=user_main_keyboard(is_admin=is_admin(message.from_user.id)))
        return
    user_info = await api.get_user(username)
    if not user_info or user_info.get("error"):
        await message.answer(f"❌ کاربر «{username}» پیدا نشد. دوباره وارد کنید:", reply_markup=cancel_reply())
        return

    current_limit = user_info.get("data_limit") or 0
    used = user_info.get("used_traffic") or 0
    current_gb = round(current_limit / (1024**3), 2) if current_limit else "نامحدود"
    used_gb = round(used / (1024**3), 2)

    order_id = await db.create_order(
        user_id=message.from_user.id, panel_id=data["panel_id"],
        username=username, plan_id=data["plan_id"],
        volume_gb=data["volume_gb"], price=data["price"]
    )
    await state.update_data(order_id=order_id, username=username)
    await state.set_state(Form.waiting_receipt)

    card_number = await db.get_setting("card_number", settings.CARD_NUMBER)
    account_number = await db.get_setting("account_number", "")
    card_owner = await db.get_setting("card_owner", settings.CARD_OWNER)

    pay_text = (
        f"✅ سفارش #{order_id}\n\n"
        f"👤 یوزرنیم: <code>{username}</code>\n"
        f"📊 حجم فعلی: {current_gb} گیگ | مصرف: {used_gb} گیگ\n"
        f"📦 پلن: {data['title']} ({data['volume_gb']} گیگ)\n"
        f"💰 مبلغ: <b>{data['price']:,} تومان</b>\n\n"
        f"💳 شماره کارت:\n<code>{card_number}</code>\n"
    )
    if account_number:
        pay_text += f"🏦 شماره حساب / شبا:\n<code>{account_number}</code>\n"
    pay_text += f"صاحب حساب: {card_owner}\n\nپس از واریز، <b>عکس رسید</b> را ارسال کنید."

    await message.answer(pay_text, parse_mode="HTML", reply_markup=cancel_reply())


@router.message(Form.waiting_receipt, F.photo)
async def process_receipt(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    order_id = data.get("order_id")
    if not order_id:
        await state.clear()
        await message.answer("سفارش پیدا نشد.")
        return
    file_id = message.photo[-1].file_id
    await db.update_order(order_id, receipt_file_id=file_id, status="pending")
    order = await db.get_order(order_id)
    panel = await db.get_panel(order["panel_id"])
    caption = (
        f"🧾 رسید سفارش #{order_id}\n\n"
        f"👤 تلگرام: {message.from_user.id}\n"
        f"👤 یوزرنیم: <code>{order['username']}</code>\n"
        f"🖥 پنل: {panel['name'] if panel else '-'}\n"
        f"📦 {order['volume_gb']}GB | 💰 {order['price']:,} تومان\n\nتأیید یا رد:"
    )
    try:
        await bot.send_photo(
            chat_id=settings.ADMIN_ID, photo=file_id,
            caption=caption, parse_mode="HTML", reply_markup=confirm_order(order_id)
        )
    except Exception:
        pass
    await state.clear()
    await message.answer(
        "✅ رسید ارسال شد. بعد از تأیید ادمین حجم اضافه می‌شود.",
        reply_markup=user_main_keyboard(is_admin=is_admin(message.from_user.id))
    )


@router.message(Form.waiting_receipt)
async def process_receipt_wrong(message: Message):
    if message.text == "❌ انصراف":
        return
    await message.answer("لطفاً فقط عکس رسید بفرستید یا انصراف بزنید.")


# ==================== ADMIN PANEL ====================

@router.message(F.text == "⚙️ پنل ادمین")
async def open_admin_panel(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("⛔️ دسترسی ندارید.")
        return
    await state.clear()
    await message.answer("⚙️ پنل مدیریت ادمین:", reply_markup=admin_panel_keyboard())


@router.callback_query(F.data == "admin_menu")
async def cb_admin_menu(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.clear()
    try:
        await callback.message.edit_text("⚙️ پنل مدیریت")
    except Exception:
        pass
    await callback.message.answer("⚙️ پنل مدیریت ادمین:", reply_markup=admin_panel_keyboard())
    await callback.answer()


# ---------- Panels ----------

@router.message(F.text == "🖥 مدیریت پنل‌ها")
@router.callback_query(F.data == "manage_panels")
async def manage_panels(event: Message | CallbackQuery):
    if not is_admin(event.from_user.id):
        return
    panels = await db.get_panels(active_only=False)
    text = "🖥 مدیریت پنل‌ها:\n\n" + ("هیچ پنلی ثبت نشده." if not panels else "")
    kb = panels_list(panels)
    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, reply_markup=kb)
        await event.answer()
    else:
        await event.answer(text, reply_markup=kb)


@router.callback_query(F.data == "add_panel")
async def cb_add_panel(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(Form.add_panel_name)
    await state.update_data(admin_context=True)
    await callback.message.edit_text("📝 نام پنل را وارد کنید:")
    await callback.message.answer("نام پنل:", reply_markup=cancel_reply())
    await callback.answer()


@router.message(Form.add_panel_name)
async def process_panel_name(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id) or message.text == "❌ انصراف":
        return
    await state.update_data(name=message.text.strip())
    await state.set_state(Form.add_panel_url)
    await message.answer("🔗 آدرس پنل (https://...):")


@router.message(Form.add_panel_url)
async def process_panel_url(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id) or message.text == "❌ انصراف":
        return
    url = message.text.strip().rstrip("/")
    if not url.startswith("http"):
        await message.answer("❌ باید با http/https شروع شود.")
        return
    await state.update_data(url=url)
    await state.set_state(Form.add_panel_user)
    await message.answer("👤 یوزرنیم ادمین پنل:")


@router.message(Form.add_panel_user)
async def process_panel_user(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id) or message.text == "❌ انصراف":
        return
    await state.update_data(username=message.text.strip())
    await state.set_state(Form.add_panel_pass)
    await message.answer("🔑 پسورد ادمین پنل:")


@router.message(Form.add_panel_pass)
async def process_panel_pass(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id) or message.text == "❌ انصراف":
        return
    data = await state.get_data()
    panel_id = await db.add_panel(data["name"], data["url"], data["username"], message.text.strip())
    await state.clear()
    api = await get_panel_api(panel_id)
    test = await api.test_connection() if api else {"success": False, "message": "خطا"}
    status = "✅ اتصال موفق" if test["success"] else f"❌ {test['message']}"
    await message.answer(f"✅ پنل «{data['name']}» اضافه شد.\n{status}", reply_markup=admin_panel_keyboard())


@router.callback_query(F.data.startswith("panel_"))
async def cb_panel_detail(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    if not callback.data.startswith("panel_") or callback.data.count("_") != 1:
        return
    panel_id = int(callback.data.split("_")[1])
    panel = await db.get_panel(panel_id)
    if not panel:
        await callback.answer("پیدا نشد", show_alert=True)
        return
    text = (
        f"🖥 <b>{panel['name']}</b>\n🔗 <code>{panel['url']}</code>\n"
        f"👤 <code>{panel['username']}</code>\nوضعیت: {'فعال' if panel['is_active'] else 'غیرفعال'}"
    )
    await callback.message.edit_text(text, reply_markup=panel_actions(panel_id), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("test_panel_"))
async def cb_test_panel(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    panel_id = int(callback.data.split("_")[2])
    api = await get_panel_api(panel_id)
    if not api:
        await callback.answer("پیدا نشد", show_alert=True)
        return
    await callback.answer("تست...")
    result = await api.test_connection()
    await callback.message.answer(result["message"])


@router.callback_query(F.data.startswith("delete_panel_"))
async def cb_delete_panel(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    await db.delete_panel(int(callback.data.split("_")[2]))
    await callback.answer("حذف شد", show_alert=True)
    panels = await db.get_panels(active_only=False)
    await callback.message.edit_text("🖥 مدیریت پنل‌ها:", reply_markup=panels_list(panels))


# ---------- Plans ----------

@router.message(F.text == "📦 مدیریت پلن‌ها")
@router.callback_query(F.data == "manage_plans")
async def manage_plans(event: Message | CallbackQuery):
    if not is_admin(event.from_user.id):
        return
    plans = await db.get_plans(active_only=False)
    text = "📦 مدیریت پلن‌ها (مرتب‌شده بر اساس حجم):\n\n" + ("هیچ پلنی نیست." if not plans else "")
    kb = plans_list(plans)
    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, reply_markup=kb)
        await event.answer()
    else:
        await event.answer(text, reply_markup=kb)


@router.callback_query(F.data == "add_plan")
async def cb_add_plan(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(Form.add_plan_title)
    await state.update_data(admin_context=True)
    await callback.message.edit_text("📝 عنوان پلن:")
    await callback.message.answer("عنوان:", reply_markup=cancel_reply())
    await callback.answer()


@router.message(Form.add_plan_title)
async def process_plan_title(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id) or message.text == "❌ انصراف":
        return
    await state.update_data(title=message.text.strip())
    await state.set_state(Form.add_plan_volume)
    await message.answer("📊 حجم به گیگ (حداقل ۵۰۰):")


@router.message(Form.add_plan_volume)
async def process_plan_volume(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id) or message.text == "❌ انصراف":
        return
    try:
        volume = int(message.text.strip())
        if volume < 500:
            await message.answer("❌ حداقل ۵۰۰ گیگ.")
            return
    except ValueError:
        await message.answer("❌ فقط عدد.")
        return
    await state.update_data(volume_gb=volume)
    await state.set_state(Form.add_plan_price)
    await message.answer("💰 قیمت به تومان:")


@router.message(Form.add_plan_price)
async def process_plan_price(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id) or message.text == "❌ انصراف":
        return
    try:
        price = int(message.text.strip().replace(",", "").replace("،", ""))
        if price <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ قیمت معتبر وارد کنید.")
        return
    data = await state.get_data()
    await db.add_plan(data["title"], data["volume_gb"], price)
    per_gb = round(price / data["volume_gb"])
    await state.clear()
    await message.answer(
        f"✅ پلن اضافه شد:\n📦 {data['title']}\n📊 {data['volume_gb']}GB\n"
        f"💰 {price:,} تومان (هر گیگ {per_gb:,})",
        reply_markup=admin_panel_keyboard()
    )


@router.callback_query(F.data.regexp(r"^plan_\d+$"))
async def cb_plan_detail(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    plan_id = int(callback.data.split("_")[1])
    plan = await db.get_plan(plan_id)
    if not plan:
        await callback.answer("پیدا نشد", show_alert=True)
        return
    per_gb = round(plan["price"] / plan["volume_gb"]) if plan["volume_gb"] else 0
    text = (
        f"📦 <b>{plan['title']}</b>\n📊 {plan['volume_gb']} گیگ\n"
        f"💰 {plan['price']:,} تومان\n📈 هر گیگ: {per_gb:,} تومان\n"
        f"وضعیت: {'فعال' if plan['is_active'] else 'غیرفعال'}"
    )
    await callback.message.edit_text(text, reply_markup=plan_actions(plan_id), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("toggle_plan_"))
async def cb_toggle_plan(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    plan_id = int(callback.data.split("_")[2])
    plan = await db.get_plan(plan_id)
    if not plan:
        return
    await db.update_plan(plan_id, is_active=0 if plan["is_active"] else 1)
    plan = await db.get_plan(plan_id)
    per_gb = round(plan["price"] / plan["volume_gb"]) if plan["volume_gb"] else 0
    text = (
        f"📦 <b>{plan['title']}</b>\n📊 {plan['volume_gb']} گیگ\n"
        f"💰 {plan['price']:,} تومان\n📈 هر گیگ: {per_gb:,}\n"
        f"وضعیت: {'فعال' if plan['is_active'] else 'غیرفعال'}"
    )
    await callback.message.edit_text(text, reply_markup=plan_actions(plan_id), parse_mode="HTML")
    await callback.answer("تغییر کرد")


@router.callback_query(F.data.startswith("delete_plan_"))
async def cb_delete_plan(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    await db.delete_plan(int(callback.data.split("_")[2]))
    await callback.answer("حذف شد", show_alert=True)
    plans = await db.get_plans(active_only=False)
    await callback.message.edit_text("📦 مدیریت پلن‌ها:", reply_markup=plans_list(plans))


@router.callback_query(F.data.startswith("edit_plan_price_"))
async def cb_edit_plan_price(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(Form.edit_plan_price)
    await state.update_data(plan_id=int(callback.data.split("_")[3]), admin_context=True)
    await callback.message.edit_text("💰 قیمت جدید:")
    await callback.message.answer("قیمت:", reply_markup=cancel_reply())
    await callback.answer()


@router.message(Form.edit_plan_price)
async def process_edit_price(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id) or message.text == "❌ انصراف":
        return
    try:
        price = int(message.text.strip().replace(",", "").replace("،", ""))
    except ValueError:
        await message.answer("❌ عدد معتبر.")
        return
    data = await state.get_data()
    await db.update_plan(data["plan_id"], price=price)
    await state.clear()
    await message.answer(f"✅ قیمت: {price:,} تومان", reply_markup=admin_panel_keyboard())


# ---------- Finance ----------

@router.message(F.text == "💰 تنظیمات مالی")
async def finance_settings(message: Message):
    if not is_admin(message.from_user.id):
        return
    card = await db.get_setting("card_number", settings.CARD_NUMBER)
    account = await db.get_setting("account_number", "-")
    owner = await db.get_setting("card_owner", settings.CARD_OWNER)
    await message.answer(
        f"💰 تنظیمات مالی\n\n"
        f"💳 شماره کارت: <code>{card}</code>\n"
        f"🏦 شماره حساب/شبا: <code>{account}</code>\n"
        f"👤 صاحب حساب: {owner}\n\n"
        "این اطلاعات هنگام خرید به کاربر نمایش داده می‌شود.",
        reply_markup=finance_keyboard(),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "set_card_number")
async def cb_set_card(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(Form.set_card_number)
    await state.update_data(admin_context=True)
    await callback.message.answer("شماره کارت جدید:", reply_markup=cancel_reply())
    await callback.answer()


@router.message(Form.set_card_number)
async def process_card(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id) or message.text == "❌ انصراف":
        return
    await db.set_setting("card_number", message.text.strip())
    await state.clear()
    await message.answer("✅ شماره کارت ذخیره شد.", reply_markup=admin_panel_keyboard())


@router.callback_query(F.data == "set_account_number")
async def cb_set_account(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(Form.set_account_number)
    await state.update_data(admin_context=True)
    await callback.message.answer("شماره حساب یا شبا:", reply_markup=cancel_reply())
    await callback.answer()


@router.message(Form.set_account_number)
async def process_account(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id) or message.text == "❌ انصراف":
        return
    await db.set_setting("account_number", message.text.strip())
    await state.clear()
    await message.answer("✅ شماره حساب ذخیره شد.", reply_markup=admin_panel_keyboard())


@router.callback_query(F.data == "set_card_owner")
async def cb_set_owner(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(Form.set_card_owner)
    await state.update_data(admin_context=True)
    await callback.message.answer("نام صاحب حساب:", reply_markup=cancel_reply())
    await callback.answer()


@router.message(Form.set_card_owner)
async def process_owner(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id) or message.text == "❌ انصراف":
        return
    await db.set_setting("card_owner", message.text.strip())
    await state.clear()
    await message.answer("✅ نام صاحب حساب ذخیره شد.", reply_markup=admin_panel_keyboard())


# ---------- Backup Settings ----------

@router.message(F.text == "🗄 تنظیمات بک‌آپ")
async def backup_settings(message: Message):
    if not is_admin(message.from_user.id):
        return
    hours = await db.get_setting("backup_interval_hours", "24")
    await message.answer(
        f"🗄 تنظیمات بک‌آپ\n\n"
        f"⏰ فاصله بک‌آپ خودکار: هر {hours} ساعت\n\n"
        "Export: دانلود فایل دیتابیس\n"
        "Import: بازگردانی از فایل بک‌آپ",
        reply_markup=backup_settings_keyboard()
    )


@router.callback_query(F.data == "backup_export")
async def backup_export(callback: CallbackQuery, bot: Bot):
    if not is_admin(callback.from_user.id):
        return
    await callback.answer("در حال تهیه...")
    try:
        db_path = settings.DB_PATH
        if not os.path.exists(db_path):
            await callback.message.answer("❌ دیتابیس پیدا نشد.")
            return
        name = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        path = os.path.join(settings.BASE_DIR, "data", name)
        shutil.copy2(db_path, path)
        await bot.send_document(
            chat_id=settings.ADMIN_ID,
            document=FSInputFile(path),
            caption=f"📤 Export دیتابیس\n📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )
        os.remove(path)
        await callback.message.answer("✅ بک‌آپ ارسال شد.")
    except Exception as e:
        await callback.message.answer(f"❌ خطا: {e}")


@router.callback_query(F.data == "backup_import")
async def backup_import_start(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(Form.backup_import)
    await state.update_data(admin_context=True)
    await callback.message.answer(
        "📥 فایل بک‌آپ (.db) را ارسال کنید.\n⚠️ دیتابیس فعلی جایگزین می‌شود!",
        reply_markup=cancel_reply()
    )
    await callback.answer()


@router.message(Form.backup_import, F.document)
async def backup_import_file(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    doc = message.document
    if not doc.file_name or not doc.file_name.endswith(".db"):
        await message.answer("❌ فقط فایل .db بفرستید.")
        return
    try:
        bot = message.bot
        file = await bot.get_file(doc.file_id)
        dest = settings.DB_PATH
        # backup current first
        if os.path.exists(dest):
            shutil.copy2(dest, dest + ".before_import")
        await bot.download_file(file.file_path, dest)
        await state.clear()
        await message.answer(
            "✅ دیتابیس بازگردانی شد.\nربات را یک‌بار ری‌استارت کنید:\n"
            "<code>systemctl restart pasaradminbot</code>",
            parse_mode="HTML",
            reply_markup=admin_panel_keyboard()
        )
    except Exception as e:
        await message.answer(f"❌ خطا: {e}", reply_markup=admin_panel_keyboard())
        await state.clear()


@router.message(Form.backup_import)
async def backup_import_wrong(message: Message):
    if message.text == "❌ انصراف":
        return
    await message.answer("لطفاً فایل .db ارسال کنید یا انصراف بزنید.")


@router.callback_query(F.data == "backup_interval")
async def backup_interval_start(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(Form.backup_interval)
    await state.update_data(admin_context=True)
    await callback.message.answer(
        "⏰ فاصله بک‌آپ خودکار را به ساعت وارد کنید (مثلاً 6 یا 12 یا 24):\n"
        "حداقل ۱ ساعت.",
        reply_markup=cancel_reply()
    )
    await callback.answer()


@router.message(Form.backup_interval)
async def process_backup_interval(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id) or message.text == "❌ انصراف":
        return
    try:
        hours = int(message.text.strip())
        if hours < 1:
            raise ValueError
    except ValueError:
        await message.answer("❌ عدد معتبر (حداقل ۱).")
        return
    await db.set_setting("backup_interval_hours", str(hours))
    await state.clear()
    await message.answer(
        f"✅ بک‌آپ خودکار هر {hours} ساعت یک‌بار ارسال می‌شود.\n"
        "برای اعمال، سرویس را ری‌استارت کنید:\n"
        "<code>systemctl restart pasaradminbot</code>",
        parse_mode="HTML",
        reply_markup=admin_panel_keyboard()
    )


# ---------- Approve / Reject ----------

@router.callback_query(F.data.startswith("approve_order_"))
async def cb_approve_order(callback: CallbackQuery, bot: Bot):
    if not is_admin(callback.from_user.id):
        return
    order_id = int(callback.data.split("_")[2])
    order = await db.get_order(order_id)
    if not order:
        await callback.answer("پیدا نشد", show_alert=True)
        return
    if order["status"] == "paid":
        await callback.answer("قبلاً تأیید شده", show_alert=True)
        return
    api = await get_panel_api(order["panel_id"])
    if not api:
        await callback.answer("پنل پیدا نشد", show_alert=True)
        return
    await callback.answer("در حال افزودن...")
    result = await api.add_volume(order["username"], order["volume_gb"])
    if result["success"]:
        await db.update_order(order_id, status="paid")
        text = (
            f"✅ سفارش #{order_id} تأیید شد.\n{result['message']}\n"
            f"قبل: {result.get('old_limit_gb')} گیگ → بعد: {result.get('new_limit_gb')} گیگ"
        )
        try:
            await callback.message.edit_caption(caption=text, reply_markup=None)
        except Exception:
            await callback.message.answer(text)
        try:
            await bot.send_message(
                order["user_id"],
                f"✅ سفارش #{order_id} تأیید شد.\n"
                f"حجم {order['volume_gb']} گیگ به «{order['username']}» اضافه شد."
            )
        except Exception:
            pass
    else:
        await callback.message.answer(f"❌ {result['message']}")


@router.callback_query(F.data.startswith("reject_order_"))
async def cb_reject_order(callback: CallbackQuery, bot: Bot):
    if not is_admin(callback.from_user.id):
        return
    order_id = int(callback.data.split("_")[2])
    order = await db.get_order(order_id)
    await db.update_order(order_id, status="rejected")
    try:
        await callback.message.edit_caption(caption=f"❌ سفارش #{order_id} رد شد.", reply_markup=None)
    except Exception:
        pass
    await callback.answer("رد شد")
    if order:
        try:
            await bot.send_message(order["user_id"], f"❌ سفارش #{order_id} رد شد.")
        except Exception:
            pass


# ---------- Status ----------

@router.message(F.text == "ℹ️ وضعیت ربات")
async def bot_status(message: Message):
    if not is_admin(message.from_user.id):
        return
    panels = await db.get_panels()
    plans = await db.get_plans()
    pending = await db.get_pending_orders()
    hours = await db.get_setting("backup_interval_hours", "24")
    await message.answer(
        f"ℹ️ وضعیت\n\n🖥 پنل‌ها: {len(panels)}\n📦 پلن‌ها: {len(plans)}\n"
        f"📋 در انتظار تأیید: {len(pending)}\n⏰ بک‌آپ هر {hours} ساعت\n"
        f"👤 ادمین: <code>{settings.ADMIN_ID}</code>",
        parse_mode="HTML"
    )


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    data = await state.get_data()
    admin_ctx = data.get("admin_context") and is_admin(message.from_user.id)
    await go_back(message, state, admin_context=admin_ctx)
