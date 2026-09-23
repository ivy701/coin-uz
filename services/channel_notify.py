import logging
import os
import uuid
import datetime
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BufferedInputFile

import config
from services.receipt_generator import generate_receipt_bytes

logger = logging.getLogger(__name__)

CHANNEL_ID = config.CHANNEL_ORDERS or "@coinstatuz_org"
# Admin @cofeature Telegram ID for verification checks
ADMIN_CHECK_ID = int(os.getenv("ADMIN_CHECK_ID") or (config.ADMINS[0] if config.ADMINS else 8202423244))


def _emoji(emoji_id: str | None, fallback: str) -> str:
    if emoji_id:
        return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'
    return fallback


async def notify_stars(
    username: str,
    quantity: int,
    price: int,
    order_id: str | None = None,
    user_id: int | None = None
) -> None:
    star_e = _emoji(config.EMOJI_STAR, "⭐️")
    target_e = _emoji(config.EMOJI_TARGET, "🎯")
    amount_e = _emoji(config.EMOJI_STARS_AMOUNT, "💫")
    money_e = _emoji(config.EMOJI_MONEY_CH, "💰")
    rocket_e = _emoji(config.EMOJI_ROCKET, "🚀")

    oid = order_id or f"CS-{uuid.uuid4().hex[:6].upper()}"
    uname = str(username).strip().lstrip("@")
    target_str = f"@{uname}" if uname and not uname.isdigit() else f"ID: {uname}"
    price_formatted = f"{price:,} so'm"

    caption = (
        f"{star_e} <b>CoinStat UZ — Stars Muvaffaqiyatli Yuborildi!</b>\n\n"
        f"🆔 <b>Buyurtma ID:</b> <code>#{oid}</code>\n"
        f"{target_e} <b>Qabul qiluvchi:</b> {target_str}\n"
        f"{amount_e} <b>Miqdor:</b> {quantity} Stars\n"
        f"{money_e} <b>Summa:</b> {price_formatted}\n\n"
        f"{rocket_e} Stars hisobga muvaffaqiyatli o'tkazildi!\n"
        f"🌐 <b>Kanal:</b> @CoinStatUz | 🤖 <b>Bot:</b> @CoinStatuz_bot"
    )

    try:
        photo_bytes = generate_receipt_bytes(
            order_id=oid,
            username=target_str,
            product_name="Telegram Stars",
            amount_str=f"{quantity} Stars",
            price_str=price_formatted.upper(),
            status="MUVAFFAQIYATLI"
        )
    except Exception as e:
        logger.warning(f"Error generating receipt image for stars: {e}")
        photo_bytes = None

    await _send_receipt(caption, photo_bytes, oid, user_id=user_id)


async def notify_premium(
    username: str,
    months: int,
    price: int,
    order_id: str | None = None,
    user_id: int | None = None
) -> None:
    star_e = _emoji(config.EMOJI_STAR, "⭐️")
    target_e = _emoji(config.EMOJI_TARGET, "🎯")
    calendar_e = _emoji(config.EMOJI_CALENDAR, "📅")
    money_e = _emoji(config.EMOJI_MONEY_CH, "💰")
    rocket_e = _emoji(config.EMOJI_ROCKET, "🚀")

    oid = order_id or f"CS-{uuid.uuid4().hex[:6].upper()}"
    uname = str(username).strip().lstrip("@")
    target_str = f"@{uname}" if uname and not uname.isdigit() else f"ID: {uname}"
    price_formatted = f"{price:,} so'm"

    caption = (
        f"{star_e} <b>CoinStat UZ — Premium Muvaffaqiyatli Yuborildi!</b>\n\n"
        f"🆔 <b>Buyurtma ID:</b> <code>#{oid}</code>\n"
        f"{target_e} <b>Qabul qiluvchi:</b> {target_str}\n"
        f"{calendar_e} <b>Muddat:</b> {months} oy\n"
        f"{money_e} <b>Summa:</b> {price_formatted}\n\n"
        f"{rocket_e} Premium obuna muvaffaqiyatli faollashtirildi!\n"
        f"🌐 <b>Kanal:</b> @CoinStatUz | 🤖 <b>Bot:</b> @CoinStatuz_bot"
    )

    try:
        photo_bytes = generate_receipt_bytes(
            order_id=oid,
            username=target_str,
            product_name="Telegram Premium",
            amount_str=f"{months} Oylik",
            price_str=price_formatted.upper(),
            status="MUVAFFAQIYATLI"
        )
    except Exception as e:
        logger.warning(f"Error generating receipt image for premium: {e}")
        photo_bytes = None

    await _send_receipt(caption, photo_bytes, oid, user_id=user_id)


