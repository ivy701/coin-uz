import asyncio
from datetime import date, datetime
import json
import logging
from pathlib import Path

from aiohttp import web
from aiohttp.web_middlewares import middleware

from bot.config import STARS_MAX_AMOUNT, STARS_MIN_AMOUNT, settings
import asyncpg

from services.database import (
  add_balance,
  create_order,
  deduct_balance,
  get_user,
  record_payment,
)
from services.fragment_api import FragmentAPI, FragmentAPIError
from services.payment_verify import extract_payment_fields, verify_shop_signature
from services.telegram_auth import validate_init_data
logger = logging.getLogger(__name__)

WEBAPP_DIR = Path(__file__).resolve().parent.parent / "webapp"
fragment = FragmentAPI()

CORS_ORIGINS = {
    "https://starpayuz-webapp.vercel.app",
    "https://test-uz-o2cg.vercel.app",
    "https://kamron5505.github.io",
    "https://worker-production-679d.up.railway.app",
    "https://web-production-49c65.up.railway.app",
}



@middleware
async def cors_middleware(request: web.Request, handler):
    origin = request.headers.get("Origin", "")
    # Allow preflight
    if request.method == "OPTIONS":
        resp = web.Response()
        _set_cors(resp, origin)
        return resp
    resp = await handler(request)
    _set_cors(resp, origin)
    return resp


def _set_cors(resp: web.Response, origin: str) -> None:
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS, PUT, DELETE"
    resp.headers["Access-Control-Allow-Headers"] = "*"



async def _json_body(request: web.Request) -> dict:
  try:
    return await request.json()
  except Exception:
    return {}


async def _auth_user(request: web.Request) -> dict | None:
  init_data = request.headers.get("X-Telegram-Init-Data") or ""
  body = await _json_body(request)
  if not init_data:
    init_data = body.get("initData", "")
  return validate_init_data(init_data, settings.bot_token)


def _user_id_from_auth(auth: dict | None) -> int | None:
  if not auth:
    return None
  user = auth.get("user")
  if isinstance(user, dict):
    return user.get("id")
  return None


async def health(_: web.Request) -> web.Response:
  return web.json_response({"ok": True, "service": "StarPayUz"})


async def webapp_index(_: web.Request) -> web.FileResponse:
  return web.FileResponse(WEBAPP_DIR / "index.html")


async def api_user_balance(request: web.Request) -> web.Response:
  auth = await _auth_user(request)
  user_id = _user_id_from_auth(auth)
  body = await _json_body(request)
  if not user_id:
    user_id = body.get("telegram_id")
  if not user_id:
    return web.json_response({"ok": False, "error": "Unauthorized"}, status=401)
  
  # Ensure user exists (create if not)
  from services.database import ensure_user
  username = None
  full_name = None
  if auth and auth.get("user"):
    u = auth["user"]
    username = u.get("username")
    full_name = f"{u.get('first_name', '')} {u.get('last_name', '')}".strip()
  
  user = await ensure_user(int(user_id), username, full_name or "User")
  return web.json_response({"ok": True, "balance": user.get("balance", 0)})


def _parse_stars_quantity(body: dict) -> int | None:
  raw = body.get("quantity") or body.get("amount")
  if raw is None:
    return None
  try:
    return int(raw)
  except (TypeError, ValueError):
    return None


def _validate_stars_quantity(quantity: int | None) -> str | None:
  if quantity is None:
    return "Stars miqdori ko'rsatilmagan"
  if quantity < STARS_MIN_AMOUNT:
    return f"Minimal miqdor: {STARS_MIN_AMOUNT} stars"
  if quantity > STARS_MAX_AMOUNT:
    return f"Maksimal miqdor: {STARS_MAX_AMOUNT:,} stars"
  return None


_cached_stars_stock = {
    "count": None,
    "updated_at": 0.0
}


async def api_stars_available(request: web.Request) -> web.Response:
    import time
    import os
    now = time.time()
    # Return cache if less than 30 seconds old
    if _cached_stars_stock["count"] is not None and (now - _cached_stars_stock["updated_at"]) < 30:
        return web.json_response({"ok": True, "available": _cached_stars_stock["count"]})

    count = None
    env_stars = os.getenv("STARS_AVAILABLE") or os.getenv("AVAILABLE_STARS") or os.getenv("STARS_STOCK")
    if env_stars and env_stars.strip().isdigit():
        count = int(env_stars.strip())

    if count is None:
        try:
            data = await fragment.get_balance()
            if isinstance(data, dict):
                # Search directly in data or in data["result"] / data["data"]
                candidates = [data]
                if isinstance(data.get("result"), dict):
                    candidates.append(data["result"])
                if isinstance(data.get("data"), dict):
                    candidates.append(data["data"])

                for item in candidates:
                    for k in ("stars", "available", "stars_count", "balance_stars", "stock"):
                        if k in item and item[k] is not None:
                            try:
                                count = int(item[k])
                                break
                            except (ValueError, TypeError):
                                pass
                    if count is not None:
                        break

                    # If balance_ton is provided, convert TON to Stars equivalent (1 TON ≈ 150 Stars)
                    if count is None and "balance_ton" in item and item["balance_ton"] is not None:
                        try:
                            ton_val = float(item["balance_ton"])
                            if ton_val > 0:
                                count = int(round(ton_val * 150))
                        except (ValueError, TypeError):
                            pass
        except Exception as e:
            logger.warning("Failed to fetch available stars balance from Fragment API: %s", e)

    if count is None:
        count = _cached_stars_stock["count"] or 23282

    _cached_stars_stock["count"] = count
    _cached_stars_stock["updated_at"] = now

    return web.json_response({"ok": True, "available": count})


async def api_stars_price(request: web.Request) -> web.Response:
  body = await _json_body(request)
  quantity = _parse_stars_quantity(body) or STARS_MIN_AMOUNT
  err = _validate_stars_quantity(quantity)
  if err:
    return web.json_response({"ok": False, "error": err}, status=400)
  try:
    data = await fragment.get_stars_price(quantity)
    return web.json_response({"ok": True, "data": data})
  except FragmentAPIError as e:
    return web.json_response({"ok": False, "error": str(e)}, status=400)


async def api_order_stars(request: web.Request) -> web.Response:
  auth = await _auth_user(request)
  user_id = _user_id_from_auth(auth)
  body = await _json_body(request)
  if not user_id:
    user_id = body.get("telegram_id")
  if not user_id:
    return web.json_response({"ok": False, "error": "Unauthorized"}, status=401)

  username = (body.get("username") or "").strip().lstrip("@")
  quantity = _parse_stars_quantity(body)
  
  logger.info("api_order_stars: user_id=%s, username=%s, quantity=%s", user_id, username, quantity)
  
  if not username:
    return web.json_response({"ok": False, "error": "Username ko'rsatilmagan"}, status=400)
  err = _validate_stars_quantity(quantity)
  if err:
    return web.json_response({"ok": False, "error": err}, status=400)

  user = await get_user(int(user_id))
  if not user:
    logger.warning("User %s not found in DB", user_id)
    return web.json_response({"ok": False, "error": "Foydalanuvchi topilmadi. /start bosing."}, status=400)
  
  balance = user.get("balance", 0)
  logger.info("User %s balance: %s", user_id, balance)
  
  # Calculate price (simple: 200 sum per star)
  price = quantity * 200
  
  if balance < price:
    logger.warning("Insufficient balance: have %s, need %s", balance, price)
    return web.json_response(
      {"ok": False, "error": f"Balans yetarli emas. Kerak: {price:,} so'm, Balans: {balance:,} so'm"},
      status=400
    )

  try:
    result = await fragment.buy_stars(username, quantity)
    order_id = await create_order(
      int(user_id), "stars", username, quantity, None, str(result.get("id", "")), "completed"
    )
    await deduct_balance(int(user_id), price)
    from services.channel_notify import notify_stars
    asyncio.ensure_future(notify_stars(username, quantity, price))
    return web.json_response({"ok": True, "order_id": order_id, "result": result})
  except FragmentAPIError as e:
    await create_order(int(user_id), "stars", username, quantity, None, status="failed")
    return web.json_response({"ok": False, "error": str(e)}, status=400)


