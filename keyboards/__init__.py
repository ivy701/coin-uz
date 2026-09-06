from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    WebAppInfo
)
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
import config


def get_webapp_main_keyboard(user_id: int | None = None, lang: str = "uz", balance: int | None = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    admin_url = getattr(config, 'SUPPORT_URL', 'https://t.me/cofeature') or "https://t.me/cofeature"
    channel_url = "https://t.me/CoinStatUz"
    webapp_url = getattr(config, 'WEBAPP_URL', '') or ''
    if not webapp_url:
        webapp_url = "https://t.me/CoinStatuz_bot/app"

    query_params = []
    if user_id:
        query_params.append(f"uid={user_id}")
    if balance is not None:
        query_params.append(f"bal={balance}")
    query_str = f"?{'&'.join(query_params)}" if query_params else ""

    if webapp_url.startswith("http://") or webapp_url.startswith("https://"):
        if webapp_url.startswith("https://t.me/"):
            builder.row(
                InlineKeyboardButton(
                    text="🦆 Web App",
                    url=webapp_url,
                )
            )
        else:
            url = f"{webapp_url.rstrip('/')}/index.html{query_str}"
            builder.row(
                InlineKeyboardButton(
                    text="🦆 Web App",
                    web_app=WebAppInfo(url=url),
                )
            )
    else:
        url = f"https://{webapp_url.lstrip('/')}/index.html{query_str}"
        builder.row(
            InlineKeyboardButton(
                text="🦆 Web App",
                web_app=WebAppInfo(url=url),
            )
        )

    builder.row(
        InlineKeyboardButton(
            text="🤓 Admin",
            url=admin_url,
        ),
        InlineKeyboardButton(
            text="📢 Yangiliklar",
            url=channel_url,
        )
    )

    return builder.as_markup()


def get_quick_topup_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="10,000 so'm", callback_data="quick_topup_10000"),
        InlineKeyboardButton(text="25,000 so'm", callback_data="quick_topup_25000"),
    )
    builder.row(
        InlineKeyboardButton(text="50,000 so'm", callback_data="quick_topup_50000"),
        InlineKeyboardButton(text="100,000 so'm", callback_data="quick_topup_100000"),
    )
    builder.row(
        InlineKeyboardButton(text="250,000 so'm", callback_data="quick_topup_250000"),
        InlineKeyboardButton(text="500,000 so'm", callback_data="quick_topup_500000"),
    )
    builder.row(
        InlineKeyboardButton(text="◀️ Bosh menyu", callback_data="back_to_main"),
    )
    return builder.as_markup()


def get_language_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🇺🇿 O'zbekcha", callback_data="set_lang_uz"),
        InlineKeyboardButton(text="🇷🇺 Русский", callback_data="set_lang_ru"),
    )
    return builder.as_markup()


def get_main_keyboard() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()

    builder.row(
        KeyboardButton(text="💰 Balans to'ldirish"),
        KeyboardButton(text="⭐ Stars xarid"),
    )
    builder.row(
        KeyboardButton(text="💎 Premium"),
        KeyboardButton(text="🎁 Sovg'alar"),
    )
    builder.row(
        KeyboardButton(text="📦 Buyurtmalarim"),
        KeyboardButton(text="🏠 Bosh menyu"),
    )

    return builder.as_markup(resize_keyboard=True)


def get_stars_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    for package in config.PRODUCTS["stars"]["packages"]:
        amount = package["amount"]
        price = package["price"]
        builder.row(
            InlineKeyboardButton(
                text=f"⭐ {amount} Stars - {price:,} so'm",
                callback_data=f"buy_stars_{amount}"
            )
        )

    builder.row(
        InlineKeyboardButton(text="◀️ Orqaga", callback_data="back_to_main")
    )

    return builder.as_markup()


def get_premium_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    for package in config.PRODUCTS["premium"]["packages"]:
        duration = package["duration"]
        price = package["price"]
        name = package["name"]
        builder.row(
            InlineKeyboardButton(
                text=f"💎 Premium {name} - {price:,} so'm",
                callback_data=f"buy_premium_{duration}"
            )
        )

    builder.row(
        InlineKeyboardButton(text="◀️ Orqaga", callback_data="back_to_main")
    )

    return builder.as_markup()


def get_payment_keyboard(payment_url: str, order_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(text="💳 To'lash", url=payment_url)
    )
    builder.row(
        InlineKeyboardButton(text="✅ To'lovni tekshirish", callback_data=f"check_payment_{order_id}")
    )
    builder.row(
        InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"cancel_order_{order_id}")
    )

    return builder.as_markup()


def get_webapp_keyboard() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()

    builder.row(
        KeyboardButton(
            text="🛒 Magazin ochish",
            web_app=WebAppInfo(url=f"{config.WEBAPP_URL}/index.html?v=11.0")
        )
    )
    builder.row(
        KeyboardButton(text="◀️ Orqaga")
    )

    return builder.as_markup(resize_keyboard=True)


def get_admin_main_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📊 Statistika", callback_data="admin_stats"))
    builder.row(InlineKeyboardButton(text="👥 Foydalanuvchilar", callback_data="admin_users"))
    builder.row(InlineKeyboardButton(text="💰 Balans boshqaruvi", callback_data="admin_balance"))
    builder.row(InlineKeyboardButton(text="💳 To'lovni tasdiqlash", callback_data="admin_confirm_payments"))
    builder.row(InlineKeyboardButton(text="📢 Xabar yuborish", callback_data="admin_broadcast"))
    builder.row(InlineKeyboardButton(text="📦 Buyurtmalar", callback_data="admin_orders"))
    builder.row(InlineKeyboardButton(text="⚙️ Sozlamalar", callback_data="admin_settings"))
    return builder.as_markup()


