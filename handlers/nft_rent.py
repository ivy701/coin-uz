"""
Telegram Bot Handlers for Marketapp & TON NFT Rental Service
Features:
- Interactive catalog: Gifts, Usernames, Numbers with pagination and photos
- Duration selection & atomic balance checkout
- "Mening ijaralarim" list & duration extension
- Admin commands: /nft_orders, /nft_margin, /nft_wallet
"""

from __future__ import annotations

import logging
from aiogram import Router, F, Bot
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup,
    InlineKeyboardButton, FSInputFile, URLInputFile
)
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

import config
from services.marketapp_service import marketapp_service
from services.database import get_user, db_conn

logger = logging.getLogger(__name__)
router = Router()


def _is_admin(user_id: int) -> bool:
    env_admins = [int(x.strip()) for x in (getattr(config, "ADMINS", []) or []) if str(x).strip().isdigit()]
    extra = [8202423244, 6552579124, 762282299]
    return user_id in env_admins or user_id in extra


# === 1. MAIN RENT ENTRY ===

@router.message(Command("rent"))
@router.message(F.text == "🖼 NFT Ijara")
async def show_nft_rent_home(message: Message):
    """Show NFT Rental Categories & Main Hub."""
    user_id = message.from_user.id if message.from_user else 0
    user = await get_user(user_id)
    bal = user.get("balance", 0) if user else 0

    margin = marketapp_service.margin_percent
    ton_rate = marketapp_service.ton_rate_uzs

    text = (
        "🖼 <b>CoinStat UZ — Telegram NFT Ijarasi</b>\n\n"
        "⚡ <b>Marketapp & TON blockchain</b> orqali Telegram sovg'alari, chiroyli username va +888 raqamlarni avtomatik ijaraga oling!\n\n"
        f"👛 <b>Sizning balansingiz:</b> <code>{bal:,}</code> so'm\n"
        f"📊 <b>Joriy kurs:</b> 1 TON ≈ <code>{ton_rate:,}</code> so'm (Ustama: {margin}%)\n"
        "🛡 <b>Kafolat:</b> Balansingizdan so'mda to'laysiz, bot TON hamyon orqali smart-kontraktda darhol ijarani rasmiylashtiradi.\n\n"
        "Kerakli bo'limni tanlang 👇"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎁 Sovg'alar (Gifts)", callback_data="rent_cat_gifts_0"),
            InlineKeyboardButton(text="🔤 Usernamelar", callback_data="rent_cat_usernames_0")
        ],
        [
            InlineKeyboardButton(text="🔢 Nomerlar (+888)", callback_data="rent_cat_numbers_0"),
            InlineKeyboardButton(text="📋 Mening ijaralarim", callback_data="rent_my_list")
        ],
        [
            InlineKeyboardButton(text="💰 Balansni to'ldirish", callback_data="btn_topup")
        ]
    ])

    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "rent_home")
async def callback_rent_home(callback: CallbackQuery):
    """Return to rent home menu."""
    await callback.answer()
    user_id = callback.from_user.id
    user = await get_user(user_id)
    bal = user.get("balance", 0) if user else 0

    margin = marketapp_service.margin_percent
    ton_rate = marketapp_service.ton_rate_uzs

    text = (
        "🖼 <b>CoinStat UZ — Telegram NFT Ijarasi</b>\n\n"
        "⚡ <b>Marketapp & TON blockchain</b> orqali Telegram sovg'alari, chiroyli username va +888 raqamlarni avtomatik ijaraga oling!\n\n"
        f"👛 <b>Sizning balansingiz:</b> <code>{bal:,}</code> so'm\n"
        f"📊 <b>Joriy kurs:</b> 1 TON ≈ <code>{ton_rate:,}</code> so'm (Ustama: {margin}%)\n\n"
        "Kerakli bo'limni tanlang 👇"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎁 Sovg'alar (Gifts)", callback_data="rent_cat_gifts_0"),
            InlineKeyboardButton(text="🔤 Usernamelar", callback_data="rent_cat_usernames_0")
        ],
        [
            InlineKeyboardButton(text="🔢 Nomerlar (+888)", callback_data="rent_cat_numbers_0"),
            InlineKeyboardButton(text="📋 Mening ijaralarim", callback_data="rent_my_list")
        ],
        [
            InlineKeyboardButton(text="💰 Balansni to'ldirish", callback_data="btn_topup")
        ]
    ])

    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")