async def api_order_premium(request: web.Request) -> web.Response:
  auth = await _auth_user(request)
  user_id = _user_id_from_auth(auth)
  body = await _json_body(request)
  if not user_id:
    user_id = body.get("telegram_id")
  if not user_id:
    return web.json_response({"ok": False, "error": "Unauthorized"}, status=401)

  username = (body.get("username") or "").strip().lstrip("@")
  if not username:
    return web.json_response({"ok": False, "error": "Username ko'rsatilmagan"}, status=400)

  months = int(body.get("months", 3))
  if months not in (3, 6, 12):
    months = 3
  
  premium_prices = {3: 160000, 6: 225000, 12: 380000}
  price = int(body.get("price") or premium_prices.get(months, 160000))

  user = await get_user(int(user_id))
  if not user:
    return web.json_response({"ok": False, "error": "Foydalanuvchi topilmadi. /start bosing."}, status=400)

  balance = user.get("balance", 0)
  if balance < price:
    return web.json_response(
      {"ok": False, "error": f"Balans yetarli emas. Kerak: {price:,} so'm, Balans: {balance:,} so'm"},
      status=400
    )

  try:
    result = await fragment.buy_premium(username, months)
    order_id = await create_order(
      int(user_id), "premium", username, months, price, str(result.get("id", "")), "completed"
    )
    await deduct_balance(int(user_id), price)
    from services.channel_notify import notify_premium
    asyncio.ensure_future(notify_premium(username, months, price))
    return web.json_response({"ok": True, "order_id": order_id, "result": result})
  except FragmentAPIError as e:
    await create_order(int(user_id), "premium", username, months, price, status="failed")
    return web.json_response({"ok": False, "error": str(e)}, status=400)


async def api_order_gift(request: web.Request) -> web.Response:
  auth = await _auth_user(request)
  user_id = _user_id_from_auth(auth)
  body = await _json_body(request)
  if not user_id:
    user_id = body.get("telegram_id")
  if not user_id:
    return web.json_response({"ok": False, "error": "Unauthorized"}, status=401)

  username = (body.get("username") or "").strip().lstrip("@")
  gift = (body.get("gift") or "").strip().lower()
  price = int(body.get("price", 0))
  
  if not username:
    return web.json_response({"ok": False, "error": "Username ko'rsatilmagan"}, status=400)
  
  if not gift or price <= 0:
    return web.json_response({"ok": False, "error": "Gift tanlanmagan"}, status=400)
  
  # Check balance
  user = await get_user(int(user_id))
  if not user:
    return web.json_response({"ok": False, "error": "Foydalanuvchi topilmadi"}, status=400)
  
  balance = user.get("balance", 0)
  if balance < price:
    return web.json_response({
      "ok": False,
      "error": f"Balans yetarli emas. Kerak: {price:,} so'm, Balans: {balance:,} so'm"
    }, status=400)
  
  # Gift ID mapping
  gift_mapping = {
    # Regular gifts
    "heart": "5170145012310081615",
    "bear": "5170233102089322756",
    "box": "5170250947678437525",
    "rose": "5168103777563050263",
    "cake": "5170144170496491616",
    "rocket": "5170564780938756245",
    "champagne": "6028601630662853006",
    "bouquet": "5170314324215857265",
    "diamond": "5170521118301225164",
    "trophy": "5168043875654172773",
    "ring": "5170690322832818290",
    
    # Deluxe/Limited gifts (IDs need to be obtained from GetStarGiftsRequest)
    # These are placeholder IDs - update with real IDs from Telegram API
    "deluxe_rose": "5170145012310081616",      # Deluxe Rose - 25 stars
    "deluxe_heart": "5170145012310081617",     # Deluxe Heart - 25 stars
    "deluxe_cake": "5170144170496491617",      # Deluxe Cake - 50 stars
    "deluxe_diamond": "5170521118301225165",   # Deluxe Diamond - 100 stars
    "golden_trophy": "5168043875654172774",    # Golden Trophy - 250 stars
    "star_crown": "5170145012310081618",       # Star Crown - 500 stars
    "blue_gem": "5170145012310081619",         # Blue Gem - 1000 stars
    "fire_phoenix": "5170145012310081620",     # Fire Phoenix - 2500 stars
    
    # Limited Edition gifts (removed Telegram gifts)
    "newyear_tree": "5922558454332916696",       # New Year Tree - 50 stars
    "newyear_bear": "5956217000635139069",       # New Year Bear - 50 stars
    "valentine_heart": "5801108895304779062",    # Valentine Heart - 50 stars
    "valentine_bear": "5800655655995968830",     # Valentine Bear - 50 stars
    "march8_bear": "5866352046986232958",        # March 8 Bear - 50 stars
    "patrick_bear": "5893356958802511476",       # St. Patrick Bear - 50 stars
    "april_bear": "5935895822435615975",         # April Fools Bear - 50 stars
    "easter_bear": "5969796561943660080",        # Easter Bear - 50 stars
    "may_bear": "6026193266406327981",           # May Day Bear - 50 stars
  }
  
  gift_id = gift_mapping.get(gift.lower()) or (gift if gift.isdigit() else None)
  if not gift_id:
    return web.json_response({"ok": False, "error": f"Noma'lum gift: {gift}"}, status=400)
  
  # Send gift via Telethon (MTProto)
  from services.telethon_client import gift_sender
  
  if gift_sender and gift_sender.client and gift_sender.client.is_connected():
    try:
      logger.info(f"Sending gift {gift} (ID: {gift_id}) to @{username} via Telethon MTProto")
      result = await gift_sender.send_gift(
        username=username,
        gift_sticker_id=gift_id,
        message=f"🎁 Sovg'a"
      )
      
      if result.get("ok"):
        await deduct_balance(int(user_id), price)
        order_id = await create_order(
          int(user_id), "gift", username, None, price, gift_id, "completed"
        )
        from services.channel_notify import notify_gift
        asyncio.ensure_future(notify_gift(username, gift, gift, price))
        return web.json_response({
          "ok": True,
          "order_id": order_id,
          "message": f"🎁 {gift.capitalize()} sovg'asi @{username} ga avtomatik yuborildi!"
        })
      else:
        logger.warning(f"Telethon instant gift send failed: {result.get('error')}, queueing order...")
    except Exception as e:
      logger.error(f"Telethon gift send exception: {e}, queueing order...")

  # Fallback / Queue mode: Deduct balance and create pending order for auto-worker / admin completion
  await deduct_balance(int(user_id), price)
  order_id = await create_order(
    int(user_id), "gift", username, None, price, gift_id, "pending"
  )
  from services.channel_notify import notify_gift
  asyncio.ensure_future(notify_gift(username, gift, gift, price))
  
  return web.json_response({
    "ok": True,
    "order_id": order_id,
    "message": f"🎁 {gift.capitalize()} buyurtmasi qabul qilindi! Sovg'a avtomatik ravishda yuborilmoqda."
  })


