import os
from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
    FSInputFile,
)

from bot.config import settings
from bot.keyboards import bottom_reply_keyboard, main_inline_keyboard
from services.database import ensure_user, get_user

router = Router()

BANNER_FILE = os.path.abspath("images/start_banner.jpg")
if not os.path.exists(BANNER_FILE):
    BANNER_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "images", "start_banner.jpg")

EMOJI_DUCK_WAVE = "5472235990955334730"  # 👋 / 🐥 Custom Wave
EMOJI_LIGHTNING = "5825794181183836432"  # ⚡️ Custom lightning
EMOJI_ID_ICON = "5879770735999717115"    # 💼 User ID icon
EMOJI_DOWN = "5229212516415978792"       # ⬇️ Circle down arrow


def menu_text(
  user: dict,
  username: str | None,
  first_name: str | None,
) -> str:
  user_dict = user or {}
  display = f"@{username}" if username else (first_name or "Foydalanuvchi")
  user_id_val = user_dict.get("sp_id") or user_dict.get("id") or user_dict.get("telegram_id", "—")
  return (
    f'<tg-emoji emoji-id="{EMOJI_DUCK_WAVE}">🐥</tg-emoji> Xush kelibsiz, {display}\n\n'
    f'<tg-emoji emoji-id="{EMOJI_LIGHTNING}">⚡️</tg-emoji> Qulay interfeys\n'
    f'<tg-emoji emoji-id="{EMOJI_LIGHTNING}">⚡️</tg-emoji> Qulay to\'lov\n'
    f'<tg-emoji emoji-id="{EMOJI_LIGHTNING}">⚡️</tg-emoji> To\'liq avtomatlashtirilgan xizmat\n\n'
    f'<tg-emoji emoji-id="{EMOJI_ID_ICON}">💼</tg-emoji> User ID: {user_id_val}\n\n'
    f'Pastdagi tugmani bosing va hoziroq boshlang <tg-emoji emoji-id="{EMOJI_DOWN}">⬇️</tg-emoji>'
  )


async def send_start_banner(message: Message, text: str, reply_markup: InlineKeyboardMarkup) -> None:
    if os.path.exists(BANNER_FILE):
        try:
            await message.answer_photo(
                photo=FSInputFile(BANNER_FILE),
                caption=text,
                reply_markup=reply_markup,
                parse_mode="HTML"
            )
            return
        except Exception:
            pass
    await message.answer(
        text,
        reply_markup=reply_markup,
        parse_mode="HTML",
    )


@router.message(Command("admin"))
async def cmd_admin(message: Message) -> None:
    """Admin panel inside the bot"""
    if not message.from_user:
        return
    user_id = message.from_user.id
    admin_ids = settings.admin_ids or []
    if user_id not in admin_ids:
        await message.answer(
            "❌ <b>Bu buyruq faqat administratorlar uchun.</b>",
            parse_mode="HTML",
        )
        return
    from keyboards import get_admin_main_keyboard
    await message.answer(
        "🔐 <b>Admin Panel</b>\n\nXush kelibsiz, administrator!",
        reply_markup=get_admin_main_keyboard(),
        parse_mode="HTML",
    )


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
  tg = message.from_user
  if not tg:
    return

  ref_id = None
  if message.text and len(message.text.split()) > 1:
    arg = message.text.split(maxsplit=1)[1]
    if arg.isdigit():
      ref_id = int(arg)

  user = await ensure_user(tg.id, tg.username, tg.full_name, referred_by=ref_id)
  await send_start_banner(
    message=message,
    text=menu_text(user, tg.username, tg.first_name),
    reply_markup=main_inline_keyboard(user_id=tg.id),
  )


@router.message(Command("menu"))
async def cmd_menu(message: Message) -> None:
  tg = message.from_user
  if not tg:
    return
  user = await get_user(tg.id) or await ensure_user(
    tg.id, tg.username, tg.full_name
  )
  await send_start_banner(
    message=message,
    text=menu_text(user, tg.username, tg.first_name),
    reply_markup=main_inline_keyboard(user_id=tg.id),
  )

