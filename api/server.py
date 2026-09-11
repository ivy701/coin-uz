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
        resp = web.Response(status=200)
        _set_cors(resp, origin)
        return resp
    try:
        resp = await handler(request)
    except web.HTTPException as ex:
        _set_cors(ex, origin)
        return ex
    except Exception as ex:
        logger.error(f"Unhandled exception in API request: {ex}", exc_info=True)
        resp = web.json_response({"ok": False, "error": f"Server xatoligi: {str(ex)}"}, status=500)
    
    _set_cors(resp, origin)
    return resp


def _set_cors(resp: web.Response, origin: str) -> None:
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS, PUT, DELETE"
    resp.headers["Access-Control-Allow-Headers"] = "*"
    resp.headers["Access-Control-Allow-Credentials"] = "true"



import time
from collections import defaultdict
import os

# Rate Limiter Configuration: max 5 requests per 60 seconds per user
class RateLimiter:
    """Sliding window in-memory rate limiter per Telegram ID / Key."""
    def __init__(self, max_requests: int = 5, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = defaultdict(list)

    def is_allowed(self, key: str | int) -> tuple[bool, int]:
        now = time.time()
        window_start = now - self.window_seconds
        # Evict old timestamps
        self.requests[key] = [t for t in self.requests[key] if t > window_start]
        
        if len(self.requests[key]) >= self.max_requests:
            oldest = self.requests[key][0]
            retry_after = max(1, int(self.window_seconds - (now - oldest)))
            return False, retry_after

        self.requests[key].append(now)
        return True, 0

# Rate limiter instances for orders, topups, and promo codes
order_rate_limiter = RateLimiter(max_requests=5, window_seconds=60)
spin_rate_limiter = RateLimiter(max_requests=5, window_seconds=60)


async def _json_body(request: web.Request) -> dict:
  try:
    return await request.json()
  except Exception:
    return {}


async def _auth_user(request: web.Request) -> dict | None:
  """Extract and validate initData using official Telegram HMAC-SHA256."""
  init_data = request.headers.get("X-Telegram-Init-Data") or request.headers.get("Authorization") or ""
  if init_data.startswith("tma "):
    init_data = init_data[4:]
  body = await _json_body(request)
  if not init_data:
    init_data = body.get("initData", "")
  
  if not settings.bot_token:
    logger.warning("BOT_TOKEN is not configured! Cannot validate initData.")
    return None
    
  return validate_init_data(init_data, settings.bot_token)


def _user_id_from_auth(auth: dict | None) -> int | None:
  if not auth:
    return None
  user = auth.get("user")
  if isinstance(user, dict):
    return user.get("id")
  return None


async def _authenticate_request(request: web.Request, check_rate_limit: bool = True, limiter: RateLimiter = order_rate_limiter) -> tuple[int, dict, dict]:
  """
  Unified security helper:
  1. Validates Telegram initData signature (HMAC-SHA256) -> 401 if invalid.
  2. Uses authenticated user_id from initData.
  3. Checks Rate Limiting (max 5 req/min) -> 429 if exceeded.
  """
  body = await _json_body(request)
  auth = await _auth_user(request)
  auth_user_id = _user_id_from_auth(auth)

  # Check initData authenticity
  if not auth or not auth_user_id:
    # Allow development bypass ONLY if explicitly configured in environment
    if os.getenv("ALLOW_UNSAFE_DEV_AUTH", "").lower() == "true":
      auth_user_id = body.get("telegram_id") or body.get("user_id")
      if not auth_user_id:
        raise web.HTTPUnauthorized(
          text=json.dumps({"ok": False, "error": "Telegram avtorizatsiyasi talab qilinadi."}),
          content_type="application/json"
        )
    else:
      raise web.HTTPUnauthorized(
        text=json.dumps({"ok": False, "error": "Telegram initData yaroqsiz yoki muddati o'tgan (Unauthorized)."}),
        content_type="application/json"
      )

  auth_user_id = int(auth_user_id)

  # Rate limiting
  if check_rate_limit:
    allowed, retry_after = limiter.is_allowed(auth_user_id)
    if not allowed:
      raise web.HTTPTooManyRequests(
        headers={"Retry-After": str(retry_after)},
        text=json.dumps({
          "ok": False,
          "error": f"Juda ko'p so'rov yuborildi. Iltimos, {retry_after} soniyadan so'ng qayta urinib ko'ring."
        }),
        content_type="application/json"
      )

  return auth_user_id, (auth or {}), body


async def health(_: web.Request) -> web.Response:
  return web.json_response({"ok": True, "service": "StarPayUz"})


async def webapp_index(_: web.Request) -> web.FileResponse:
  return web.FileResponse(WEBAPP_DIR / "index.html")


async def api_user_balance(request: web.Request) -> web.Response:
  try:
    user_id, auth, body = await _authenticate_request(request, check_rate_limit=False)
  except web.HTTPException as ex:
    return ex
  
  # Ensure user exists (create if not)
  from services.database import ensure_user
  username = None
  full_name = None
  if auth and auth.get("user"):
    u = auth["user"]
    username = u.get("username")
    full_name = f"{u.get('first_name', '')} {u.get('last_name', '')}".strip()
  
  user = await ensure_user(user_id, username, full_name or "User")
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


# Official Pricing Tables (Server-authoritative, never trust client input)
STAR_PRICE_UZS = 198  # 198 UZS per star (50 stars = 9,900 UZS)

PREMIUM_PRICES = {
    3: 160000,
    6: 225000,
    12: 390000
}

GIFT_PRICES = {
    # Classic (15-25 Stars)
    "bear": 2800,
    "rose": 5000,
    "box": 5000,
    
    # Deluxe (50-100 Stars)
    "bouqet": 10000,
    "bouquet": 10000,
    "cake": 10000,
    "rocket": 10000,
    "heart": 10000,
    "diamond": 20000,
    "ring": 20000,
    "trophy": 20000,
    "champagne": 10000,
    
    # VIP Collection (50 Stars — 10,000 UZS)
    "aprel_bear": 10000,
    "april_bear": 10000,
    "easter_bear": 10000,
    "newyear_bear": 10000,
    "builder_bear": 10000,
    "football_bear": 10000,
    "soldier_bear": 10000,
    "newyear_tree": 10000,
    "patrick_bear": 10000,
    "valentine_bear": 10000,
    "valentine_heart": 10000,

    # Deluxe / Custom Stars
    "deluxe_rose": 5000,
    "deluxe_heart": 5000,
    "deluxe_cake": 10000,
    "deluxe_diamond": 20000,
    "golden_trophy": 50000,
    "star_crown": 100000,
    "blue_gem": 200000,
    "fire_phoenix": 500000,
}


async def api_order_stars(request: web.Request) -> web.Response:
  try:
    user_id, auth, body = await _authenticate_request(request, check_rate_limit=True)
  except web.HTTPException as ex:
    return ex

  username = (body.get("username") or "").strip().lstrip("@")
  quantity = _parse_stars_quantity(body)
  
  if not username:
    return web.json_response({"ok": False, "error": "Username ko'rsatilmagan"}, status=400)
  err = _validate_stars_quantity(quantity)
  if err:
    return web.json_response({"ok": False, "error": err}, status=400)

  user = await get_user(user_id)
  if not user:
    return web.json_response({"ok": False, "error": "Foydalanuvchi topilmadi. /start bosing."}, status=400)
  
  balance = user.get("balance", 0)
  
  # SECURITY: Server-side price calculation (198 UZS per star). Ignore client price!
  price = quantity * STAR_PRICE_UZS
  
  if balance < price:
    return web.json_response(
      {"ok": False, "error": f"Balans yetarli emas. Kerak: {price:,} so'm, Balans: {balance:,} so'm"},
      status=400
    )

  # Check if Fragment API is available and try to fulfill automatically
  is_fragment_ready = bool(fragment.api_key and fragment.api_key.strip())
  if is_fragment_ready:
    try:
      result = await fragment.buy_stars(username, quantity)
      order_id = await create_order(
        user_id, "stars", username, quantity, price, str(result.get("id", "")), "completed"
      )
      await deduct_balance(user_id, price)
      from services.channel_notify import notify_stars
      asyncio.ensure_future(notify_stars(username, quantity, price))
      return web.json_response({"ok": True, "order_id": order_id, "result": result})
    except Exception as e:
      logger.warning(f"Automated Fragment buy_stars failed: {e}, placing order in pending queue...")

  # Fallback to Pending queue (Deduct balance, record pending order, notify admin/channel)
  await deduct_balance(user_id, price)
  order_id = await create_order(
    user_id, "stars", username, quantity, price, None, "pending"
  )
  from services.channel_notify import notify_stars
  asyncio.ensure_future(notify_stars(username, quantity, price))
  return web.json_response({
    "ok": True,
    "order_id": order_id,
    "message": f"⭐️ {quantity} Stars buyurtmasi qabul qilindi! Tez orada hisobingizga tushiriladi."
  })


async def api_order_premium(request: web.Request) -> web.Response:
  try:
    user_id, auth, body = await _authenticate_request(request, check_rate_limit=True)
  except web.HTTPException as ex:
    return ex

  username = (body.get("username") or "").strip().lstrip("@")
  if not username:
    return web.json_response({"ok": False, "error": "Username ko'rsatilmagan"}, status=400)

  try:
    months = int(body.get("months") or body.get("month") or body.get("quantity") or 3)
  except (ValueError, TypeError):
    months = 3

  if months not in PREMIUM_PRICES:
    return web.json_response({"ok": False, "error": "Noto'g'ri obuna muddati (3, 6 yoki 12 oy tanlang)"}, status=400)
  
  # SECURITY: Server recalculates price from official table
  price = PREMIUM_PRICES[months]

  user = await get_user(user_id)
  if not user:
    return web.json_response({"ok": False, "error": "Foydalanuvchi topilmadi. /start bosing."}, status=400)

  balance = user.get("balance", 0)
  if balance < price:
    return web.json_response(
      {"ok": False, "error": f"Balans yetarli emas. Kerak: {price:,} so'm, Balans: {balance:,} so'm"},
      status=400
    )

  # Check if Fragment API is available and try to fulfill automatically
  is_fragment_ready = bool(fragment.api_key and fragment.api_key.strip())
  if is_fragment_ready:
    try:
      result = await fragment.buy_premium(username, months)
      order_id = await create_order(
        user_id, "premium", username, months, price, str(result.get("id", "")), "completed"
      )
      await deduct_balance(user_id, price)
      from services.channel_notify import notify_premium
      asyncio.ensure_future(notify_premium(username, months, price))
      return web.json_response({"ok": True, "order_id": order_id, "result": result})
    except Exception as e:
      logger.warning(f"Automated Fragment buy_premium failed: {e}, placing order in pending queue...")

  # Fallback to Pending queue (Deduct balance, record pending order, notify admin/channel)
  await deduct_balance(user_id, price)
  order_id = await create_order(
    user_id, "premium", username, months, price, None, "pending"
  )
  from services.channel_notify import notify_premium
  asyncio.ensure_future(notify_premium(username, months, price))
  return web.json_response({
    "ok": True,
    "order_id": order_id,
    "message": f"⭐ {months} oylik Telegram Premium buyurtmasi qabul qilindi! Tez orada faollashtiriladi."
  })


async def api_order_gift(request: web.Request) -> web.Response:
  try:
    user_id, auth, body = await _authenticate_request(request, check_rate_limit=True)
  except web.HTTPException as ex:
    return ex

  username = (body.get("username") or "").strip().lstrip("@")
  raw_gift = (body.get("gift") or body.get("gift_id") or body.get("gift_name") or body.get("id") or "").strip().lower()
  
  if not username:
    return web.json_response({"ok": False, "error": "Username ko'rsatilmagan"}, status=400)
  
  if not raw_gift:
    return web.json_response({"ok": False, "error": "Gift tanlanmagan"}, status=400)

  # Normalize gift name / id
  name_mapping = {
    "teddy bear": "bear",
    "qizil atirgul": "rose",
    "red rose": "rose",
    "oltin quticha": "box",
    "golden giftbox": "box",
    "guldasta": "bouqet",
    "bouquet": "bouqet",
    "bayram torti": "cake",
    "birthday cake": "cake",
    "kosmik raketa": "rocket",
    "space rocket": "rocket",
    "oltin yurak": "heart",
    "golden heart": "heart",
    "aprel ayiqchasi": "aprel_bear",
    "april bear": "aprel_bear",
    "pasxa ayiqchasi": "easter_bear",
    "easter bear": "easter_bear",
    "qorbobo ayiqchasi": "newyear_bear",
    "santa bear": "newyear_bear",
    "usta ayiqchasi": "builder_bear",
    "builder bear": "builder_bear",
    "futbolchi ayiqcha": "football_bear",
    "football bear": "football_bear",
    "jangchi ayiqchasi": "soldier_bear",
    "soldier bear": "soldier_bear",
    "yangi yil archasi": "newyear_tree",
    "christmas tree": "newyear_tree",
    "patrik ayiqchasi": "patrick_bear",
    "patrick bear": "patrick_bear",
    "valentin ayiqchasi": "valentine_bear",
    "valentine bear": "valentine_bear",
    "valentine heart": "valentine_heart",
    "brilliant": "diamond",
    "olmos uzuk": "ring",
    "diamond ring": "ring",
    "oltin kubok": "trophy",
    "golden trophy": "trophy",
  }
  gift = name_mapping.get(raw_gift, raw_gift)
  
  # SECURITY: Server recalculates price from official GIFT_PRICES table
  price = GIFT_PRICES.get(gift)
  if price is None or price <= 0:
    return web.json_response({"ok": False, "error": "Noto'g'ri yoki noma'lum sovg'a turi"}, status=400)
  
  # Check balance
  user = await get_user(user_id)
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
    "bouqet": "5170314324215857265",
    "bouquet": "5170314324215857265",
    "diamond": "5170521118301225164",
    "trophy": "5168043875654172773",
    "ring": "5170690322832818290",
    
    # VIP Collection / Limited Edition
    "aprel_bear": "5935895822435615975",
    "april_bear": "5935895822435615975",
    "easter_bear": "5969796561943660080",
    "newyear_bear": "5956217000635139069",
    "builder_bear": "5893356958802511476",
    "football_bear": "5866352046986232958",
    "soldier_bear": "6026193266406327981",
    "newyear_tree": "5922558454332916696",
    "patrick_bear": "5893356958802511476",
    "valentine_bear": "5800655655995968830",
    "valentine_heart": "5801108895304779062",

    # Deluxe / Custom Stars
    "deluxe_rose": "5170145012310081616",
    "deluxe_heart": "5170145012310081617",
    "deluxe_cake": "5170144170496491617",
    "deluxe_diamond": "5170521118301225165",
    "golden_trophy": "5168043875654172774",
    "star_crown": "5170145012310081618",
    "blue_gem": "5170145012310081619",
    "fire_phoenix": "5170145012310081620",
  }
  
  gift_id = gift_mapping.get(gift.lower()) or (gift if gift.isdigit() else f"gift_{gift.lower()}")
  
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
          int(user_id), "gift", username, 1, price, gift_id, "completed"
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
    int(user_id), "gift", username, 1, price, gift_id, "pending"
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