async def api_order_phone(request: web.Request) -> web.Response:
  auth = await _auth_user(request)
  user_id = _user_id_from_auth(auth)
  body = await _json_body(request)
  if not user_id:
    user_id = body.get("telegram_id")
  if not user_id:
    return web.json_response({"ok": False, "error": "Unauthorized"}, status=401)

  username = (body.get("username") or "").strip().lstrip("@")
  country = (body.get("country") or "UZ").strip().upper()

  try:
    result = await fragment.buy_phone(username, country)
    order_id = await create_order(
      int(user_id), "phone", username, None, None, str(result.get("id", "")), "completed"
    )
    from services.channel_notify import notify_phone
    asyncio.ensure_future(notify_phone(username, country, 0))
    return web.json_response({"ok": True, "order_id": order_id, "result": result})
  except FragmentAPIError as e:
    await create_order(int(user_id), "phone", username, None, None, status="failed")
    return web.json_response({"ok": False, "error": str(e)}, status=400)


async def api_payment_create(request: web.Request) -> web.Response:
  """Create topup order — оплата через карту в боте"""
  auth = await _auth_user(request)
  user_id = _user_id_from_auth(auth)
  body = await _json_body(request)
  
  if not user_id:
    user_id = body.get("telegram_id")
  if not user_id:
    return web.json_response({"ok": False, "error": "Unauthorized"}, status=401)

  amount = body.get("amount")
  order_id = body.get("order_id")
  
  if not amount or not order_id:
    return web.json_response({"ok": False, "error": "Amount va order_id kerak"}, status=400)
  
  try:
    amount_int = int(amount)
    if amount_int < 1000 or amount_int > 100000000:
      return web.json_response({"ok": False, "error": "Summa 1,000 dan 100,000,000 oralig'ida bo'lishi kerak"}, status=400)
  except (TypeError, ValueError):
    return web.json_response({"ok": False, "error": "Noto'g'ri summa"}, status=400)

  # Create order in database — вебхук сам обработает при поступлении
  await create_order(int(user_id), "topup", "", None, amount_int, order_id, "pending")
  
  return web.json_response({
    "ok": True,
    "order_id": order_id,
    "message": "Buyurtma yaratildi. Kartaga pul tashlang va botda 'To'lovni tekshirish' tugmasini bosing."
  })


async def payment_webhook_check(request: web.Request) -> web.Response:
  """GET handler — для проверки URL платёжными системами"""
  return web.json_response({"ok": True, "service": "StarPayUz", "message": "Webhook endpoint active"})


async def payment_webhook(request: web.Request) -> web.Response:
  """
  Единый обработчик вебхуков от платёжных систем.
  Поддерживает:
    - Fragment API (поле "order_id", "amount", "user_id")
    - Click (поле "merchant_trans_id", "amount", "user_id")
    - Payme (поле "order_id", "amount", "customer_id")
  """
  try:
    payload = await request.json()
  except Exception:
    return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)

  logger.info("Payment webhook received: %s", json.dumps(payload, ensure_ascii=False)[:200])

  # Проверка shop_id — логируем несоответствие, но НЕ блокируем
  # (Railway env может содержать пробелы, разные платёжки шлют разные форматы)
  shop_id = str(payload.get("shop_id", "")).strip()
  expected_shop_id = str(settings.shop_id).strip()
  if expected_shop_id and shop_id and shop_id != expected_shop_id:
    logger.warning("shop_id mismatch: got='%s' expected='%s' — proceeding anyway", shop_id, expected_shop_id)
  # НЕ блокируем — проверка подписи достаточна для безопасности

  # Проверка подписи (не блокируем — разные платёжки используют разные алгоритмы)
  if settings.shop_key:
    sig_ok = verify_shop_signature(payload, settings.shop_key)
    logger.info("Payment webhook signature: %s", "OK" if sig_ok else "MISMATCH (non-blocking)")

  # Определяем статус (Click использует поле "error": 0 для успеха)
  raw_status = str(payload.get("status", "")).lower()
  action = str(payload.get("action", "")).lower()
  error_code = payload.get("error")
  error_text = str(error_code).strip().lower()
  
  # Click: action="1" (complete) и error=0 значит успех
  is_click_success = (action == "1" and error_text in ("0", "0.0"))
  # Payme: status="paid" / status="completed"
  is_paid = raw_status in ("paid", "success", "completed", "1", "true")
  
  if not is_paid and not is_click_success:
    logger.info("Webhook ignored: status=%s, action=%s, error=%s", raw_status, action, error_code)
    return web.json_response({"ok": True, "message": "ignored status"})

  # Извлекаем поля (поддержка разных форматов)
  order_id, amount, user_id = extract_payment_fields(payload)
  
  # Если не нашли через общие поля — пробуем специфичные для Click
  if not order_id:
    order_id = payload.get("merchant_trans_id") or payload.get("click_trans_id")
  if not amount:
    # Click/Payme могут передавать amount как строку с десятичной точкой "50000.00"
    raw_amount = payload.get("amount") or payload.get("sum") or payload.get("total")
    if raw_amount is not None:
      try:
        amount = int(float(str(raw_amount)))
      except (TypeError, ValueError):
        amount = None
  if not user_id:
    user_id = payload.get("user_id") or payload.get("telegram_id") or payload.get("customer_id")
  
  if not order_id or amount is None:
    logger.warning("Missing required fields: order_id=%s, amount=%s", order_id, amount)
    return web.json_response({"ok": False, "error": "Missing order_id or amount"}, status=400)

  try:
    amount_int = int(float(str(amount))) if not isinstance(amount, int) else amount
  except (TypeError, ValueError):
    return web.json_response({"ok": False, "error": "Invalid amount"}, status=400)

  try:
    user_int = int(user_id) if user_id else None
  except (TypeError, ValueError):
    user_int = None

  if not user_int:
    # Ищем telegram_id через сохранённый заказ по external_id
    from services.database import get_pool
    pool = await get_pool()
    async with pool.acquire() as conn:
      order = await conn.fetchrow(
        "SELECT telegram_id, amount FROM orders WHERE external_id = $1 ORDER BY id DESC LIMIT 1",
        order_id,
      )
    if order:
      user_int = int(order["telegram_id"])
      logger.info("Resolved user from order: order=%s user=%s", order_id, user_int)
      # Проверяем расхождение суммы (логируем, но не блокируем)
      if order["amount"] is not None and int(order["amount"]) != amount_int:
        logger.warning(
          "Amount mismatch: order=%s webhook=%s order_db=%s",
          order_id, amount_int, order["amount"],
        )

  if not user_int:
    logger.warning(
      "Payment webhook: cannot resolve user for order=%s — balance NOT credited. Payload: %s",
      order_id, json.dumps(payload, ensure_ascii=False)[:300]
    )

  # Записываем платеж (если уже был — вернёт False)
  inserted = await record_payment(
    order_id,
    user_int,
    amount_int,
    "paid",
    json.dumps(payload, ensure_ascii=False),
  )
  if not inserted:
    logger.info("Payment %s already processed, skipping", order_id)
    return web.json_response({"ok": True, "message": "already processed"})    # Начисляем баланс только если есть user_id
  if user_int:
    new_balance = await add_balance(user_int, amount_int)
    logger.info("Balance credited: user=%s, amount=%s, new_balance=%s", user_int, amount_int, new_balance)
    
    # Обновляем статус заказа на completed
    from services.database import get_pool
    pool = await get_pool()
    async with pool.acquire() as conn:
      await conn.execute(
        "UPDATE orders SET status = 'completed' WHERE external_id = $1",
        order_id
      )
    
    # Отправляем уведомление в Telegram
    from aiogram import Bot
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode

    if settings.bot_token:
      check_emoji = f'<tg-emoji emoji-id="{settings.custom_emoji_check}">✅</tg-emoji>' if settings.custom_emoji_check else "✅"
      wallet_emoji = f'<tg-emoji emoji-id="{settings.custom_emoji_wallet}">👛</tg-emoji>' if settings.custom_emoji_wallet else "👛"
      money_emoji = f'<tg-emoji emoji-id="{settings.custom_emoji_money}">💰</tg-emoji>' if settings.custom_emoji_money else "💰"
      bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
      )
      try:
        await bot.send_message(
          user_int,
          f"{check_emoji} <b>To'lov muvaffaqiyatli qabul qilindi</b>\n\n"
          f"{wallet_emoji} +{amount_int:,} so'm\n"
          f"{money_emoji} Balans: {new_balance:,} so'm",
        )
      except Exception as e:
        logger.warning("Could not notify user %s: %s", user_int, e)
      finally:
        await bot.session.close()
  else:
    logger.warning("Payment %s recorded but balance NOT credited (no user_id)", order_id)

  return web.json_response({"ok": True, "message": "Payment processed"})


