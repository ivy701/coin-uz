from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.config import settings


def _btn(
    text: str,
    *,
    web_app_url: str | None = None,
    callback_data: str | None = None,
    url: str | None = None,
    style: str | None = None,
    icon_custom_emoji_id: str | None = None,
) -> InlineKeyboardButton:
    kwargs: dict = {"text": text}
    if web_app_url:
        kwargs["web_app"] = WebAppInfo(url=web_app_url)
    if callback_data:
        kwargs["callback_data"] = callback_data
    if url:
        kwargs["url"] = url
    if style:
        kwargs["style"] = style
    if icon_custom_emoji_id:
        kwargs["icon_custom_emoji_id"] = icon_custom_emoji_id
    return InlineKeyboardButton(**kwargs)


EMOJI_BTN_WEBAPP = "5472401690793614752"
EMOJI_BTN_ADMIN = "5474667187258006816"
EMOJI_BTN_NEWS = "5307943162486994719"


def main_inline_keyboard(user_id: int | None = None) -> InlineKeyboardMarkup:
    base = settings.webapp_base_url or "https://t.me/CoinStatuz_bot/app"
    admin_url = settings.support_url or "https://t.me/cofeature"
    channel_url = "https://t.me/CoinStatUz"
    
    params = ["v=26.0"]
    if user_id:
        params.append(f"uid={user_id}")
    query_str = f"?{'&'.join(params)}"

    if base.startswith("http://") or base.startswith("https://"):
        url = f"{base.rstrip('/')}/index.html{query_str}"
        web_app_btn = InlineKeyboardButton(text="Web App", web_app=WebAppInfo(url=url), icon_custom_emoji_id=EMOJI_BTN_WEBAPP)
    elif base.startswith("https://t.me/"):
        web_app_btn = InlineKeyboardButton(text="Web App", url=base, icon_custom_emoji_id=EMOJI_BTN_WEBAPP)
    else:
        url = f"https://{base.lstrip('/')}/index.html{query_str}"
        web_app_btn = InlineKeyboardButton(text="Web App", web_app=WebAppInfo(url=url), icon_custom_emoji_id=EMOJI_BTN_WEBAPP)

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [web_app_btn],
            [
                InlineKeyboardButton(text="Admin", url=admin_url, icon_custom_emoji_id=EMOJI_BTN_ADMIN),
                InlineKeyboardButton(text="Yangiliklar", url=channel_url, icon_custom_emoji_id=EMOJI_BTN_NEWS),
            ],
        ]
    )


def topup_back_keyboard() -> InlineKeyboardMarkup:
    """Back button for topup screen"""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text="◀️ Orqaga",
        callback_data="topup_back"
    ))
    return builder.as_markup()


def topup_payment_keyboard(order_id: str) -> InlineKeyboardMarkup:
    """Payment check + cancel buttons"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✅ To'lovni tekshirish",
            callback_data=f"check_payment_{order_id}"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="❌ Bekor qilish",
            callback_data=f"cancel_order_{order_id}"
        )
    )
    return builder.as_markup()


def stars_keyboard() -> InlineKeyboardMarkup:
    """Stars purchase packages"""
    builder = InlineKeyboardBuilder()
    for amount, price in [
        (50, 9900), (75, 15000), (100, 20000),
        (250, 50000), (500, 100000),
    ]:
        builder.row(InlineKeyboardButton(
            text=f"⭐ {amount} Stars — {price:,} so'm",
            callback_data=f"buy_stars_{amount}"
        ))
    builder.row(InlineKeyboardButton(text="◀️ Orqaga", callback_data="refresh_menu"))
    return builder.as_markup()


def premium_keyboard() -> InlineKeyboardMarkup:
    """Premium subscription packages"""
    builder = InlineKeyboardBuilder()
    for duration, price, name in [
        (3, 160000, "3 oy"), (6, 225000, "6 oy"), (12, 390000, "12 oy"),
    ]:
        builder.row(InlineKeyboardButton(
            text=f"💎 Premium {name} — {price:,} so'm",
            callback_data=f"buy_premium_{duration}"
        ))
    builder.row(InlineKeyboardButton(text="◀️ Orqaga", callback_data="refresh_menu"))
    return builder.as_markup()


def bosh_menu_keyboard() -> InlineKeyboardMarkup:
    """Blue Bosh Menu button"""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text="🏠 Bosh Menu",
        callback_data="refresh_menu",
        style="primary",
    ))
    return builder.as_markup()


def bottom_reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="💰 Narxlar"),
                KeyboardButton(text="📚 Qo'llanma"),
            ],
            [KeyboardButton(text="🔄 Tilni almashtirish")],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )
