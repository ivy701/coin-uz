from datetime import datetime, timedelta
import logging
import os

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

import config
import keyboards
from services import payment_client
from services.database import db

logger = logging.getLogger(__name__)

router = Router()

TASHKENT_OFFSET = timedelta(hours=5)
TIMEOUT_MINUTES = 5


class BalanceStates(StatesGroup):
    waiting_amount = State()
    waiting_receipt = State()


def tashkent_now() -> datetime:
    """Return current time in Tashkent (UTC+5)"""
    return datetime.utcnow() + TASHKENT_OFFSET


def format_time(dt: datetime) -> str:
    return dt.strftime("%H:%M:%S")


@router.message(F.text.in_({"✨ Hisobni to'ldirish", "💰 Balans to'ldirish", "Balans to'ldirish", "Hisobni to'ldirish", "Balans"}))
@router.message(F.text.startswith("/topup") | F.text.startswith("/balance") | F.text.startswith("/balans"))
@router.callback_query(F.data.in_({"topup_menu", "topup"}))
async def topup_menu(event: Message | CallbackQuery, state: FSMContext):
    """Show balance top-up menu with quick amounts"""
    if isinstance(event, CallbackQuery):
        await event.answer()
        user_id = event.from_user.id
        msg = event.message
    else:
        user_id = event.from_user.id
        msg = event

    user = await db.get_user(user_id)
    if not user:
        await msg.answer("❌ Foydalanuvchi topilmadi!")
        return

    text = (
        f'<tg-emoji emoji-id="{config.CUSTOM_EMOJI_MONEY}">💰</tg-emoji> '
        f"<b>Balansni to'ldirish</b>\n\n"
        f"Kerakli miqdorni tanlang yoki o'zingiz yozing:\n\n"
        f'<tg-emoji emoji-id="{config.CUSTOM_EMOJI_DOWN}">⬇️</tg-emoji> '
        f"Minimal: 1 000 so'm\n"
        f'<tg-emoji emoji-id="{config.CUSTOM_EMOJI_UP}">⬆️</tg-emoji> '
        f"Maksimal: 2 500 000 so'm"
    )

    if isinstance(event, CallbackQuery):
        await msg.edit_text(text, parse_mode="HTML", reply_markup=keyboards.get_quick_topup_keyboard())
    else:
        await msg.answer(text, parse_mode="HTML", reply_markup=keyboards.get_quick_topup_keyboard())
    await state.set_state(BalanceStates.waiting_amount)


@router.callback_query(F.data.startswith("quick_topup_"))
async def process_quick_topup(callback: CallbackQuery, state: FSMContext):
    """Process quick topup amount selection"""
    await callback.answer()
    amount_str = callback.data.replace("quick_topup_", "")
    try:
        amount = int(amount_str)
    except ValueError:
        return

    await state.clear()
    user_id = callback.from_user.id

    import time
    order_id = f"topup_{user_id}_{int(time.time())}"
    await db.create_order(
        order_id=order_id,
        user_id=user_id,
        product_type="topup",
        amount=amount,
        price=amount,
    )
    card_number = os.getenv("CARD_NUMBER", "4916 9903 6986 6493")
    card_owner = os.getenv("CARD_OWNER", "T M")
    expires_in = 300

    now = tashkent_now()
    expires_at = now + timedelta(seconds=expires_in)

    card_text = (
        f"✅ <b>To'lov so'rovi yaratildi!</b>\n\n"
        f'<tg-emoji emoji-id="{config.CUSTOM_EMOJI_ID}">🆔</tg-emoji> '
        f"Buyurtma: <code>{order_id}</code>\n"
        f'<tg-emoji emoji-id="{config.CUSTOM_EMOJI_MONEY}">💰</tg-emoji> '
        f"Miqdori: <b>{amount:,} so'm</b>\n\n"
        f'<tg-emoji emoji-id="{config.CUSTOM_EMOJI_CARD}">💳</tg-emoji> '
        f"<b>To'lov uchun karta:</b>\n"
        f"<code>{card_number}</code>\n"
        f'<tg-emoji emoji-id="{config.CUSTOM_EMOJI_USER}">👤</tg-emoji> '
        f"{card_owner}\n\n"
        f'<tg-emoji emoji-id="{config.CUSTOM_EMOJI_CLOCK}">⏰</tg-emoji> '
        f"Pul o'tkazing va <b>✅ To'lovni tekshirish</b> tugmasini bosing!\n\n"
        f'<tg-emoji emoji-id="{config.CUSTOM_EMOJI_WARN}">⚠️</tg-emoji> '
        f"Muddat: {format_time(now)} — {format_time(expires_at)} (Toshkent)\n"
        f"Aniq {TIMEOUT_MINUTES} daqiqa."
    )

    await callback.message.edit_text(
        card_text,
        parse_mode="HTML",
        reply_markup=keyboards.get_card_payment_keyboard(order_id),
    )


