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
    admin_main_menu, panels_list, panel_actions,
    plans_list, plan_actions, buy_select_panel, buy_select_plan,
    confirm_order, cancel_kb, back_to_menu
)
from bot.services.pasarguard import get_panel_api, PasarGuardAPI

router = Router()


class AdminStates(StatesGroup):
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


# ==================== START & MENU ====================

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("⛔️ این ربات فقط برای ادمین قابل استفاده است.")
        return
    await state.clear()
    await message.answer(
        "👋 به ربات خرید حجم پاسارگارد خوش آمدید.\n\n"
        "از منوی زیر استفاده کنید:",
        reply_markup=admin_main_menu()
    )


@router.callback_query(F.data == "admin_menu")
async def cb_admin_menu(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.clear()
    await callback.message.edit_text(
        "🏠 منوی اصلی ادمین:",
        reply_markup=admin_main_menu()
    )
    await callback.answer()


@router.callback_query(F.data == "cancel_state")
async def cb_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "❌ عملیات لغو شد.",
        reply_markup=admin_main_menu()
    )
    await callback.answer()


# ==================== PANEL MANAGEMENT ====================

@router.callback_query(F.data == "manage_panels")
async def cb_manage_panels(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    panels = await db.get_panels(active_only=False)
    text = "🖥 مدیریت پنل‌ها:\n\n"
    if not panels:
        text += "هیچ پنلی ثبت نشده است."
    await callback.message.edit_text(text, reply_markup=panels_list(panels))
    await callback.answer()


@router.callback_query(F.data == "add_panel")
async def cb_add_panel(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(AdminStates.add_panel_name)
    await callback.message.edit_text(
        "📝 نام پنل را وارد کنید (مثلاً: پنل اصلی):\n\n"
        "برای انصراف /cancel بزنید.",
        reply_markup=cancel_kb()
    )
    await callback.answer()


@router.message(AdminStates.add_panel_name)
async def process_panel_name(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.update_data(name=message.text.strip())
    await state.set_state(AdminStates.add_panel_url)
    await message.answer(
        "🔗 آدرس پنل را وارد کنید (مثلاً: https://panel.example.com):\n"
        "بدون / در انتها",
        reply_markup=cancel_kb()
    )


@router.message(AdminStates.add_panel_url)
async def process_panel_url(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    url = message.text.strip().rstrip("/")
    if not url.startswith("http"):
        await message.answer("❌ آدرس باید با http یا https شروع شود.")
        return
    await state.update_data(url=url)
    await state.set_state(AdminStates.add_panel_user)
    await message.answer("👤 یوزرنیم ادمین پنل را وارد کنید:", reply_markup=cancel_kb())


@router.message(AdminStates.add_panel_user)
async def process_panel_user(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.update_data(username=message.text.strip())
    await state.set_state(AdminStates.add_panel_pass)
    await message.answer("🔑 پسورد ادمین پنل را وارد کنید:", reply_markup=cancel_kb())


@router.message(AdminStates.add_panel_pass)
async def process_panel_pass(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    data = await state.get_data()
    password = message.text.strip()

    panel_id = await db.add_panel(
        name=data["name"],
        url=data["url"],
        username=data["username"],
        password=password
    )
    await state.clear()

    # Test connection
    api = await get_panel_api(panel_id)
    test = await api.test_connection() if api else {"success": False, "message": "خطا"}

    status = "✅ اتصال موفق" if test["success"] else f"❌ {test['message']}"

    await message.answer(
        f"✅ پنل «{data['name']}» اضافه شد.\n"
        f"وضعیت اتصال: {status}",
        reply_markup=admin_main_menu()
    )


@router.callback_query(F.data.startswith("panel_"))
async def cb_panel_detail(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    panel_id = int(callback.data.split("_")[1])
    panel = await db.get_panel(panel_id)
    if not panel:
        await callback.answer("پنل پیدا نشد", show_alert=True)
        return
    text = (
        f"🖥 پنل: <b>{panel['name']}</b>\n"
        f"🔗 آدرس: <code>{panel['url']}</code>\n"
        f"👤 یوزرنیم: <code>{panel['username']}</code>\n"
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
        await callback.answer("پنل پیدا نشد", show_alert=True)
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
    await callback.answer("پنل حذف شد", show_alert=True)
    panels = await db.get_panels(active_only=False)
    await callback.message.edit_text("🖥 مدیریت پنل‌ها:", reply_markup=panels_list(panels))


# ==================== PLAN MANAGEMENT ====================

@router.callback_query(F.data == "manage_plans")
async def cb_manage_plans(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    plans = await db.get_plans(active_only=False)
    text = "📦 مدیریت پلن‌های حجم:\n\n"
    if not plans:
        text += "هیچ پلنی تعریف نشده.\nاز دکمه زیر پلن اضافه کنید (از ۵۰۰ گیگ به بالا)."
    await callback.message.edit_text(text, reply_markup=plans_list(plans))
    await callback.answer()


@router.callback_query(F.data == "add_plan")
async def cb_add_plan(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(AdminStates.add_plan_title)
    await callback.message.edit_text(
        "📝 عنوان پلن را وارد کنید (مثلاً: ۵۰۰ گیگ):\n\n"
        "برای انصراف /cancel",
        reply_markup=cancel_kb()
    )
    await callback.answer()


@router.message(AdminStates.add_plan_title)
async def process_plan_title(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.update_data(title=message.text.strip())
    await state.set_state(AdminStates.add_plan_volume)
    await message.answer(
        "📊 حجم را به گیگابایت وارد کنید (عدد، مثلاً 500 یا 1024):\n"
        "حداقل ۵۰۰ گیگ",
        reply_markup=cancel_kb()
    )


@router.message(AdminStates.add_plan_volume)
async def process_plan_volume(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    try:
        volume = int(message.text.strip())
        if volume < 500:
            await message.answer("❌ حداقل حجم ۵۰۰ گیگابایت است.")
            return
    except ValueError:
        await message.answer("❌ فقط عدد وارد کنید.")
        return
    await state.update_data(volume_gb=volume)
    await state.set_state(AdminStates.add_plan_price)
    await message.answer("💰 قیمت را به تومان وارد کنید (فقط عدد):", reply_markup=cancel_kb())


@router.message(AdminStates.add_plan_price)
async def process_plan_price(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    try:
        price = int(message.text.strip().replace(",", "").replace("،", ""))
        if price <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ قیمت معتبر وارد کنید.")
        return

    data = await state.get_data()
    plan_id = await db.add_plan(
        title=data["title"],
        volume_gb=data["volume_gb"],
        price=price
    )
    await state.clear()
    await message.answer(
        f"✅ پلن اضافه شد:\n"
        f"📦 {data['title']}\n"
        f"📊 {data['volume_gb']} گیگابایت\n"
        f"💰 {price:,} تومان",
        reply_markup=admin_main_menu()
    )


@router.callback_query(F.data.startswith("plan_"))
async def cb_plan_detail(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    plan_id = int(callback.data.split("_")[1])
    plan = await db.get_plan(plan_id)
    if not plan:
        await callback.answer("پلن پیدا نشد", show_alert=True)
        return
    text = (
        f"📦 <b>{plan['title']}</b>\n"
        f"📊 حجم: {plan['volume_gb']} گیگابایت\n"
        f"💰 قیمت: {plan['price']:,} تومان\n"
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
    new_status = 0 if plan["is_active"] else 1
    await db.update_plan(plan_id, is_active=new_status)
    await callback.answer("وضعیت تغییر کرد")
    plan = await db.get_plan(plan_id)
    text = (
        f"📦 <b>{plan['title']}</b>\n"
        f"📊 حجم: {plan['volume_gb']} گیگابایت\n"
        f"💰 قیمت: {plan['price']:,} تومان\n"
        f"وضعیت: {'فعال' if plan['is_active'] else 'غیرفعال'}"
    )
    await callback.message.edit_text(text, reply_markup=plan_actions(plan_id), parse_mode="HTML")


@router.callback_query(F.data.startswith("delete_plan_"))
async def cb_delete_plan(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    plan_id = int(callback.data.split("_")[2])
    await db.delete_plan(plan_id)
    await callback.answer("پلن حذف شد", show_alert=True)
    plans = await db.get_plans(active_only=False)
    await callback.message.edit_text("📦 مدیریت پلن‌ها:", reply_markup=plans_list(plans))


@router.callback_query(F.data.startswith("edit_plan_price_"))
async def cb_edit_plan_price(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    plan_id = int(callback.data.split("_")[3])
    await state.set_state(AdminStates.edit_plan_price)
    await state.update_data(plan_id=plan_id)
    await callback.message.edit_text(
        "💰 قیمت جدید را به تومان وارد کنید:",
        reply_markup=cancel_kb()
    )
    await callback.answer()


@router.message(AdminStates.edit_plan_price)
async def process_edit_price(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    try:
        price = int(message.text.strip().replace(",", "").replace("،", ""))
    except ValueError:
        await message.answer("❌ عدد معتبر وارد کنید.")
        return
    data = await state.get_data()
    await db.update_plan(data["plan_id"], price=price)
    await state.clear()
    await message.answer(f"✅ قیمت به {price:,} تومان تغییر کرد.", reply_markup=admin_main_menu())


# ==================== BUY VOLUME ====================

@router.callback_query(F.data == "buy_volume")
async def cb_buy_volume(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    panels = await db.get_panels()
    if not panels:
        await callback.answer("ابتدا یک پنل اضافه کنید!", show_alert=True)
        return
    plans = await db.get_plans()
    if not plans:
        await callback.answer("ابتدا حداقل یک پلن حجم تعریف کنید!", show_alert=True)
        return

    if len(panels) == 1:
        await state.update_data(panel_id=panels[0]["id"])
        await callback.message.edit_text(
            "📦 پلن حجم مورد نظر را انتخاب کنید:",
            reply_markup=buy_select_plan(plans)
        )
    else:
        await callback.message.edit_text(
            "🖥 پنل مورد نظر را انتخاب کنید:",
            reply_markup=buy_select_panel(panels)
        )
    await callback.answer()


@router.callback_query(F.data.startswith("buy_panel_"))
async def cb_buy_select_panel(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    panel_id = int(callback.data.split("_")[2])
    await state.update_data(panel_id=panel_id)
    plans = await db.get_plans()
    await callback.message.edit_text(
        "📦 پلن حجم مورد نظر را انتخاب کنید:",
        reply_markup=buy_select_plan(plans)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("buy_plan_"))
async def cb_buy_select_plan(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    plan_id = int(callback.data.split("_")[2])
    plan = await db.get_plan(plan_id)
    if not plan:
        await callback.answer("پلن پیدا نشد", show_alert=True)
        return
    await state.update_data(plan_id=plan_id, volume_gb=plan["volume_gb"], price=plan["price"], title=plan["title"])
    await state.set_state(AdminStates.buy_username)
    await callback.message.edit_text(
        f"📦 پلن انتخاب شده: <b>{plan['title']}</b>\n"
        f"📊 حجم: {plan['volume_gb']} گیگابایت\n"
        f"💰 مبلغ: {plan['price']:,} تومان\n\n"
        "👤 یوزرنیم کاربر در پنل را وارد کنید:",
        reply_markup=cancel_kb(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(AdminStates.buy_username)
async def process_buy_username(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    username = message.text.strip()
    data = await state.get_data()

    # Check user exists in panel
    api = await get_panel_api(data["panel_id"])
    if not api:
        await message.answer("❌ پنل پیدا نشد.", reply_markup=admin_main_menu())
        await state.clear()
        return

    user_info = await api.get_user(username)
    if not user_info or user_info.get("error"):
        await message.answer(
            f"❌ کاربر «{username}» در پنل پیدا نشد.\n"
            "یوزرنیم را درست وارد کنید یا دوباره تلاش کنید.",
            reply_markup=cancel_kb()
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
    await state.set_state(AdminStates.waiting_receipt)

    card_number = await db.get_setting("card_number", settings.CARD_NUMBER)
    card_owner = await db.get_setting("card_owner", settings.CARD_OWNER)

    await message.answer(
        f"✅ سفارش ثبت شد (#{order_id})\n\n"
        f"👤 یوزرنیم: <code>{username}</code>\n"
        f"📊 حجم فعلی: {current_gb} گیگ | مصرف شده: {used_gb} گیگ\n"
        f"📦 پلن: {data['title']} ({data['volume_gb']} گیگ)\n"
        f"💰 مبلغ قابل پرداخت: <b>{data['price']:,} تومان</b>\n\n"
        f"💳 شماره کارت:\n<code>{card_number}</code>\n"
        f"صاحب کارت: {card_owner}\n\n"
        "پس از واریز، <b>عکس رسید</b> را همینجا ارسال کنید.",
        parse_mode="HTML",
        reply_markup=cancel_kb()
    )


@router.message(AdminStates.waiting_receipt, F.photo)
async def process_receipt(message: Message, state: FSMContext, bot: Bot):
    if not is_admin(message.from_user.id):
        return
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

    # Send to admin (self) for confirmation - already is admin
    caption = (
        f"🧾 رسید پرداخت سفارش #{order_id}\n\n"
        f"👤 یوزرنیم پنل: <code>{order['username']}</code>\n"
        f"🖥 پنل: {panel['name'] if panel else '-'}\n"
        f"📦 حجم: {order['volume_gb']} گیگابایت\n"
        f"💰 مبلغ: {order['price']:,} تومان\n\n"
        "لطفاً تأیید یا رد کنید:"
    )
    await message.answer_photo(
        photo=file_id,
        caption=caption,
        parse_mode="HTML",
        reply_markup=confirm_order(order_id)
    )
    await state.clear()
    await message.answer(
        "✅ رسید دریافت شد. منتظر تأیید بمانید (یا خودتان تأیید کنید).",
        reply_markup=admin_main_menu()
    )


@router.message(AdminStates.waiting_receipt)
async def process_receipt_wrong(message: Message):
    await message.answer("لطفاً فقط عکس رسید را ارسال کنید یا /cancel بزنید.")


# ==================== APPROVE / REJECT ====================

@router.callback_query(F.data.startswith("approve_order_"))
async def cb_approve_order(callback: CallbackQuery, bot: Bot):
    if not is_admin(callback.from_user.id):
        return
    order_id = int(callback.data.split("_")[2])
    order = await db.get_order(order_id)
    if not order:
        await callback.answer("سفارش پیدا نشد", show_alert=True)
        return
    if order["status"] == "paid":
        await callback.answer("این سفارش قبلاً تأیید شده", show_alert=True)
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
            f"حجم جدید: {result.get('new_limit_gb')} گیگ\n"
            f"مصرف شده: {result.get('used_gb')} گیگ"
        )
        await callback.message.edit_caption(caption=text, reply_markup=None)
        await callback.message.answer(text, reply_markup=admin_main_menu())
    else:
        await callback.message.answer(
            f"❌ خطا در افزودن حجم:\n{result['message']}\n\n"
            "می‌توانید دوباره تلاش کنید یا دستی در پنل اضافه کنید.",
            reply_markup=admin_main_menu()
        )


@router.callback_query(F.data.startswith("reject_order_"))
async def cb_reject_order(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    order_id = int(callback.data.split("_")[2])
    await db.update_order(order_id, status="rejected")
    await callback.message.edit_caption(
        caption=f"❌ سفارش #{order_id} رد شد.",
        reply_markup=None
    )
    await callback.answer("سفارش رد شد")


@router.callback_query(F.data == "pending_orders")
async def cb_pending_orders(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    orders = await db.get_pending_orders()
    if not orders:
        await callback.answer("سفارش در انتظاری وجود ندارد", show_alert=True)
        return
    text = "📋 سفارش‌های در انتظار:\n\n"
    for o in orders:
        text += f"#{o['id']} | {o['username']} | {o['volume_gb']}GB | {o['price']:,} تومان | {o['status']}\n"
    await callback.message.edit_text(text, reply_markup=back_to_menu())
    await callback.answer()


# ==================== CARD SETTINGS ====================

@router.callback_query(F.data == "card_settings")
async def cb_card_settings(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    card_number = await db.get_setting("card_number", settings.CARD_NUMBER)
    card_owner = await db.get_setting("card_owner", settings.CARD_OWNER)
    text = (
        f"💳 تنظیمات کارت‌به‌کارت:\n\n"
        f"شماره کارت: <code>{card_number}</code>\n"
        f"صاحب کارت: {card_owner}\n\n"
        "برای تغییر، یکی از گزینه‌ها را انتخاب کنید:"
    )
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✏️ تغییر شماره کارت", callback_data="set_card_number"))
    builder.row(InlineKeyboardButton(text="✏️ تغییر نام صاحب کارت", callback_data="set_card_owner"))
    builder.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="admin_menu"))
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "set_card_number")
async def cb_set_card_number(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.set_card_number)
    await callback.message.edit_text("شماره کارت جدید را وارد کنید:", reply_markup=cancel_kb())
    await callback.answer()


@router.message(AdminStates.set_card_number)
async def process_card_number(message: Message, state: FSMContext):
    await db.set_setting("card_number", message.text.strip())
    await state.clear()
    await message.answer("✅ شماره کارت ذخیره شد.", reply_markup=admin_main_menu())


@router.callback_query(F.data == "set_card_owner")
async def cb_set_card_owner(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.set_card_owner)
    await callback.message.edit_text("نام صاحب کارت را وارد کنید:", reply_markup=cancel_kb())
    await callback.answer()


@router.message(AdminStates.set_card_owner)
async def process_card_owner(message: Message, state: FSMContext):
    await db.set_setting("card_owner", message.text.strip())
    await state.clear()
    await message.answer("✅ نام صاحب کارت ذخیره شد.", reply_markup=admin_main_menu())


# ==================== BACKUP ====================

@router.callback_query(F.data == "backup_now")
async def cb_backup_now(callback: CallbackQuery, bot: Bot):
    if not is_admin(callback.from_user.id):
        return
    await callback.answer("در حال تهیه بک‌آپ...")
    try:
        db_path = settings.DB_PATH
        if not os.path.exists(db_path):
            await callback.message.answer("❌ فایل دیتابیس پیدا نشد.")
            return

        backup_name = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        backup_path = os.path.join(settings.BASE_DIR, "data", backup_name)
        shutil.copy2(db_path, backup_path)

        await bot.send_document(
            chat_id=settings.ADMIN_ID,
            document=FSInputFile(backup_path),
            caption=f"🗄 بک‌آپ دیتابیس\n📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        os.remove(backup_path)
        await callback.message.answer("✅ بک‌آپ با موفقیت ارسال شد.")
    except Exception as e:
        await callback.message.answer(f"❌ خطا در بک‌آپ: {e}")


@router.callback_query(F.data == "bot_status")
async def cb_bot_status(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    panels = await db.get_panels()
    plans = await db.get_plans()
    pending = await db.get_pending_orders()
    text = (
        f"ℹ️ وضعیت ربات\n\n"
        f"🖥 تعداد پنل‌ها: {len(panels)}\n"
        f"📦 تعداد پلن‌های فعال: {len(plans)}\n"
        f"📋 سفارش‌های در انتظار: {len(pending)}\n"
        f"👤 ادمین: <code>{settings.ADMIN_ID}</code>"
    )
    await callback.message.edit_text(text, reply_markup=back_to_menu(), parse_mode="HTML")
    await callback.answer()


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    await message.answer("❌ عملیات لغو شد.", reply_markup=admin_main_menu())