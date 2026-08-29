import asyncio
import logging
import time

from aiogram import F, Bot, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import config
import keyboards
import keyboards.admin as admin_kb
from services.database import (
    add_balance, add_balance_history, deduct_balance, db,
    get_all_users_telegram_ids, get_dashboard_stats, get_order_by_id,
    get_orders_paginated, get_users_paginated, search_users_db,
    block_user_db, unblock_user_db, delete_user_db,
    update_order_status, record_payment, get_pool,
    get_user, reset_balance,
)

logger = logging.getLogger(__name__)
router = Router()


class AdminStates(StatesGroup):
    broadcast_text = State()
    search_query = State()
    settings_key = State()
    settings_value = State()
    check_sp_id = State()
    check_amount = State()
    check_reason = State()
    stars_sp_id = State()
    stars_amount = State()
    stars_reason = State()
    sub_channel_input = State()
    admin_add_input = State()
    balance_sp_id = State()
    balance_amount = State()
    balance_reset_sp_id = State()
    giveaway_title = State()
    giveaway_desc = State()
    giveaway_winners = State()
    giveaway_channel = State()


ADMIN_IDS = list(config.ADMINS)

_runtime_settings = {
    "stars_price_per_unit": 200,
    "min_topup_amount": 1000,
    "max_topup_amount": 100_000_000,
    "referral_bonus": 300,
    "gift_enabled": True,
    "stars_enabled": True,
    "maintenance_mode": False,
    "ref_contest_enabled": True,
    "ref_contest_prize": 500,
    "ref_contest_min_refs": 5,
    "required_channels": [],
    "autopay_enabled": False,
}

SETTINGS_LABELS = {
    "stars_price_per_unit": "⭐ Stars narxi (so'm/1 star)",
    "min_topup_amount": "💳 Min. to'ldirish (so'm)",
    "max_topup_amount": "💳 Maks. to'ldirish (so'm)",
    "referral_bonus": "👥 Referal bonusi (so'm)",
    "gift_enabled": "🎁 Sovg'alar (true/false)",
    "stars_enabled": "⭐ Stars xizmati (true/false)",
    "maintenance_mode": "🔧 Texnik ishlar rejimi (true/false)",
}


def _is_admin(user_id: int) -> bool:
    import os
    env_admins = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "8202423244").split(",") if x.strip().isdigit()]
    return user_id in config.ADMINS or user_id in ADMIN_IDS or user_id in env_admins or user_id in [8202423244, 6552579124, 762282299]


async def _deny(message: Message):
    uid = message.from_user.id if message.from_user else 0
    await message.answer(
        f"❌ <b>Bu buyruq faqat administratorlar uchun.</b>\n\n"
        f"🆔 <b>Sizning Telegram ID ingiz:</b> <code>{uid}</code>\n"
        f"📌 Admin paneldan foydalanish uchun server <code>ADMIN_IDS</code> sozlamasiga shu ID ni kiriting yoki admin bilan bog'laning: @cofeature",
        parse_mode="HTML"
    )


async def _get_ping(bot: Bot) -> int:
    start = time.monotonic()
    await bot.get_me()
    return int((time.monotonic() - start) * 1000)


async def _admin_header(bot: Bot) -> str:
    ping = await _get_ping(bot)
    return (
        "⚙️ <b>Admin panel</b>\n\n"
        f"💡 PING: {ping} MS\n\n"
        "Siz administrator huquqiga egasiz.\n"
        "Iltimos, ehtiyotkorlik bilan ishlang."
    )


async def _go_main(callback_or_msg, state: FSMContext = None):
    if state:
        await state.clear()
    if isinstance(callback_or_msg, CallbackQuery):
        header = await _admin_header(callback_or_msg.bot)
        await callback_or_msg.message.edit_text(header, reply_markup=admin_kb.admin_main_keyboard())
    else:
        header = await _admin_header(callback_or_msg.bot)
        await callback_or_msg.answer(header, reply_markup=admin_kb.admin_main_keyboard())


@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext = None):
    if not message.from_user:
        return
    if not _is_admin(message.from_user.id):
        await _deny(message)
        return
    if state:
        await state.clear()
    header = await _admin_header(message.bot)
    await message.answer(header, reply_markup=admin_kb.admin_main_keyboard())


@router.callback_query(F.data == "admin_main_menu")
async def admin_main_menu_cb(callback: CallbackQuery, state: FSMContext = None):
    await callback.answer()
    await _go_main(callback, state)


@router.message(Command("confirm"))
async def cmd_confirm(message: Message):
    if not message.from_user:
        return
    if not _is_admin(message.from_user.id):
        await _deny(message)
        return
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("❌ Buyurtma ID sini kiriting:\n\n<code>/confirm topup_abc123</code>")
        return
    order_id = args[1].strip()
    await message.answer(f"⏳ Tekshirilmoqda: <code>{order_id}</code>...")
    from services.payment_client import confirm_payment
    result = await confirm_payment(order_id)
    if result.get("ok"):
        await message.answer(
            f"✅ <b>To'lov tasdiqlandi!</b>\n\n"
            f"📦 Buyurtma: <code>{order_id}</code>\n"
            f"💰 Summa: {result.get('amount', 0):,} so'm\n"
            f"💳 Yangi balans: {result.get('new_balance', 0):,} so'm",
        )
    elif "PAYMENT_SERVER_URL not configured" in result.get("error", ""):
        await _confirm_locally(message, order_id)
    else:
        err_msg = result.get('error', "Noma'lum xatolik")
        await message.answer(f"❌ Xatolik: {err_msg}")


# ═══════════════════════════════════════════
# PROMO-KOD YARATISH VA BOSHQARISH
# ═══════════════════════════════════════════

@router.message(Command("addpromo", "promo"))
@router.message(F.text.startswith("/addpromo") | F.text.startswith("/promo"))
async def cmd_add_promocode(message: Message):
    if not message.from_user:
        return
    if not _is_admin(message.from_user.id):
        await _deny(message)
        return

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer(
            "🎟 <b>Yangi Promo-kod yaratish:</b>\n\n"
            "Buyruqdan so'ng promo-kod nomini yozing:\n"
            "👉 <code>/addpromo OMAD2026</code>\n"
            "👉 <code>/promo BEAR777</code>\n"
            "👉 <code>/promo TEKIN</code>\n\n"
            "<i>Kod faqat 1 martalik ishlaydi va Omad G'ildiragida 1 ta bepul spin beradi.</i>",
            parse_mode="HTML"
        )
        return

    raw_code = parts[1].strip().upper()
    from services.database import create_promocode
    ok = await create_promocode(raw_code)
    if ok:
        await message.answer(
            f"✅ <b>Yangi Promo-kod muvaffaqiyatli yaratildi!</b>\n\n"
            f"🎟 <b>Kod:</b> <code>{raw_code}</code>\n"
            f"📌 <b>Holati:</b> Faol (1 martalik)\n"
            f"🎁 <b>Yutuq:</b> 15⭐ yoki 25⭐ Telegram Gift\n\n"
            f"<i>Foydalanuvchi ushbu kodni WebApp'dagi Omad G'ildiragiga kiritib ishlatishi mumkin!</i>",
            parse_mode="HTML"
        )
    else:
        await message.answer(f"❌ Xatolik: <code>{raw_code}</code> kodini bazaga saqlab bo'lmadi!", parse_mode="HTML")


@router.message(Command("promolist", "promolar", "promos"))
@router.message(F.text.in_({"/promolist", "/promolar", "/promos"}))
async def cmd_list_promocodes(message: Message):
    if not message.from_user or not _is_admin(message.from_user.id):
        await _deny(message)
        return

    from services.database import get_all_promocodes
    promos = await get_all_promocodes(limit=30)
    if not promos:
        await message.answer("ℹ️ Hozircha bazada promo-kodlar mavjud emas.")
        return

    lines = ["🎟 <b>So'nggi Promo-kodlar ro'yxati:</b>\n"]
    for p in promos:
        code = p.get("code")
        is_used = bool(p.get("is_used"))
        if is_used:
            user_name = p.get("used_by_username") or p.get("used_by_name") or str(p.get("used_by_id"))
            lines.append(f"❌ <code>{code}</code> — Ishlatilgan (@{user_name})")
        else:
            lines.append(f"✅ <code>{code}</code> — <b>Faol (1 martalik)</b>")

    lines.append("\n👉 Yangi kod qo'shish: <code>/addpromo KOD</code>")
    lines.append("👉 Kodni o'chirish: <code>/delpromo KOD</code>")

    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("delpromo"))