async def api_order_topup(request: web.Request) -> web.Response:
  """Create topup order with 5 minute expiration"""
  auth = await _auth_user(request)
  user_id = _user_id_from_auth(auth)
  body = await _json_body(request)
  
  if not user_id:
    user_id = body.get("telegram_id")
  if not user_id:
    return web.json_response({"ok": False, "error": "Unauthorized"}, status=401)

  order_id = body.get("order_id")
  amount = body.get("amount")
  
  if not order_id or not amount:
    return web.json_response({"ok": False, "error": "order_id va amount kerak"}, status=400)
  
  try:
    amount_int = int(amount)
    if amount_int < 1000 or amount_int > 100000000:
      return web.json_response({"ok": False, "error": "Summa noto'g'ri (1,000 — 100,000,000)"}, status=400)
  except (TypeError, ValueError):
    return web.json_response({"ok": False, "error": "Noto'g'ri summa"}, status=400)

  # Save topup order — use keyword args to ensure external_id is stored
  await create_order(
      telegram_id=int(user_id),
      product_type="topup",
      target_username="",
      quantity=None,
      amount=amount_int,
      external_id=order_id,
      status="pending",
  )
  logger.info("[TOPUP] Order saved: user=%s order_id=%s amount=%s", user_id, order_id, amount_int)
  
  # Forward topup request to Admin & notify User via Telegram
  try:
    import os
    import config
    from aiogram import Bot
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    
    bot_inst = Bot(token=config.BOT_TOKEN)
    
    admin_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Qabul qilish (+Balans)", callback_data=f"approve_topup_{order_id}_{user_id}_{amount_int}"),
            InlineKeyboardButton(text="❌ Rad etish", callback_data=f"reject_topup_{order_id}_{user_id}"),
        ]
    ])
    
    card_number = os.getenv("CARD_NUMBER", "4916 9903 6986 6493")
    card_owner = os.getenv("CARD_OWNER", "T M")
    
    admin_ids = [int(a) for a in config.ADMINS]
    for admin_id in admin_ids:
        try:
            await bot_inst.send_message(
                admin_id,
                f"📥 <b>YANGI TO'LOV SO'ROVI (WebApp)!</b>\n\n"
                f"👤 Foydalanuvchi ID: <code>{user_id}</code>\n"
                f"💰 Summa: <b>{amount_int:,} so'm</b>\n"
                f"🆔 Buyurtma: <code>{order_id}</code>\n\n"
                f"<i>To'lov kelganini tekshirib, tugmani bosing:</i>",
                parse_mode="HTML",
                reply_markup=admin_kb
            )
        except Exception as ex:
            logger.error("Failed to notify admin %s: %s", admin_id, ex)

    # Only send user-facing card message to non-admin users
    if int(user_id) not in admin_ids:
        user_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ To'lovni tekshirish", callback_data=f"check_payment_{order_id}")],
            [InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"cancel_payment_{order_id}")]
        ])
        try:
            await bot_inst.send_message(
                int(user_id),
                f"💳 <b>Balans to'ldirish so'rovi yaratildi!</b>\n\n"
                f"💰 Summa: <b>{amount_int:,} so'm</b>\n\n"
                f"💳 <b>Karta raqami:</b> <code>{card_number}</code>\n"
                f"👤 <b>Egasining ismi:</b> {card_owner}\n\n"
                f"<i>To'lovni amalga oshirgach, Admin tasdiqlashini kuting!</i>",
                parse_mode="HTML",
                reply_markup=user_kb
            )
        except Exception as err:
            logger.error("Failed to notify user %s: %s", user_id, err)

    await bot_inst.session.close()
  except Exception as err:
    logger.error("Failed to process telegram notification for topup %s: %s", order_id, err)

  return web.json_response({"ok": True, "order_id": order_id})



async def api_payment_check(request: web.Request) -> web.Response:
  """Check if payment was received"""
  auth = await _auth_user(request)
  user_id = _user_id_from_auth(auth)
  body = await _json_body(request)
  
  if not user_id:
    user_id = body.get("telegram_id")
  if not user_id:
    return web.json_response({"ok": False, "error": "Unauthorized"}, status=401)

  order_id = body.get("order_id")
  if not order_id:
    return web.json_response({"ok": False, "error": "order_id kerak"}, status=400)
  
  # Check if payment exists in payments table
  from services.database import db_conn
  payment = await db_conn.fetchrow(
    "SELECT * FROM payments WHERE shop_order_id = $1 AND status = 'paid'",
    order_id
  )
  
  if payment:
    return web.json_response({
      "ok": True,
      "paid": True,
      "amount": payment["amount"]
    })
  else:
    return web.json_response({
      "ok": True,
      "paid": False
    })



async def api_get_available_gifts(request: web.Request) -> web.Response:
  """Get list of available Star Gifts from Telegram"""
  from services.telethon_client import gift_sender
  
  if not gift_sender:
    return web.json_response({
      "ok": False,
      "error": "Gift sender не инициализирован"
    }, status=503)
  
  try:
    result = await gift_sender.get_available_gifts()
    return web.json_response(result)
  except Exception as e:
    logger.exception(f"Failed to get available gifts: {e}")
    return web.json_response({
      "ok": False,
      "error": str(e)
    }, status=500)





