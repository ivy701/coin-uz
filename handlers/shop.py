from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
import keyboards
from services.database import db
import config
import uuid
import logging
from services.fragment_api import fragment_client
from datetime import datetime

logger = logging.getLogger(__name__)
router = Router()


@router.message(F.text == "⭐ Stars olish")
async def buy_stars_menu(message: Message):
    """Show stars purchase menu"""
    text = (
        "⭐ <b>Telegram Stars sotib olish</b>\n\n"
        "Stars — Telegram ichida maxsus kontent va xizmatlarni "
        "sotib olish uchun ishlatiladi.\n\n"
        "📦 <b>Mavjud paketlar:</b>"
    )
    
    await message.answer(
        text,
        reply_markup=keyboards.get_stars_keyboard(),
        parse_mode="HTML"
    )


@router.message(F.text == "💎 Premium olish")
async def buy_premium_menu(message: Message):
    """Show premium purchase menu"""
    text = (
        "💎 <b>Telegram Premium sotib olish</b>\n\n"
        "Premium obuna bilan qo'shimcha imkoniyatlarga ega bo'ling:\n\n"
        "✨ Tezroq yuklab olish tezligi\n"
        "📁 4 GB gacha fayllar\n"
        "🎨 Eksklyuziv stikerlar\n"
        "👤 Premium emoji va badge\n"
        "💬 Kengaytirilgan chat imkoniyatlari\n\n"
        "📦 <b>Mavjud paketlar:</b>"
    )
    
    await message.answer(
        text,
        reply_markup=keyboards.get_premium_keyboard(),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("buy_stars_"))
async def process_buy_stars(callback: CallbackQuery):
    """Process stars purchase"""
    await callback.answer()
    
    amount = int(callback.data.split("_")[2])
    user_id = callback.from_user.id

    if amount < config.STARS_MIN_AMOUNT or amount > config.STARS_MAX_AMOUNT:
        await callback.message.answer(
            f"❌ Stars miqdori {config.STARS_MIN_AMOUNT:,} dan {config.STARS_MAX_AMOUNT:,} gacha bo'lishi kerak."
        )
        return
    
    # Find price for this amount
    price = None
    for package in config.PRODUCTS["stars"]["packages"]:
        if package["amount"] == amount:
            price = package["price"]
            break
    
    if not price:
        await callback.message.answer("❌ Xatolik yuz berdi!")
        return
    
    # Check user balance
    user = await db.get_user(user_id)
    
    if not user:
        await callback.message.answer("❌ Foydalanuvchi topilmadi!")
        return
    
    if user['balance'] >= price:
        # Sufficient balance, process immediately
        await db.update_balance(user_id, price, 'subtract')
        
        # Create order
        order_id = str(uuid.uuid4())[:8]
        username = callback.from_user.username or str(user_id)
        await db.create_order(order_id, user_id, "stars", amount, price, target_username=username, status="processing")
        await db.update_order(order_id, status="processing")
        
        is_fragment_ready = bool(fragment_client.api_key and fragment_client.api_key.strip())
        success = False
        result = None
        
        if is_fragment_ready:
            try:
                result = await fragment_client.buy_stars(username, amount)
                if result and (result.get("ok") or result.get("status") == "success" or result.get("id")):
                    success = True
            except Exception as e:
                logger.warning(f"Automated Fragment buy_stars failed: {e}, falling back to pending queue...")
        
        if success:
            await db.update_order(
                order_id, 
                status="completed",
                completed_at=datetime.utcnow().isoformat()
            )
            from services.channel_notify import notify_stars
            try:
                await notify_stars(username, amount, price)
            except Exception as e:
                logger.warning(f"notify_stars error: {e}")
            
            user = await db.get_user(user_id)
            await callback.message.answer(
                f"✅ <b>Muvaffaqiyatli!</b>\n\n"
                f"⭐ <b>{amount}</b> Stars hisobingizga qo'shildi!\n"
                f"👤 Qabul qiluvchi: @{username}\n"
                f"💰 Yangi balans: {user['balance']:,.0f} so'm",
                parse_mode="HTML",
                reply_markup=keyboards.get_main_keyboard()
            )
        else:
            # Fallback mode: Order is queued as pending
            await db.update_order(order_id, status="pending")
            from services.channel_notify import notify_stars
            try:
                await notify_stars(username, amount, price)
            except Exception as e:
                logger.warning(f"notify_stars error: {e}")
            
            user = await db.get_user(user_id)
            await callback.message.answer(
                f"✅ <b>Buyurtmangiz qabul qilindi!</b>\n\n"
                f"⭐ <b>{amount} Stars</b> → @{username}\n"
                f"🆔 Buyurtma ID: <code>{order_id}</code>\n"
                f"⏳ Holat: <i>Kutilmoqda (Tez orada yetkaziladi)</i>\n"
                f"💰 Yangi balans: {user['balance']:,.0f} so'm",
                parse_mode="HTML",
                reply_markup=keyboards.get_main_keyboard()
            )
    else:
        # Need to top up
        needed = price - user['balance']
        text = (
            f"💰 <b>Balans yetarli emas!</b>\n\n"
            f"Kerakli summa: {price:,.0f} so'm\n"
            f"Sizning balansingiz: {user['balance']:,.0f} so'm\n"
            f"Yetishmayotgan: {needed:,.0f} so'm\n\n"
            f"Hisobni to'ldiring va qayta urinib ko'ring."
        )
        
        await callback.message.answer(
            text,
            parse_mode="HTML",
            reply_markup=keyboards.get_main_keyboard()
        )