# === 2. CATALOG & PAGINATION ===

@router.callback_query(F.data.startswith("rent_cat_"))
async def callback_browse_category(callback: CallbackQuery):
    """Display paginated list of NFTs for a category."""
    await callback.answer()
    parts = callback.data.split("_")
    category = parts[2]
    page = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 0

    cat_titles = {
        "gifts": "🎁 Telegram Sovg'alari",
        "usernames": "🔤 Telegram Usernamelar",
        "numbers": "🔢 Anonim Raqamlar (+888)"
    }
    title = cat_titles.get(category, "NFT Kolleksiyasi")

    catalog = await marketapp_service.get_available_nfts(category=category)
    items = catalog.get("items", [])

    page_size = 4
    total_pages = max(1, (len(items) + page_size - 1) // page_size)
    page = max(0, min(page, total_pages - 1))

    start_idx = page * page_size
    page_items = items[start_idx:start_idx + page_size]

    text = (
        f"🖼 <b>{title}</b>\n\n"
        f"⚡ <i>Quyidagi ro'yxatdan o'zingizga yoqqan NFT'ni tanlang va qulay muddatga ijaraga oling:</i>\n\n"
    )

    builder = InlineKeyboardBuilder()

    if not page_items:
        text += "⚠️ <i>Hozirda bu bo'limda bo'sh NFT'lar mavjud emas. Birozdan so'ng qayta tekshiring.</i>\n"
    else:
        for idx, item in enumerate(page_items, start=start_idx + 1):
            name = item["nft_name"]
            day_uzs = item["price_per_day_uzs"]
            ton_p = item["price_per_day_ton"]
            text += f"<b>{idx}. {name}</b>\n"
            text += f"   💰 Kunlik: <code>{day_uzs:,} so'm</code> ({ton_p} TON)\n"
            text += f"   ⏱ Muddat: {item['min_duration']}–{item['max_duration']} kun\n\n"

            # Button for each item
            builder.row(InlineKeyboardButton(
                text=f"👉 {name} ({day_uzs:,} so'm/kun)",
                callback_data=f"rent_item_{category}_{start_idx + (idx - start_idx - 1)}"
            ))

    # Pagination navigation
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"rent_cat_{category}_{page - 1}"))
    nav_row.append(InlineKeyboardButton(text=f"📄 {page + 1}/{total_pages}", callback_data="rent_noop"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton(text="Keyingi ➡️", callback_data=f"rent_cat_{category}_{page + 1}"))

    if nav_row:
        builder.row(*nav_row)

    builder.row(
        InlineKeyboardButton(text="◀️ Bo'limlarga qaytish", callback_data="rent_home"),
        InlineKeyboardButton(text="📋 Ijaralarim", callback_data="rent_my_list")
    )

    try:
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")


@router.callback_query(F.data == "rent_noop")
async def callback_noop(callback: CallbackQuery):
    await callback.answer()


# === 3. ITEM CARD & DURATION SELECTION ===

@router.callback_query(F.data.startswith("rent_item_"))
async def callback_view_item(callback: CallbackQuery):
    """View detailed card of a selected NFT and pick duration."""
    await callback.answer()
    parts = callback.data.split("_")
    category = parts[2]
    item_idx = int(parts[3])

    catalog = await marketapp_service.get_available_nfts(category=category)
    items = catalog.get("items", [])
    if item_idx >= len(items):
        await callback.answer("NFT topilmadi", show_alert=True)
        return

    item = items[item_idx]
    user_id = callback.from_user.id
    user = await get_user(user_id)
    bal = user.get("balance", 0) if user else 0

    name = item["nft_name"]
    addr = item["nft_address"]
    day_uzs = item["price_per_day_uzs"]
    ton_p = item["price_per_day_ton"]
    min_d = item["min_duration"]
    max_d = item["max_duration"]

    text = (
        f"💎 <b>NFT: {name}</b>\n\n"
        f"🏷 <b>Kategoriya:</b> {category.capitalize()}\n"
        f"💰 <b>Kunlik narx:</b> <code>{day_uzs:,} so'm</code> ({ton_p} TON)\n"
        f"⏱ <b>Ruxsat etilgan muddat:</b> {min_d} kundan {max_d} kungacha\n"
        f"👛 <b>Sizning balansingiz:</b> <code>{bal:,} so'm</code>\n\n"
        "Ijara muddatini tanlang 👇"
    )

    builder = InlineKeyboardBuilder()

    # Duration choices based on min/max
    durations = [d for d in [1, 3, 7, 14, 30] if min_d <= d <= max_d]
    if not durations:
        durations = [min_d]

    duration_buttons = []
    for d in durations:
        _, tot_uzs = marketapp_service.calculate_price_uzs(ton_p, d)
        duration_buttons.append(InlineKeyboardButton(
            text=f"🗓 {d} kun ({tot_uzs:,} so'm)",
            callback_data=f"rent_dur_{category}_{item_idx}_{d}"
        ))

    for btn in duration_buttons:
        builder.row(btn)

    builder.row(
        InlineKeyboardButton(text="◀️ Ro'yxatga qaytish", callback_data=f"rent_cat_{category}_0")
    )

    try:
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")


# === 4. CHECKOUT CONFIRMATION ===

@router.callback_query(F.data.startswith("rent_dur_"))
async def callback_confirm_checkout(callback: CallbackQuery):
    """Show final order confirmation before atomic deduction."""
    await callback.answer()
    parts = callback.data.split("_")
    category = parts[2]
    item_idx = int(parts[3])
    days = int(parts[4])

    catalog = await marketapp_service.get_available_nfts(category=category)
    items = catalog.get("items", [])
    if item_idx >= len(items):
        await callback.answer("NFT topilmadi", show_alert=True)
        return

    item = items[item_idx]
    user_id = callback.from_user.id
    user = await get_user(user_id)
    bal = user.get("balance", 0) if user else 0

    name = item["nft_name"]
    ton_p = item["price_per_day_ton"]
    day_uzs, total_uzs = marketapp_service.calculate_price_uzs(ton_p, days)

    is_sufficient = bal >= total_uzs

    text = (
        "📋 <b>IJARA BUYURTMASINI TASDIQLASH</b>\n\n"
        f"💎 <b>NFT:</b> <code>{name}</code>\n"
        f"⏱ <b>Muddat:</b> {days} kun\n"
        f"💰 <b>Kunlik narx:</b> {day_uzs:,} so'm\n"
        f"💵 <b>Jami to'lov:</b> <b>{total_uzs:,} so'm</b>\n\n"
        f"👛 <b>Sizning balansingiz:</b> <code>{bal:,} so'm</code>\n"
    )

    if not is_sufficient:
        deficit = total_uzs - bal
        text += (
            f"\n❌ <b>Mablag' yetarli emas!</b>\n"
            f"Yetishmayotgan summa: <code>{deficit:,} so'm</code>.\n"
            f"Iltimos, avval hisobingizni to'ldiring."
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Balansni to'ldirish", callback_data="btn_topup")],
            [InlineKeyboardButton(text="◀️ Orqaga", callback_data=f"rent_item_{category}_{item_idx}")]
        ])
    else:
        text += (
            "\n⚡ <i>'Tasdiqlash va to'lash' tugmasini bosganingizda balansingizdan mablag' yechiladi va NFT Marketapp smart-kontrakt orqali avtomatik ijaraga olinadi.</i>"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="✅ Tasdiqlash va to'lash",
                callback_data=f"rent_pay_{category}_{item_idx}_{days}_{total_uzs}"
            )],
            [InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"rent_item_{category}_{item_idx}")]
        ])

    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")