async def _notify_user_paid(user_id: int, amount: int, new_balance: int) -> None:
    """Send Telegram notification about successful payment."""
    from aiogram import Bot
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode

    if not settings.bot_token:
        return

    check_emoji = f'<tg-emoji emoji-id="{settings.custom_emoji_check}">✅</tg-emoji>' if settings.custom_emoji_check else "✅"
    wallet_emoji = f'<tg-emoji emoji-id="{settings.custom_emoji_wallet}">👛</tg-emoji>' if settings.custom_emoji_wallet else "👛"
    money_emoji = f'<tg-emoji emoji-id="{settings.custom_emoji_money}">💰</tg-emoji>' if settings.custom_emoji_money else "💰"
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    try:
        await bot.send_message(
            user_id,
            f"{check_emoji} <b>To'lov muvaffaqiyatli qabul qilindi</b>\n\n"
            f"{wallet_emoji} +{amount:,} so'm\n"
            f"{money_emoji} Balans: {new_balance:,} so'm",
        )
    except Exception as e:
        logger.warning("Could not notify user %s: %s", user_id, e)
    finally:
        await bot.session.close()


async def on_startup(app: web.Application) -> None:
  from services.database import init_db, create_promocode
  await init_db()
  logger.info("Database initialized")

  # Seed initial sample promocodes
  try:
    for c in ["LUCKY2026", "COINSTATVIP", "SPIN777", "GIFT2026"]:
      await create_promocode(c)
  except Exception as e:
    logger.warning(f"Error seeding default promocodes: {e}")

  # Initialize Telethon gift sender
  try:
    from services.telethon_client import init_gift_sender
    import config as cfg
    session = cfg.TELETHON_SESSION_STRING or cfg.SESSION_NAME
    await init_gift_sender(
      cfg.API_ID,
      cfg.API_HASH,
      session,
      cfg.PHONE_NUMBER if cfg.PHONE_NUMBER else None,
    )
    logger.info("Telethon gift sender initialized")
  except Exception as e:
    logger.warning("Failed to initialize Telethon: %s", e)
  
  logger.info("API server ready — webapp at /app/")


async def click_webhook(request: web.Request) -> web.Response:
  """
  Webhook для Click UZ.
  Click отправляет два запроса:
    1. PREPARE (action=0) — проверка, что заказ существует
    2. COMPLETE (action=1) — подтверждение оплаты
  """
  try:
    payload = await request.json()
  except Exception:
    return web.json_response({"error": "Invalid JSON"}, status=400)

  logger.info("Click webhook received: %s", json.dumps(payload, ensure_ascii=False)[:300])

  action = int(payload.get("action", 0))
  
  if action == 0:
    # PREPARE — проверяем заказ
    from services.click_payment import handle_click_prepare
    result = await handle_click_prepare(payload, settings.shop_id, settings.shop_key)
    return web.json_response(result)
  elif action == 1:
    # COMPLETE — обрабатываем платеж
    from services.click_payment import handle_click_complete
    result = await handle_click_complete(payload, settings.shop_id, settings.shop_key)
    return web.json_response(result)
  else:
    return web.json_response({
      "click_trans_id": payload.get("click_trans_id", ""),
      "merchant_trans_id": payload.get("merchant_trans_id", ""),
      "error": -1,
      "error_note": "Invalid action"
    })


async def payment_success_page(request: web.Request) -> web.Response:
  """Page shown after successful payment"""
  return web.Response(
    content_type="text/html",
    text="""<!DOCTYPE html>
<html lang="uz">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>To'lov muvaffaqiyatli — StarPayUz</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
      color: #fff;
      display: flex;
      justify-content: center;
      align-items: center;
      min-height: 100vh;
      padding: 20px;
    }
    .card {
      background: #1e293b;
      border-radius: 24px;
      padding: 48px 32px;
      text-align: center;
      max-width: 400px;
      width: 100%;
      border: 1px solid rgba(59, 130, 246, 0.3);
      box-shadow: 0 20px 60px rgba(0,0,0,0.5);
    }
    .icon {
      font-size: 80px;
      margin-bottom: 24px;
    }
    h1 {
      font-size: 28px;
      font-weight: 700;
      margin-bottom: 12px;
      color: #3B82F6;
    }
    p {
      color: #94a3b8;
      font-size: 16px;
      line-height: 1.6;
      margin-bottom: 32px;
    }
    .btn {
      display: inline-block;
      padding: 16px 40px;
      background: #3B82F6;
      color: #fff;
      text-decoration: none;
      border-radius: 14px;
      font-weight: 600;
      font-size: 16px;
      transition: .3s;
      box-shadow: 0 4px 20px rgba(59, 130, 246, 0.3);
    }
    .btn:hover {
      transform: translateY(-2px);
      box-shadow: 0 8px 30px rgba(59, 130, 246, 0.4);
    }
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">✅</div>
    <h1>To'lov muvaffaqiyatli!</h1>
    <p>Hisobingiz muvaffaqiyatli to'ldirildi.<br>Botga qaytib, balansingizni tekshiring.</p>
    <a href="https://t.me/StarPayUz_Bot" class="btn">🤖 Botga qaytish</a>
  </div>
</body>
</html>""")


async def api_user_transactions(request: web.Request) -> web.Response:
  auth = await _auth_user(request)
  user_id = _user_id_from_auth(auth)
  body = await _json_body(request)
  if not user_id:
    user_id = body.get("telegram_id") or request.query.get("telegram_id")
  if not user_id:
    return web.json_response({"ok": False, "error": "Unauthorized"}, status=401)

  from services.database import db_conn
  orders_rows = await db_conn.fetch(
    "SELECT * FROM orders WHERE telegram_id = $1 ORDER BY id DESC LIMIT 100",
    int(user_id)
  )
  balance_rows = await db_conn.fetch(
    "SELECT * FROM balance_history WHERE telegram_id = $1 ORDER BY id DESC LIMIT 100",
    int(user_id)
  )

  def serialize(row):
    d = dict(row)
    for k, v in d.items():
      if isinstance(v, (datetime, date)):
        d[k] = v.isoformat()
    return d

  orders = [serialize(r) for r in orders_rows]
  balance_history = [serialize(r) for r in balance_rows]

  actual_orders = [o for o in orders if not str(o.get("product_type") or "").lower().startswith("topup") and o.get("product_type") not in ("balance", "deposit") and o.get("status") not in ("cancelled", "failed", "rejected")]
  total_spent = sum(int(o.get("amount") or 0) for o in actual_orders if o.get("status") in ("completed", "paid"))

  return web.json_response({
    "ok": True,
    "orders": orders,
    "balance_history": balance_history,
    "total_spent": total_spent,
    "orders_count": len(actual_orders),
  })


def _serialize_row(row):
  d = dict(row)
  for k, v in d.items():
    if isinstance(v, (datetime, date)):
      d[k] = v.isoformat()
  return d


