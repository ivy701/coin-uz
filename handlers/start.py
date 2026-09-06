from aiogram import Router, F, Bot
from aiogram.types import Message, MessageEntity, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.utils.formatting import Text, Bold, as_list, as_marked_section
from aiogram.enums import ParseMode
import logging
import keyboards
from services.database import db
from datetime import datetime

logger = logging.getLogger(__name__)
router = Router()

# Premium emoji IDs
EMOJI_DUCK_WAVE = "5361664082409740777"  # 🐥 Duck wave / smile
EMOJI_LIGHTNING = "5224496844188458905"  # ⚡️ Neon lightning
EMOJI_ID_ICON = "5818885490065017876"    # 💼 Duck ID / Suitcase
EMOJI_DOWN = "5229212516415978792"       # ⬇️ Circle down arrow
EMOJI_WAVE = "5312345830382910731"       # 👋
EMOJI_ORANGE = "5336936725765700868"     # 🟠
EMOJI_WALLET = "5215420556089776398"     # 👛
EMOJI_MONEY = "5407091881219736716"      # 💰
EMOJI_PEOPLE = "5879905000972358125"     # 👥
EMOJI_STAR = "5807791714093502248"       # ⭐️
EMOJI_GIFT = "5348068314629315530"       # 🎁
EMOJI_CHECKMARK = "5980930633298350051"  # ✅
EMOJI_CROSS = "5273914604752216432"      # ❌
EMOJI_MONEY_TEXT = "5811989245761426317"  # 💰 в тексте
EMOJI_UP = "5229113938326599381"         # ⬆️


def get_welcome_text(user: dict | None, username: str | None, first_name: str | None) -> str:
    user_dict = user or {}
    lang = user_dict.get("language", "uz")
    default_name = "Пользователь" if lang == "ru" else "Foydalanuvchi"
    display = f"@{username}" if username else (first_name or default_name)
    user_id_val = user_dict.get("sp_id") or user_dict.get("id") or user_dict.get("telegram_id", "—")

    if lang == "ru":
        return (
            f'<tg-emoji emoji-id="{EMOJI_DUCK_WAVE}">🐥</tg-emoji> Xush kelibsiz, {display}\n\n'
            f'<tg-emoji emoji-id="{EMOJI_LIGHTNING}">⚡️</tg-emoji> Qulay interfeys\n'
            f'<tg-emoji emoji-id="{EMOJI_LIGHTNING}">⚡️</tg-emoji> Qulay to\'lov\n'
            f'<tg-emoji emoji-id="{EMOJI_LIGHTNING}">⚡️</tg-emoji> To\'liq avtomatlashtirilgan xizmat\n\n'
            f'<tg-emoji emoji-id="{EMOJI_ID_ICON}">💼</tg-emoji> User ID: {user_id_val}\n\n'
            f'Pastdagi tugmani bosing va hoziroq boshlang <tg-emoji emoji-id="{EMOJI_DOWN}">⬇️</tg-emoji>'
        )

    return (
        f'<tg-emoji emoji-id="{EMOJI_DUCK_WAVE}">🐥</tg-emoji> Xush kelibsiz, {display}\n\n'
        f'<tg-emoji emoji-id="{EMOJI_LIGHTNING}">⚡️</tg-emoji> Qulay interfeys\n'
        f'<tg-emoji emoji-id="{EMOJI_LIGHTNING}">⚡️</tg-emoji> Qulay to\'lov\n'
        f'<tg-emoji emoji-id="{EMOJI_LIGHTNING}">⚡️</tg-emoji> To\'liq avtomatlashtirilgan xizmat\n\n'
        f'<tg-emoji emoji-id="{EMOJI_ID_ICON}">💼</tg-emoji> User ID: {user_id_val}\n\n'
        f'Pastdagi tugmani bosing va hoziroq boshlang <tg-emoji emoji-id="{EMOJI_DOWN}">⬇️</tg-emoji>'
    )