# === 5. EXECUTE ATOMIC RENTAL ===

@router.callback_query(F.data.startswith("rent_pay_"))
async def callback_execute_rent(callback: CallbackQuery):
    """Perform atomic rent transaction with concurrency lock and refunds on error."""
    await callback.answer("Buyurtma bajarilmoqda...", show_alert=False)
    parts = callback.data.split("_")
    category = parts[2]
    item_idx = int(parts[3])
    days = int(parts[4])
    expected_uzs = int(parts[5])

    user_id = callback.from_user.id
    username = callback.from_user.username or callback.from_user.first_name or f"User#{user_id}"

    catalog = await marketapp_service.get_available_nfts(category=category)
    items = catalog.get("items", [])
    if item_idx >= len(items):
        await callback.message.answer("❌ NFT ro'yxatdan topilmadi.")
        return

    item = items[item_idx]

    # Status message
    loading_msg = await callback.message.edit_text(
        "⏳ <b>NFT ijaraga olinmoqda...</b>\n\n"
        "• Balans tekshirilmoqda...\n"
        "• Marketapp smart-kontraktiga so'rov yuborilmoqda...\n"
        "<i>Iltimos, bir necha soniya kuting...</i>",
        parse_mode="HTML"
    )

    # Execute rental service
    result = await marketapp_service.execute_nft_rental(
        user_id=user_id,
        username=username,
        nft_address=item["nft_address"],
        nft_name=item["nft_name"],
        category=category,
        days=days,
        price_per_day_ton=item["price_per_day_ton"],
        expected_total_uzs=expected_uzs,
        image_url=item.get("image_url", "")
    )

    if result.get("ok"):
        order_id = result.get("order_id", "?")
        tx_hash = result.get("tx_hash", "—")
        status = result.get("status", "completed")

        if status == "review":
            res_text = (
                f"⏳ <b>BUYURTMA TEKSHIRUV HOLATIDA!</b>\n\n"
                f"🆔 <b>Buyurtma ID:</b> #{order_id}\n"
                f"💎 <b>NFT:</b> <code>{item['nft_name']}</code>\n"
                f"⏱ <b>Muddat:</b> {days} kun\n\n"
                f"<i>Tranzaksiya blokcheynda tasdiqlanishi kutilmoqda. Tasdiqlanishi bilanoq NFT profilingizga ulanadi.</i>"
            )
        else:
            res_text = (
                f"🎉 <b>TABRIKLAYMIZ! NFT IJARAGA OLINDI!</b>\n\n"
                f"💎 <b>NFT:</b> <code>{item['nft_name']}</code>\n"
                f"⏱ <b>Muddat:</b> {days} kun\n"
                f"💰 <b>To'lov:</b> {expected_uzs:,} so'm\n"
                f"🆔 <b>Buyurtma ID:</b> #{order_id}\n"
                f"🔗 <b>Tx Hash:</b> <code>{tx_hash}</code>\n\n"
                f"⚡ <i>Siz endi 'Mening ijaralarim' bo'limi orqali ushbu NFT'ni boshqarishingiz mumkin.</i>"
            )

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 Mening ijaralarim", callback_data="rent_my_list")],
            [InlineKeyboardButton(text="🖼 Boshqa NFT'lar", callback_data="rent_home")]
        ])
        await loading_msg.edit_text(res_text, reply_markup=kb, parse_mode="HTML")
    else:
        err_msg = result.get("error", "Kutilmagan xatolik yuz berdi")
        res_text = (
            f"❌ <b>Xatolik yuz berdi:</b>\n\n"
            f"{err_msg}\n\n"
            f"<i>Agar mablag' yechilgan bo'lsa, u balansingizga to'liq qaytarildi.</i>"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Qayta urinish", callback_data=f"rent_item_{category}_{item_idx}")],
            [InlineKeyboardButton(text="🏠 Bosh menyu", callback_data="rent_home")]
        ])
        await loading_msg.edit_text(res_text, reply_markup=kb, parse_mode="HTML")


