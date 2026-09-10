"""Client for Fragment API Uz — https://fragment-api.uz/api/v1"""

from __future__ import annotations

import logging
from typing import Any
import aiohttp

import config

logger = logging.getLogger(__name__)


class FragmentAPIError(Exception):
    def __init__(self, message: str, status: int | None = None, payload: Any = None):
        super().__init__(message)
        self.status = status
        self.payload = payload


class FragmentAPI:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
    ):
        raw_key = api_key or getattr(config, 'FRAGMENT_API_KEY', '') or ""
        self.api_key = "".join(raw_key.split())
        raw_url = (base_url or getattr(config, 'FRAGMENT_API_URL', 'https://fragment-api.uz/api/v1') or 'https://fragment-api.uz/api/v1').strip().rstrip('/')
        if not raw_url.endswith('/v1'):
            if raw_url.endswith('/api'):
                raw_url = f"{raw_url}/v1"
            else:
                raw_url = f"{raw_url}/api/v1"
        self.base_url = raw_url

    def _headers(self) -> dict[str, str]:
        return {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def _request(
        self,
        method: str,
        path: str,
        json: dict | None = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}/{path.lstrip('/')}"
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.request(
                method, url, headers=self._headers(), json=json or {}
            ) as resp:
                try:
                    data = await resp.json(content_type=None)
                except Exception:
                    data = {"raw": await resp.text()}

                if resp.status >= 400 or (isinstance(data, dict) and data.get("ok") is False):
                    msg = data.get("message") or data.get("error") or str(data)
                    raise FragmentAPIError(msg, resp.status, data)
                if isinstance(data, dict):
                    return data
                return {"data": data}

    async def get_balance(self) -> dict[str, Any]:
        """Project wallet balance on Fragment platform."""
        res = await self._request("POST", "wallet/balance", json={})
        return res.get("result", res)

    async def get_stars_price(self, quantity: int) -> dict[str, Any]:
        """Get Telegram Stars prices."""
        res = await self._request("POST", "stars/pricing", json={"amount": quantity})
        return res.get("result", res)

    async def get_premium_prices(self) -> dict[str, Any]:
        """Get Telegram Premium packages pricing."""
        res = await self._request("POST", "premium/pricing", json={})
        return res.get("result", res)

    async def get_user_info(self, username: str) -> dict[str, Any]:
        """Get Telegram user info from fragment."""
        username = username.lstrip("@")
        res = await self._request("POST", "getInfo", json={"username": username})
        return res.get("result", res)

    async def buy_stars(self, username: str, quantity: int) -> dict[str, Any]:
        """Buy Telegram Stars."""
        username = username.lstrip("@")
        return await self._request(
            "POST",
            "stars/buy",
            json={"username": username, "amount": quantity},
        )

    async def buy_premium(self, username: str, months: int) -> dict[str, Any]:
        """Buy Telegram Premium."""
        username = username.lstrip("@")
        return await self._request(
            "POST",
            "premium/buy",
            json={"username": username, "months": months},
        )


fragment_api = FragmentAPI()
fragment_client = fragment_api