@router.message(BalanceStates.waiting_amount)
async def process_topup_amount(message: Message, state: FSMContext):
    """Process top-up amount — create order via ElderPay or fallback locally"""
    try:
        amount = float(message.text.replace(",", "").replace(" ", ""))

        if amount < 1000:
            await message.answer("❌ Minimal summa: 1 000 so'm. Qayta urinib ko'ring.")
            return

        if amount > 2500000:
            await message.answer("❌ Maksimal summa: 2 500 000 so'm. Qayta urinib ko'ring.")
            return

        await state.clear()
        user_id = message.from_user.id

        # Try creating via ElderPay
        try:
            result = await payment_client.create_elderpay_order(user_id, int(amount))
        except Exception as e:
            result = {"success": False, "error": str(e)}

        if result.get("success"):
            data = result["data"]
            order_id = data["order_id"]
            card_number = data.get("card_number") or os.getenv("CARD_NUMBER", "4916 9903 6986 6493")
            card_owner = data.get("card_owner") or os.getenv("CARD_OWNER", "T M")
            expires_in = data.get("expires_in", 300)
        else:
            # Fallback to local order creation
            import time
            order_id = f"topup_{user_id}_{int(time.time())}"
            await db.create_order(
                order_id=order_id,
                user_id=user_id,
                product_type="topup",
                amount=int(amount),
                price=int(amount),
            )
            card_number = os.getenv("CARD_NUMBER", "4916 9903 6986 6493")
            card_owner = os.getenv("CARD_OWNER", "T M")
            expires_in = 300

        now = tashkent_now()
        expires_at = now + timedelta(seconds=expires_in)

        card_text = (
            f"✅ <b>To'lov so'rovi yaratildi!</b>\n\n"
            f'<tg-emoji emoji-id="{config.CUSTOM_EMOJI_ID}">🆔</tg-emoji> '
            f"Buyurtma: <code>{order_id}</code>\n"
            f'<tg-emoji emoji-id="{config.CUSTOM_EMOJI_MONEY}">💰</tg-emoji> '
            f"Miqdori: {int(amount):,} so'm\n\n"
            f'<tg-emoji emoji-id="{config.CUSTOM_EMOJI_CARD}">💳</tg-emoji> '
            f"<b>To'lov uchun karta:</b>\n"
            f"<code>{card_number}</code>\n"
            f'<tg-emoji emoji-id="{config.CUSTOM_EMOJI_USER}">👤</tg-emoji> '
            f"{card_owner}\n\n"
            f'<tg-emoji emoji-id="{config.CUSTOM_EMOJI_CLOCK}">⏰</tg-emoji> '
            f"Pul o'tkazing va <b>✅ To'lovni tekshirish</b> tugmasini bosing!\n\n"
            f'<tg-emoji emoji-id="{config.CUSTOM_EMOJI_WARN}">⚠️</tg-emoji> '
            f"Muddat: {format_time(now)} — {format_time(expires_at)} (Toshkent)\n"
            f"Aniq {TIMEOUT_MINUTES} daqiqa."
        )

        await message.answer(
            card_text,
            parse_mode="HTML",
            reply_markup=keyboards.get_card_payment_keyboard(order_id),
        )

    except ValueError:
        await message.answer("❌ Noto'g'ri format! Faqat raqam kiriting.")