# === 6. "MENING IJARALARIM" & EXTENSION ===

@router.message(Command("my_rents"))
@router.callback_query(F.data == "rent_my_list")
async def show_my_rentals(event: Message | CallbackQuery):
    """Show list of active/expired NFT rentals owned by user."""
    user_id = event.from_user.id if event.from_user else 0
    if isinstance(event, CallbackQuery):
        await event.answer()

    rentals = await marketapp_service.get_user_rentals(user_id)

    text = "📋 <b>Sizning NFT Ijaralaringiz</b>\n\n"
    builder = InlineKeyboardBuilder()

    if not rentals:
        text += (
            "Hozirda sizda faol NFT ijaralari mavjud emas.\n\n"
            "Katalogdan eng sara sovg'a yoki chiroyli nomerni tanlab, ijaraga oling! 👇"
        )
        builder.row(InlineKeyboardButton(text="🚀 NFT Katalogini ko'rish", callback_data="rent_home"))
    else:
        for r in rentals[:8]:
            r_id = r["id"]
            name = r.get("nft_name") or "NFT"
            days = r.get("days", 1)
            rem = r.get("remaining_days", 1)
            status = r.get("status", "active")
            status_text = "Faol 🟢" if status == "active" else "Tugagan 🔴"

            text += (
                f"💎 <b>{name}</b>\n"
                f"   ⏱ Jami muddat: {days} kun | Qoldi: <b>{rem} kun</b>\n"
                f"   📊 Holat: {status_text}\n\n"
            )

            # Extension button if active
            builder.row(InlineKeyboardButton(
                text=f"⏳ {name} — Muddatni uzaytirish",
                callback_data=f"rent_ext_opt_{r_id}"
            ))

        builder.row(InlineKeyboardButton(text="➕ Yangi NFT ijaraga olish", callback_data="rent_home"))

    if isinstance(event, CallbackQuery):
        try:
            await event.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        except Exception:
            await event.message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    else:
        await event.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")