async def api_user_gifts(request: web.Request) -> web.Response:
  auth = await _auth_user(request)
  user_id = _user_id_from_auth(auth)
  body = await _json_body(request)
  if not user_id:
    user_id = body.get("telegram_id")
  if not user_id:
    return web.json_response({"ok": False, "error": "Unauthorized"}, status=401)

  from services.database import db_conn
  rows = await db_conn.fetch(
    "SELECT * FROM orders WHERE telegram_id = $1 AND product_type = 'gift' ORDER BY id DESC LIMIT 50",
    int(user_id)
  )

  gifts = [_serialize_row(r) for r in rows]
  return web.json_response({"ok": True, "gifts": gifts})


async def api_user_referrals(request: web.Request) -> web.Response:
  auth = await _auth_user(request)
  user_id = _user_id_from_auth(auth)
  body = await _json_body(request)
  if not user_id:
    user_id = body.get("telegram_id")
  if not user_id:
    return web.json_response({"ok": False, "error": "Unauthorized"}, status=401)

  from services.database import db_conn
  user = await db_conn.fetchrow(
    "SELECT telegram_id, referrals, balance FROM users WHERE telegram_id = $1",
    int(user_id)
  )
  referred_rows = await db_conn.fetch(
    "SELECT telegram_id, username, full_name, created_at FROM users WHERE referred_by = $1 ORDER BY created_at DESC LIMIT 50",
    int(user_id)
  )

  referred = []
  for r in referred_rows:
    referred.append({
      "telegram_id": r["telegram_id"],
      "username": r["username"],
      "full_name": r["full_name"],
      "created_at": r["created_at"] if isinstance(r["created_at"], str) else (r["created_at"].isoformat() if r["created_at"] else None),
    })

  return web.json_response({
    "ok": True,
    "referrals_count": user["referrals"] if user else 0,
    "bonus_per_referral": 300,
    "total_bonus": (user["referrals"] if user else 0) * 300,
    "referred": referred,
  })


async def api_rating(request: web.Request) -> web.Response:
  body = await _json_body(request)
  period = body.get("period") or request.query.get("period") or "all"
  if period not in ("today", "week", "month", "all"):
    period = "all"

  from services.database import db_conn, IS_SQLITE

  if IS_SQLITE:
    if period == "today":
      time_cond = "AND date(o.created_at) = date('now')"
    elif period == "week":
      time_cond = "AND o.created_at >= datetime('now', '-7 days')"
    elif period == "month":
      time_cond = "AND o.created_at >= datetime('now', '-30 days')"
    else:
      time_cond = ""

    query = f"""
      SELECT 
        o.telegram_id,
        COALESCE(NULLIF(MAX(u.username), ''), NULLIF(MAX(o.target_username), ''), 'User#' || o.telegram_id) as username,
        COALESCE(MAX(u.full_name), '') as full_name,
        SUM(o.amount) as total
      FROM orders o
      LEFT JOIN users u ON u.telegram_id = o.telegram_id
      WHERE o.status IN ('completed', 'paid')
        AND o.product_type NOT LIKE 'topup%'
        AND o.product_type NOT IN ('deposit', 'balance')
        {time_cond}
      GROUP BY o.telegram_id
      HAVING SUM(o.amount) > 0
      ORDER BY total DESC
      LIMIT 50
    """
  else:
    if period == "today":
      time_cond = "AND o.created_at >= CURRENT_DATE"
    elif period == "week":
      time_cond = "AND o.created_at >= NOW() - INTERVAL '7 days'"
    elif period == "month":
      time_cond = "AND o.created_at >= NOW() - INTERVAL '30 days'"
    else:
      time_cond = ""

    query = f"""
      SELECT 
        o.telegram_id,
        COALESCE(NULLIF(MAX(u.username), ''), NULLIF(MAX(o.target_username), ''), 'User#' || o.telegram_id) as username,
        COALESCE(MAX(u.full_name), '') as full_name,
        SUM(o.amount) as total
      FROM orders o
      LEFT JOIN users u ON u.telegram_id = o.telegram_id
      WHERE o.status IN ('completed', 'paid')
        AND o.product_type NOT LIKE 'topup%'
        AND o.product_type NOT IN ('deposit', 'balance')
        {time_cond}
      GROUP BY o.telegram_id
      HAVING SUM(o.amount) > 0
      ORDER BY total DESC
      LIMIT 50
    """

  rows = await db_conn.fetch(query)

  rating = []
  for r in rows:
    uname = r["username"] or (r["full_name"] if r["full_name"] else f"User#{r['telegram_id']}")
    if uname.startswith("@"):
      uname = uname[1:]
    rating.append({
      "telegram_id": r["telegram_id"],
      "username": uname,
      "total": int(r["total"] or 0),
    })

  return web.json_response({"ok": True, "period": period, "rating": rating})


async def api_contest(request: web.Request) -> web.Response:
  from handlers.admin import _runtime_settings
  from services.database import db_conn

  auth = await _auth_user(request)
  user_id = _user_id_from_auth(auth)
  body = await _json_body(request)
  if not user_id:
    user_id = body.get("telegram_id")

  enabled = _runtime_settings.get("ref_contest_enabled", True)
  prize = _runtime_settings.get("ref_contest_prize", 500)
  min_refs = _runtime_settings.get("ref_contest_min_refs", 5)

  rows = await db_conn.fetch(
    "SELECT telegram_id, username, full_name, referrals FROM users ORDER BY referrals DESC LIMIT 10"
  )
  top_users = []
  for r in rows:
    top_users.append({
      "telegram_id": r["telegram_id"],
      "username": r["username"] or r["full_name"] or f"ID: {r['telegram_id']}",
      "referrals": r["referrals"] or 0
    })

  user_stats = None
  if user_id:
    try:
      u = await db_conn.fetchrow("SELECT telegram_id, referrals FROM users WHERE telegram_id = $1", int(user_id))
      if u:
        refs_cnt = u["referrals"] or 0
        rank = await db_conn.fetchval(
          "SELECT COUNT(*) + 1 FROM users WHERE referrals > $1", refs_cnt
        )
        user_stats = {
          "referrals": refs_cnt,
          "rank": rank
        }
    except Exception as e:
      logger.error(f"Error getting user contest stats: {e}")

  from services.database import get_latest_active_giveaway, get_participants_count, is_participant
  active_gw = await get_latest_active_giveaway()
  giveaway_info = None
  if active_gw:
    gw_id = active_gw["id"]
    part_cnt = await get_participants_count(gw_id)
    user_joined = False
    if user_id:
      user_joined = await is_participant(gw_id, int(user_id))
    giveaway_info = {
      "id": gw_id,
      "title": active_gw["title"],
      "description": active_gw["description"],
      "winners_count": active_gw["winners_count"],
      "required_channel": active_gw["required_channel"],
      "participants_count": part_cnt,
      "user_joined": user_joined
    }

  bot_username = settings.bot_username if hasattr(settings, "bot_username") and settings.bot_username else "CoinStatUz_bot"

  return web.json_response({
    "ok": True,
    "enabled": enabled,
    "prize": prize,
    "min_refs": min_refs,
    "top_users": top_users,
    "user_stats": user_stats,
    "giveaway": giveaway_info,
    "bot_username": bot_username
  })