@router.message(F.text.startswith("/delpromo"))
async def cmd_del_promocode(message: Message):
    if not message.from_user or not _is_admin(message.from_user.id):
        await _deny(message)
        return

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer("❌ O'chirish uchun kodni kiriting:\nMasalan: <code>/delpromo CS-7711</code>", parse_mode="HTML")
        return

    code_to_del = parts[1].strip().upper()
    from services.database import delete_promocode
    ok = await delete_promocode(code_to_del)
    if ok:
        await message.answer(f"🗑 <code>{code_to_del}</code> promo-kodi muvaffaqiyatli o'chirildi!", parse_mode="HTML")
    else:
        await message.answer(f"❌ Xatolik yuz berdi!", parse_mode="HTML")


# ═══════════════════════════════════════════
# 1. STATISTIKA
# ═══════════════════════════════════════════

@router.callback_query(F.data == "admin_stats")
async def admin_stats_cb(callback: CallbackQuery):
    await callback.answer("⏳ Yuklanmoqda...")
    try:
        stats = await get_dashboard_stats()
        pool = await get_pool()
        async with pool.acquire() as conn:
            payments_count = await conn.fetchval("SELECT COUNT(*) FROM payments") or 0
            total_profit = await conn.fetchval(
                "SELECT COALESCE(SUM(amount), 0) FROM payments WHERE status = 'paid'"
            ) or 0
        text = (
            f"📊 <b>Statistika</b>\n\n"
            f"👥 <b>Jami foydalanuvchilar:</b> {stats['total_users']:,}\n"
            f"📅 Bugun: {stats['new_today']:,}\n"
            f"📅 Oxirgi 7 kun: {stats['new_week']:,}\n\n"
            f"💳 <b>To'lovlar soni:</b> {payments_count:,}\n"
            f"💰 <b>Umumiy daromad:</b> {total_profit:,} so'm"
        )
    except Exception as e:
        logger.error(f"Stats error: {e}")
        text = "❌ Statistikani yuklashda xatolik."
    await callback.message.edit_text(text, reply_markup=admin_kb.stats_keyboard())


# ═══════════════════════════════════════════
# 2. FOYDALANUVCHILAR
# ═══════════════════════════════════════════

@router.callback_query(F.data == "admin_users")
async def admin_users_menu_cb(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        "🔴 <b>Foydalanuvchilar</b>\n\nAmalni tanlang:",
        reply_markup=admin_kb.users_main_keyboard(),
    )


@router.callback_query(F.data.startswith("admin_users_list_"))
async def admin_users_list_cb(callback: CallbackQuery):
    await callback.answer()
    data = callback.data
    if data == "admin_users_list_skip":
        return
    page = int(data.split("_")[-1])
    try:
        users, total = await get_users_paginated(page=page, page_size=10)
        text = f"👥 <b>Foydalanuvchilar</b> (jami: {total:,})\n\n"
        for u in users:
            name = u.get("username") or u.get("full_name") or "—"
            blocked = " 🔒" if u.get("is_blocked") else ""
            text += f"• <code>{u['sp_id']}</code> <b>{name}</b>{blocked}\n  Balans: {u['balance']:,} so'm\n"
    except Exception as e:
        logger.error(f"Users list error: {e}")
        text = "❌ Xatolik."
    await callback.message.edit_text(text, reply_markup=admin_kb.users_list_keyboard(page, total > page * 10))