@router.callback_query(F.data.startswith("check_payment_"))
async def check_payment_status(callback: CallbackQuery, state: FSMContext):
    """Check payment status or prompt user to upload receipt"""
    order_id = callback.data.split("_", 2)[2]

    # Check via ElderPay first
    result = await payment_client.check_elderpay_order(order_id)

    if result.get("success") and result.get("data", {}).get("paid"):
        data = result["data"]
        amount = data.get("amount", 0)
        new_balance = data.get("new_balance", 0)

        check_emoji = f'<tg-emoji emoji-id="{config.CUSTOM_EMOJI_CHECK}">✅</tg-emoji>'
        wallet_emoji = f'<tg-emoji emoji-id="{config.CUSTOM_EMOJI_WALLET}">👛</tg-emoji>'
        money_emoji = f'<tg-emoji emoji-id="{config.CUSTOM_EMOJI_MONEY}">💰</tg-emoji>'

        text = (
            f"{check_emoji} <b>To'lov muvaffaqiyatli qabul qilindi</b>\n\n"
            f"{wallet_emoji} +{amount:,} so'm\n"
            f"{money_emoji} Balans: {new_balance:,} so'm"
        )

        await callback.message.edit_text(text, parse_mode="HTML")
        await callback.message.answer(
            "🏠 Bosh menyu:",
            reply_markup=keyboards.get_webapp_main_keyboard()
        )
    else:
        order = await db.get_order(order_id)
        amount = order.get("amount", 0) if order else 0

        await callback.answer()
        text = (
            f"⏳ <b>To'lov so'rovi yuborilgan!</b>\n\n"
            f"🆔 Buyurtma: <code>{order_id}</code>\n"
            f"💰 Summa: <b>{amount:,} so'm</b>\n\n"
            f"Admin to'lovni tasdiqlashi bilanoq balansingiz avtomatik to'ldiriladi."
        )
        await callback.message.answer(text, parse_mode="HTML")


@router.message(BalanceStates.waiting_receipt, F.photo | F.document)
async def process_receipt(message: Message, state: FSMContext, bot: Bot):
    """Receive receipt photo/document and send to Admin for approval"""
    data = await state.get_data()
    order_id = data.get("order_id")
    amount = data.get("amount", 0)
    user = message.from_user

    await state.clear()

    # User notification
    await message.answer(
        "✅ <b>Chekingiz qabul qilindi va Adminga yuborildi!</b>\n\n"
        "Admin chekni tekshirib chiqadi va tez orada balansingiz to'ldiriladi.",
        parse_mode="HTML",
        reply_markup=keyboards.get_webapp_main_keyboard()
    )

    # Prepare Admin message
    admin_text = (
        f"📥 <b>YANGI TO'LOV CHEKI!</b>\n\n"
        f"👤 Foydalanuvchi: {user.full_name} (@{user.username or 'yo_q'})\n"
        f"🆔 Telegram ID: <code>{user.id}</code>\n"
        f"🆔 Buyurtma ID: <code>{order_id}</code>\n"
        f"💰 Summa: <b>{amount:,} so'm</b>\n"
    )

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Qabul qilish", callback_data=f"admin_approve_receipt_{order_id}"),
        InlineKeyboardButton(text="❌ Rad etish", callback_data=f"admin_reject_receipt_{order_id}")
    )

    for admin_id in config.ADMINS:
        try:
            if message.photo:
                photo_id = message.photo[-1].file_id
                await bot.send_photo(
                    admin_id,
                    photo=photo_id,
                    caption=admin_text,
                    parse_mode="HTML",
                    reply_markup=builder.as_markup()
                )
            elif message.document:
                doc_id = message.document.file_id
                await bot.send_document(
                    admin_id,
                    document=doc_id,
                    caption=admin_text,
                    parse_mode="HTML",
                    reply_markup=builder.as_markup()
                )
        except Exception as e:
            logger.error("Failed to send receipt to admin %s: %s", admin_id, e)


@router.message(BalanceStates.waiting_receipt)
async def process_receipt_invalid(message: Message):
    """Handle text message when waiting for receipt"""
    await message.answer("❌ Iltimos, to'lov chekining <b>rasmini</b> yoki <b>faylini</b> yuboring.")