async def notify_gift(
    username: str,
    gift_id: str,
    gift_name: str,
    price: int,
    order_id: str | None = None,
    user_id: int | None = None
) -> None:
    gift_header_e = _emoji(config.EMOJI_GIFT, "🎁")
    target_e = _emoji(config.EMOJI_TARGET, "🎯")
    amount_e = _emoji(config.EMOJI_STARS_AMOUNT, "💫")
    money_e = _emoji(config.EMOJI_MONEY_CH, "💰")
    rocket_e = _emoji(config.EMOJI_ROCKET_GIFT, "🚀")

    oid = order_id or f"CS-{uuid.uuid4().hex[:6].upper()}"
    uname = str(username).strip().lstrip("@")
    target_str = f"@{uname}" if uname and not uname.isdigit() else f"ID: {uname}"
    price_formatted = f"{price:,} so'm"

    caption = (
        f"{gift_header_e} <b>CoinStat UZ — Telegram Gift Yuborildi!</b>\n\n"
        f"🆔 <b>Buyurtma ID:</b> <code>#{oid}</code>\n"
        f"{target_e} <b>Qabul qiluvchi:</b> {target_str}\n"
        f"{amount_e} <b>Gift:</b> {gift_name}\n"
        f"{money_e} <b>Summa:</b> {price_formatted}\n\n"
        f"{rocket_e} Gift sovg'asi yetkazildi!\n"
        f"🌐 <b>Kanal:</b> @CoinStatUz | 🤖 <b>Bot:</b> @CoinStatuz_bot"
    )

    try:
        photo_bytes = generate_receipt_bytes(
            order_id=oid,
            username=target_str,
            product_name=f"Gift: {gift_name}",
            amount_str="1 dona",
            price_str=price_formatted.upper(),
            status="MUVAFFAQIYATLI"
        )
    except Exception as e:
        logger.warning(f"Error generating receipt image for gift: {e}")
        photo_bytes = None

    await _send_receipt(caption, photo_bytes, oid, user_id=user_id)


async def notify_phone(
    username: str,
    country: str,
    price: int = 0,
    order_id: str | None = None,
    user_id: int | None = None
) -> None:
    star_e = _emoji(config.EMOJI_STAR, "⭐️")
    target_e = _emoji(config.EMOJI_TARGET, "🎯")
    money_e = _emoji(config.EMOJI_MONEY_CH, "💰")
    rocket_e = _emoji(config.EMOJI_ROCKET, "🚀")

    oid = order_id or f"CS-{uuid.uuid4().hex[:6].upper()}"
    uname = str(username).strip().lstrip("@")
    target_str = f"@{uname}" if uname and not uname.isdigit() else f"ID: {uname}"
    price_formatted = f"{price:,} so'm"

    caption = (
        f"{star_e} <b>CoinStat UZ — Raqam Muvaffaqiyatli Xarid Qilindi!</b>\n\n"
        f"🆔 <b>Buyurtma ID:</b> <code>#{oid}</code>\n"
        f"{target_e} <b>Qabul qiluvchi:</b> {target_str}\n"
        f"🌍 <b>Davlat:</b> {country}\n"
        f"{money_e} <b>Summa:</b> {price_formatted}\n\n"
        f"{rocket_e} Telegram raqam hisobga muvaffaqiyatli yetkazildi!\n"
        f"🌐 <b>Kanal:</b> @CoinStatUz | 🤖 <b>Bot:</b> @CoinStatuz_bot"
    )

    try:
        photo_bytes = generate_receipt_bytes(
            order_id=oid,
            username=target_str,
            product_name="Telegram Raqam",
            amount_str=country,
            price_str=price_formatted.upper(),
            status="MUVAFFAQIYATLI"
        )
    except Exception as e:
        logger.warning(f"Error generating receipt image for phone: {e}")
        photo_bytes = None

    await _send_receipt(caption, photo_bytes, oid, user_id=user_id)


async def _send_receipt(
    caption: str,
    photo_bytes: bytes | None,
    order_id: str,
    user_id: int | None = None
) -> None:
    """Send receipt photo and caption to channel, admin @cofeature, and buyer."""
    if not config.BOT_TOKEN:
        logger.warning("BOT_TOKEN not set, skipping receipt dispatch")
        return

    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    targets = []
    # 1. Orders Channel
    if CHANNEL_ID:
        targets.append(("channel", CHANNEL_ID, caption))

    # 2. Admin @cofeature for verification
    if ADMIN_CHECK_ID:
        admin_cap = (
            f"🧾 <b>YANGI TO'LOV CHEKI (NAZORAT)</b>\n"
            f"👨‍💻 <i>Admin @cofeature uchun avtomatik tekshiruv kvitansiyasi:</i>\n\n"
            + caption
        )
        targets.append(("admin", ADMIN_CHECK_ID, admin_cap))

    # 3. Customer (if ID available)
    if user_id:
        user_cap = (
            f"🧾 <b>XARIDINGIZ CHEKI</b>\n\n"
            + caption
        )
        targets.append(("user", user_id, user_cap))

    try:
        for role, chat_target, cap in targets:
            try:
                if photo_bytes:
                    photo_file = BufferedInputFile(photo_bytes, filename=f"receipt_{order_id}.png")
                    await bot.send_photo(chat_id=chat_target, photo=photo_file, caption=cap)
                else:
                    await bot.send_message(chat_id=chat_target, text=cap)
                logger.info("Receipt successfully sent to %s (%s)", role, chat_target)
            except Exception as ex:
                logger.warning("Failed to send receipt to %s (%s): %s", role, chat_target, ex)
    finally:
        await bot.session.close()