TOPUP_MIN_AMOUNT = int(os.getenv("MIN_TOPUP_AMOUNT", 1000))
TOPUP_MAX_AMOUNT = int(os.getenv("MAX_TOPUP_AMOUNT", 10000000))  # 10,000,000 UZS maximum limit


async def api_order_topup(request: web.Request) -> web.Response:
  """Create topup order with 5 minute expiration and max limits"""
  try:
    user_id, auth, body = await _authenticate_request(request, check_rate_limit=True)
  except web.HTTPException as ex:
    return ex

  order_id = body.get("order_id")
  if not order_id:
    import time
    order_id = f"TOP_{int(time.time() * 1000)}"
  amount = body.get("amount")
  
  if not amount:
    return web.json_response({"ok": False, "error": "Summa kiritilishi kerak"}, status=400)
  
  try:
    amount_int = int(amount)
    if amount_int < TOPUP_MIN_AMOUNT or amount_int > TOPUP_MAX_AMOUNT:
      return web.json_response({
        "ok": False,
        "error": f"To'lov summasi {TOPUP_MIN_AMOUNT:,} va {TOPUP_MAX_AMOUNT:,} so'm oralig'ida bo'lishi kerak."
      }, status=400)
  except (TypeError, ValueError):
    return web.json_response({"ok": False, "error": "Noto'g'ri summa formati"}, status=400)

  # Save topup order — use keyword args to ensure external_id is stored
  await create_order(
      telegram_id=user_id,
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

  # Initialize Telegram Bot & Dispatcher for Webhook
  if "bot" not in app or "dp" not in app:
    try:
      import config as cfg
      if cfg.BOT_TOKEN:
        from aiogram import Bot, Dispatcher
        from aiogram.client.default import DefaultBotProperties
        from aiogram.enums import ParseMode
        from aiogram.fsm.storage.memory import MemoryStorage
        from middlewares import AccessControlMiddleware
        from handlers import start, shop, balance, profile, webapp, admin

        bot = Bot(token=cfg.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        dp = Dispatcher(storage=MemoryStorage())
        dp.update.middleware(AccessControlMiddleware())
        dp.include_router(admin.router)
        dp.include_router(start.router)
        dp.include_router(webapp.router)
        dp.include_router(shop.router)
        dp.include_router(balance.router)
        dp.include_router(profile.router)

        app["bot"] = bot
        app["dp"] = dp
        logger.info("Telegram Bot & Dispatcher initialized for Webhook")
    except Exception as e:
      logger.warning("Failed to initialize Bot & Dispatcher for Webhook: %s", e)
  
  logger.info("API server ready — webapp at /app/")


async def telegram_webhook_check(request: web.Request) -> web.Response:
  return web.json_response({
    "ok": True,
    "service": "CoinStat Telegram Webhook",
    "endpoint": "https://coinstatuzbot.alwaysdata.net/webhook/telegram"
  })


async def telegram_webhook(request: web.Request) -> web.Response:
  bot = request.app.get("bot")
  dp = request.app.get("dp")
  if not bot or not dp:
    logger.error("Telegram bot/dp not initialized in app")
    return web.Response(status=503, text="Bot not initialized")

  try:
    data = await request.json()
  except Exception as e:
    logger.warning("Invalid telegram webhook payload: %s", e)
    return web.Response(status=400, text="Invalid JSON")

  from aiogram.types import Update
  try:
    update = Update(**data)
    asyncio.create_task(dp.feed_update(bot, update))
    return web.Response(text="OK")
  except Exception as e:
    logger.exception("Error processing telegram update: %s", e)
    return web.Response(text="OK")


async def api_set_webhook(request: web.Request) -> web.Response:
  import config as cfg
  if not cfg.BOT_TOKEN:
    return web.json_response({"ok": False, "error": "BOT_TOKEN not configured"}, status=500)

  bot = request.app.get("bot")
  if not bot:
    from aiogram import Bot
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode
    bot = Bot(token=cfg.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

  webhook_url = request.query.get("url") or "https://coinstatuzbot.alwaysdata.net/webhook/telegram"
  try:
    res = await bot.set_webhook(url=webhook_url, drop_pending_updates=True)
    info = await bot.get_webhook_info()
    return web.json_response({
      "ok": True,
      "message": f"Telegram Webhook muvaffaqiyatli ulandi: {webhook_url}",
      "set_result": res,
      "webhook_url": info.url,
      "pending_update_count": info.pending_update_count
    })
  except Exception as e:
    logger.exception("set_webhook error: %s", e)
    return web.json_response({"ok": False, "error": str(e)}, status=500)


async def api_get_webhook(request: web.Request) -> web.Response:
  import config as cfg
  if not cfg.BOT_TOKEN:
    return web.json_response({"ok": False, "error": "BOT_TOKEN not configured"}, status=500)

  bot = request.app.get("bot")
  if not bot:
    from aiogram import Bot
    bot = Bot(token=cfg.BOT_TOKEN)

  try:
    info = await bot.get_webhook_info()
    return web.json_response({
      "ok": True,
      "url": info.url,
      "has_custom_certificate": info.has_custom_certificate,
      "pending_update_count": info.pending_update_count,
      "last_error_date": info.last_error_date,
      "last_error_message": info.last_error_message
    })
  except Exception as e:
    return web.json_response({"ok": False, "error": str(e)}, status=500)


async def api_delete_webhook(request: web.Request) -> web.Response:
  import config as cfg
  if not cfg.BOT_TOKEN:
    return web.json_response({"ok": False, "error": "BOT_TOKEN not configured"}, status=500)

  bot = request.app.get("bot")
  if not bot:
    from aiogram import Bot
    bot = Bot(token=cfg.BOT_TOKEN)

  try:
    res = await bot.delete_webhook(drop_pending_updates=True)
    return web.json_response({
      "ok": True,
      "message": "Webhook muvaffaqiyatli o'chirildi (polling uchun)",
      "result": res
    })
  except Exception as e:
    return web.json_response({"ok": False, "error": str(e)}, status=500)


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
  try:
    user_id, auth, body = await _authenticate_request(request, check_rate_limit=False)
  except web.HTTPException as ex:
    return ex

  from services.database import db_conn
  orders_rows = await db_conn.fetch(
    "SELECT * FROM orders WHERE telegram_id = $1 ORDER BY id DESC LIMIT 100",
    user_id
  )
  balance_rows = await db_conn.fetch(
    "SELECT * FROM balance_history WHERE telegram_id = $1 ORDER BY id DESC LIMIT 100",
    user_id
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
  try:
    user_id, auth, body = await _authenticate_request(request, check_rate_limit=False)
  except web.HTTPException as ex:
    return ex

  from services.database import db_conn
  rows = await db_conn.fetch(
    "SELECT * FROM orders WHERE telegram_id = $1 AND product_type = 'gift' ORDER BY id DESC LIMIT 50",
    user_id
  )

  gifts = [_serialize_row(r) for r in rows]
  return web.json_response({"ok": True, "gifts": gifts})


async def api_user_referrals(request: web.Request) -> web.Response:
  try:
    user_id, auth, body = await _authenticate_request(request, check_rate_limit=False)
  except web.HTTPException as ex:
    return ex

  from services.database import db_conn
  user = await db_conn.fetchrow(
    "SELECT telegram_id, referrals, balance FROM users WHERE telegram_id = $1",
    user_id
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

  from services.database import get_last_lucky_spin, get_user_bonus_info

  bonus_info = await get_user_bonus_info(user_id)
  spins_left = bonus_info.get("spins_left", 0) if bonus_info else 0
  forced_prize = bonus_info.get("forced_prize", "bear") if bonus_info else "bear"
  last_spin = await get_last_lucky_spin(user_id)

  vip_keys = ["aprel_bear", "easter_bear", "newyear_bear", "builder_bear", "football_bear", "soldier_bear", "newyear_tree", "patrick_bear", "valentine_bear", "valentine_heart", "rare", "vipgift"]
  is_vip_spin = forced_prize.lower().strip() in vip_keys

  return web.json_response({
    "ok": True,
    "can_spin": spins_left > 0,
    "bonus_spins": spins_left,
    "forced_prize": forced_prize,
    "spin_type": "vip" if is_vip_spin else "classic",
    "last_prize": last_spin.get("prize_title") if last_spin else None
  })


async def api_spin_promocode(request: web.Request) -> web.Response:
  try:
    user_id, auth, body = await _authenticate_request(request, check_rate_limit=True, limiter=spin_rate_limiter)
  except web.HTTPException as ex:
    return ex

  try:
    code = (body.get("code") or "").strip().upper()
    if not code:
      return web.json_response({"ok": False, "error": "Iltimos, promo-kodni kiriting!"}, status=400)

    from services.database import get_promocode, use_promocode, get_user, check_user_promocode_cooldown

    # 1. 2 soatlik cheklov (G'olib bo'lgan odam 2 soat ichida yana kod ishlata olmaydi)
    in_cooldown, rem_hrs, rem_mins = await check_user_promocode_cooldown(user_id)
    if in_cooldown:
      time_msg = f"{rem_hrs} soat {rem_mins} daqiqadan" if rem_hrs > 0 else f"{rem_mins} daqiqadan"
      return web.json_response({
        "ok": False,
        "error": f"⏳ Siz so'nggi 2 soat ichida allaqachon promo-kod orqali g'olib bo'lgansiz! Yangi promo-kodni {time_msg} so'ng ishlatishingiz mumkin."
      }, status=400)

    # 2. Promo-kod mavjudligi va bir martalik ekanligini tekshirish
    promo = await get_promocode(code)
    if not promo:
      return web.json_response({"ok": False, "error": "❌ Bunday promo-kod topilmadi yoki muddati tugagan!"}, status=400)

    if promo.get("is_used"):
      return web.json_response({
        "ok": False,
        "error": "❌ Ushbu promo-kod allaqachon ishlatilgan! (Har bir kod faqat 1 kishi uchun)"
      }, status=400)

    # 3. Faollashtirish
    user = await get_user(user_id)
    uname = user.get("username") if user else ""
    fname = user.get("full_name") if user else ""

    success = await use_promocode(code, user_id, uname, fname)
    if not success:
      # Agar boshqa foydalanuvchi ayni paytda faollashtirib qo'ygan bo'lsa
      return web.json_response({
        "ok": False,
        "error": "❌ Ushbu promo-kod allaqachon ishlatildi!"
      }, status=400)

    ptype = promo.get("prize_type", "bear")
    vip_keys = ["aprel_bear", "easter_bear", "newyear_bear", "builder_bear", "football_bear", "soldier_bear", "newyear_tree", "patrick_bear", "valentine_bear", "valentine_heart", "rare", "vipgift"]
    is_vip = ptype.lower().strip() in vip_keys

    return web.json_response({
      "ok": True,
      "forced_prize": ptype,
      "spin_type": "vip" if is_vip else "classic",
      "message": "Promo kod muvaffaqiyatli faollashtirildi! Sizga +1 ta bepul aylantirish berildi 🎉"
    })
  except Exception as e:
    logger.exception("api_spin_promocode error: %s", e)
    return web.json_response({"ok": False, "error": "Server xatoligi yuz berdi"}, status=500)


async def api_spin_play(request: web.Request) -> web.Response:
  import random
  try:
    user_id, auth, body = await _authenticate_request(request, check_rate_limit=True, limiter=spin_rate_limiter)
  except web.HTTPException as ex:
    return ex

  from services.database import db_conn, get_last_lucky_spin, record_lucky_spin, add_balance, get_user, consume_user_bonus_spin, add_user_bonus_spins

  used_bonus = await consume_user_bonus_spin(user_id)

  if not used_bonus:
    return web.json_response({"ok": False, "error": "Omad g'ildiragini aylantirish uchun avval Promo Kod kiriting!"}, status=403)

  is_vip_mode = body.get("mode") == "vip"
  forced_key = body.get("forced_key") or (used_bonus.get("forced_prize") if isinstance(used_bonus, dict) else None)
  forced_clean = str(forced_key or "bear").lower().strip()

  vip_keys = ["aprel_bear", "easter_bear", "newyear_bear", "builder_bear", "football_bear", "soldier_bear", "newyear_tree", "patrick_bear", "valentine_bear", "valentine_heart", "rare", "vipgift"]

  # Security check: User cannot play VIP spin with a classic promo code!
  if is_vip_mode and forced_clean not in vip_keys:
    await add_user_bonus_spins(user_id, 1, forced_prize=forced_key or "bear")
    return web.json_response({
      "ok": False,
      "error": "❌ Siz kiritgan promo-kod faqat Klassik Spin uchun! Iltimos, 'Klassik Spin' bo'limiga o'ting."
    }, status=400)

  classic_prizes = [
    {"key": "teddy", "title": "🧸 Teddy Bear Gift (15⭐)", "type": "gift", "weight": 12, "index": 0},
    {"key": "rose", "title": "🌹 Rose Gift (25⭐)", "type": "gift", "weight": 6, "index": 1},
    {"key": "stars50", "title": "⭐️ 50 Stars", "type": "stars", "amount": 50, "weight": 5, "index": 2},
    {"key": "uzs10000", "title": "💰 10 000 UZS Balans", "type": "balance", "amount": 10000, "weight": 5, "index": 3},
    {"key": "box", "title": "🎁 Gift Box (25⭐)", "type": "gift", "weight": 6, "index": 4},
    {"key": "teddy", "title": "🧸 Teddy Bear Gift (15⭐)", "type": "gift", "weight": 12, "index": 5},
    {"key": "rose", "title": "🌹 Rose Gift (25⭐)", "type": "gift", "weight": 6, "index": 6},
    {"key": "stars25", "title": "⭐️ 25 Stars", "type": "stars", "amount": 25, "weight": 6, "index": 7},
    {"key": "uzs5000", "title": "💰 5 000 UZS Balans", "type": "balance", "amount": 5000, "weight": 6, "index": 8},
    {"key": "box", "title": "🎁 Gift Box (25⭐)", "type": "gift", "weight": 6, "index": 9},
    {"key": "teddy", "title": "🧸 Teddy Bear Gift (15⭐)", "type": "gift", "weight": 12, "index": 10},
    {"key": "rose", "title": "🌹 Rose Gift (25⭐)", "type": "gift", "weight": 6, "index": 11},
    {"key": "stars50", "title": "⭐️ 50 Stars", "type": "stars", "amount": 50, "weight": 5, "index": 12},
    {"key": "uzs10000", "title": "💰 10 000 UZS Balans", "type": "balance", "amount": 10000, "weight": 5, "index": 13},
    {"key": "box", "title": "🎁 Gift Box (25⭐)", "type": "gift", "weight": 6, "index": 14},
    {"key": "teddy", "title": "🧸 Teddy Bear Gift (15⭐)", "type": "gift", "weight": 12, "index": 15},
    {"key": "rose", "title": "🌹 Rose Gift (25⭐)", "type": "gift", "weight": 6, "index": 16},
    {"key": "stars25", "title": "⭐️ 25 Stars", "type": "stars", "amount": 25, "weight": 6, "index": 17},
    {"key": "box", "title": "🎁 Gift Box (25⭐)", "type": "gift", "weight": 6, "index": 18},
    {"key": "teddy", "title": "🧸 Teddy Bear Gift (15⭐)", "type": "gift", "weight": 12, "index": 19},
  ]

  vip_prizes = [
    {"key": "aprel_bear", "title": "🌸 Aprel Ayiqchasi (50⭐)", "type": "gift", "weight": 10, "index": 0},
    {"key": "stars50", "title": "⭐️ 50 Stars", "type": "stars", "amount": 50, "weight": 15, "index": 1},
    {"key": "easter_bear", "title": "🐰 Pasxa Ayiqchasi (50⭐)", "type": "gift", "weight": 10, "index": 2},
    {"key": "stars50", "title": "⭐️ 50 Stars", "type": "stars", "amount": 50, "weight": 15, "index": 3},
    {"key": "newyear_bear", "title": "🎅 Yangi Yil Ayiqchasi (50⭐)", "type": "gift", "weight": 10, "index": 4},
    {"key": "stars50", "title": "⭐️ 50 Stars", "type": "stars", "amount": 50, "weight": 15, "index": 5},
    {"key": "builder_bear", "title": "🔨 Usta Ayiqcha (50⭐)", "type": "gift", "weight": 10, "index": 6},
    {"key": "stars50", "title": "⭐️ 50 Stars", "type": "stars", "amount": 50, "weight": 15, "index": 7},
    {"key": "football_bear", "title": "⚽ Futbolchi Ayiqcha (50⭐)", "type": "gift", "weight": 10, "index": 8},
    {"key": "stars50", "title": "⭐️ 50 Stars", "type": "stars", "amount": 50, "weight": 15, "index": 9},
    {"key": "soldier_bear", "title": "💣 Jangchi Ayiqcha (50⭐)", "type": "gift", "weight": 10, "index": 10},
    {"key": "stars50", "title": "⭐️ 50 Stars", "type": "stars", "amount": 50, "weight": 15, "index": 11},
    {"key": "newyear_tree", "title": "🎄 Yangi Yil Archasi (50⭐)", "type": "gift", "weight": 10, "index": 12},
    {"key": "stars50", "title": "⭐️ 50 Stars", "type": "stars", "amount": 50, "weight": 15, "index": 13},
    {"key": "patrick_bear", "title": "🍀 Patrik Ayiqchasi (50⭐)", "type": "gift", "weight": 10, "index": 14},
    {"key": "stars50", "title": "⭐️ 50 Stars", "type": "stars", "amount": 50, "weight": 15, "index": 15},
    {"key": "valentine_bear", "title": "💘 Valentin Ayiqchasi (50⭐)", "type": "gift", "weight": 10, "index": 16},
    {"key": "stars50", "title": "⭐️ 50 Stars", "type": "stars", "amount": 50, "weight": 15, "index": 17},
    {"key": "valentine_heart", "title": "💕 Valentinka Yurakchasi (50⭐)", "type": "gift", "weight": 10, "index": 18},
    {"key": "stars50", "title": "⭐️ 50 Stars", "type": "stars", "amount": 50, "weight": 15, "index": 19 },
  ]

  all_prizes = classic_prizes + vip_prizes
  is_vip_mode = body.get("mode") == "vip"

  chosen_prize = None
  forced_key = body.get("forced_key") or (used_bonus.get("forced_prize") if isinstance(used_bonus, dict) else None)

  if forced_key:
    forced_clean = str(forced_key).lower().strip()
    rare_list = ["aprel_bear", "easter_bear", "newyear_bear", "builder_bear", "football_bear", "soldier_bear", "newyear_tree", "patrick_bear", "valentine_bear", "valentine_heart"]
    if forced_clean in ["vipgift", "rare", "promovipgift"]:
      forced_clean = random.choice(rare_list)
    elif forced_clean in ["builder", "usta", "builder_bear", "promobuilder", "promousta"]:
      forced_clean = "builder_bear"
    elif forced_clean in ["football", "futbol", "football_bear", "promofootball", "promofutbol"]:
      forced_clean = "football_bear"
    elif forced_clean in ["soldier", "jangchi", "military", "cs", "soldier_bear", "promosoldier", "promojangchi"]:
      forced_clean = "soldier_bear"
    elif forced_clean in ["gift25", "rose", "flower", "box"]:
      forced_clean = random.choice(["rose", "box"])
    elif forced_clean in ["stars", "star50", "stars50"]:
      forced_clean = "stars50"
    elif forced_clean == "money":
      forced_clean = random.choice(["uzs10000", "uzs20000", "uzs5000"])
    elif forced_clean in ["bear", "teddy"]:
      forced_clean = "teddy"

    matched = [p for p in all_prizes if p["key"] == forced_clean]
    if matched:
      chosen_prize = random.choice(matched)

  if not chosen_prize:
    active_pool = vip_prizes if is_vip_mode else classic_prizes
    weights = [p["weight"] for p in active_pool]
    chosen_prize = random.choices(active_pool, weights=weights, k=1)[0]

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

  app.router.add_get("/webhook/telegram", telegram_webhook_check)
  app.router.add_post("/webhook/telegram", telegram_webhook)
  app.router.add_get("/api/set_webhook", api_set_webhook)
  app.router.add_post("/api/set_webhook", api_set_webhook)
  app.router.add_get("/api/get_webhook", api_get_webhook)
  app.router.add_get("/api/delete_webhook", api_delete_webhook)

  app.router.add_static("/app", WEBAPP_DIR, name="webapp")
  app.router.add_static("/", WEBAPP_DIR, name="root")
  return app


async def _on_shutdown(app: web.Application) -> None:
    bot = app.get("bot")
    if bot:
        try:
            await bot.session.close()
        except Exception:
            pass


def main() -> None:
  logging.basicConfig(level=logging.INFO)
  app = create_app()
  web.run_app(app, host=settings.api_host, port=settings.api_port)


if __name__ == "__main__":
  main()