REQUIRED_CHANNEL = "@CoinStatUz"
REQUIRED_CHANNEL_URL = "https://t.me/CoinStatUz"


async def is_user_subscribed(bot: Bot, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=REQUIRED_CHANNEL, user_id=user_id)
        if member.status in ["creator", "administrator", "member"]:
            return True
        if member.status == "restricted" and getattr(member, "is_member", False):
            return True
        return False
    except Exception as e:
        logger.warning("Could not check subscription for user %s: %s", user_id, e)
        # If bot is not admin in channel, don't lock all users out
        return True


def get_subscription_keyboard(lang: str = "uz") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    channel_text = "📢 Kanalga a'zo bo'lish" if lang != "ru" else "📢 Подписаться на канал"
    check_text = "✅ Tekshirish" if lang != "ru" else "✅ Проверить"

    builder.row(
        InlineKeyboardButton(text=channel_text, url=REQUIRED_CHANNEL_URL)
    )
    builder.row(
        InlineKeyboardButton(text=check_text, callback_data="check_subscription")
    )
    return builder.as_markup()


def get_sub_required_text(lang: str = "uz") -> str:
    if lang == "ru":
        return (
            "⚠️ <b>Для использования бота подпишитесь на наш официальный канал!</b>\n\n"
            "📢 Канал: https://t.me/CoinStatUz\n\n"
            "После подписки нажмите кнопку <b>✅ Проверить</b>."
        )
    return (
        "⚠️ <b>Botdan foydalanish uchun rasmiy kanalimizga a'zo bo'ling!</b>\n\n"
        "📢 Kanal: https://t.me/CoinStatUz\n\n"
        "A'zo bo'lgach <b>✅ Tekshirish</b> tugmasini bosing."
    )


