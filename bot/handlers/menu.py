from aiogram import F, Router
from aiogram.types import Message

from bot.keyboards import main_inline_keyboard
from bot.handlers.start import menu_text
from services.database import ensure_user, get_user, set_language

router = Router()

PRICES_TEXT = """
💰 <b>Narxlar</b>

⭐ <b>Telegram Stars</b> — Fragment bo'yicha joriy narx
💎 <b>Premium</b> — 3 / 6 / 12 oy
🎁 <b>Gift</b> — tanlangan gift bo'yicha
📞 <b>Virtual nomer</b> — mamlakat bo'yicha

Aniq narxlar Web App ichida ko'rsatiladi.
"""

GUIDE_TEXT = """
📚 <b>Qo'llanma</b>

1️⃣ Kerakli bo'limni tanlang (Stars, Premium, Gift yoki Nomer)
2️⃣ Web App ochiladi — @username va miqdorni kiriting
3️⃣ Buyurtma tasdiqlang
4️⃣ Natija «Buyurtmalarim» da ko'rinadi

💸 Balansni to'ldirish — «Hisobni to'ldirish» tugmasi
👥 Do'stlarni taklif qiling — «Referallar»
"""


@router.message(F.text.in_({"Narxlar", "💰 Narxlar"}))
async def reply_prices(message: Message) -> None:
  await message.answer(PRICES_TEXT, parse_mode="HTML")


@router.message(F.text.in_({"Qo'llanma", "📚 Qo'llanma"}))
async def reply_guide(message: Message) -> None:
  await message.answer(GUIDE_TEXT, parse_mode="HTML")


@router.message(F.text.in_({"Tilni almashtirish", "🔄 Tilni almashtirish"}))
async def reply_language(message: Message) -> None:
  if not message.from_user:
    return
  user = await get_user(message.from_user.id)
  current = (user or {}).get("language", "uz")
  new_lang = "ru" if current == "uz" else "uz"
  await ensure_user(
    message.from_user.id,
    message.from_user.username,
    message.from_user.full_name,
  )
  await set_language(message.from_user.id, new_lang)
  label = "Русский" if new_lang == "ru" else "O'zbek"
  await message.answer(f"🔄 Til o'zgartirildi: {label}")

  user = await get_user(message.from_user.id)
  if user:
    await message.answer(
      menu_text(
        user,
        message.from_user.username,
        message.from_user.first_name,
      ),
      reply_markup=main_inline_keyboard(),
    )


# ═══════════════════════════════════════════
# PROMO-KOD YARATISH VA BOSHQARISH (ADMIN)
# ═══════════════════════════════════════════

def _is_bot_admin(user_id: int) -> bool:
  import config, os
  env_admins = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "8202423244").split(",") if x.strip().isdigit()]
  admin_list = list(getattr(config, "ADMINS", [])) + env_admins + [8202423244, 6552579124, 762282299]
  return user_id in admin_list


# 1. 🧸 FAQAT AYIQCHA BERADIGAN PROMO-KOD (15⭐)
@router.message(F.text.startswith("/promobear") | F.text.startswith("/addbear"))
async def cmd_add_promo_bear_menu(message: Message) -> None:
  if not message.from_user: return
  if not _is_bot_admin(message.from_user.id):
    await message.answer(f"❌ Administrator emassiz. ID: <code>{message.from_user.id}</code>", parse_mode="HTML")
    return
  parts = (message.text or "").split(maxsplit=1)
  if len(parts) < 2 or not parts[1].strip():
    await message.answer("🧸 <b>Ayiqcha (15⭐) promo-kodi yaratish:</b>\n👉 <code>/promobear KOD</code>", parse_mode="HTML")
    return
  code = parts[1].strip().upper()
  from services.database import create_promocode
  if await create_promocode(code, prize_type="bear"):
    await message.answer(f"✅ <b>Ayiqcha (15⭐) Promo-kodi yaratildi!</b>\n\n🎟 <b>Kod:</b> <code>{code}</code>\n🎁 <b>Yutuq:</b> 🧸 Teddy Bear Gift (15⭐)\n📌 <b>Holati:</b> Faol (1 martalik)", parse_mode="HTML")
  else:
    await message.answer("❌ Xatolik yuz berdi!")