def get_admin_payments_keyboard(orders: list, page: int = 1, total: int = 0) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for o in orders:
        label = f"💰 #{o['id']} — {o.get('telegram_id', '?')} — {o.get('amount', 0):,} so'm"
        builder.row(InlineKeyboardButton(
            text=label,
            callback_data=f"admin_pay_detail_{o['id']}"
        ))
    has_next = (page * 5) < total
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"admin_pay_page_{page-1}"))
    nav.append(InlineKeyboardButton(text=f"{page}", callback_data="admin_pay_skip"))
    if has_next:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"admin_pay_page_{page+1}"))
    if nav:
        builder.row(*nav)
    builder.row(InlineKeyboardButton(text="◀️ Orqaga", callback_data="admin_main_menu"))
    return builder.as_markup()


def get_admin_pay_confirm_keyboard(order_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✅ To'lov keldi — Balansni to'ldirish",
            callback_data=f"admin_pay_confirm_{order_id}"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="❌ Bekor qilish",
            callback_data=f"admin_pay_reject_{order_id}"
        )
    )
    builder.row(InlineKeyboardButton(text="◀️ Orqaga", callback_data="admin_confirm_payments"))
    return builder.as_markup()


def get_admin_back_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="◀️ Orqaga", callback_data="admin_main_menu"))
    return builder.as_markup()


def get_admin_users_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📋 Ro'yxat", callback_data="admin_users_list_1"))
    builder.row(InlineKeyboardButton(text="🔍 Qidirish", callback_data="admin_users_search"))
    builder.row(InlineKeyboardButton(text="◀️ Orqaga", callback_data="admin_main_menu"))
    return builder.as_markup()


def get_admin_users_list_keyboard(page: int, has_next: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"admin_users_list_{page-1}"))
    nav.append(InlineKeyboardButton(text=f"{page}", callback_data="admin_users_list_skip"))
    if has_next:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"admin_users_list_{page+1}"))
    if nav:
        builder.row(*nav)
    builder.row(InlineKeyboardButton(text="◀️ Orqaga", callback_data="admin_users"))
    return builder.as_markup()


def get_admin_user_actions_keyboard(telegram_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🔒 Bloklash", callback_data=f"admin_user_block_{telegram_id}"),
        InlineKeyboardButton(text="🔓 Blokdan chiqarish", callback_data=f"admin_user_unblock_{telegram_id}"),
    )
    builder.row(
        InlineKeyboardButton(text="🗑 O'chirish", callback_data=f"admin_user_delete_{telegram_id}"),
    )
    builder.row(InlineKeyboardButton(text="◀️ Orqaga", callback_data="admin_users"))
    return builder.as_markup()


def get_admin_orders_keyboard(orders: list, page: int = 1, total: int = 0) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for o in orders:
        status_emoji = {"pending": "⏳", "processing": "🔄", "completed": "✅",
                        "failed": "❌", "cancelled": "🚫"}.get(o["status"], "❓")
        label = f"{status_emoji} #{o['id']} — {o.get('product_type', '?')}"
        builder.row(InlineKeyboardButton(
            text=label, callback_data=f"admin_order_detail_{o['id']}"
        ))
    has_next = (page * 5) < total
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"admin_orders_page_{page-1}"))
    nav.append(InlineKeyboardButton(text=f"{page}", callback_data="admin_orders_skip"))
    if has_next:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"admin_orders_page_{page+1}"))
    if nav:
        builder.row(*nav)
    builder.row(InlineKeyboardButton(text="◀️ Orqaga", callback_data="admin_main_menu"))
    return builder.as_markup()


def get_admin_order_detail_keyboard(order_id: int, current_status: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    statuses = ["pending", "processing", "completed", "failed", "cancelled"]
    for s in statuses:
        if s != current_status:
            builder.row(InlineKeyboardButton(
                text=f"➡️ {s.title()}", callback_data=f"admin_order_status_{order_id}_{s}"
            ))
    builder.row(InlineKeyboardButton(text="◀️ Orqaga", callback_data="admin_orders"))
    return builder.as_markup()


def get_admin_balance_actions_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="➕ Qo'shish", callback_data="admin_balance_act_add"),
        InlineKeyboardButton(text="➖ Ayirish", callback_data="admin_balance_act_deduct"),
    )
    builder.row(InlineKeyboardButton(text="◀️ Orqaga", callback_data="admin_main_menu"))
    return builder.as_markup()


def get_admin_broadcast_confirm_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Yuborish", callback_data="admin_broadcast_confirm"),
        InlineKeyboardButton(text="❌ Bekor qilish", callback_data="admin_broadcast_cancel"),
    )
    return builder.as_markup()


def get_admin_keyboard() -> InlineKeyboardMarkup:
    return get_admin_main_keyboard()


def get_confirm_keyboard(action: str, data: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(text="✅ Ha", callback_data=f"confirm_{action}_{data}"),
        InlineKeyboardButton(text="❌ Yo'q", callback_data=f"cancel_{action}")
    )

    return builder.as_markup()


def get_back_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="◀️ Orqaga", callback_data="back_to_main")
    )
    return builder.as_markup()


def get_card_payment_keyboard(order_id: str) -> InlineKeyboardMarkup:
    import os
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✅ To'lovni tekshirish",
            callback_data=f"check_payment_{order_id}"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="👨‍💻 Adminga murojaat qilish",
            url=os.getenv("SUPPORT_URL", "https://t.me/cofeature")
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="❌ Bekor qilish",
            callback_data=f"cancel_order_{order_id}"
        )
    )
    return builder.as_markup()


def get_bosh_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="🏠 Bosh Menu",
            callback_data="back_to_main",
            style="primary",
        )
    )
    return builder.as_markup()