@router.message(CommandStart())
async def cmd_start(message: Message):
    """Handle /start command"""
    try:
        user_id = message.from_user.id
        username = message.from_user.username
        first_name = message.from_user.first_name
        
        # Check for referral
        referrer_id = None
        if message.text and len(message.text.split()) > 1:
            try:
                param = message.text.split()[1].strip()
                if param.startswith("ref_"):
                    param = param.replace("ref_", "")
                ref_val = int(param)
                if ref_val != user_id:
                    referrer_id = ref_val
            except Exception:
                pass
        
        user = await db.create_user(user_id, username, first_name, referrer_id)
        if not user:
            user = await db.get_user(user_id)
        lang = user.get("language", "uz") if user else "uz"

        # Check mandatory subscription
        subscribed = await is_user_subscribed(message.bot, user_id)
        if not subscribed:
            await message.answer(
                get_sub_required_text(lang),
                reply_markup=get_subscription_keyboard(lang),
                parse_mode="HTML"
            )
            return

        welcome_text = get_welcome_text(user, username, first_name)
        user_bal = user.get("balance", 0) if user else 0

        await message.answer(
            welcome_text,
            reply_markup=keyboards.get_webapp_main_keyboard(user_id, lang=lang, balance=user_bal),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.exception("Error in cmd_start: %s", e)
        try:
            fallback_user_id = message.from_user.id if message.from_user else None
            await message.answer(
                "👋 <b>Assalomu alaykum!</b>\n\nCoinStat UZ botiga xush kelibsiz!\n\n<blockquote><b>Kerakli bo'limni tanlang:</b></blockquote>",
                reply_markup=keyboards.get_webapp_main_keyboard(fallback_user_id),
                parse_mode="HTML"
            )
        except Exception:
            pass


@router.callback_query(F.data == "check_subscription")
async def check_subscription_callback(callback: CallbackQuery):
    """Callback for checking mandatory channel subscription"""
    user_id = callback.from_user.id
    user = await db.get_user(user_id)
    lang = user.get("language", "uz") if user else "uz"
    user_bal = user.get("balance", 0) if user else 0

    bot = callback.bot
    subscribed = await is_user_subscribed(bot, user_id)
    if not subscribed:
        alert_text = "❌ Siz hali kanalga a'zo bo'lmadingiz!" if lang != "ru" else "❌ Вы ещё не подписались на канал!"
        await callback.answer(alert_text, show_alert=True)
        return

    success_msg = "✅ Rahmat! Xush kelibsiz!" if lang != "ru" else "✅ Спасибо! Добро пожаловать!"
    await callback.answer(success_msg, show_alert=True)

    try:
        await callback.message.delete()
    except Exception:
        pass

    welcome_text = get_welcome_text(user, callback.from_user.username, callback.from_user.first_name)
    await callback.message.answer(
        welcome_text,
        reply_markup=keyboards.get_webapp_main_keyboard(user_id, lang=lang, balance=user_bal),
        parse_mode="HTML"
    )


@router.message(Command("lang"))
@router.message(Command("language"))
@router.callback_query(F.data == "select_language")
async def select_language_handler(event: Message | CallbackQuery):
    """Show language selection options"""
    if isinstance(event, CallbackQuery):
        await event.answer()
        msg = event.message
    else:
        msg = event

    text = "🌐 <b>Tilni tanlang / Выберите язык:</b>"
    await msg.answer(text, reply_markup=keyboards.get_language_keyboard(), parse_mode="HTML")


@router.callback_query(F.data.startswith("set_lang_"))
async def set_language_callback(callback: CallbackQuery):
    """Save selected language for user"""
    await callback.answer()
    user_id = callback.from_user.id
    new_lang = "ru" if callback.data == "set_lang_ru" else "uz"

    from services.database import db_conn
    await db_conn.execute("UPDATE users SET language = $1 WHERE telegram_id = $2", new_lang, user_id)

    user = await db.get_user(user_id)
    confirm_text = "✅ Til muvaffaqiyatli O'zbekchaga o'zgartirildi!" if new_lang == "uz" else "✅ Язык успешно изменён на Русский!"
    await callback.message.answer(confirm_text)

    welcome_text = get_welcome_text(user, callback.from_user.username, callback.from_user.first_name)
    await callback.message.answer(
        welcome_text,
        reply_markup=keyboards.get_webapp_main_keyboard(user_id, lang=new_lang),
        parse_mode="HTML"
    )


@router.message(F.text.in_({"🏠 Bosh menyu", "🏠 Главное меню"}))
async def back_to_main(message: Message):
    """Return to main menu"""
    user_id = message.from_user.id
    user = await db.get_user(user_id)
    
    if user:
        lang = user.get("language", "uz")
        welcome_text = get_welcome_text(user, message.from_user.username, message.from_user.first_name)
        await message.answer(
            welcome_text,
            reply_markup=keyboards.get_webapp_main_keyboard(user_id, lang=lang),
            parse_mode="HTML"
        )


@router.callback_query(F.data == "my_orders")
async def callback_my_orders(callback: CallbackQuery):
    """Show user's orders"""
    await callback.answer()
    user_id = callback.from_user.id
    
    orders = await db.get_user_orders(user_id, limit=10)
    
    if not orders:
        await callback.message.answer(
            "📦 <b>Buyurtmalarim</b>\n\n"
            "Sizda hali buyurtmalar yo'q.",
            parse_mode="HTML"
        )
        return
    
    text = "📦 <b>So'nggi 10 ta buyurtma:</b>\n\n"
    
    for order in orders:
        status_emoji = {
            "pending": "⏳",
            "processing": "🔄",
            "completed": "✅",
            "failed": "❌",
            "cancelled": "🚫"
        }.get(order['status'], "❓")
        
        product_name = {
            "stars": "⭐ Stars",
            "premium": "💎 Premium",
            "topup": "💰 Hisobni to'ldirish",
            "phone": "📱 Virtual raqam",
            "gift": "🎁 Gift"
        }.get(order['product_type'], order['product_type'])
        
        text += (
            f"{status_emoji} <b>{product_name}</b>\n"
            f"   ID: <code>{order['order_id']}</code>\n"
            f"   Summa: {order['price']:,.0f} so'm\n"
            f"   Sana: {order['created_at'][:19].replace('T', ' ')}\n\n"
        )
    
    await callback.message.answer(text, parse_mode="HTML")


@router.callback_query(F.data == "referrals")
async def callback_referrals(callback: CallbackQuery):
    """Show referral information"""
    await callback.answer()
    user_id = callback.from_user.id
    
    user = await db.get_user(user_id)
    
    if not user:
        await callback.message.answer("❌ Foydalanuvchi topilmadi!")
        return
    
    # Get referral link
    bot_username = (await callback.bot.me()).username
    referral_link = f"https://t.me/{bot_username}?start={user_id}"
    
    # Count referrals
    referrals = await db.get_referrals(user_id)
    
    text = (
        f"👥 <b>Referral dasturi</b>\n\n"
        f"Do'stlaringizni taklif qiling va bonus oling!\n\n"
        f"📊 <b>Sizning statistikangiz:</b>\n"
        f"👤 Taklif qilinganlar: {len(referrals)} ta\n"
        f"💰 Referal bonusi: {len(referrals) * 5000:,.0f} so'm\n\n"
        f"🎁 Har bir do'stingiz uchun: 5,000 so'm\n\n"
        f"🔗 <b>Sizning havolangiz:</b>\n"
        f"<code>{referral_link}</code>\n\n"
        f"Havolani nusxalab, do'stlaringizga yuboring!"
    )
    
    await callback.message.answer(text, parse_mode="HTML")


@router.callback_query(F.data == "stars_menu")
async def callback_stars_menu(callback: CallbackQuery):
    """Show stars purchase menu"""
    await callback.answer()
    
    text = (
        f'<tg-emoji emoji-id="{EMOJI_STAR}">⭐</tg-emoji> <b>Telegram Stars sotib olish</b>\n\n'
        "Stars — Telegram ichida maxsus kontent va xizmatlarni "
        "sotib olish uchun ishlatiladi.\n\n"
        "📦 <b>Mavjud paketlar:</b>"
    )
    
    await callback.message.answer(
        text,
        reply_markup=keyboards.get_stars_keyboard(),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "premium_menu")
async def callback_premium_menu(callback: CallbackQuery):
    """Show premium purchase menu"""
    await callback.answer()
    
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
    
    await callback.message.answer(
        text,
        reply_markup=keyboards.get_premium_keyboard(),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "phone_menu")
async def callback_phone_menu(callback: CallbackQuery):
    """Show phone menu"""
    await callback.answer()
    
    text = (
        "📱 <b>Virtual raqamlar</b>\n\n"
        "Tez orada mavjud bo'ladi...\n\n"
        "Bu bo'limda siz turli xizmatlar uchun "
        "virtual telefon raqamlarini sotib olishingiz mumkin bo'ladi."
    )
    
    await callback.message.answer(text, parse_mode="HTML")


@router.callback_query(F.data == "gift_menu")
async def callback_gift_menu(callback: CallbackQuery):
    """Show gift menu"""
    await callback.answer()
    
    text = (
        f'<tg-emoji emoji-id="{EMOJI_GIFT}">🎁</tg-emoji> <b>Gift sovg\'alar</b>\n\n'
        "Tez orada mavjud bo'ladi...\n\n"
        "Bu bo'limda siz do'stlaringizga Premium, "
        "Stars va boshqa sovg'alarni yuborishingiz mumkin bo'ladi."
    )
    
    await callback.message.answer(
        text,
        parse_mode="HTML"
    )


@router.callback_query(F.data == "topup_menu")
async def callback_topup_menu(callback: CallbackQuery, state: FSMContext):
    """Show topup amount request"""
    await callback.answer()
    
    user_id = callback.from_user.id
    user = await db.get_user(user_id)
    
    if not user:
        text = f'<tg-emoji emoji-id="{EMOJI_CROSS}">❌</tg-emoji> Foydalanuvchi topilmadi!'
        await callback.message.answer(text, parse_mode="HTML")
        return
    
    from keyboards import get_back_keyboard
    text = (
        f'<tg-emoji emoji-id="{EMOJI_MONEY_TEXT}">💰</tg-emoji> '
        f"<b>Balansni to'ldirish</b>\n\n"
        f"Quyidagi miqdorni kiriting:\n\n"
        f'<tg-emoji emoji-id="{EMOJI_DOWN}">⬇️</tg-emoji> '
        f"Minimal: 1 000 so'm\n"
        f'<tg-emoji emoji-id="{EMOJI_UP}">⬆️</tg-emoji> '
        f"Maksimal: 2 500 000 so'm"
    )
    
    await callback.message.answer(text, parse_mode="HTML", reply_markup=get_back_keyboard())
    from handlers.balance import BalanceStates
    await state.set_state(BalanceStates.waiting_amount)


@router.callback_query(F.data == "support")
async def callback_support(callback: CallbackQuery):
    """Show support information"""
    await callback.answer()
    
    text = (
        "🔒 <b>Qo'llab-quvvatlash</b>\n\n"
        "Savol yoki muammo bo'lsa, biz bilan bog'laning:\n\n"
        "👤 Admin: @cofeature\n"
        "📢 Kanal: @coinstatuz_org\n\n"
        "⏰ Ish vaqti: 24/7 (har kuni)"
    )
    
    await callback.message.answer(text, parse_mode="HTML")


@router.callback_query(F.data == "back_to_main")
async def callback_back_to_main(callback: CallbackQuery):
    """Return to main menu via callback"""
    await callback.answer()
    user_id = callback.from_user.id
    user = await db.get_user(user_id)
    lang = user.get("language", "uz") if user else "uz"
    welcome_text = get_welcome_text(user, callback.from_user.username, callback.from_user.first_name)
    try:
        await callback.message.edit_text(
            welcome_text,
            reply_markup=keyboards.get_webapp_main_keyboard(user_id, lang=lang),
            parse_mode="HTML"
        )
    except Exception:
        await callback.message.answer(
            welcome_text,
            reply_markup=keyboards.get_webapp_main_keyboard(user_id, lang=lang),
            parse_mode="HTML"
        )


@router.message(Command("konkurs"))
@router.message(F.text.in_({"🏆 Konkurs", "🏆 Konkurslar", "📢 Referal konkurs"}))
@router.callback_query(F.data == "user_contest")
async def user_contest_handler(event: Message | CallbackQuery):
    """Display user contest section, leaderboard, and referral link"""
    if isinstance(event, CallbackQuery):
        await event.answer()
        msg = event.message
        user_id = event.from_user.id
    else:
        msg = event
        user_id = event.from_user.id

    from handlers.admin import _runtime_settings
    from services.database import db_conn, db

    enabled = _runtime_settings.get("ref_contest_enabled", True)
    prize = _runtime_settings.get("ref_contest_prize", 500)
    min_refs = _runtime_settings.get("ref_contest_min_refs", 5)

    status_str = "✅ <b>FAOL</b>" if enabled else "❌ <b>VAQTINCHA TO'XTATILGAN</b>"

    user = await db.get_user(user_id)
    user_refs = user.get("referrals", 0) if user else 0

    rows = await db_conn.fetch(
        "SELECT telegram_id, username, full_name, referrals FROM users ORDER BY referrals DESC LIMIT 10"
    )

    top_text = ""
    if not rows:
        top_text = "<i>Hozircha ishtirokchilar yo'q. Birinchi bo'lib taklif qiling!</i>\n"
    else:
        for i, r in enumerate(rows, 1):
            name = r["username"] or r["full_name"] or f"ID: {r['telegram_id']}"
            display_name = name if name.startswith("@") else f"<b>{name}</b>"
            medal = "🥇" if i == 1 else ("🥈" if i == 2 else ("🥉" if i == 3 else f"{i}."))
            top_text += f"{medal} {display_name} — <b>{r['referrals']}</b> ta\n"

    bot_info = await msg.bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={user_id}"

    text = (
        f"🏆 <b>REFERAL KONKURS</b>\n\n"
        f"Holati: {status_str}\n"
        f"💰 Sovrin: <b>{prize:,}</b> so'm\n"
        f"🎯 Minimal talab: <b>{min_refs}</b> ta referal\n\n"
        f"📊 <b>Sizning natijangiz:</b>\n"
        f"👥 Taklif qilgan do'stlaringiz: <b>{user_refs}</b> ta\n\n"
        f"🥇 <b>TOP-10 ISHTIROKCHILAR:</b>\n"
        f"{top_text}\n"
        f"🔗 <b>Sizning taklif havolangiz:</b>\n"
        f"<code>{ref_link}</code>\n\n"
        f"<i>Do'stlaringizni taklif qiling va konkursda g'olib bo'ling!</i>"
    )

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🔄 Yangilash", callback_data="user_contest"),
        InlineKeyboardButton(
            text="🔗 Do'stlarga ulashish",
            url=f"https://t.me/share/url?url={ref_link}&text=CoinStat%20UZ%20botida%20konkursda%20qatnashib%20pul%20yuting!"
        )
    )
    builder.row(
        InlineKeyboardButton(text="◀️ Orqaga", callback_data="back_to_main")
    )

    if isinstance(event, CallbackQuery):
        try:
            await msg.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        except Exception:
            await msg.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    else:
        await msg.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")