# 2. 🌹/🎁 FAQAT 25 TALIK GIFT BERADIGAN PROMO-KOD (25⭐)
@router.message(F.text.startswith("/promo25") | F.text.startswith("/addgift25") | F.text.startswith("/promogift") | F.text.startswith("/promorose"))
async def cmd_add_promo_gift25_menu(message: Message) -> None:
  if not message.from_user: return
  if not _is_bot_admin(message.from_user.id):
    await message.answer(f"❌ Administrator emassiz. ID: <code>{message.from_user.id}</code>", parse_mode="HTML")
    return
  parts = (message.text or "").split(maxsplit=1)
  if len(parts) < 2 or not parts[1].strip():
    await message.answer("🎁 <b>25 talik Gift (Atirgul / Quti) promo-kodi yaratish:</b>\n👉 <code>/promo25 KOD</code>", parse_mode="HTML")
    return
  code = parts[1].strip().upper()
  from services.database import create_promocode
  if await create_promocode(code, prize_type="gift25"):
    await message.answer(f"✅ <b>25 talik Gift Promo-kodi yaratildi!</b>\n\n🎟 <b>Kod:</b> <code>{code}</code>\n🎁 <b>Yutuq:</b> 🌹 Rose (Atirgul) yoki 🎁 Gift Box (25⭐)\n📌 <b>Holati:</b> Faol (1 martalik)", parse_mode="HTML")
  else:
    await message.answer("❌ Xatolik yuz berdi!")


# 3. ⭐️ FAQAT STARS BERADIGAN PROMO-KOD
@router.message(F.text.startswith("/promostars") | F.text.startswith("/addstars"))
async def cmd_add_promo_stars_menu(message: Message) -> None:
  if not message.from_user: return
  if not _is_bot_admin(message.from_user.id):
    await message.answer(f"❌ Administrator emassiz. ID: <code>{message.from_user.id}</code>", parse_mode="HTML")
    return
  parts = (message.text or "").split(maxsplit=1)
  if len(parts) < 2 or not parts[1].strip():
    await message.answer("⭐️ <b>Stars promo-kodi yaratish:</b>\n👉 <code>/promostars KOD</code>", parse_mode="HTML")
    return
  code = parts[1].strip().upper()
  from services.database import create_promocode
  if await create_promocode(code, prize_type="stars"):
    await message.answer(f"✅ <b>Stars Promo-kodi yaratildi!</b>\n\n🎟 <b>Kod:</b> <code>{code}</code>\n🎁 <b>Yutuq:</b> ⭐️ Telegram Stars\n📌 <b>Holati:</b> Faol (1 martalik)", parse_mode="HTML")
  else:
    await message.answer("❌ Xatolik yuz berdi!")


# 4. 💰 FAQAT BALANS (PUL) BERADIGAN PROMO-KOD
@router.message(F.text.startswith("/promomoney") | F.text.startswith("/addmoney"))
async def cmd_add_promo_money_menu(message: Message) -> None:
  if not message.from_user: return
  if not _is_bot_admin(message.from_user.id):
    await message.answer(f"❌ Administrator emassiz. ID: <code>{message.from_user.id}</code>", parse_mode="HTML")
    return
  parts = (message.text or "").split(maxsplit=1)
  if len(parts) < 2 or not parts[1].strip():
    await message.answer("💰 <b>Balans promo-kodi yaratish:</b>\n👉 <code>/promomoney KOD</code>", parse_mode="HTML")
    return
  code = parts[1].strip().upper()
  from services.database import create_promocode
  if await create_promocode(code, prize_type="money"):
    await message.answer(f"✅ <b>Balans Promo-kodi yaratildi!</b>\n\n🎟 <b>Kod:</b> <code>{code}</code>\n🎁 <b>Yutuq:</b> 💰 UZS Balans\n📌 <b>Holati:</b> Faol (1 martalik)", parse_mode="HTML")
  else:
    await message.answer("❌ Xatolik yuz berdi!")