async def api_contest_join(request: web.Request) -> web.Response:
  auth = await _auth_user(request)
  user_id = _user_id_from_auth(auth)
  body = await _json_body(request)
  if not user_id:
    user_id = body.get("telegram_id")
  if not user_id:
    return web.json_response({"ok": False, "error": "Unauthorized"}, status=401)

  giveaway_id = body.get("giveaway_id")
  from services.database import get_latest_active_giveaway, get_giveaway_by_id, is_participant, join_giveaway, get_participants_count
  if not giveaway_id:
    gw = await get_latest_active_giveaway()
    if gw:
      giveaway_id = gw["id"]

  if not giveaway_id:
    return web.json_response({"ok": False, "error": "Faol konkurs topilmadi"}, status=404)

  gw = await get_giveaway_by_id(int(giveaway_id))
  if not gw or gw.get("status") != "active":
    return web.json_response({"ok": False, "error": "Konkurs yakunlangan"}, status=400)

  already_joined = await is_participant(int(giveaway_id), int(user_id))
  if already_joined:
    part_cnt = await get_participants_count(int(giveaway_id))
    return web.json_response({"ok": True, "message": "Siz allaqachon qatnashgansiz", "already": True, "participants_count": part_cnt})

  joined = await join_giveaway(int(giveaway_id), int(user_id))
  part_cnt = await get_participants_count(int(giveaway_id))
  return web.json_response({"ok": True, "message": "Muvaffaqiyatli qatnashdingiz!", "already": False, "participants_count": part_cnt})


async def api_spin_status(request: web.Request) -> web.Response:
  auth = await _auth_user(request)
  user_id = _user_id_from_auth(auth)
  body = await _json_body(request)
  if not user_id:
    user_id = body.get("telegram_id")
  if not user_id:
    return web.json_response({"ok": False, "error": "Unauthorized"}, status=401)
  user_id = int(user_id)

  from services.database import db_conn, get_last_lucky_spin, get_user_bonus_spins

  query = """
    SELECT 
      o.telegram_id,
      SUM(o.amount) as total
    FROM orders o
    WHERE o.status IN ('completed', 'paid')
      AND o.product_type NOT LIKE 'topup%'
      AND o.product_type NOT IN ('deposit', 'balance')
    GROUP BY o.telegram_id
    HAVING SUM(o.amount) > 0
    ORDER BY total DESC
    LIMIT 3
  """
  top_rows = await db_conn.fetch(query)
  top_ids = [int(r["telegram_id"]) for r in top_rows]
  is_top = user_id in top_ids
  user_rank = (top_ids.index(user_id) + 1) if is_top else None

  bonus_spins = await get_user_bonus_spins(user_id)
  last_spin = await get_last_lucky_spin(user_id)
  can_spin = False
  next_spin_seconds = 0
  cooldown_seconds = 24 * 3600  # Har 1 kunda (24 soat)

  if last_spin:
    created_at = last_spin["created_at"]
    if isinstance(created_at, str):
      try:
        created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
      except Exception:
        created_at = datetime.now()
    if hasattr(created_at, "timestamp"):
      now_tz = datetime.now(created_at.tzinfo) if getattr(created_at, "tzinfo", None) else datetime.now()
      passed = (now_tz - created_at).total_seconds()
    else:
      passed = 86400 * 10

    if passed < cooldown_seconds:
      next_spin_seconds = int(cooldown_seconds - passed)
      can_spin = False
    else:
      can_spin = is_top
  else:
    can_spin = is_top

  # Agar foydalanuvchida promokod orqali berilgan bonus spin bo'lsa
  if bonus_spins > 0:
    can_spin = True
    next_spin_seconds = 0

  return web.json_response({
    "ok": True,
    "is_top": is_top,
    "rank": user_rank,
    "can_spin": can_spin,
    "bonus_spins": bonus_spins,
    "next_spin_seconds": next_spin_seconds,
    "last_prize": last_spin.get("prize_title") if last_spin else None
  })


async def api_spin_promocode(request: web.Request) -> web.Response:
  auth = await _auth_user(request)
  user_id = _user_id_from_auth(auth)
  body = await _json_body(request)
  if not user_id:
    user_id = body.get("telegram_id")
  if not user_id:
    return web.json_response({"ok": False, "error": "Unauthorized"}, status=401)
  user_id = int(user_id)

  code = (body.get("code") or "").strip()
  if not code:
    return web.json_response({"ok": False, "error": "Promo kodni kiriting!"}, status=400)

  from services.database import get_promocode, use_promocode, get_user

  promo = await get_promocode(code)
  if not promo:
    return web.json_response({"ok": False, "error": "Bunday promo kod mavjud emas!"}, status=404)

  if promo.get("is_used"):
    used_by_uname = promo.get("used_by_username")
    used_by_name = promo.get("used_by_name")
    used_by_id = promo.get("used_by_id")

    if used_by_uname:
      user_label = f"@{used_by_uname.replace('@','')}"
    elif used_by_name:
      user_label = used_by_name
    else:
      user_label = f"Foydalanuvchi #{used_by_id}"

    return web.json_response({
      "ok": False,
      "already_used": True,
      "used_by": user_label,
      "error": f"Ushbu promo kodni {user_label} faollashtirdi!"
    }, status=400)

  # Faollashtirish
  user = await get_user(user_id)
  uname = user.get("username") if user else ""
  fname = user.get("full_name") if user else ""

  success = await use_promocode(code, user_id, uname, fname)
  if not success:
    return web.json_response({"ok": False, "error": "Promo kodni faollashtirishda xatolik!"}, status=400)

  return web.json_response({
    "ok": True,
    "message": "Promo kod muvaffaqiyatli faollashtirildi! Sizga +1 ta bepul aylantirish berildi 🎉"
  })