@router.callback_query(F.data.startswith("join_giveaway_"))
async def callback_join_giveaway(callback: CallbackQuery):
    """Process user clicking 'Qatnashish' button on Giveaway post"""
    gw_id = int(callback.data.split("_")[-1])
    user_id = callback.from_user.id

    from services.database import get_giveaway_by_id, is_participant, join_giveaway, get_participants_count, db
    await db.create_user(user_id, callback.from_user.username, callback.from_user.first_name)

    gw = await get_giveaway_by_id(gw_id)
    if not gw or gw.get("status") != "active":
        await callback.answer("❌ Ushbu konkurs yakunlangan yoki topilmadi!", show_alert=True)
        return

    required_channel = gw.get("required_channel", "@CoinStatUz")
    try:
        member = await callback.bot.get_chat_member(chat_id=required_channel, user_id=user_id)
        if member.status not in ["creator", "administrator", "member"]:
            await callback.answer(
                f"❌ Konkursda qatnashish uchun avval {required_channel} kanaliga a'zo bo'lishingiz kerak!",
                show_alert=True
            )
            return
    except Exception as e:
        logger.warning("Subscription check error: %s", e)

    already_joined = await is_participant(gw_id, user_id)
    if already_joined:
        part_cnt = await get_participants_count(gw_id)
        await callback.answer(f"ℹ️ Siz ushbu konkursda allaqachon qatnashyapsiz! 🎉\nJami ishtirokchilar: {part_cnt} ta", show_alert=True)
        return

    joined = await join_giveaway(gw_id, user_id)
    if joined:
        part_cnt = await get_participants_count(gw_id)
        await callback.answer(f"🎉 Tabriklaymiz! Siz konkursda muvaffaqiyatli qatnashdingiz!\nJami ishtirokchilar: {part_cnt} ta", show_alert=True)
    else:
        await callback.answer("❌ Xatolik yuz berdi. Qayta urinib ko'ring.", show_alert=True)