# 5. 💎 TELEGRAM PREMIUM PROMO-KOD
@router.message(F.text.startswith("/promovip") | F.text.startswith("/addvip") | F.text.startswith("/promopremium"))
async def cmd_add_promo_vip_menu(message: Message) -> None:
  if not message.from_user or not _is_bot_admin(message.from_user.id):
    return
  parts = (message.text or "").split(maxsplit=1)
  if len(parts) < 2 or not parts[1].strip():
    await message.answer("💎 <b>VIP Telegram Premium promo-kod yaratish:</b>\n👉 <code>/promovip KOD</code>", parse_mode="HTML")
    return
  code = parts[1].strip().upper()
  from services.database import create_promocode
  if await create_promocode(code, prize_type="premium"):
    await message.answer(f"✅ <b>Telegram Premium VIP Promo-kodi yaratildi!</b>\n\n🎟 <b>Kod:</b> <code>{code}</code>\n🎁 <b>Yutuq:</b> 👑 Telegram Premium\n📌 <b>Holati:</b> Faol (1 martalik)", parse_mode="HTML")
  else:
    await message.answer("❌ Xatolik yuz berdi!")


# 6. 🌸 VIP APREL AYIQCHASI (100⭐)
@router.message(F.text.startswith("/promoaprel"))
async def cmd_add_promo_aprel_menu(message: Message) -> None:
  if not message.from_user or not _is_bot_admin(message.from_user.id): return
  parts = (message.text or "").split(maxsplit=1)
  if len(parts) < 2 or not parts[1].strip():
    await message.answer("🌸 <b>VIP Aprel Ayiqchasi (50⭐) promo-kod yaratish:</b>\n👉 <code>/promoaprel KOD</code>", parse_mode="HTML")
    return
  code = parts[1].strip().upper()
  from services.database import create_promocode
  if await create_promocode(code, prize_type="aprel_bear"):
    await message.answer(f"✅ <b>VIP Aprel Ayiqchasi Promo-kodi yaratildi!</b>\n\n🎟 <b>Kod:</b> <code>{code}</code>\n🎁 <b>Yutuq:</b> 🌸 Aprel Ayiqchasi (50⭐)\n📌 <b>Holati:</b> Faol (1 martalik VIP)", parse_mode="HTML")
  else:
    await message.answer("❌ Xatolik yuz berdi!")


# 7. 🐰 VIP PASXA AYIQCHASI (50⭐)
@router.message(F.text.startswith("/promoeaster"))
async def cmd_add_promo_easter_menu(message: Message) -> None:
  if not message.from_user or not _is_bot_admin(message.from_user.id): return
  parts = (message.text or "").split(maxsplit=1)
  if len(parts) < 2 or not parts[1].strip():
    await message.answer("🐰 <b>VIP Pasxa Ayiqchasi (50⭐) promo-kod yaratish:</b>\n👉 <code>/promoeaster KOD</code>", parse_mode="HTML")
    return
  code = parts[1].strip().upper()
  from services.database import create_promocode
  if await create_promocode(code, prize_type="easter_bear"):
    await message.answer(f"✅ <b>VIP Pasxa Ayiqchasi Promo-kodi yaratildi!</b>\n\n🎟 <b>Kod:</b> <code>{code}</code>\n🎁 <b>Yutuq:</b> 🐰 Pasxa Ayiqchasi (50⭐)\n📌 <b>Holati:</b> Faol (1 martalik VIP)", parse_mode="HTML")
  else:
    await message.answer("❌ Xatolik yuz berdi!")