@router.callback_query(F.data.startswith("rent_ext_opt_"))
async def callback_extension_options(callback: CallbackQuery):
    """Choose days to extend active rental."""
    await callback.answer()
    rent_id = int(callback.data.split("_")[3])
    rent_item = await get_nft_rent_by_id(rent_id)

    if not rent_item or int(rent_item.get("telegram_id", 0)) != callback.from_user.id:
        await callback.answer("Ijara topilmadi", show_alert=True)
        return

    name = rent_item.get("nft_name", "NFT")
    text = (
        f"⏳ <b>{name} — Ijara muddatini uzaytirish</b>\n\n"
        "Qancha kunga uzaytirmoqchisiz? Tanlang 👇"
    )

    builder = InlineKeyboardBuilder()
    for d in [3, 7, 14, 30]:
        _, tot_uzs = marketapp_service.calculate_price_uzs(0.02, d)
        builder.row(InlineKeyboardButton(
            text=f"🗓 +{d} kun (~{tot_uzs:,} so'm)",
            callback_data=f"rent_ext_do_{rent_id}_{d}"
        ))

    builder.row(InlineKeyboardButton(text="◀️ Orqaga", callback_data="rent_my_list"))
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")


@router.callback_query(F.data.startswith("rent_ext_do_"))
async def callback_execute_extension(callback: CallbackQuery):
    """Execute NFT rental extension via extend_rent_nft()."""
    await callback.answer("Uzaytirilmoqda...", show_alert=False)
    parts = callback.data.split("_")
    rent_id = int(parts[3])
    extra_days = int(parts[4])
    user_id = callback.from_user.id

    res = await marketapp_service.execute_nft_extension(
        user_id=user_id,
        rent_id=rent_id,
        extra_days=extra_days,
        price_per_day_ton="0.02"
    )

    if res.get("ok"):
        msg = res.get("message", "Ijara muvaffaqiyatli uzaytirildi!")
        await callback.message.answer(f"✅ {msg}")
    else:
        err = res.get("error", "Xatolik yuz berdi")
        await callback.message.answer(f"❌ {err}")

    # Return to my rents list
    await show_my_rentals(callback)


# === 7. ADMIN COMMANDS (/nft_orders, /nft_margin, /nft_wallet) ===

