"""Client for Abu Store API (Roxiy) — https://stars.roxiy.uz/api/v1"""

from __future__ import annotations

import logging
import uuid
import time
from typing import Any, Optional
import aiohttp

import config

logger = logging.getLogger(__name__)


class AbuStoreAPIError(Exception):
    def __init__(self, message: str, status: int | None = None, code: str | None = None, payload: Any = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.payload = payload


class AbuStoreAPI:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
    ):
        raw_key = api_key or getattr(config, 'ROXIY_API_KEY', '') or ""
        self.api_key = "".join(raw_key.split())
        raw_url = (base_url or getattr(config, 'ROXIY_API_URL', 'https://stars.roxiy.uz/api/v1') or 'https://stars.roxiy.uz/api/v1').strip().rstrip('/')
        if not raw_url.endswith('/v1'):
            if raw_url.endswith('/api'):
                raw_url = f"{raw_url}/v1"
            else:
                raw_url = f"{raw_url}/api/v1"
        self.base_url = raw_url

    def _headers(self, idempotency_key: Optional[str] = None) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "CoinStatUz-App/1.0",
        }
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        return headers

    async def _request(
        self,
        method: str,
        path: str,
        json_data: dict | None = None,
        params: dict | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}/{path.lstrip('/')}"
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.request(
                method,
                url,
                headers=self._headers(idempotency_key=idempotency_key),
                json=json_data,
                params=params,
            ) as resp:
                try:
                    data = await resp.json(content_type=None)
                except Exception:
                    raw_text = await resp.text()
                    data = {"ok": False, "raw": raw_text}

                if resp.status >= 400 or (isinstance(data, dict) and data.get("ok") is False):
                    err_obj = data.get("error") if isinstance(data.get("error"), dict) else {}
                    err_msg = err_obj.get("message") or data.get("error") or data.get("message") or f"HTTP {resp.status}"
                    err_code = err_obj.get("code") if isinstance(err_obj, dict) else None
                    logger.warning("Abu Store API Error [%s]: %s (payload: %s)", resp.status, err_msg, data)
                    raise AbuStoreAPIError(err_msg, resp.status, err_code, data)

                return data

    async def get_balance(self) -> float:
        """Get live balance in UZS."""
        try:
            res = await self._request("GET", "balance")
            if res.get("ok"):
                bal_obj = res.get("data") or {}
                raw_bal = bal_obj.get("balance", 0)
                return float(raw_bal)
        except Exception as e:
            logger.warning("Abu Store get_balance error: %s", e)
        return 0.0

    async def get_services(self) -> dict[str, Any]:
        """Fetch available services and current unit prices."""
        return await self._request("GET", "services")

    async def get_gifts(self) -> list[dict[str, Any]]:
        """Fetch available gifts list with gift_id and prices."""
        res = await self._request("GET", "gifts")
        data = res.get("data") or {}
        return data.get("gifts") or []

    async def buy_stars(self, username: str, amount: int, max_price: float | None = None) -> dict[str, Any]:
        """Buy Telegram Stars via Abu Store API."""
        username = username.lstrip("@").strip()
        idem_key = f"stars_{username}_{amount}_{int(time.time()*1000)}_{uuid.uuid4().hex[:6]}"
        payload = {
            "service": "stars",
            "username": username,
            "amount": int(amount),
        }
        if max_price:
            payload["max_price"] = f"{float(max_price):.2f}"
        return await self._request("POST", "orders", json_data=payload, idempotency_key=idem_key)

    async def buy_premium(self, username: str, months: int, max_price: float | None = None) -> dict[str, Any]:
        """Buy Telegram Premium (3, 6, 12 months) via Abu Store API."""
        username = username.lstrip("@").strip()
        idem_key = f"prem_{username}_{months}_{int(time.time()*1000)}_{uuid.uuid4().hex[:6]}"
        payload = {
            "service": "premium",
            "username": username,
            "months": int(months),
        }
        if max_price:
            payload["max_price"] = f"{float(max_price):.2f}"
        return await self._request("POST", "orders", json_data=payload, idempotency_key=idem_key)

    async def buy_gift(self, username: str, gift_id: str, note: str = "", anonymous: bool = False) -> dict[str, Any]:
        """Send Telegram Gift via Abu Store API."""
        username = username.lstrip("@").strip()
        idem_key = f"gift_{username}_{gift_id}_{int(time.time()*1000)}_{uuid.uuid4().hex[:6]}"
        payload = {
            "service": "gift",
            "username": username,
            "gift_id": str(gift_id),
            "anonymous": bool(anonymous),
        }
        if note:
            payload["note"] = note[:30]
        return await self._request("POST", "orders", json_data=payload, idempotency_key=idem_key)

    async def get_order_status(self, order_id: str) -> dict[str, Any]:
        """Get order status from Abu Store."""
        return await self._request("GET", f"orders/{order_id}")


abu_store_client = AbuStoreAPI()