@router.callback_query(F.data == "admin_users_search")
async def admin_users_search_start_cb(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.edit_text(
        "🔍 <b>Foydalanuvchini qidirish</b>\n\nTelegram ID, username yoki SP ID ni kiriting:"
    )
    await state.set_state(AdminStates.search_query)


@router.message(AdminStates.search_query)
async def admin_users_search_result_msg(message: Message, state: FSMContext):
    query = message.text.strip()
    try:
        users = await search_users_db(query)
        if not users:
            await message.answer("❌ Foydalanuvchi topilmadi.")
        else:
            for u in users[:5]:
                name = u.get("username") or u.get("full_name") or "—"
                blocked = " 🔒" if u.get("is_blocked") else ""
                text = (
                    f"👤 <b>#{u['sp_id']}</b>{blocked}\n"
                    f"Telegram ID: <code>{u['telegram_id']}</code>\n"
                    f"Ism: {name}\n"
                    f"Balans: <b>{u['balance']:,}</b> so'm\n"
                    f"Referallar: {u.get('referrals', 0)}"
                )
                await message.answer(text, reply_markup=admin_kb.user_actions_keyboard(u['telegram_id']))
    except Exception as e:
        logger.error(f"Search error: {e}")
        await message.answer("❌ Xatolik.")
    await state.clear()
    await _go_main(message)


@router.callback_query(F.data.startswith("admin_user_block_"))
async def admin_user_block_cb(callback: CallbackQuery):
    await callback.answer()
    tid = int(callback.data.split("_")[-1])
    try:
        await block_user_db(tid)
        await callback.message.edit_text(f"✅ Foydalanuvchi <code>{tid}</code> bloklandi.")
    except Exception as e:
        await callback.message.edit_text(f"❌ Xatolik: {e}")


@router.callback_query(F.data.startswith("admin_user_unblock_"))
async def admin_user_unblock_cb(callback: CallbackQuery):
    await callback.answer()
    tid = int(callback.data.split("_")[-1])
    try:
        await unblock_user_db(tid)
        await callback.message.edit_text(f"✅ Foydalanuvchi <code>{tid}</code> blokdan chiqarildi.")
    except Exception as e:
        await callback.message.edit_text(f"❌ Xatolik: {e}")


@router.callback_query(F.data.startswith("admin_user_delete_"))
async def admin_user_delete_cb(callback: CallbackQuery):
    await callback.answer()
    tid = int(callback.data.split("_")[-1])
    try:
        await delete_user_db(tid)
        await callback.message.edit_text(f"🗑 Foydalanuvchi <code>{tid}</code> o'chirildi.")
    except Exception as e:
        await callback.message.edit_text(f"❌ Xatolik: {e}")


# ═══════════════════════════════════════════
# 3. XABAR YUBORISH
# ═══════════════════════════════════════════

@router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast_start_cb(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.edit_text(
        "📨 <b>Xabar yuborish</b>\n\n"
        "Barcha foydalanuvchilarga yubormoqchi bo'lgan xabaringizni yuboring\n"
        "(matn, rasm, video — istalgan format):"
    )
    await state.set_state(AdminStates.broadcast_text)


@router.message(AdminStates.broadcast_text)
async def admin_broadcast_preview_msg(message: Message, state: FSMContext):
    await state.update_data(broadcast_msg_id=message.message_id, broadcast_chat_id=message.chat.id)
    await message.bot.copy_message(
        chat_id=message.chat.id, from_chat_id=message.chat.id, message_id=message.message_id,
    )
    await message.answer("📨 <b>Ushbu xabarni yuborish?</b>", reply_markup=admin_kb.broadcast_confirm_keyboard())


@router.callback_query(F.data == "admin_broadcast_confirm")
async def admin_broadcast_confirm_cb(callback: CallbackQuery, state: FSMContext):
    await callback.answer("⏳ Yuborilmoqda...")
    data = await state.get_data()
    msg_id, chat_id = data.get("broadcast_msg_id"), data.get("broadcast_chat_id")
    if not msg_id or not chat_id:
        await callback.message.edit_text("❌ Xabar topilmadi.")
        return
    await callback.message.edit_text("⏳ Xabar yuborilmoqda...")
    try:
        tgs = await get_all_users_telegram_ids()
        sent = 0
        for tid in tgs:
            try:
                await callback.bot.copy_message(chat_id=tid, from_chat_id=chat_id, message_id=msg_id)
                sent += 1
            except Exception as exc:
                logger.warning(f"Broadcast failed to {tid}: {exc}")
            await asyncio.sleep(0.05)
        await callback.message.answer(f"✅ Xabar yuborildi. Yuborilgan: {sent}/{len(tgs)}")
    except Exception as e:
        await callback.message.answer(f"❌ Xatolik: {e}")
    await state.clear()
    await _go_main(callback.message)


@router.callback_query(F.data == "admin_broadcast_cancel")
async def admin_broadcast_cancel_cb(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await callback.message.edit_text("❌ Xabar yuborish bekor qilindi.")
    await _go_main(callback.message)


# ═══════════════════════════════════════════
# 4. SOZLAMALAR
# ═══════════════════════════════════════════

def _settings_text() -> str:
    lines = ["⚙️ <b>Sozlamalar</b>\n"]
    for key, label in SETTINGS_LABELS.items():
        val = _runtime_settings.get(key)
        lines.append(f"• {label}\n  <code>{key}</code> = <b>{val}</b>")
    lines.append("\n✏️ O'zgartirish uchun pastdagi parametrni bosing:")
    return "\n".join(lines)


def _settings_keyboard():
    from aiogram.types import InlineKeyboardButton
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    for key in SETTINGS_LABELS:
        builder.row(InlineKeyboardButton(text=f"✏️ {SETTINGS_LABELS[key].split('(')[0].strip()}", callback_data=f"admin_set_{key}"))
    builder.row(InlineKeyboardButton(text="⬅️ Orqaga", callback_data="admin_main_menu"))
    return builder.as_markup()


@router.callback_query(F.data == "admin_settings")
async def admin_settings_menu_cb(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(_settings_text(), reply_markup=_settings_keyboard())


@router.callback_query(F.data.startswith("admin_set_"))
async def admin_set_key_cb(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    key = callback.data[len("admin_set_"):]
    if key not in _runtime_settings:
        await callback.answer("❌ Noma'lum parametr", show_alert=True)
        return
    current = _runtime_settings[key]
    label = SETTINGS_LABELS.get(key, key)
    await callback.message.edit_text(
        f"✏️ <b>{label}</b>\n\n"
        f"Hozirgi qiymat: <code>{current}</code>\n\n"
        f"Yangi qiymatni kiriting:\n<i>(son yoki true/false)</i>"
    )
    await state.update_data(settings_key=key)
    await state.set_state(AdminStates.settings_value)


@router.message(AdminStates.settings_value)
async def admin_set_value_msg(message: Message, state: FSMContext):
    data = await state.get_data()
    key = data.get("settings_key")
    raw = (message.text or "").strip()
    if key not in _runtime_settings:
        await message.answer("❌ Xatolik. /admin ni bosing")
        await state.clear()
        return
    current = _runtime_settings[key]
    try:
        if isinstance(current, bool):
            if raw.lower() in ("true", "1", "ha", "yes"):
                new_val = True
            elif raw.lower() in ("false", "0", "yo'q", "no"):
                new_val = False
            else:
                raise ValueError("true yoki false bo'lishi kerak")
        elif isinstance(current, int):
            new_val = int(raw.replace(",", "").replace(" ", ""))
        elif isinstance(current, float):
            new_val = float(raw)
        else:
            new_val = raw
    except ValueError as e:
        await message.answer(f"❌ Noto'g'ri qiymat: {e}\nQayta urinib ko'ring:")
        return
    _runtime_settings[key] = new_val
    logger.info(f"Admin {message.from_user.id} changed {key}: {current} → {new_val}")
    await message.answer(
        f"✅ <b>Sozlama yangilandi</b>\n\n{label}\nEski: <code>{current}</code>\nYangi: <b><code>{new_val}</code></b>",
    )
    await state.clear()
    await message.answer(_settings_text(), reply_markup=_settings_keyboard())


def get_setting(key: str):
    return _runtime_settings.get(key)


# ═══════════════════════════════════════════
# 5. CHEK YARATISH
# ═══════════════════════════════════════════

@router.callback_query(F.data == "admin_create_check")
async def admin_create_check_cb(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.edit_text(
        "⚡ <b>Chek yaratish</b>\n\n"
        "Foydalanuvchi SP ID sini kiriting:"
    )
    await state.set_state(AdminStates.check_sp_id)


@router.message(AdminStates.check_sp_id)
async def admin_check_sp_id_msg(message: Message, state: FSMContext):
    text = message.text.strip()
    if not text.isdigit():
        await message.answer("❌ SP ID raqam bo'lishi kerak. Qayta kiriting yoki /admin ni bosing.")
        return
    sp_id = int(text)
    user = await db.get_user_by_sp_id(sp_id)
    if not user:
        await message.answer(f"❌ SP ID <code>{sp_id}</code> bo'yicha foydalanuvchi topilmadi.")
        return
    await state.update_data(check_sp_id=sp_id, check_user_tid=user["telegram_id"])
    await message.answer(
        f"👤 <b>Foydalanuvchi #{sp_id}</b>\n"
        f"Balans: <b>{user['balance']:,}</b> so'm\n\n"
        f"Chek summasini kiriting (so'mda):"
    )
    await state.set_state(AdminStates.check_amount)


@router.message(AdminStates.check_amount)
async def admin_check_amount_msg(message: Message, state: FSMContext):
    try:
        amount = int(message.text.strip().replace(",", "").replace(" ", ""))
    except ValueError:
        await message.answer("❌ Noto'g'ri summa. Raqam kiriting.")
        return
    if amount <= 0:
        await message.answer("❌ Summa 0 dan katta bo'lishi kerak.")
        return
    await state.update_data(check_amount=amount)
    data = await state.get_data()
    sp_id = data["check_sp_id"]
    await message.answer(
        f"⚡ <b>Chek ma'lumotlari</b>\n\n"
        f"Foydalanuvchi: #{sp_id}\n"
        f"Summa: {amount:,} so'm\n\n"
        f"Tasdiqlaysizmi?",
        reply_markup=admin_kb.check_confirm_keyboard(sp_id, amount),
    )


@router.callback_query(F.data.startswith("admin_check_confirm_"))
async def admin_check_confirm_cb(callback: CallbackQuery, state: FSMContext):
    await callback.answer("⏳ Chek yaratilmoqda...")
    parts = callback.data.split("_")
    sp_id = int(parts[3])
    amount = int(parts[4])
    user = await db.get_user_by_sp_id(sp_id)
    if not user:
        await callback.message.edit_text("❌ Foydalanuvchi topilmadi.")
        return
    tid = user["telegram_id"]
    new_balance = await add_balance(tid, amount)
    await record_payment(f"check_{sp_id}_{int(time.time())}", tid, amount, "paid",
                          f'{{"source": "chek", "admin_id": {callback.from_user.id}}}')
    await _notify_balance_add(callback.bot, tid, amount, new_balance)
    username = user.get("username") or str(tid)
    await callback.message.edit_text(
        f"✅ <b>Chek yaratildi!</b>\n\n"
        f"👤 Foydalanuvchi: #{sp_id} (@{username})\n"
        f"💰 Summa: {amount:,} so'm\n"
        f"💳 Yangi balans: {new_balance:,} so'm\n\n"
        f"✅ Balans to'ldirildi."
    )
    await _go_main(callback.message)


# ═══════════════════════════════════════════
# 6. REFERAL KONKURS
# ═══════════════════════════════════════════

@router.callback_query(F.data == "admin_ref_contest")
async def admin_ref_contest_cb(callback: CallbackQuery):
    await callback.answer()
    enabled = _runtime_settings.get("ref_contest_enabled", False)
    status = "✅ Yoqilgan" if enabled else "❌ O'chirilgan"
    prize = _runtime_settings.get("ref_contest_prize", 500)
    min_refs = _runtime_settings.get("ref_contest_min_refs", 5)
    await callback.message.edit_text(
        f"📢 <b>Referal konkurs</b>\n\n"
        f"Holati: {status}\n"
        f"Sovrin: {prize:,} so'm\n"
        f"Min. referallar: {min_refs} ta\n\n"
        f"🏆 Eng yaxshi referallarni ko'rish uchun pastdagi tugmani bosing.",
        reply_markup=admin_kb.ref_contest_keyboard(),
    )


@router.callback_query(F.data == "admin_ref_rating")
async def admin_ref_rating_cb(callback: CallbackQuery):
    await callback.answer("⏳ Yuklanmoqda...")
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT telegram_id, username, full_name, referrals FROM users ORDER BY referrals DESC LIMIT 10"
            )
        if not rows:
            text = "🏆 <b>Top referallar</b>\n\nHozircha hech kim yo'q."
        else:
            text = "🏆 <b>Top 10 referallar</b>\n\n"
            for i, r in enumerate(rows, 1):
                name = r["username"] or r["full_name"] or f"#{r['telegram_id']}"
                text += f"{i}. <b>{name}</b> — {r['referrals']} ta\n"
        await callback.message.edit_text(text, reply_markup=admin_kb.back_button("admin_ref_contest"))
    except Exception as e:
        logger.error(f"Ref rating error: {e}")
        await callback.message.edit_text("❌ Xatolik.", reply_markup=admin_kb.back_button("admin_ref_contest"))


@router.callback_query(F.data == "admin_ref_settings")
async def admin_ref_settings_cb(callback: CallbackQuery):
    await callback.answer()
    enabled = _runtime_settings.get("ref_contest_enabled", False)
    prize = _runtime_settings.get("ref_contest_prize", 500)
    min_refs = _runtime_settings.get("ref_contest_min_refs", 5)
    status = "✅ Yoqilgan" if enabled else "❌ O'chirilgan"
    text = (
        f"⚙️ <b>Konkurs sozlamalari</b>\n\n"
        f"Holati: {status}\n"
        f"Sovrin: {prize:,} so'm\n"
        f"Min. referallar: {min_refs} ta\n\n"
        f"Sozlamalarni o'zgartirish uchun <b>Sozlamalar</b> bo'limiga o'ting:\n"
        f"<code>ref_contest_enabled</code> — yoqish/o'chirish\n"
        f"<code>ref_contest_prize</code> — sovrin miqdori\n"
        f"<code>ref_contest_min_refs</code> — minimal referallar soni"
    )
    await callback.message.edit_text(text, reply_markup=admin_kb.back_button("admin_ref_contest"))


@router.callback_query(F.data == "admin_create_giveaway")
async def admin_create_giveaway_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.answer(
        "📢 <b>Yangi Konkurs yaratish</b>\n\n"
        "Konkurs sarlavhasi / Sovg'a nomini kiriting:\n"
        "<i>(Masalan: 🎉 50,000 SO'M VA VIP SOVG'ALAR KONKURSI!)</i>"
    )
    await state.set_state(AdminStates.giveaway_title)


@router.message(AdminStates.giveaway_title)
async def process_giveaway_title(message: Message, state: FSMContext):
    title = message.text.strip()
    await state.update_data(giveaway_title=title)
    await message.answer(
        "📝 Endi konkurs tavsifi va sovg'alar haqida batafsil ma'lumot kiriting:\n"
        "<i>(Masalan: 1-o'rin: 30,000 so'm, 2-o'rin: 15,000 so'm, 3-o'rin: 5,000 so'm!)</i>"
    )
    await state.set_state(AdminStates.giveaway_desc)


@router.message(AdminStates.giveaway_desc)
async def process_giveaway_desc(message: Message, state: FSMContext):
    desc = message.text.strip()
    await state.update_data(giveaway_desc=desc)
    await message.answer(
        "🎲 G'oliblarning sonini kiriting (raqamda):\n"
        "<i>(Masalan: 1 yoki 3)</i>"
    )
    await state.set_state(AdminStates.giveaway_winners)


@router.message(AdminStates.giveaway_winners)
async def process_giveaway_winners(message: Message, state: FSMContext):
    if not message.text.isdigit() or int(message.text) <= 0:
        await message.answer("❌ Iltimos, to'g'ri son kiriting (masalan: 1 yoki 3):")
        return
    winners_cnt = int(message.text)
    await state.update_data(giveaway_winners=winners_cnt)
    
    await message.answer(
        "📢 Majburiy a'zolik kanalini kiriting:\n"
        "<i>(Masalan: @CoinStatUz yoki @coinstatuz_org)</i>"
    )
    await state.set_state(AdminStates.giveaway_channel)


@router.message(AdminStates.giveaway_channel)
async def process_giveaway_channel(message: Message, state: FSMContext):
    channel = message.text.strip()
    if not channel.startswith("@"):
        channel = f"@{channel}"

    data = await state.get_data()
    title = data.get("giveaway_title")
    desc = data.get("giveaway_desc")
    winners_cnt = data.get("giveaway_winners", 1)

    from services.database import create_giveaway
    gw_id = await create_giveaway(title, desc, winners_cnt, channel)

    await state.clear()

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📢 Kanalga joylash", callback_data=f"admin_post_giveaway_{gw_id}"),
        InlineKeyboardButton(text="🤖 Botda qoldirish", callback_data="admin_ref_contest")
    )

    await message.answer(
        f"✅ <b>Konkurs muvaffaqiyatli yaratildi! (ID: #{gw_id})</b>\n\n"
        f"<b>Sarlavha:</b> {title}\n"
        f"<b>Tavsif:</b> {desc}\n"
        f"<b>G'oliblar soni:</b> {winners_cnt} ta\n"
        f"<b>Kanal:</b> {channel}\n\n"
        f"Ushbu konkursni rasmiy kanalga e'lon qilaymi?",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("admin_post_giveaway_"))
async def admin_post_giveaway_to_channel(callback: CallbackQuery):
    gw_id = int(callback.data.split("_")[-1])
    from services.database import get_giveaway_by_id
    gw = await get_giveaway_by_id(gw_id)
    if not gw:
        await callback.answer("❌ Konkurs topilmadi!", show_alert=True)
        return

    channel = gw.get("required_channel", "@CoinStatUz")

    post_text = (
        f"🎁 <b>YANGI KONKURS / GIVEAWAY!</b> 🎁\n\n"
        f"🏆 <b>{gw['title']}</b>\n\n"
        f"📝 <b>Shartlar va Sovg'alar:</b>\n"
        f"{gw['description']}\n\n"
        f"👥 G'oliblar soni: <b>{gw['winners_count']} ta</b>\n"
        f"📢 Majburiy kanal: <b>{channel}</b>\n\n"
        f"👇 Qatnashish uchun pastdagi <b>🎉 Qatnashish</b> tugmasini bosing!"
    )

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🎉 Qatnashish", callback_data=f"join_giveaway_{gw_id}"),
    )

    try:
        await callback.bot.send_message(
            chat_id=channel,
            text=post_text,
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
        await callback.answer("✅ Kanalga e'lon qilindi!", show_alert=True)
        await callback.message.edit_text(
            f"✅ <b>Konkurs {channel} kanaliga muvaffaqiyatli e'lon qilindi!</b>",
            reply_markup=admin_kb.back_button("admin_ref_contest")
        )
    except Exception as e:
        logger.error(f"Error posting giveaway to channel: {e}")
        await callback.answer(f"❌ Kanalga yuborishda xatolik! Bot {channel} kanalida admin ekanligiga ishonch hosil qiling.", show_alert=True)


@router.callback_query(F.data == "admin_finish_giveaway")
async def admin_finish_giveaway_cb(callback: CallbackQuery):
    await callback.answer("⏳ G'oliblar aniqlanmoqda...")
    from services.database import get_latest_active_giveaway, finish_giveaway_and_pick_winners, get_participants_count
    
    gw = await get_latest_active_giveaway()
    if not gw:
        await callback.message.edit_text("ℹ️ Hozirda faol konkurs yo'q.", reply_markup=admin_kb.back_button("admin_ref_contest"))
        return

    gw_id = gw["id"]
    part_cnt = await get_participants_count(gw_id)
    winners = await finish_giveaway_and_pick_winners(gw_id)

    if not winners:
        await callback.message.edit_text(
            f"❌ Konkurs yakunlandi, lekin ishtirokchilar topilmadi (Ishtirokchilar soni: {part_cnt}).",
            reply_markup=admin_kb.back_button("admin_ref_contest")
        )
        return

    winners_text = ""
    for i, w in enumerate(winners, 1):
        name = w["username"] or w["full_name"] or f"ID: {w['telegram_id']}"
        display_name = f"@{name}" if not name.startswith("@") and not name.startswith("ID:") else name
        winners_text += f"{i}. 🏆 <b>{display_name}</b> (<code>{w['telegram_id']}</code>)\n"

        try:
            await callback.bot.send_message(
                chat_id=w["telegram_id"],
                text=f"🎉 <b>TABRIKLAYMIZ!</b>\n\nSiz <b>{gw['title']}</b> konkursida g'olib bo'ldingiz! 🏆\nSovrinni olish uchun admin bilan bog'laning: @cofeature",
                parse_mode="HTML"
            )
        except Exception:
            pass

    channel = gw.get("required_channel", "@CoinStatUz")
    announce_text = (
        f"🏆 <b>KONKURS YAKUNLANDI VA G'OLIBLAR ANIQLANDI!</b> 🏆\n\n"
        f"📌 Konkurs: <b>{gw['title']}</b>\n"
        f"👥 Jami ishtirokchilar: <b>{part_cnt} ta</b>\n\n"
        f"🎉 <b>G'OLIBLAR:</b>\n"
        f"{winners_text}\n"
        f"Barcha g'oliblarni tabriklaymiz! Sovrinlar uchun admin @cofeature ga yozing."
    )

    try:
        await callback.bot.send_message(chat_id=channel, text=announce_text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Error posting winners to channel: {e}")

    await callback.message.edit_text(
        f"🎉 <b>G'oliblar omadli ravishda aniqlandi!</b>\n\n{winners_text}",
        reply_markup=admin_kb.back_button("admin_ref_contest"),
        parse_mode="HTML"
    )


# ═══════════════════════════════════════════
# 7. MAJBURIY OBUNA
# ═══════════════════════════════════════════

@router.callback_query(F.data == "admin_required_sub")
async def admin_required_sub_cb(callback: CallbackQuery):
    await callback.answer()
    channels = _runtime_settings.get("required_channels", [])
    text = "📌 <b>Majburiy obuna</b>\n\n"
    if channels:
        text += "Quyidagi kanallarga obuna talab qilinadi:\n"
        for ch in channels:
            text += f"• {ch}\n"
    else:
        text += "Hozircha kanallar yo'q.\n\n➕ Kanal qo'shish tugmasini bosing."
    await callback.message.edit_text(text, reply_markup=admin_kb.required_sub_keyboard(channels))


@router.callback_query(F.data == "admin_sub_add")
async def admin_sub_add_cb(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.edit_text(
        "📌 <b>Kanal qo'shish</b>\n\n"
        "Kanal username (masalan: @kanal_nomi) yoki ID sini kiriting:"
    )
    await state.set_state(AdminStates.sub_channel_input)


@router.message(AdminStates.sub_channel_input)
async def admin_sub_channel_msg(message: Message, state: FSMContext):
    channel = message.text.strip()
    channels = _runtime_settings.get("required_channels", [])
    if channel not in channels:
        channels.append(channel)
        _runtime_settings["required_channels"] = channels
        await message.answer(f"✅ Kanal {channel} qo'shildi.")
    else:
        await message.answer(f"⚠️ Kanal {channel} allaqachon mavjud.")
    await state.clear()
    await _go_main(message)


@router.callback_query(F.data.startswith("admin_sub_del_"))
async def admin_sub_del_cb(callback: CallbackQuery):
    await callback.answer()
    channel = callback.data[len("admin_sub_del_"):]
    channels = _runtime_settings.get("required_channels", [])
    if channel in channels:
        channels.remove(channel)
        _runtime_settings["required_channels"] = channels
    await admin_required_sub_cb(callback)


# ═══════════════════════════════════════════
# 8. PREMIUMLAR
# ═══════════════════════════════════════════

@router.callback_query(F.data == "admin_premiums")
async def admin_premiums_cb(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        "⭐ <b>Premiumlar</b>\n\n"
        "Premium obunalarni boshqarish.\n\n"
        "💡 Premium berish va boshqarish uchun quyidagi tugmalardan foydalaning:",
        reply_markup=admin_kb.premiums_keyboard(),
    )


@router.callback_query(F.data == "admin_premiums_list")
async def admin_premiums_list_cb(callback: CallbackQuery):
    await callback.answer("⏳ Yuklanmoqda...")
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            # Check if premium_until column exists
            from asyncpg import UndefinedColumnError
            try:
                rows = await conn.fetch(
                    "SELECT telegram_id, username, full_name FROM users WHERE premium_until IS NOT NULL AND premium_until > NOW() ORDER BY premium_until DESC LIMIT 20"
                )
                if rows:
                    text = "⭐ <b>Premium foydalanuvchilar</b>\n\n"
                    for r in rows:
                        name = r["username"] or r["full_name"] or f"#{r['telegram_id']}"
                        text += f"• {name}\n"
                else:
                    text = "⭐ <b>Premium foydalanuvchilar</b>\n\nHozircha premium foydalanuvchilar yo'q."
            except UndefinedColumnError:
                text = "⭐ <b>Premium foydalanuvchilar</b>\n\nMa'lumotlar bazasida premium_ustun maydoni yo'q.\n"
                text += "Premium funksiyasi hozircha faqat <b>Sozlamalar</b> bo'limida boshqariladi."
    except Exception as e:
        logger.error(f"Premiums list error: {e}")
        text = "❌ Xatolik."
    await callback.message.edit_text(text, reply_markup=admin_kb.back_button("admin_premiums"))


@router.callback_query(F.data == "admin_premiums_grant")
async def admin_premiums_grant_cb(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        "⭐ <b>Premium berish</b>\n\n"
        "Premium berish uchun <b>Chek yaratish</b> bo'limidan foydalaning.\n\n"
        "Yoki <b>Sozlamalar</b> bo'limida premium narxini o'zgartiring.",
        reply_markup=admin_kb.back_button("admin_premiums"),
    )


# ═══════════════════════════════════════════
# 9. SOVG'ALAR
# ═══════════════════════════════════════════

@router.callback_query(F.data == "admin_gifts")
async def admin_gifts_cb(callback: CallbackQuery):
    await callback.answer("⏳ Yuklanmoqda...")
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            total_gifts = await conn.fetchval("SELECT COUNT(*) FROM orders WHERE product_type = 'gift'") or 0
            today_gifts = await conn.fetchval(
                "SELECT COUNT(*) FROM orders WHERE product_type = 'gift' AND created_at >= CURRENT_DATE"
            ) or 0
            gift_revenue = await conn.fetchval(
                "SELECT COALESCE(SUM(amount), 0) FROM orders WHERE product_type = 'gift' AND status = 'completed'"
            ) or 0
        gift_status = "✅ Yoqilgan" if _runtime_settings.get('gift_enabled') else "❌ O'chirilgan"
        text = (
            f"🎁 <b>Sovg'alar</b>\n\n"
            f"📦 Jami sovg'alar: {total_gifts:,}\n"
            f"📅 Bugun: {today_gifts:,}\n"
            f"💰 Daromad: {gift_revenue:,} so'm\n\n"
            f"Sovg'alar xizmati: {gift_status}"
        )
    except Exception as e:
        logger.error(f"Gifts error: {e}")
        text = "❌ Xatolik."
    await callback.message.edit_text(text, reply_markup=admin_kb.gifts_keyboard())


# ═══════════════════════════════════════════
# 10. AVTOTO'LOV
# ═══════════════════════════════════════════

@router.callback_query(F.data == "admin_autopay")
async def admin_autopay_cb(callback: CallbackQuery):
    await callback.answer()
    enabled = _runtime_settings.get("autopay_enabled", False)
    status = "✅ Yoqilgan" if enabled else "❌ O'chirilgan"
    await callback.message.edit_text(
        f"💸 <b>Avtoto'lov</b>\n\n"
        f"Holati: {status}\n\n"
        "Avtoto'lov yoqilgan bo'lsa, foydalanuvchilar to'lovni amalga oshirgandan so'ng\n"
        "balans avtomatik ravishda to'ldiriladi.\n\n"
        "Holatni o'zgartirish uchun tugmani bosing:",
        reply_markup=admin_kb.autopay_keyboard(enabled),
    )


@router.callback_query(F.data == "admin_autopay_toggle")
async def admin_autopay_toggle_cb(callback: CallbackQuery):
    await callback.answer()
    _runtime_settings["autopay_enabled"] = not _runtime_settings.get("autopay_enabled", False)
    await admin_autopay_cb(callback)


# ═══════════════════════════════════════════
# 11. TO'LOV TIZIMI
# ═══════════════════════════════════════════

@router.callback_query(F.data == "admin_payment_system")
async def admin_payment_system_cb(callback: CallbackQuery):
    await callback.answer()
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            total_orders = await conn.fetchval("SELECT COUNT(*) FROM orders") or 0
            completed = await conn.fetchval("SELECT COUNT(*) FROM orders WHERE status = 'completed'") or 0
            pending = await conn.fetchval("SELECT COUNT(*) FROM orders WHERE status = 'pending'") or 0
            total_payments = await conn.fetchval("SELECT COUNT(*) FROM payments") or 0
        text = (
            "💳 <b>To'lov tizimi</b>\n\n"
            f"📦 Jami buyurtmalar: {total_orders:,}\n"
            f"✅ Bajarilgan: {completed:,}\n"
            f"⏳ Kutilayotgan: {pending:,}\n"
            f"💳 To'lovlar: {total_payments:,}\n\n"
            "To'lov tizimi sozlamalari <b>.env</b> faylida joylashgan."
        )
    except Exception as e:
        logger.error(f"Payment system error: {e}")
        text = "❌ Xatolik."
    await callback.message.edit_text(text, reply_markup=admin_kb.payment_system_keyboard())


# ═══════════════════════════════════════════
# 12. STARS TO'LDIRISH
# ═══════════════════════════════════════════

@router.callback_query(F.data == "admin_stars_topup")
async def admin_stars_topup_cb(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.edit_text(
        "⭐ <b>Stars to'ldirish</b>\n\n"
        "Foydalanuvchi SP ID sini kiriting:"
    )
    await state.set_state(AdminStates.stars_sp_id)


@router.message(AdminStates.stars_sp_id)
async def admin_stars_sp_id_msg(message: Message, state: FSMContext):
    text = message.text.strip()
    if not text.isdigit():
        await message.answer("❌ SP ID raqam bo'lishi kerak.")
        return
    sp_id = int(text)
    user = await db.get_user_by_sp_id(sp_id)
    if not user:
        await message.answer(f"❌ SP ID <code>{sp_id}</code> bo'yicha foydalanuvchi topilmadi.")
        return
    await state.update_data(stars_sp_id=sp_id, stars_user_tid=user["telegram_id"])
    price_per_unit = _runtime_settings.get("stars_price_per_unit", 200)
    await message.answer(
        f"👤 <b>Foydalanuvchi #{sp_id}</b>\n"
        f"Balans: <b>{user['balance']:,}</b> so'm\n\n"
        f"Stars miqdorini kiriting (1 star = {price_per_unit:,} so'm):"
    )
    await state.set_state(AdminStates.stars_amount)


@router.message(AdminStates.stars_amount)
async def admin_stars_amount_msg(message: Message, state: FSMContext):
    try:
        stars_count = int(message.text.strip().replace(",", "").replace(" ", ""))
    except ValueError:
        await message.answer("❌ Noto'g'ri miqdor. Raqam kiriting.")
        return
    if stars_count <= 0:
        await message.answer("❌ Miqdor 0 dan katta bo'lishi kerak.")
        return
    price_per_unit = _runtime_settings.get("stars_price_per_unit", 200)
    total_amount = stars_count * price_per_unit
    await state.update_data(stars_count=stars_count, stars_amount=total_amount)
    data = await state.get_data()
    sp_id = data["stars_sp_id"]
    await message.answer(
        f"⭐ <b>Stars ma'lumotlari</b>\n\n"
        f"Foydalanuvchi: #{sp_id}\n"
        f"Stars: {stars_count} ⭐\n"
        f"Summa: {total_amount:,} so'm\n\n"
        f"Tasdiqlaysizmi?",
        reply_markup=admin_kb.stars_topup_confirm_keyboard(sp_id, stars_count),
    )


@router.callback_query(F.data.startswith("admin_stars_confirm_"))
async def admin_stars_confirm_cb(callback: CallbackQuery, state: FSMContext):
    await callback.answer("⏳ Balans to'ldirilmoqda...")
    parts = callback.data.split("_")
    sp_id = int(parts[3])
    stars_count = int(parts[4])
    price_per_unit = _runtime_settings.get("stars_price_per_unit", 200)
    total_amount = stars_count * price_per_unit
    user = await db.get_user_by_sp_id(sp_id)
    if not user:
        await callback.message.edit_text("❌ Foydalanuvchi topilmadi.")
        return
    tid = user["telegram_id"]
    new_balance = await add_balance(tid, total_amount)
    await record_payment(f"stars_{sp_id}_{int(time.time())}", tid, total_amount, "paid",
                          f'{{"source": "stars_admin", "admin_id": {callback.from_user.id}}}')
    await _notify_balance_add(callback.bot, tid, total_amount, new_balance)
    username = user.get("username") or str(tid)
    await callback.message.edit_text(
        f"✅ <b>Stars to'ldirildi!</b>\n\n"
        f"👤 Foydalanuvchi: #{sp_id} (@{username})\n"
        f"⭐ Stars: {stars_count}\n"
        f"💰 Summa: {total_amount:,} so'm\n"
        f"💳 Yangi balans: {new_balance:,} so'm",
    )
    await _go_main(callback.message)


# ═══════════════════════════════════════════
# 13. BALANCE MANAGEMENT (ADD/DEDUCT/RESET)
# ═══════════════════════════════════════════

@router.callback_query(F.data == "admin_balance")
async def admin_balance_menu_cb(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        "💰 <b>Balansni boshqarish</b>\n\n"
        "Foydalanuvchi balansini boshqarish uchun pastdagi tugmalardan foydalaning:",
        reply_markup=admin_kb.balance_main_keyboard(),
    )


# ── Add Balance ──

@router.callback_query(F.data == "admin_balance_add")
async def admin_balance_add_start_cb(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.update_data(balance_action="add")
    await callback.message.edit_text(
        "💰 <b>Balans qo'shish</b>\n\n"
        "Foydalanuvchi SP ID sini kiriting:"
    )
    await state.set_state(AdminStates.balance_sp_id)


# ── Deduct Balance ──

@router.callback_query(F.data == "admin_balance_deduct")
async def admin_balance_deduct_start_cb(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.update_data(balance_action="deduct")
    await callback.message.edit_text(
        "💰 <b>Balansdan ayirish</b>\n\n"
        "Foydalanuvchi SP ID sini kiriting:"
    )
    await state.set_state(AdminStates.balance_sp_id)


# ── SP ID input for add/deduct ──

@router.message(AdminStates.balance_sp_id)
async def admin_balance_sp_id_msg(message: Message, state: FSMContext):
    text = message.text.strip()
    if not text.isdigit():
        await message.answer("❌ SP ID raqam bo'lishi kerak. Qayta kiriting yoki /admin ni bosing.")
        return
    sp_id = int(text)
    user = await db.get_user_by_sp_id(sp_id)
    if not user:
        await message.answer(f"❌ SP ID <code>{sp_id}</code> bo'yicha foydalanuvchi topilmadi.")
        return
    data = await state.get_data()
    action = data.get("balance_action")
    await state.update_data(balance_sp_id=sp_id, balance_user_tid=user["telegram_id"], balance_user_balance=user["balance"])
    action_label = "qo'shish" if action == "add" else "ayirish"
    await message.answer(
        f"👤 <b>Foydalanuvchi #{sp_id}</b>\n"
        f"Joriy balans: <b>{user['balance']:,}</b> so'm\n\n"
        f"Balansdan {action_label} uchun summani kiriting (so'mda):"
    )
    await state.set_state(AdminStates.balance_amount)


# ── Amount input for add/deduct ──

@router.message(AdminStates.balance_amount)
async def admin_balance_amount_msg(message: Message, state: FSMContext):
    try:
        amount = int(message.text.strip().replace(",", "").replace(" ", ""))
    except ValueError:
        await message.answer("❌ Noto'g'ri summa. Raqam kiriting.")
        return
    if amount <= 0:
        await message.answer("❌ Summa 0 dan katta bo'lishi kerak.")
        return
    data = await state.get_data()
    action = data.get("balance_action")
    sp_id = data["balance_sp_id"]
    user_balance = data.get("balance_user_balance", 0)
    if action == "deduct" and user_balance < amount:
        await message.answer(
            f"❌ Foydalanuvchi balansida so'ralgan summa yetarli emas.\n"
            f"Joriy balans: <b>{user_balance:,}</b> so'm\n"
            f"Talab qilingan: <b>{amount:,}</b> so'm"
        )
        return
    await state.update_data(balance_amount=amount)
    action_label = "Qo'shiladi" if action == "add" else "Ayiriladi"
    await message.answer(
        f"💰 <b>Ma'lumotlarni tekshiring</b>\n\n"
        f"Foydalanuvchi: #{sp_id}\n"
        f"{action_label}: {amount:,} so'm\n"
        f"Joriy balans: {user_balance:,} so'm\n\n"
        f"Tasdiqlaysizmi?",
        reply_markup=admin_kb.balance_confirm_keyboard(sp_id, amount, action),
    )


# ── Confirm add/deduct ──

@router.callback_query(F.data.startswith("admin_balance_confirm_"))
async def admin_balance_confirm_cb(callback: CallbackQuery, state: FSMContext):
    await callback.answer("⏳ Amal bajarilmoqda...")
    parts = callback.data.split("_")
    action = parts[3]
    sp_id = int(parts[4])
    amount = int(parts[5])
    user = await db.get_user_by_sp_id(sp_id)
    if not user:
        await callback.message.edit_text("❌ Foydalanuvchi topilmadi.")
        return
    tid = user["telegram_id"]
    balance_before = user["balance"]
    admin_id = callback.from_user.id

    if action == "add":
        new_balance = await add_balance(tid, amount)
        tx_type = "admin_add"
        action_text = "qo'shildi"
    else:
        if balance_before < amount:
            await callback.message.edit_text("❌ Balansda yetarli mablag' yo'q.")
            return
        await deduct_balance(tid, amount)
        new_balance = balance_before - amount
        tx_type = "admin_deduct"
        action_text = "ayirildi"

    await add_balance_history(tid, amount, tx_type, balance_before, new_balance,
                              f"Admin {action_text}: SP #{sp_id}", admin_id)

    if action == "add":
        await _notify_balance_add(callback.bot, tid, amount, new_balance)

    username = user.get("username") or str(tid)
    await callback.message.edit_text(
        f"✅ <b>Balans {action_text}!</b>\n\n"
        f"👤 Foydalanuvchi: #{sp_id} (@{username})\n"
        f"💰 Summa: {amount:,} so'm\n"
        f"💳 Eski balans: {balance_before:,} so'm\n"
        f"💳 Yangi balans: {new_balance:,} so'm"
    )
    await _go_main(callback.message)


# ── Reset Balance ──

@router.callback_query(F.data == "admin_balance_reset")
async def admin_balance_reset_start_cb(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.edit_text(
        "🔄 <b>Balansni nolga tushirish</b>\n\n"
        "Foydalanuvchi SP ID sini kiriting:"
    )
    await state.set_state(AdminStates.balance_reset_sp_id)


@router.message(AdminStates.balance_reset_sp_id)
async def admin_balance_reset_sp_id_msg(message: Message, state: FSMContext):
    text = message.text.strip()
    if not text.isdigit():
        await message.answer("❌ SP ID raqam bo'lishi kerak. Qayta kiriting yoki /admin ni bosing.")
        return
    sp_id = int(text)
    user = await db.get_user_by_sp_id(sp_id)
    if not user:
        await message.answer(f"❌ SP ID <code>{sp_id}</code> bo'yicha foydalanuvchi topilmadi.")
        return
    await state.update_data(balance_reset_sp_id=sp_id)
    await message.answer(
        f"👤 <b>Foydalanuvchi #{sp_id}</b>\n"
        f"Joriy balans: <b>{user['balance']:,}</b> so'm\n\n"
        f"⚠️ Balansni nolga tushirishni tasdiqlaysizmi?",
        reply_markup=admin_kb.balance_reset_confirm_keyboard(sp_id),
    )


@router.callback_query(F.data.startswith("admin_balance_reset_confirm_"))
async def admin_balance_reset_confirm_cb(callback: CallbackQuery, state: FSMContext):
    await callback.answer("⏳ Balans nolga tushirilmoqda...")
    sp_id = int(callback.data.split("_")[-1])
    user = await db.get_user_by_sp_id(sp_id)
    if not user:
        await callback.message.edit_text("❌ Foydalanuvchi topilmadi.")
        return
    tid = user["telegram_id"]
    balance_before = user["balance"]
    admin_id = callback.from_user.id

    new_balance = await reset_balance(tid)
    await add_balance_history(tid, -balance_before, "admin_reset", balance_before, 0,
                              f"Admin reset: SP #{sp_id}", admin_id)

    username = user.get("username") or str(tid)
    await callback.message.edit_text(
        f"✅ <b>Balans nolga tushirildi!</b>\n\n"
        f"👤 Foydalanuvchi: #{sp_id} (@{username})\n"
        f"💰 Eski balans: {balance_before:,} so'm\n"
        f"💳 Yangi balans: <b>0</b> so'm"
    )
    await _go_main(callback.message)


# ═══════════════════════════════════════════
# 14. ADMIN SOZLAMALARI
# ═══════════════════════════════════════════

@router.callback_query(F.data == "admin_admins_settings")
async def admin_admins_settings_cb(callback: CallbackQuery):
    await callback.answer()
    text = "🔐 <b>Admin sozlamalari</b>\n\nHozirgi adminlar:\n"
    for aid in ADMIN_IDS:
        text += f"• <code>{aid}</code>\n"
    text += "\nAdmin qo'shish yoki o'chirish uchun tugmalardan foydalaning:"
    await callback.message.edit_text(text, reply_markup=admin_kb.admins_keyboard(ADMIN_IDS))


@router.callback_query(F.data == "admin_admin_add")
async def admin_admin_add_cb(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.edit_text(
        "🔐 <b>Admin qo'shish</b>\n\n"
        "Yangi adminning Telegram ID sini kiriting:"
    )
    await state.set_state(AdminStates.admin_add_input)


@router.message(AdminStates.admin_add_input)
async def admin_admin_add_msg(message: Message, state: FSMContext):
    text = message.text.strip()
    if not text.isdigit():
        await message.answer("❌ Telegram ID raqam bo'lishi kerak.")
        return
    new_id = int(text)
    if new_id in ADMIN_IDS:
        await message.answer(f"⚠️ Admin <code>{new_id}</code> allaqachon mavjud.")
    else:
        ADMIN_IDS.append(new_id)
        await message.answer(f"✅ Admin <code>{new_id}</code> qo'shildi.")
    await state.clear()
    await _go_main(message)


@router.callback_query(F.data.startswith("admin_admin_del_"))
async def admin_admin_del_cb(callback: CallbackQuery):
    await callback.answer()
    aid = int(callback.data.split("_")[-1])
    if aid in ADMIN_IDS:
        ADMIN_IDS.remove(aid)
    await admin_admins_settings_cb(callback)


# ═══════════════════════════════════════════
# Foydalanuvchiga bildirishnoma yuborish
# ═══════════════════════════════════════════

async def _notify_balance_add(bot: Bot, telegram_id: int, amount: int, new_balance: int):
    try:
        text = (
            f"<tg-emoji emoji-id=\"{config.CUSTOM_EMOJI_CHECK}\">✅</tg-emoji> "
            f"<b>To'lov muvaffaqiyatli qabul qilindi</b>\n\n"
            f"<tg-emoji emoji-id=\"{config.CUSTOM_EMOJI_WALLET}\">👛</tg-emoji> "
            f"+{amount:,} so'm\n"
            f"<tg-emoji emoji-id=\"{config.CUSTOM_EMOJI_MONEY}\">💰</tg-emoji> "
            f"Balans: {new_balance:,} so'm"
        )
        await bot.send_message(telegram_id, text)
    except Exception as e:
        logger.warning(f"Could not notify user {telegram_id}: {e}")


# ═══════════════════════════════════════════
# /confirm yordamchi
# ═══════════════════════════════════════════

async def _confirm_locally(message: Message, order_id: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        order = await conn.fetchrow("SELECT * FROM orders WHERE external_id = $1", order_id)
        if not order:
            await message.answer(f"❌ Buyurtma topilmadi: <code>{order_id}</code>")
            return
        if order["status"] != "pending":
            await message.answer(f"⚠️ Buyurtma <code>{order_id}</code> xolati allaqachon «{order['status']}»")
            return
        tid = order["telegram_id"]
        amount = order["amount"]
        new_balance = await add_balance(tid, amount)
        await conn.execute("UPDATE orders SET status = 'completed' WHERE external_id = $1", order_id)
        await record_payment(order_id, tid, amount, "paid",
                              f'{{"source": "admin_confirm_local", "admin_id": {message.from_user.id}}}')
        bot = Bot(token=config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        try:
            user_text = (
                f"<tg-emoji emoji-id=\"{config.CUSTOM_EMOJI_CHECK}\">✅</tg-emoji> "
                f"<b>To'lov muvaffaqiyatli tasdiqlandi</b>\n\n"
                f"<tg-emoji emoji-id=\"{config.CUSTOM_EMOJI_WALLET}\">👛</tg-emoji> "
                f"Hisobingizga <b>{amount:,}</b> so'm qo'shildi.\n"
                f"<tg-emoji emoji-id=\"{config.CUSTOM_EMOJI_MONEY}\">💰</tg-emoji> "
                f"Yangi balans: <b>{new_balance:,}</b> so'm"
            )
            await bot.send_message(tid, user_text)
        except Exception as e:
            logger.warning(f"Could not notify user {tid}: {e}")
        finally:
            await bot.session.close()
        user = await conn.fetchrow("SELECT * FROM users WHERE telegram_id = $1", tid)
        username = user["username"] if user else str(tid)
        await message.answer(
            f"✅ <b>To'lov tasdiqlandi!</b>\n\n"
            f"👤 Foydalanuvchi: @{username}\n"
            f"📦 Buyurtma: <code>{order_id}</code>\n"
            f"💰 Summa: {amount:,} so'm\n"
            f"💳 Yangi balans: {new_balance:,} so'm\n\n"
            f"📨 Foydalanuvchiga xabar yuborildi.",
        )


# ═══════════════════════════════════════════
# 15. TOPUP APPROVAL & REJECTION CALLBACKS
# ═══════════════════════════════════════════

# ═══════════════════════════════════════════
# 15. TOPUP APPROVAL & REJECTION CALLBACKS
# ═══════════════════════════════════════════

_processing_orders = set()

@router.callback_query(F.data.startswith("approve_topup_") | F.data.startswith("admin_approve_"))
async def admin_approve_topup_cb(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        await callback.answer("❌ Faqat adminlar uchun!", show_alert=True)
        return

    data = callback.data
    user_id = None
    amount = None
    order_id = None

    # Case 1: admin_approve_receipt_{order_id}
    if data.startswith("admin_approve_receipt_"):
        order_id = data.replace("admin_approve_receipt_", "")
        order = await db.get_order(order_id)
        if order:
            user_id = order.get("telegram_id")
            amount = order.get("amount")

    # Case 2: approve_topup_{orderId}_{userId}_{amount} or admin_approve_{orderId}_{userId}_{amount}
    if not user_id or not amount:
        parts = data.split("_")
        try:
            amount = int(parts[-1])
            user_id = int(parts[-2])
            order_id = "_".join(parts[2:-2]) if len(parts) > 4 else parts[2]
        except Exception:
            try:
                order_id = parts[2]
                user_id = int(parts[3])
                amount = int(parts[4])
            except Exception:
                pass

    # Case 3: If still not resolved, query db by extracted order_id
    if not user_id or not amount:
        if not order_id:
            order_id = data.replace("approve_topup_", "").replace("admin_approve_", "")
        order = await db.get_order(order_id)
        if order:
            user_id = order.get("telegram_id")
            amount = order.get("amount")

    if not user_id or not amount:
        logger.error("Failed to parse approve callback data: %s", data)
        await callback.answer("❌ Buyurtma ma'lumotlarini aniqlab bo'lmadi!", show_alert=True)
        return

    lock_key = str(order_id) if order_id else f"{user_id}_{amount}"
    if lock_key in _processing_orders:
        await callback.answer("⚠️ Ushbu to'lov allaqachon tasdiqlanmoqda yoki tasdiqlangan!", show_alert=True)
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        return

    _processing_orders.add(lock_key)

    # Immediately remove buttons from message so user cannot click again
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    # Check database status
    if order_id:
        existing_order = await db.get_order(order_id)
        if existing_order and existing_order.get("status") in ("completed", "paid"):
            await callback.answer("⚠️ Ushbu to'lov allaqachon tasdiqlangan!", show_alert=True)
            return
        elif existing_order and existing_order.get("status") in ("rejected", "cancelled"):
            await callback.answer("⚠️ Ushbu to'lov allaqachon rad etilgan!", show_alert=True)
            return

    await callback.answer("⏳ To'lov tasdiqlanmoqda...")

    try:
        if order_id:
            await db.update_order(order_id, status="completed")

        new_balance = await add_balance(user_id, amount)
        await add_balance_history(user_id, amount, "topup", new_balance - amount, new_balance,
                                  f"Admin to'lovni tasdiqladi: #{order_id}", callback.from_user.id)
        await record_payment(str(order_id), user_id, amount, "paid",
                              f'{{"source": "admin_approval_button", "admin_id": {callback.from_user.id}}}')

        # Notify user
        try:
            user_text = (
                f"✅ <b>To'lovingiz muvaffaqiyatli tasdiqlandi!</b>\n\n"
                f"💰 Qo'shildi: <b>+{amount:,} so'm</b>\n"
                f"👛 Yangi balansingiz: <b>{new_balance:,} so'm</b>\n\n"
                f"<i>Xaridingiz uchun rahmat! Xizmatlardan foydalanishingiz mumkin.</i>"
            )
            await callback.bot.send_message(
                user_id,
                user_text,
                reply_markup=keyboards.get_webapp_main_keyboard(user_id, balance=new_balance),
                parse_mode="HTML"
            )
        except Exception as ex:
            logger.warning("Could not notify user %s: %s", user_id, ex)

        # Edit admin message
        try:
            updated_text = (
                f"✅ <b>TO'LOV TASDIQLANDI!</b>\n\n"
                f"👤 Foydalanuvchi ID: <code>{user_id}</code>\n"
                f"💰 Summa: <b>+{amount:,} so'm</b>\n"
                f"💳 Yangi balans: <b>{new_balance:,} so'm</b>\n"
                f"🆔 Buyurtma: <code>{order_id}</code>\n"
                f"👨‍💻 Tasdiqladi: @{callback.from_user.username or callback.from_user.id}\n\n"
                f"<i>Foydalanuvchi hisobiga pul qo'shildi va xabar yuborildi.</i>"
            )
            if callback.message.photo or callback.message.document:
                await callback.message.edit_caption(caption=updated_text, parse_mode="HTML", reply_markup=None)
            else:
                await callback.message.edit_text(updated_text, parse_mode="HTML", reply_markup=None)
        except Exception:
            await callback.message.reply(f"✅ To'lov tasdiqlandi! (+{amount:,} so'm)")
    except Exception as e:
        logger.error("Error in admin_approve_topup_cb: %s", e)
        if lock_key in _processing_orders:
            _processing_orders.remove(lock_key)


@router.callback_query(F.data.startswith("reject_topup_") | F.data.startswith("admin_reject_"))
async def admin_reject_topup_cb(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        await callback.answer("❌ Faqat adminlar uchun!", show_alert=True)
        return

    data = callback.data
    user_id = None
    order_id = None

    if data.startswith("admin_reject_receipt_"):
        order_id = data.replace("admin_reject_receipt_", "")
        order = await db.get_order(order_id)
        if order:
            user_id = order.get("telegram_id")
    else:
        parts = data.split("_")
        try:
            user_id = int(parts[-1])
            order_id = "_".join(parts[2:-1]) if len(parts) > 3 else parts[2]
        except Exception:
            order_id = data.replace("reject_topup_", "").replace("admin_reject_", "")
            order = await db.get_order(order_id)
            if order:
                user_id = order.get("telegram_id")

    lock_key = str(order_id) if order_id else f"reject_{user_id}"
    if lock_key in _processing_orders:
        await callback.answer("⚠️ Ushbu so'rov allaqachon ko'rib chiqilgan!", show_alert=True)
        return

    if order_id:
        existing_order = await db.get_order(order_id)
        if existing_order and existing_order.get("status") in ("completed", "paid", "rejected", "cancelled"):
            await callback.answer("⚠️ Ushbu so'rov allaqachon ko'rib chiqilgan!", show_alert=True)
            try:
                await callback.message.edit_reply_markup(reply_markup=None)
            except Exception:
                pass
            return

    _processing_orders.add(lock_key)
    await callback.answer("❌ To'lov rad etildi.")

    if order_id:
        await db.update_order(order_id, status="rejected")

    # Notify user if ID available
    if user_id:
        try:
            user_text = (
                f"❌ <b>To'lov so'rovingiz rad etildi yoki bekor qilindi.</b>\n\n"
                f"🆔 Buyurtma: <code>{order_id}</code>\n\n"
                f"<i>Agar to'lov qilgan bo'lsangiz, admin bilan bog'laning: @cofeature</i>"
            )
            await callback.bot.send_message(user_id, user_text, parse_mode="HTML")
        except Exception as ex:
            logger.warning("Could not notify user %s: %s", user_id, ex)

    try:
        updated_text = (
            f"❌ <b>TO'LOV RAD ETILDI!</b>\n\n"
            f"🆔 Buyurtma: <code>{order_id}</code>\n"
            f"👨‍💻 Rad etdi: @{callback.from_user.username or callback.from_user.id}"
        )
        if callback.message.photo or callback.message.document:
            await callback.message.edit_caption(caption=updated_text, parse_mode="HTML", reply_markup=None)
        else:
            await callback.message.edit_text(updated_text, parse_mode="HTML", reply_markup=None)
    except Exception:
        await callback.message.reply("❌ To'lov so'rovi rad etildi.")