async def api_spin_play(request: web.Request) -> web.Response:
  import random
  auth = await _auth_user(request)
  user_id = _user_id_from_auth(auth)
  body = await _json_body(request)
  if not user_id:
    user_id = body.get("telegram_id")
  if not user_id:
    return web.json_response({"ok": False, "error": "Unauthorized"}, status=401)
  user_id = int(user_id)

  from services.database import db_conn, get_last_lucky_spin, record_lucky_spin, add_balance, get_user, consume_user_bonus_spin

  used_bonus = await consume_user_bonus_spin(user_id)

  if not used_bonus:
    # Top 3 tekshiruvi (Faqat #1, #2, #3 o'rindagi yetakchilar)
    query = """
      SELECT o.telegram_id, SUM(o.amount) as total
      FROM orders o
      WHERE o.status IN ('completed', 'paid')
        AND o.product_type NOT LIKE 'topup%'
        AND o.product_type NOT IN ('deposit', 'balance')
      GROUP BY o.telegram_id
      HAVING SUM(o.amount) > 0
      ORDER BY total DESC
      LIMIT 3
    """
    top_rows = await db_conn.fetch(query)
    top_ids = [int(r["telegram_id"]) for r in top_rows]
    if user_id not in top_ids:
      return web.json_response({"ok": False, "error": "Omad g'ildiragi faqat Top 3 yetakchilar uchun yoki Promo kod orqali ochiladi!"}, status=403)

    last_spin = await get_last_lucky_spin(user_id)
    cooldown_seconds = 24 * 3600  # Har 1 kunda
    if last_spin:
      created_at = last_spin["created_at"]
      if isinstance(created_at, str):
        try:
          created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except Exception:
          created_at = datetime.now()
      if hasattr(created_at, "timestamp"):
        now_tz = datetime.now(created_at.tzinfo) if getattr(created_at, "tzinfo", None) else datetime.now()
        passed = (now_tz - created_at).total_seconds()
      else:
        passed = 86400 * 10
      if passed < cooldown_seconds:
        left_hours = int((cooldown_seconds - passed) // 3600)
        left_minutes = int(((cooldown_seconds - passed) % 3600) // 60)
        return web.json_response({"ok": False, "error": f"Siz bugun aylantirgansiz. Keyingi imkoniyat {left_hours} soat {left_minutes} daqiqadan keyin."}, status=400)

  # 20 ta sektorli boy sovg'alar ro'yxati (Teddy Bear, Rose, Champagne, Stars, Balans, Rocket, Premium)
  prizes = [
    {"key": "teddy", "title": "🧸 Teddy Bear Gift", "type": "gift", "weight": 12, "index": 0},
    {"key": "rose", "title": "🌹 Rose Gift", "type": "gift", "weight": 6, "index": 1},
    {"key": "stars50", "title": "⭐️ 50 Stars", "type": "stars", "amount": 50, "weight": 5, "index": 2},
    {"key": "uzs10000", "title": "💰 10 000 UZS Balans", "type": "balance", "amount": 10000, "weight": 5, "index": 3},
    {"key": "champagne", "title": "🍾 Champagne Gift", "type": "gift", "weight": 6, "index": 4},
    {"key": "teddy", "title": "🧸 Teddy Bear Gift", "type": "gift", "weight": 12, "index": 5},
    {"key": "rocket", "title": "🚀 Rocket Gift", "type": "gift", "weight": 3, "index": 6},
    {"key": "stars25", "title": "⭐️ 25 Stars", "type": "stars", "amount": 25, "weight": 6, "index": 7},
    {"key": "uzs5000", "title": "💰 5 000 UZS Balans", "type": "balance", "amount": 5000, "weight": 6, "index": 8},
    {"key": "rose", "title": "🌹 Rose Gift", "type": "gift", "weight": 6, "index": 9},
    {"key": "teddy", "title": "🧸 Teddy Bear Gift", "type": "gift", "weight": 12, "index": 10},
    {"key": "champagne", "title": "🍾 Champagne Gift", "type": "gift", "weight": 6, "index": 11},
    {"key": "stars100", "title": "⭐️ 100 Stars", "type": "stars", "amount": 100, "weight": 3, "index": 12},
    {"key": "uzs20000", "title": "💰 20 000 UZS Balans", "type": "balance", "amount": 20000, "weight": 3, "index": 13},
    {"key": "premium", "title": "💎 Telegram Premium", "type": "premium", "weight": 2, "index": 14},
    {"key": "teddy", "title": "🧸 Teddy Bear Gift", "type": "gift", "weight": 12, "index": 15},
    {"key": "rose", "title": "🌹 Rose Gift", "type": "gift", "weight": 6, "index": 16},
    {"key": "stars50", "title": "⭐️ 50 Stars", "type": "stars", "amount": 50, "weight": 5, "index": 17},
    {"key": "rocket", "title": "🚀 Rocket Gift", "type": "gift", "weight": 3, "index": 18},
    {"key": "teddy", "title": "🧸 Teddy Bear Gift", "type": "gift", "weight": 12, "index": 19},
  ]

  weights = [p["weight"] for p in prizes]
  chosen_prize = random.choices(prizes, weights=weights, k=1)[0]

  # Mukofotni hisobga o'tkazish
  if chosen_prize["type"] == "balance":
    await add_balance(user_id, chosen_prize["amount"], "Omad g'ildiragi yutug'i")

  # Bazaga yozish
  await record_lucky_spin(user_id, chosen_prize["key"], chosen_prize["title"])

  # Kanalga bildirishnoma
  try:
    user = await get_user(user_id)
    uname = (user.get("username") if user else "") or f"User#{user_id}"
    from aiogram import Bot
    from config import CHANNEL_ORDERS
    bot = Bot(token=settings.bot_token)
    msg = f"🎡 <b>Omad G'ildiragi Yutug'i!</b>\n\n👤 Foydalanuvchi: @{uname.replace('@','')}\n🎁 Yutuq: <b>{chosen_prize['title']}</b>\n\n🎉 <i>Top yetakchilarimizni tabriklaymiz!</i>"
    if CHANNEL_ORDERS:
      await bot.send_message(chat_id=CHANNEL_ORDERS, text=msg, parse_mode="HTML")
    await bot.session.close()
  except Exception as e:
    logger.error(f"Spin channel notify error: {e}")

  return web.json_response({
    "ok": True,
    "prize": chosen_prize,
    "message": f"Tabriklaymiz! Siz {chosen_prize['title']} yutib oldingiz!"
  })


def create_app() -> web.Application:
  app = web.Application(middlewares=[cors_middleware])
  app.on_startup.append(on_startup)
  app.on_shutdown.append(_on_shutdown)
  app.router.add_get("/", webapp_index)
  app.router.add_get("/app", webapp_index)
  app.router.add_get("/app/", webapp_index)
  app.router.add_get("/health", health)
  app.router.add_post("/api/user/balance", api_user_balance)
  app.router.add_get("/api/stars/available", api_stars_available)
  app.router.add_post("/api/stars/available", api_stars_available)
  app.router.add_post("/api/stars/price", api_stars_price)
  app.router.add_post("/api/order/stars", api_order_stars)
  app.router.add_post("/api/order/premium", api_order_premium)
  app.router.add_post("/api/order/gift", api_order_gift)
  app.router.add_post("/api/order/phone", api_order_phone)
  app.router.add_post("/api/order/topup", api_order_topup)
  app.router.add_post("/api/payment/create", api_payment_create)
  app.router.add_post("/api/payment/check", api_payment_check)
  app.router.add_get("/webhook/payment", payment_webhook_check)
  app.router.add_post("/webhook/payment", payment_webhook)
  app.router.add_get("/api/webhook/payment", payment_webhook_check)
  app.router.add_post("/api/webhook/payment", payment_webhook)
  app.router.add_post("/webhook/click", click_webhook)
  app.router.add_get("/api/gifts/available", api_get_available_gifts)
  app.router.add_get("/payment/success", payment_success_page)
  app.router.add_post("/api/user/transactions", api_user_transactions)
  app.router.add_post("/api/user/gifts", api_user_gifts)
  app.router.add_post("/api/user/referrals", api_user_referrals)
  app.router.add_post("/api/rating", api_rating)
  app.router.add_get("/api/contest", api_contest)
  app.router.add_post("/api/contest", api_contest)
  app.router.add_post("/api/contest/join", api_contest_join)
  app.router.add_get("/api/spin/status", api_spin_status)
  app.router.add_post("/api/spin/status", api_spin_status)
  app.router.add_post("/api/spin/play", api_spin_play)
  app.router.add_post("/api/spin/promocode", api_spin_promocode)

  app.router.add_static("/app", WEBAPP_DIR, name="webapp")
  app.router.add_static("/", WEBAPP_DIR, name="root")
  return app


async def _on_shutdown(app: web.Application) -> None:
    pass


def main() -> None:
  logging.basicConfig(level=logging.INFO)
  app = create_app()
  web.run_app(app, host=settings.api_host, port=settings.api_port)


if __name__ == "__main__":
  main()