@router.message(Command("nft_orders"))
async def admin_nft_orders(message: Message):
    """Admin command: view recent NFT rental orders."""
    user_id = message.from_user.id if message.from_user else 0
    if not _is_admin(user_id):
        await message.answer("❌ Bu buyruq faqat administratorlar uchun.")
        return

    orders = await marketapp_service.get_recent_nft_orders(limit=10)
    if not orders:
        await message.answer("📦 Hozircha hech qanday NFT ijara buyurtmasi mavjud emas.")
        return

    text = "📦 <b>Oxirgi NFT Ijara Buyurtmalari:</b>\n\n"
    for o in orders:
        o_id = o.get("id")
        uid = o.get("telegram_id")
        uname = o.get("target_username") or "?"
        days = o.get("quantity") or 1
        amt = o.get("amount") or 0
        status = o.get("status") or "pending"
        tx = o.get("external_id") or "—"
        tx_short = tx[:16] + "..." if len(str(tx)) > 16 else tx
        created = str(o.get("created_at") or "")[:19]

        st_icon = "🟢" if status == "completed" else ("🔴" if status == "failed" else "🟡")

        text += (
            f"<b>#{o_id}</b> | <code>{uid}</code> (@{uname}) {st_icon}\n"
            f"⏱ {days} kun | 💰 {amt:,} so'm | {status}\n"
            f"🔗 <code>{tx_short}</code>\n"
            f"⏰ {created}\n"
            "───────────────\n"
        )

    await message.answer(text, parse_mode="HTML")


@router.message(Command("nft_margin"))
async def admin_nft_margin(message: Message):
    """Admin command: view or set profit margin percentage (/nft_margin <percent>)."""
    user_id = message.from_user.id if message.from_user else 0
    if not _is_admin(user_id):
        await message.answer("❌ Bu buyruq faqat administratorlar uchun.")
        return

    args = message.text.split()
    if len(args) < 2:
        cur = marketapp_service.margin_percent
        await message.answer(
            f"📊 <b>Joriy NFT Ijara Ustamasi:</b> <code>{cur}%</code>\n\n"
            "O'zgartirish uchun: <code>/nft_margin &lt;foiz&gt;</code>\n"
            "Masalan: <code>/nft_margin 7</code>",
            parse_mode="HTML"
        )
        return

    try:
        new_margin = float(args[1].replace(",", "."))
        if new_margin < 0 or new_margin > 100:
            await message.answer("❌ Foiz 0 dan 100 gacha bo'lishi kerak.")
            return

        marketapp_service.set_margin_percent(new_margin)
        await message.answer(
            f"✅ <b>NFT ijara ustamasi muvaffaqiyatli o'zgartirildi!</b>\n\n"
            f"Yangi ustama foizi: <b>{new_margin}%</b>",
            parse_mode="HTML"
        )
    except ValueError:
        await message.answer("❌ Noto'g'ri son formati. Masalan: <code>/nft_margin 5</code>", parse_mode="HTML")


@router.message(Command("nft_wallet"))
async def admin_nft_wallet(message: Message):
    """Admin command: inspect TON wallet address, balance, and health."""
    user_id = message.from_user.id if message.from_user else 0
    if not _is_admin(user_id):
        await message.answer("❌ Bu buyruq faqat administratorlar uchun.")
        return

    msg = await message.answer("🔍 TON hamyon tekshirilmoqda...", parse_mode="HTML")
    info = await marketapp_service.get_wallet_info()

    addr = info.get("address", "—")
    bal = info.get("balance_ton", 0.0)
    healthy = info.get("healthy", False)
    dry = marketapp_service.is_dry_run()

    text = (
        "👛 <b>Bot TON Hamyon Holati (V5R1):</b>\n\n"
        f"🏷 <b>Manzil:</b> <code>{addr}</code>\n"
        f"💰 <b>Balans:</b> <code>{bal:.4f} TON</code>\n"
        f"🟢 <b>Holat:</b> {'Faol va yetarli' if healthy else 'Yetarli emas ⚠️'}\n"
        f"🧪 <b>DRY_RUN Rejimi:</b> {'Yoniq (Test)' if dry else 'Ochiq (Haqiqiy to\'lov)'}\n"
    )

    await msg.edit_text(text, parse_mode="HTML")
