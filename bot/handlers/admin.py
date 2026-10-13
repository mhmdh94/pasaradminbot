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
    buy_select_panel, buy_select_plan, confirm_order, cancel_kb, back_to_admin
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
    set_card_owner = State()


def is_admin(user_id: int) -> bool:
    return user_id == settings.ADMIN_ID


# ==================== START ====================

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    admin = is_admin(message.from_user.id)
    text = (
        "👋 به ربات خرید حجم پاسارگارد خوش آمدید.\n\n"
        "از منوی زیر استفاده کنید:"
    )
    if admin:
        text += "\n\n⚙️ شما ادمین هستید — از دکمه «پنل ادمین» وارد مدیریت شوید."
    await message.answer(text, reply_markup=user_main_keyboard(is_admin=admin))


@router.message(F.text == "🔙 بازگشت به منوی اصلی")
@router.message(F.text == "❌ انصراف")
async def back_home(message: Message, state: FSMContext):
    await state.clear()
    admin = is_admin(message.from_user.id)
    await message.answer("🏠 منوی اصلی:", reply_markup=user_main_keyboard(is_admin=admin))


@router.message(F.text == "ℹ️ راهنما")
async def help_msg(message: Message):
    await message.answer(
        "📖 راهنما\n\n"
        "1️⃣ روی «خرید حجم» بزنید\n"
        "2️⃣ پلن مورد نظر را انتخاب کنید\n"
        "3️⃣ یوزرنیم خود در پنل را وارد کنید\n"
        "4️⃣ مبلغ را به کارت واریز کنید\n"
        "5️⃣ عکس رسید را ارسال کنید\n"
        "6️⃣ بعد از تأیید ادمین، حجم به اکانت شما اضافه می‌شود."
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


# ==================== USER: BUY VOLUME ====================

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

    if len(panels) == 1:
        await state.update_data(panel_id=panels[0]["id"])
        await message.answer(
            "📦 پلن حجم مورد نظر را انتخاب کنید:",
            reply_markup=buy_select_plan(plans)
        )
    else:
        await message.answer(
            "🖥 پنل مورد نظر را انتخاب کنید:",
            reply_markup=buy_select_panel(panels)
        )


@router.callback_query(F.data == "cancel_buy")
@router.callback_query(F.data == "cancel_state")
async def cancel_buy(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    admin = is_admin(callback.from_user.id)
    await callback.message.edit_text("❌ عملیات لغو شد.")
    await callback.message.answer("🏠 منوی اصلی:", reply_markup=user_main_keyboard(is_admin=admin))
    await callback.answer()


@router.callback_query(F.data.startswith("buy_panel_"))
async def buy_select_panel_cb(callback: CallbackQuery, state: FSMContext):
    panel_id = int(callback.data.split("_")[2])
    await state.update_data(panel_id=panel_id)
    plans = await db.get_plans()
    await callback.message.edit_text(
        "📦 پلن حجم مورد نظر را انتخاب کنید:",
        reply_markup=buy_select_plan(plans)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("buy_plan_"))
async def buy_select_plan_cb(callback: CallbackQuery, state: FSMContext):
    plan_id = int(callback.data.split("_")[2])
    plan = await db.get_plan(plan_id)
    if not plan or not plan["is_active"]:
        await callback.answer("پلن در دسترس نیست", show_alert=True)
        return
    await state.update_data(
        plan_id=plan_id,
        volume_gb=plan["volume_gb"],
        price=plan["price"],
        title=plan["title"]
    )
    await state.set_state(Form.buy_username)
    await callback.message.edit_text(
        f"📦 پلن: <b>{plan['title']}</b>\n"
        f"📊 حجم: {plan['volume_gb']} گیگابایت\n"
        f"💰 مبلغ: {plan['price']:,} تومان\n\n"
        "👤 یوزرنیم خود در پنل را وارد کنید:",
        parse_mode="HTML"
    )
    await callback.message.answer("یوزرنیم را ارسال کنید یا انصراف بزنید:", reply_markup=cancel_reply())
    await callback.answer()


@router.message(Form.buy_username)
async def process_buy_username(message: Message, state: FSMContext):
    if message.text == "❌ انصراف":
        await state.clear()
        await message.answer("🏠 منوی اصلی:", reply_markup=user_main_keyboard(is_admin=is_admin(message.from_user.id)))
        return

    username = message.text.strip()
    data = await state.get_data()

    api = await get_panel_api(data["panel_id"])
    if not api:
        await message.answer("❌ خطا در اتصال به پنل. بعداً تلاش کنید.", reply_markup=user_main_keyboard(is_admin=is_admin(message.from_user.id)))
        await state.clear()
        return

    user_info = await api.get_user(username)
    if not user_info or user_info.get("error"):
        await message.answer(
            f"❌ کاربر «{username}» در پنل پیدا نشد.\n"
            "یوزرنیم را درست وارد کنید:",
            reply_markup=cancel_reply()
        )
        return

    current_limit = user_info.get("data_limit") or 0
    used = user_info.get("used_traffic") or 0
    current_gb = round(current_limit / (1024**3), 2) if current_limit else "نامحدود"
    used_gb = round(used / (1024**3), 2)

    order_id = await db.create_order(
        user_id=message.from_user.id,
        panel_id=data["panel_id"],
        username=username,
        plan_id=data["plan_id"],
        volume_gb=data["volume_gb"],
        price=data["price"]
    )
    await state.update_data(order_id=order_id, username=username)
    await state.set_state(Form.waiting_receipt)

    card_number = await db.get_setting("card_number", settings.CARD_NUMBER)
    card_owner = await db.get_setting("card_owner", settings.CARD_OWNER)

    await message.answer(
        f"✅ سفارش ثبت شد (#{order_id})\n\n"
        f"👤 یوزرنیم: <code>{username}</code>\n"
        f"📊 حجم فعلی: {current_gb} گیگ | مصرف: {used_gb} گیگ\n"
        f"📦 پلن: {data['title']} ({data['volume_gb']} گیگ)\n"
        f"💰 مبلغ: <b>{data['price']:,} تومان</b>\n\n"
        f"💳 شماره کارت:\n<code>{card_number}</code>\n"
        f"صاحب کارت: {card_owner}\n\n"
        "پس از واریز، <b>عکس رسید</b> را ارسال کنید.",
        parse_mode="HTML",
        reply_markup=cancel_reply()
    )


@router.message(Form.waiting_receipt, F.photo)
async def process_receipt(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    order_id = data.get("order_id")
    if not order_id:
        await message.answer("سفارش پیدا نشد.")
        await state.clear()
        return

    file_id = message.photo[-1].file_id
    await db.update_order(order_id, receipt_file_id=file_id, status="pending")

    order = await db.get_order(order_id)
    panel = await db.get_panel(order["panel_id"])

    caption = (
        f"🧾 رسید پرداخت سفارش #{order_id}\n\n"
        f"👤 کاربر تلگرام: {message.from_user.id}\n"
        f"👤 یوزرنیم پنل: <code>{order['username']}</code>\n"
        f"🖥 پنل: {panel['name'] if panel else '-'}\n"
        f"📦 حجم: {order['volume_gb']} گیگابایت\n"
        f"💰 مبلغ: {order['price']:,} تومان\n\n"
        "تأیید یا رد کنید:"
    )
    try:
        await bot.send_photo(
            chat_id=settings.ADMIN_ID,
            photo=file_id,
            caption=caption,
            parse_mode="HTML",
            reply_markup=confirm_order(order_id)
        )
    except Exception:
        pass

    await state.clear()
    admin = is_admin(message.from_user.id)
    await message.answer(
        "✅ رسید دریافت شد و برای ادمین ارسال شد.\n"
        "بعد از تأیید، حجم به اکانت شما اضافه می‌شود.",
        reply_markup=user_main_keyboard(is_admin=admin)
    )


@router.message(Form.waiting_receipt)
async def process_receipt_wrong(message: Message):
    if message.text == "❌ انصراف":
        return
    await message.answer("لطفاً فقط عکس رسید را ارسال کنید یا «❌ انصراف» بزنید.")


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
    await callback.message.edit_text("⚙️ پنل مدیریت")
    await callback.message.answer("⚙️ پنل مدیریت ادمین:", reply_markup=admin_panel_keyboard())
    await callback.answer()


# ---------- Panels ----------

@router.message(F.text == "🖥 مدیریت پنل‌ها")
@router.callback_query(F.data == "manage_panels")
async def manage_panels(event: Message | CallbackQuery):
    uid = event.from_user.id
    if not is_admin(uid):
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
    await callback.message.edit_text("📝 نام پنل را وارد کنید (مثلاً: پنل اصلی):")
    await callback.message.answer("نام پنل:", reply_markup=cancel_reply())
    await callback.answer()


@router.message(Form.add_panel_name)
async def process_panel_name(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    if message.text == "❌ انصراف":
        await state.clear()
        await message.answer("لغو شد.", reply_markup=admin_panel_keyboard())
        return
    await state.update_data(name=message.text.strip())
    await state.set_state(Form.add_panel_url)
    await message.answer("🔗 آدرس پنل (مثلاً https://panel.example.com):")


@router.message(Form.add_panel_url)
async def process_panel_url(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    if message.text == "❌ انصراف":
        await state.clear()
        await message.answer("لغو شد.", reply_markup=admin_panel_keyboard())
        return
    url = message.text.strip().rstrip("/")
    if not url.startswith("http"):
        await message.answer("❌ آدرس باید با http یا https شروع شود.")
        return
    await state.update_data(url=url)
    await state.set_state(Form.add_panel_user)
    await message.answer("👤 یوزرنیم ادمین پنل:")


@router.message(Form.add_panel_user)
async def process_panel_user(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    if message.text == "❌ انصراف":
        await state.clear()
        await message.answer("لغو شد.", reply_markup=admin_panel_keyboard())
        return
    await state.update_data(username=message.text.strip())
    await state.set_state(Form.add_panel_pass)
    await message.answer("🔑 پسورد ادمین پنل:")


@router.message(Form.add_panel_pass)
async def process_panel_pass(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    if message.text == "❌ انصراف":
        await state.clear()
        await message.answer("لغو شد.", reply_markup=admin_panel_keyboard())
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
    panel_id = int(callback.data.split("_")[1])
    panel = await db.get_panel(panel_id)
    if not panel:
        await callback.answer("پیدا نشد", show_alert=True)
        return
    text = (
        f"🖥 <b>{panel['name']}</b>\n"
        f"🔗 <code>{panel['url']}</code>\n"
        f"👤 <code>{panel['username']}</code>\n"
        f"وضعیت: {'فعال' if panel['is_active'] else 'غیرفعال'}"
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
    await callback.answer("در حال تست...")
    result = await api.test_connection()
    await callback.message.answer(result["message"])


@router.callback_query(F.data.startswith("delete_panel_"))
async def cb_delete_panel(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    panel_id = int(callback.data.split("_")[2])
    await db.delete_panel(panel_id)
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
    text = "📦 مدیریت پلن‌های حجم:\n\n" + ("هیچ پلنی تعریف نشده." if not plans else "")
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
    await callback.message.edit_text("📝 عنوان پلن (مثلاً: ۵۰۰ گیگ):")
    await callback.message.answer("عنوان:", reply_markup=cancel_reply())
    await callback.answer()


@router.message(Form.add_plan_title)
async def process_plan_title(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    if message.text == "❌ انصراف":
        await state.clear()
        await message.answer("لغو شد.", reply_markup=admin_panel_keyboard())
        return
    await state.update_data(title=message.text.strip())
    await state.set_state(Form.add_plan_volume)
    await message.answer("📊 حجم به گیگابایت (حداقل ۵۰۰):")


@router.message(Form.add_plan_volume)
async def process_plan_volume(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    if message.text == "❌ انصراف":
        await state.clear()
        await message.answer("لغو شد.", reply_markup=admin_panel_keyboard())
        return
    try:
        volume = int(message.text.strip())
        if volume < 500:
            await message.answer("❌ حداقل ۵۰۰ گیگابایت.")
            return
    except ValueError:
        await message.answer("❌ فقط عدد وارد کنید.")
        return
    await state.update_data(volume_gb=volume)
    await state.set_state(Form.add_plan_price)
    await message.answer("💰 قیمت به تومان (فقط عدد):")


@router.message(Form.add_plan_price)
async def process_plan_price(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    if message.text == "❌ انصراف":
        await state.clear()
        await message.answer("لغو شد.", reply_markup=admin_panel_keyboard())
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
    await state.clear()
    await message.answer(
        f"✅ پلن اضافه شد:\n📦 {data['title']}\n📊 {data['volume_gb']}GB\n💰 {price:,} تومان",
        reply_markup=admin_panel_keyboard()
    )


@router.callback_query(F.data.startswith("plan_"))
async def cb_plan_detail(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    if callback.data.startswith("plan_") and callback.data.count("_") == 1:
        plan_id = int(callback.data.split("_")[1])
    else:
        return
    plan = await db.get_plan(plan_id)
    if not plan:
        await callback.answer("پیدا نشد", show_alert=True)
        return
    text = (
        f"📦 <b>{plan['title']}</b>\n"
        f"📊 {plan['volume_gb']} گیگابایت\n"
        f"💰 {plan['price']:,} تومان\n"
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
    text = (
        f"📦 <b>{plan['title']}</b>\n"
        f"📊 {plan['volume_gb']} گیگابایت\n"
        f"💰 {plan['price']:,} تومان\n"
        f"وضعیت: {'فعال' if plan['is_active'] else 'غیرفعال'}"
    )
    await callback.message.edit_text(text, reply_markup=plan_actions(plan_id), parse_mode="HTML")
    await callback.answer("وضعیت تغییر کرد")


@router.callback_query(F.data.startswith("delete_plan_"))
async def cb_delete_plan(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    plan_id = int(callback.data.split("_")[2])
    await db.delete_plan(plan_id)
    await callback.answer("حذف شد", show_alert=True)
    plans = await db.get_plans(active_only=False)
    await callback.message.edit_text("📦 مدیریت پلن‌ها:", reply_markup=plans_list(plans))


@router.callback_query(F.data.startswith("edit_plan_price_"))
async def cb_edit_plan_price(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    plan_id = int(callback.data.split("_")[3])
    await state.set_state(Form.edit_plan_price)
    await state.update_data(plan_id=plan_id)
    await callback.message.edit_text("💰 قیمت جدید به تومان:")
    await callback.message.answer("قیمت:", reply_markup=cancel_reply())
    await callback.answer()


@router.message(Form.edit_plan_price)
async def process_edit_price(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    if message.text == "❌ انصراف":
        await state.clear()
        await message.answer("لغو شد.", reply_markup=admin_panel_keyboard())
        return
    try:
        price = int(message.text.strip().replace(",", "").replace("،", ""))
    except ValueError:
        await message.answer("❌ عدد معتبر وارد کنید.")
        return
    data = await state.get_data()
    await db.update_plan(data["plan_id"], price=price)
    await state.clear()
    await message.answer(f"✅ قیمت به {price:,} تومان تغییر کرد.", reply_markup=admin_panel_keyboard())


# ---------- Card ----------

@router.message(F.text == "💳 تنظیمات کارت")
async def card_settings(message: Message):
    if not is_admin(message.from_user.id):
        return
    card_number = await db.get_setting("card_number", settings.CARD_NUMBER)
    card_owner = await db.get_setting("card_owner", settings.CARD_OWNER)
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✏️ تغییر شماره کارت", callback_data="set_card_number"))
    builder.row(InlineKeyboardButton(text="✏️ تغییر نام صاحب کارت", callback_data="set_card_owner"))
    await message.answer(
        f"💳 تنظیمات کارت‌به‌کارت:\n\n"
        f"شماره کارت: <code>{card_number}</code>\n"
        f"صاحب کارت: {card_owner}",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "set_card_number")
async def cb_set_card_number(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(Form.set_card_number)
    await callback.message.answer("شماره کارت جدید:", reply_markup=cancel_reply())
    await callback.answer()


@router.message(Form.set_card_number)
async def process_card_number(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    if message.text == "❌ انصراف":
        await state.clear()
        await message.answer("لغو شد.", reply_markup=admin_panel_keyboard())
        return
    await db.set_setting("card_number", message.text.strip())
    await state.clear()
    await message.answer("✅ شماره کارت ذخیره شد.", reply_markup=admin_panel_keyboard())


@router.callback_query(F.data == "set_card_owner")
async def cb_set_card_owner(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(Form.set_card_owner)
    await callback.message.answer("نام صاحب کارت:", reply_markup=cancel_reply())
    await callback.answer()


@router.message(Form.set_card_owner)
async def process_card_owner(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    if message.text == "❌ انصراف":
        await state.clear()
        await message.answer("لغو شد.", reply_markup=admin_panel_keyboard())
        return
    await db.set_setting("card_owner", message.text.strip())
    await state.clear()
    await message.answer("✅ نام صاحب کارت ذخیره شد.", reply_markup=admin_panel_keyboard())


# ---------- Orders approve ----------

@router.message(F.text == "📋 سفارش‌های در انتظار")
async def pending_orders_msg(message: Message):
    if not is_admin(message.from_user.id):
        return
    orders = await db.get_pending_orders()
    if not orders:
        await message.answer("سفارش در انتظاری نیست.")
        return
    lines = ["📋 سفارش‌های در انتظار:\n"]
    for o in orders:
        lines.append(f"#{o['id']} | {o['username']} | {o['volume_gb']}GB | {o['price']:,} ت | {o['status']}")
    await message.answer("\n".join(lines))


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

    await callback.answer("در حال افزودن حجم...")
    result = await api.add_volume(order["username"], order["volume_gb"])

    if result["success"]:
        await db.update_order(order_id, status="paid")
        text = (
            f"✅ سفارش #{order_id} تأیید شد.\n\n"
            f"{result['message']}\n"
            f"حجم قبلی: {result.get('old_limit_gb')} گیگ\n"
            f"حجم جدید: {result.get('new_limit_gb')} گیگ"
        )
        try:
            await callback.message.edit_caption(caption=text, reply_markup=None)
        except Exception:
            await callback.message.answer(text)

        # Notify user
        try:
            await bot.send_message(
                order["user_id"],
                f"✅ سفارش #{order_id} تأیید شد.\n"
                f"حجم {order['volume_gb']} گیگ به اکانت «{order['username']}» اضافه شد.\n"
                f"{result['message']}"
            )
        except Exception:
            pass
    else:
        await callback.message.answer(f"❌ خطا:\n{result['message']}")


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
            await bot.send_message(order["user_id"], f"❌ سفارش #{order_id} رد شد. با پشتیبانی تماس بگیرید.")
        except Exception:
            pass


# ---------- Backup & Status ----------

@router.message(F.text == "🗄 بک‌آپ دیتابیس")
async def backup_now(message: Message, bot: Bot):
    if not is_admin(message.from_user.id):
        return
    try:
        db_path = settings.DB_PATH
        if not os.path.exists(db_path):
            await message.answer("❌ دیتابیس پیدا نشد.")
            return
        backup_name = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        backup_path = os.path.join(settings.BASE_DIR, "data", backup_name)
        shutil.copy2(db_path, backup_path)
        await bot.send_document(
            chat_id=settings.ADMIN_ID,
            document=FSInputFile(backup_path),
            caption=f"🗄 بک‌آپ\n📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        os.remove(backup_path)
        await message.answer("✅ بک‌آپ ارسال شد.")
    except Exception as e:
        await message.answer(f"❌ خطا: {e}")


@router.message(F.text == "ℹ️ وضعیت ربات")
async def bot_status(message: Message):
    if not is_admin(message.from_user.id):
        return
    panels = await db.get_panels()
    plans = await db.get_plans()
    pending = await db.get_pending_orders()
    await message.answer(
        f"ℹ️ وضعیت ربات\n\n"
        f"🖥 پنل‌ها: {len(panels)}\n"
        f"📦 پلن‌های فعال: {len(plans)}\n"
        f"📋 سفارش در انتظار: {len(pending)}\n"
        f"👤 ادمین: <code>{settings.ADMIN_ID}</code>",
        parse_mode="HTML"
    )


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    admin = is_admin(message.from_user.id)
    await message.answer("❌ لغو شد.", reply_markup=user_main_keyboard(is_admin=admin))