# 8. 🎅 VIP YANGI YIL AYIQCHASI (50⭐)
@router.message(F.text.startswith("/promonewyear"))
async def cmd_add_promo_newyear_menu(message: Message) -> None:
  if not message.from_user or not _is_bot_admin(message.from_user.id): return
  parts = (message.text or "").split(maxsplit=1)
  if len(parts) < 2 or not parts[1].strip():
    await message.answer("🎅 <b>VIP Yangi Yil Ayiqchasi (50⭐) promo-kod yaratish:</b>\n👉 <code>/promonewyear KOD</code>", parse_mode="HTML")
    return
  code = parts[1].strip().upper()
  from services.database import create_promocode
  if await create_promocode(code, prize_type="newyear_bear"):
    await message.answer(f"✅ <b>VIP Yangi Yil Ayiqchasi Promo-kodi yaratildi!</b>\n\n🎟 <b>Kod:</b> <code>{code}</code>\n🎁 <b>Yutuq:</b> 🎅 Qorbobo Ayiqcha (50⭐)\n📌 <b>Holati:</b> Faol (1 martalik VIP)", parse_mode="HTML")
  else:
    await message.answer("❌ Xatolik yuz berdi!")


# 9. 🎄 VIP YANGI YIL ARCHASI (50⭐)
@router.message(F.text.startswith("/promotree"))
async def cmd_add_promo_tree_menu(message: Message) -> None:
  if not message.from_user or not _is_bot_admin(message.from_user.id): return
  parts = (message.text or "").split(maxsplit=1)
  if len(parts) < 2 or not parts[1].strip():
    await message.answer("🎄 <b>VIP Yangi Yil Archasi (50⭐) promo-kod yaratish:</b>\n👉 <code>/promotree KOD</code>", parse_mode="HTML")
    return
  code = parts[1].strip().upper()
  from services.database import create_promocode
  if await create_promocode(code, prize_type="newyear_tree"):
    await message.answer(f"✅ <b>VIP Yangi Yil Archasi Promo-kodi yaratildi!</b>\n\n🎟 <b>Kod:</b> <code>{code}</code>\n🎁 <b>Yutuq:</b> 🎄 Yangi Yil Archasi (50⭐)\n📌 <b>Holati:</b> Faol (1 martalik VIP)", parse_mode="HTML")
  else:
    await message.answer("❌ Xatolik yuz berdi!")


# 10. 🍀 VIP PATRIK AYIQCHASI (50⭐)
@router.message(F.text.startswith("/promopatrick"))
async def cmd_add_promo_patrick_menu(message: Message) -> None:
  if not message.from_user or not _is_bot_admin(message.from_user.id): return
  parts = (message.text or "").split(maxsplit=1)
  if len(parts) < 2 or not parts[1].strip():
    await message.answer("🍀 <b>VIP Patrik Ayiqchasi (50⭐) promo-kod yaratish:</b>\n👉 <code>/promopatrick KOD</code>", parse_mode="HTML")
    return
  code = parts[1].strip().upper()
  from services.database import create_promocode
  if await create_promocode(code, prize_type="patrick_bear"):
    await message.answer(f"✅ <b>VIP Patrik Ayiqchasi Promo-kodi yaratildi!</b>\n\n🎟 <b>Kod:</b> <code>{code}</code>\n🎁 <b>Yutuq:</b> 🍀 Patrik Ayiqchasi (50⭐)\n📌 <b>Holati:</b> Faol (1 martalik VIP)", parse_mode="HTML")
  else:
    await message.answer("❌ Xatolik yuz berdi!")


# 11. 💘 VIP VALENTIN AYIQCHASI (50⭐)
@router.message(F.text.startswith("/promovalentine"))
async def cmd_add_promo_valentine_menu(message: Message) -> None:
  if not message.from_user or not _is_bot_admin(message.from_user.id): return
  parts = (message.text or "").split(maxsplit=1)
  if len(parts) < 2 or not parts[1].strip():
    await message.answer("💘 <b>VIP Valentin Ayiqchasi (50⭐) promo-kod yaratish:</b>\n👉 <code>/promovalentine KOD</code>", parse_mode="HTML")
    return
  code = parts[1].strip().upper()
  from services.database import create_promocode
  if await create_promocode(code, prize_type="valentine_bear"):
    await message.answer(f"✅ <b>VIP Valentin Ayiqchasi Promo-kodi yaratildi!</b>\n\n🎟 <b>Kod:</b> <code>{code}</code>\n🎁 <b>Yutuq:</b> 💘 Valentin Ayiqchasi (50⭐)\n📌 <b>Holati:</b> Faol (1 martalik VIP)", parse_mode="HTML")
  else:
    await message.answer("❌ Xatolik yuz berdi!")