@router.callback_query(F.data.startswith("admin_approve_receipt_"))
async def admin_approve_receipt(callback: CallbackQuery, bot: Bot):
    """Admin approves payment receipt"""
    admin_id = callback.from_user.id
    admin_list = [int(x) for x in config.ADMINS] if config.ADMINS else [8202423244]
    if admin_id not in admin_list and admin_id not in config.ADMINS:
        await callback.answer("❌ Siz admin emassiz!", show_alert=True)
        return

    order_id = callback.data.replace("admin_approve_receipt_", "")
    logger.info("[ADMIN_APPROVE] order_id=%s admin=%s", order_id, admin_id)
    order = await db.get_order(order_id)

    if not order:
        logger.warning("[ADMIN_APPROVE] Order NOT FOUND for order_id=%s", order_id)
        await callback.answer("❌ Buyurtma topilmadi!", show_alert=True)
        return

    if order.get("status") == "completed":
        await callback.answer("⚠️ Bu to'lov allaqachon tasdiqlangan!", show_alert=True)
        return

    telegram_id = order["telegram_id"]
    amount = order["amount"]

    # Update order and add balance
    await db.update_order(order_id, status="completed")
    new_balance = await db.add_balance(telegram_id, amount)
    await db.add_balance_history(
        telegram_id, amount, "topup", new_balance - amount, new_balance,
        reason=f"Admin receipt approval ({order_id})", admin_id=admin_id
    )

    await callback.answer("✅ To'lov tasdiqlandi!")

    new_caption = (callback.message.caption or callback.message.text or "") + (
        f"\n\n✅ <b>TASDIQLANDI! (+{amount:,} so'm)</b>\n"
        f"👨‍💻 Admin: {callback.from_user.full_name}"
    )
    if callback.message.photo or callback.message.document:
        await callback.message.edit_caption(caption=new_caption, parse_mode="HTML")
    else:
        await callback.message.edit_text(text=new_caption, parse_mode="HTML")

    # Notify user
    try:
        await bot.send_message(
            telegram_id,
            f"🎉 <b>To'lovingiz tasdiqlandi!</b>\n\n"
            f"👛 <b>+{amount:,} so'm</b> balansingizga qo'shildi!\n"
            f"💰 Hozirgi balans: <b>{new_balance:,} so'm</b>",
            parse_mode="HTML",
            reply_markup=keyboards.get_webapp_main_keyboard(telegram_id, balance=new_balance)
        )
    except Exception as e:
        logger.error("Failed to notify user %s: %s", telegram_id, e)


@router.callback_query(F.data.startswith("admin_reject_receipt_"))
async def admin_reject_receipt(callback: CallbackQuery, bot: Bot):
    """Admin rejects payment receipt"""
    admin_id = callback.from_user.id
    admin_list = [int(x) for x in config.ADMINS] if config.ADMINS else [8202423244]
    if admin_id not in admin_list and admin_id not in config.ADMINS:
        await callback.answer("❌ Siz admin emassiz!", show_alert=True)
        return

    order_id = callback.data.replace("admin_reject_receipt_", "")
    order = await db.get_order(order_id)

    if not order:
        await callback.answer("❌ Buyurtma topilmadi!", show_alert=True)
        return

    telegram_id = order["telegram_id"]

    await db.update_order(order_id, status="rejected")
    await callback.answer("❌ To'lov rad etildi!")

    new_caption = (callback.message.caption or callback.message.text or "") + (
        f"\n\n❌ <b>RAD ETILDI!</b>\n"
        f"👨‍💻 Admin: {callback.from_user.full_name}"
    )
    if callback.message.photo or callback.message.document:
        await callback.message.edit_caption(caption=new_caption, parse_mode="HTML")
    else:
        await callback.message.edit_text(text=new_caption, parse_mode="HTML")

    # Notify user
    try:
        await bot.send_message(
            telegram_id,
            f"❌ <b>To'lov chekingiz rad etildi!</b>\n\n"
            f"🆔 Buyurtma ID: <code>{order_id}</code>\n"
            f"Savollaringiz bo'lsa, @cofeature ga murojaat qiling.",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error("Failed to notify user %s: %s", telegram_id, e)


@router.callback_query(F.data.startswith("cancel_order_"))
async def cancel_order_handler(callback: CallbackQuery):
    """Cancel order — shows timeout message with premium emoji"""
    await callback.answer()

    order_id = callback.data.split("_", 2)[2]
    order = await db.get_order(order_id)

    if order and order.get("status") == "pending":
        await db.update_order(order_id, status="cancelled")

    text = (
        f'<tg-emoji emoji-id="{config.CUSTOM_EMOJI_WARN2}">⚠️</tg-emoji> '
        f"<b>To'lov muddati tugadi!</b>\n\n"
        f'<tg-emoji emoji-id="{config.CUSTOM_EMOJI_CLOCK}">⏰</tg-emoji> '
        f"5 daqiqa ichida to'lov amalga oshirilmaganligi sababli\n"
        f'<tg-emoji emoji-id="{config.CUSTOM_EMOJI_ID}">🆔</tg-emoji> '
        f"<code>{order_id}</code> buyurtmangiz\n"
        f"avtomatik bekor qilindi.\n\n"
        f"Qaytadan urinib ko'ring."
    )

    await callback.message.edit_text(text, parse_mode="HTML")
    await callback.message.answer(
        "🏠 Bosh menyu:",
        reply_markup=keyboards.get_bosh_menu_keyboard(),
    )