@router.callback_query(F.data.startswith("buy_premium_"))
async def process_buy_premium(callback: CallbackQuery):
    """Process premium purchase"""
    await callback.answer()
    
    duration = int(callback.data.split("_")[2])
    user_id = callback.from_user.id
    
    # Find price for this duration
    price = None
    for package in config.PRODUCTS["premium"]["packages"]:
        if package["duration"] == duration:
            price = package["price"]
            break
    
    if not price:
        await callback.message.answer("❌ Xatolik yuz berdi!")
        return
    
    # Check user balance
    user = await db.get_user(user_id)
    
    if not user:
        await callback.message.answer("❌ Foydalanuvchi topilmadi!")
        return
    
    if user['balance'] >= price:
        # Sufficient balance, process immediately
        await db.update_balance(user_id, price, 'subtract')
        
        # Create order
        order_id = str(uuid.uuid4())[:8]
        username = callback.from_user.username or str(user_id)
        await db.create_order(order_id, user_id, "premium", duration, price, target_username=username, status="processing")
        await db.update_order(order_id, status="processing")
        
        is_fragment_ready = bool(fragment_client.api_key and fragment_client.api_key.strip())
        success = False
        result = None
        
        if is_fragment_ready:
            try:
                result = await fragment_client.buy_premium(username, duration)
                if result and (result.get("ok") or result.get("status") == "success" or result.get("id")):
                    success = True
            except Exception as e:
                logger.warning(f"Automated Fragment buy_premium failed: {e}, falling back to pending queue...")
        
        if success:
            await db.update_order(
                order_id,
                status="completed",
                completed_at=datetime.utcnow().isoformat()
            )
            from services.channel_notify import notify_premium
            try:
                await notify_premium(username, duration, price)
            except Exception as e:
                logger.warning(f"notify_premium error: {e}")
            
            user = await db.get_user(user_id)
            await callback.message.answer(
                f"✅ <b>Muvaffaqiyatli!</b>\n\n"
                f"💎 Telegram Premium {duration} oyga faollashtirildi!\n"
                f"👤 Qabul qiluvchi: @{username}\n"
                f"💰 Yangi balans: {user['balance']:,.0f} so'm",
                parse_mode="HTML",
                reply_markup=keyboards.get_main_keyboard()
            )
        else:
            # Fallback mode: Order is queued as pending
            await db.update_order(order_id, status="pending")
            from services.channel_notify import notify_premium
            try:
                await notify_premium(username, duration, price)
            except Exception as e:
                logger.warning(f"notify_premium error: {e}")
            
            user = await db.get_user(user_id)
            await callback.message.answer(
                f"✅ <b>Buyurtmangiz qabul qilindi!</b>\n\n"
                f"💎 <b>Telegram Premium {duration} oy</b> → @{username}\n"
                f"🆔 Buyurtma ID: <code>{order_id}</code>\n"
                f"⏳ Holat: <i>Kutilmoqda (Tez orada faollashtiriladi)</i>\n"
                f"💰 Yangi balans: {user['balance']:,.0f} so'm",
                parse_mode="HTML",
                reply_markup=keyboards.get_main_keyboard()
            )
    else:
        # Need to top up
        needed = price - user['balance']
        text = (
            f"💰 <b>Balans yetarli emas!</b>\n\n"
            f"Kerakli summa: {price:,.0f} so'm\n"
            f"Sizning balansingiz: {user['balance']:,.0f} so'm\n"
            f"Yetishmayotgan: {needed:,.0f} so'm\n\n"
            f"Hisobni to'ldiring va qayta urinib ko'ring."
        )
        
        await callback.message.answer(
            text,
            parse_mode="HTML",
            reply_markup=keyboards.get_main_keyboard()
        )


@router.message(F.text == "📱 Nomer olish")
async def buy_phone_menu(message: Message):
    """Virtual phone numbers menu"""
    text = (
        "📱 <b>Virtual raqamlar</b>\n\n"
        "Tez orada mavjud bo'ladi...\n\n"
        "Bu bo'limda siz turli xizmatlar uchun "
        "virtual telefon raqamlarini sotib olishingiz mumkin bo'ladi."
    )
    
    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=keyboards.get_main_keyboard()
    )


@router.message(F.text == "🎁 Gift olish")
async def buy_gift_menu(message: Message):
    """Gift menu"""
    text = (
        "🎁 <b>Gift sovg'alar</b>\n\n"
        "Tez orada mavjud bo'ladi...\n\n"
        "Bu bo'limda siz do'stlaringizga Premium, "
        "Stars va boshqa sovg'alarni yuborishingiz mumkin bo'ladi."
    )
    
    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=keyboards.get_main_keyboard()
    )


@router.callback_query(F.data == "back_to_main")
async def back_to_main_callback(callback: CallbackQuery, state: FSMContext):
    """Return to main menu from inline keyboard"""
    await state.clear()
    await callback.answer()
    await callback.message.delete()
    await callback.message.answer(
        "🏠 Bosh menyu:",
        reply_markup=keyboards.get_webapp_main_keyboard()
    )