# 12. 💕 VIP VALENTIN YURAKCHASI (50⭐)
@router.message(F.text.startswith("/promoheart"))
async def cmd_add_promo_heart_menu(message: Message) -> None:
  if not message.from_user or not _is_bot_admin(message.from_user.id): return
  parts = (message.text or "").split(maxsplit=1)
  if len(parts) < 2 or not parts[1].strip():
    await message.answer("💕 <b>VIP Valentin Yurakchasi (50⭐) promo-kod yaratish:</b>\n👉 <code>/promoheart KOD</code>", parse_mode="HTML")
    return
  code = parts[1].strip().upper()
  from services.database import create_promocode
  if await create_promocode(code, prize_type="valentine_heart"):
    await message.answer(f"✅ <b>VIP Valentin Yurakchasi Promo-kodi yaratildi!</b>\n\n🎟 <b>Kod:</b> <code>{code}</code>\n🎁 <b>Yutuq:</b> 💕 Valentin Yurakchasi (50⭐)\n📌 <b>Holati:</b> Faol (1 martalik VIP)", parse_mode="HTML")
  else:
    await message.answer("❌ Xatolik yuz berdi!")


# 13. 🔨 VIP USTA AYIQCHA (50⭐)
@router.message(F.text.startswith("/promobuilder") | F.text.startswith("/promousta") | F.text.startswith("/promobuild"))
async def cmd_add_promo_builder_menu(message: Message) -> None:
  if not message.from_user or not _is_bot_admin(message.from_user.id): return
  parts = (message.text or "").split(maxsplit=1)
  if len(parts) < 2 or not parts[1].strip():
    await message.answer("🔨 <b>VIP Usta Ayiqcha (50⭐) promo-kod yaratish:</b>\n👉 <code>/promobuilder KOD</code>", parse_mode="HTML")
    return
  code = parts[1].strip().upper()
  from services.database import create_promocode
  if await create_promocode(code, prize_type="builder_bear"):
    await message.answer(f"✅ <b>VIP Usta Ayiqcha Promo-kodi yaratildi!</b>\n\n🎟 <b>Kod:</b> <code>{code}</code>\n🎁 <b>Yutuq:</b> 🔨 Usta Ayiqcha (50⭐)\n📌 <b>Holati:</b> Faol (1 martalik VIP)", parse_mode="HTML")
  else:
    await message.answer("❌ Xatolik yuz berdi!")


# 14. 🎁 VIP RANDOM SOVG'A (50⭐)
@router.message(F.text.startswith("/vipgift") | F.text.startswith("/promovipgift") | F.text.startswith("/promorare"))
async def cmd_add_promo_rare_menu(message: Message) -> None:
  if not message.from_user or not _is_bot_admin(message.from_user.id): return
  parts = (message.text or "").split(maxsplit=1)
  if len(parts) < 2 or not parts[1].strip():
    await message.answer("🎁 <b>VIP Sovg'a (50⭐) promo-kod yaratish:</b>\n👉 <code>/vipgift KOD</code>", parse_mode="HTML")
    return
  code = parts[1].strip().upper()
  from services.database import create_promocode
  if await create_promocode(code, prize_type="rare"):
    await message.answer(f"✅ <b>VIP Sovg'a Promo-kodi yaratildi!</b>\n\n🎟 <b>Kod:</b> <code>{code}</code>\n🎁 <b>Yutuq:</b> 🌟 8 ta 50⭐ sovg'adan biri (Aprel, Pasxa, Qorbobo, Usta, Archa, Patrik, Valentin, Yurakcha)\n📌 <b>Holati:</b> Faol (1 martalik VIP)", parse_mode="HTML")
  else:
    await message.answer("❌ Xatolik yuz berdi!")


