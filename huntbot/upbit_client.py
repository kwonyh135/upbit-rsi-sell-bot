import hashlib
import os
import time
import uuid
from urllib.parse import urlencode

import jwt
import requests

from huntbot.config import DEFAULT_SERVER_URL


class UpbitClient:
    def __init__(
        self,
        *,
        access_key: str | None = None,
        secret_key: str | None = None,
        server_url: str | None = None,
        session=None,
    ) -> None:
        self.access_key = access_key or os.environ.get("UPBIT_OPEN_API_ACCESS_KEY", "")
        self.secret_key = secret_key or os.environ.get("UPBIT_OPEN_API_SECRET_KEY", "")
        self.server_url = (server_url or os.environ.get("UPBIT_OPEN_API_SERVER_URL") or DEFAULT_SERVER_URL).rstrip("/")
        self.session = session or requests.Session()

    def get_minute_candles(self, market: str, *, unit: int, count: int = 200, to: str | None = None) -> list[dict]:
        params = {"market": market, "count": count}
        if to:
            params["to"] = to
        response = self.session.get(
            f"{self.server_url}/v1/candles/minutes/{unit}",
            params=params,
            timeout=10,
        )
        response.raise_for_status()
        time.sleep(0.12)
        return response.json()

    def get_orderbook(self, market: str, *, count: int = 1) -> dict:
        response = self.session.get(
            f"{self.server_url}/v1/orderbook",
            params={"markets": market, "count": count},
            timeout=10,
        )
        response.raise_for_status()
        time.sleep(0.12)
        payload = response.json()
        return payload[0] if payload else {}

    def get_accounts(self) -> list[dict]:
        response = self.session.get(
            f"{self.server_url}/v1/accounts",
            headers=self._auth_headers({}),
            timeout=10,
        )
        response.raise_for_status()
        return response.json()

    def get_order_chance(self, market: str) -> dict:
        params = {"market": market}
        response = self.session.get(
            f"{self.server_url}/v1/orders/chance",
            params=params,
            headers=self._auth_headers(params),
            timeout=10,
        )
        response.raise_for_status()
        return response.json()

    def market_sell(self, market: str, volume: str, *, identifier: str | None = None) -> dict:
        body = {"market": market, "side": "ask", "ord_type": "market", "volume": volume}
        if identifier:
            body["identifier"] = identifier
        response = self.session.post(
            f"{self.server_url}/v1/orders",
            json=body,
            headers=self._auth_headers(body),
            timeout=10,
        )
        response.raise_for_status()
        return response.json()

    def market_buy(self, market: str, price: str, *, identifier: str | None = None) -> dict:
        body = {"market": market, "side": "bid", "ord_type": "price", "price": price}
        if identifier:
            body["identifier"] = identifier
        response = self.session.post(
            f"{self.server_url}/v1/orders",
            json=body,
            headers=self._auth_headers(body),
            timeout=10,
        )
        response.raise_for_status()
        return response.json()

    def get_order(self, *, uuid: str | None = None, identifier: str | None = None) -> dict:
        if bool(uuid) == bool(identifier):
            raise ValueError("provide exactly one of uuid or identifier")
        params = {"uuid": uuid} if uuid else {"identifier": identifier}
        response = self.session.get(
            f"{self.server_url}/v1/order",
            params=params,
            headers=self._auth_headers(params),
            timeout=10,
        )
        response.raise_for_status()
        return response.json()

    def get_closed_orders(
        self,
        market: str,
        *,
        start_time: str | None = None,
        end_time: str | None = None,
        limit: int = 1000,
        order_by: str = "desc",
    ) -> list[dict]:
        params = {
            "market": market,
            "limit": limit,
            "order_by": order_by,
        }
        if start_time:
            params["start_time"] = start_time
        if end_time:
            params["end_time"] = end_time
        response = self.session.get(
            f"{self.server_url}/v1/orders/closed",
            params=params,
            headers=self._auth_headers(params),
            timeout=10,
        )
        response.raise_for_status()
        return response.json()

    def _auth_headers(self, params: dict) -> dict[str, str]:
        if not self.access_key or not self.secret_key:
            raise RuntimeError("Upbit API keys are missing. Create .env from .env.example.")
        payload = {"access_key": self.access_key, "nonce": str(uuid.uuid4())}
        if params:
            query = urlencode(params).encode()
            payload["query_hash"] = hashlib.sha512(query).hexdigest()
            payload["query_hash_alg"] = "SHA512"
        token = jwt.encode(payload, self.secret_key)
        return {"Authorization": f"Bearer {token}", "accept": "application/json"}
