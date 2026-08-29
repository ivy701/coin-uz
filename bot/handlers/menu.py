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
  import config
  admin_list = list(getattr(config, "ADMINS", []))
  return user_id in admin_list or user_id in [6552579124, 762282299]


@router.message(F.text.startswith("/addpromo") | F.text.startswith("/promo"))
async def cmd_add_promocode(message: Message) -> None:
  if not message.from_user:
    return
  if not _is_bot_admin(message.from_user.id):
    return

  parts = (message.text or "").split(maxsplit=1)
  if len(parts) < 2 or not parts[1].strip():
    await message.answer(
      "🎟 <b>Yangi Promo-kod yaratish:</b>\n\n"
      "Buyruqdan so'ng promo-kod nomini yozing:\n"
      "👉 <code>/addpromo OMAD2026</code>\n"
      "👉 <code>/promo BEAR777</code>\n"
      "👉 <code>/promo KOD123</code>\n\n"
      "<i>Kod faqat 1 martalik ishlaydi va Omad G'ildiragida 1 ta bepul spin beradi.</i>",
      parse_mode="HTML"
    )
    return

  raw_code = parts[1].strip().upper()
  from services.database import create_promocode
  ok = await create_promocode(raw_code)
  if ok:
    await message.answer(
      f"✅ <b>Yangi Promo-kod yaratildi!</b>\n\n"
      f"🎟 <b>Kod:</b> <code>{raw_code}</code>\n"
      f"📌 <b>Holati:</b> Faol (1 martalik)\n"
      f"🎁 <b>Imkoniyat:</b> Omad G'ildiragida 1 ta bepul aylantirish\n\n"
      f"<i>Foydalanuvchi bu kodni WebApp'dagi Omad G'ildiragi bo'limiga kiritib bemalol ishlatishi mumkin!</i>",
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