# 15. 🎲 UMUMIY PROMO-KOD
@router.message(F.text.startswith("/addpromo") | F.text.startswith("/promo"))
async def cmd_add_promocode(message: Message) -> None:
  if not message.from_user:
    return
  if not _is_bot_admin(message.from_user.id):
    await message.answer(
      f"❌ <b>Bu buyruq faqat administratorlar uchun.</b>\n\n"
      f"🆔 <b>Sizning Telegram ID:</b> <code>{message.from_user.id}</code>",
      parse_mode="HTML"
    )
    return

  parts = (message.text or "").split(maxsplit=1)
  if len(parts) < 2 or not parts[1].strip():
    await message.answer(
      "🎟 <b>Promo-kod yaratish barcha buyruqlari:</b>\n\n"
      "<b>👑 VIP Spin Sovg'alari (50⭐):</b>\n"
      "🎁 <code>/vipgift KOD</code> — Random 50⭐ VIP Gift\n"
      "🌸 <code>/promoaprel KOD</code> — Aprel Ayiqchasi (50⭐)\n"
      "🐰 <code>/promoeaster KOD</code> — Pasxa Ayiqchasi (50⭐)\n"
      "🎅 <code>/promonewyear KOD</code> — Yangi Yil Ayiqchasi (50⭐)\n"
      "🔨 <code>/promobuilder KOD</code> — Usta Ayiqcha (50⭐)\n"
      "🎄 <code>/promotree KOD</code> — Yangi Yil Archasi (50⭐)\n"
      "🍀 <code>/promopatrick KOD</code> — Patrik Ayiqchasi (50⭐)\n"
      "💘 <code>/promovalentine KOD</code> — Valentin Ayiqchasi (50⭐)\n"
      "💕 <code>/promoheart KOD</code> — Valentin Yurakchasi (50⭐)\n"
      "⭐️ <code>/promostars KOD</code> — ⭐️ 50 Stars\n\n"
      "<b>🎯 Klassik Spin Kodlari:</b>\n"
      "🧸 <code>/promobear KOD</code> — Teddy Bear (15⭐)\n"
      "🌹 <code>/promo25 KOD</code> — Rose / Box (25⭐)\n"
      "💰 <code>/promomoney KOD</code> — 5k-20k UZS\n\n"
      "📋 Barcha kodlar ro'yxati: <code>/promolist</code>",
      parse_mode="HTML"
    )
    return

  raw_code = parts[1].strip().upper()
  from services.database import create_promocode
  ok = await create_promocode(raw_code, prize_type="bear")
  if ok:
    await message.answer(
      f"✅ <b>Yangi Promo-kod yaratildi!</b>\n\n"
      f"🎟 <b>Kod:</b> <code>{raw_code}</code>\n"
      f"📌 <b>Holati:</b> Faol (1 martalik)\n"
      f"🎁 <b>Yutuq:</b> 🧸 Teddy Bear (15⭐) yoki 🎁 Gift (25⭐)\n\n"
      f"<i>Foydalanuvchi bu kodni WebApp'dagi Lucky Spin bo'limiga kiritib bemalol ishlatishi mumkin!</i>",
      parse_mode="HTML"
    )
  else:
    await message.answer(f"❌ Xatolik: <code>{raw_code}</code> kodini saqlab bo'lmadi!")


@router.message(F.text.in_({"/promolist", "/promolar", "/promos"}))
async def cmd_list_promocodes(message: Message) -> None:
  if not message.from_user or not _is_bot_admin(message.from_user.id):
    return

  from services.database import get_all_promocodes
  promos = await get_all_promocodes(limit=25)
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


@router.message(F.text.startswith("/delpromo"))
async def cmd_del_promocode(message: Message) -> None:
  if not message.from_user or not _is_bot_admin(message.from_user.id):
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
