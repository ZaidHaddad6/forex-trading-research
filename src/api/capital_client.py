import logging
import random
import time
import requests
from typing import Optional

logger = logging.getLogger(__name__)


class CapitalAPIError(Exception):
    pass


class CapitalClient:
    """Thin wrapper around the Capital.com REST API."""

    def __init__(self, base_url: str, api_key: str, email: str, password: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.email = email
        self.password = password
        self._cst: Optional[str] = None
        self._security_token: Optional[str] = None

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def create_session(self) -> dict:
        """Authenticate and store the session tokens. Retries on 429 with exponential backoff."""
        url = f"{self.base_url}/session"
        headers = {"X-CAP-API-KEY": self.api_key, "Content-Type": "application/json"}
        payload = {
            "identifier": self.email,
            "password": self.password,
            "encryptedPassword": False,
        }
        for attempt in range(4):
            response = requests.post(url, json=payload, headers=headers, timeout=15)
            if response.status_code == 429 and attempt < 3:
                wait = (2 ** attempt) + random.uniform(1.0, 8.0)
                logger.warning("Rate limited on session create — retrying in %.1fs (attempt %d/4)", wait, attempt + 1)
                time.sleep(wait)
                continue
            break

        self._raise_for_status(response)

        self._cst = response.headers.get("CST")
        self._security_token = response.headers.get("X-SECURITY-TOKEN")

        if not self._cst or not self._security_token:
            raise CapitalAPIError("Session tokens missing from response headers.")

        logger.info("Session created successfully (env: %s)", self.base_url)
        return response.json()

    def close_session(self) -> None:
        self._delete("/session")
        self._cst = None
        self._security_token = None
        logger.info("Session closed.")

    def ping(self) -> dict:
        return self._get("/ping")

    # ------------------------------------------------------------------
    # Account
    # ------------------------------------------------------------------

    def get_accounts(self) -> dict:
        return self._get("/accounts")

    # ------------------------------------------------------------------
    # Market data
    # ------------------------------------------------------------------

    def get_market_details(self, epic: str) -> dict:
        return self._get(f"/markets/{epic}")

    def get_prices(self, epic: str, resolution: str = "MINUTE", max_bars: int = 100) -> dict:
        """Fetch OHLCV price history.

        resolution options: MINUTE, MINUTE_5, MINUTE_15, MINUTE_30, HOUR, DAY, WEEK
        """
        params = {"resolution": resolution, "max": max_bars}
        return self._get(f"/prices/{epic}", params=params)

    # ------------------------------------------------------------------
    # Positions (trading)
    # ------------------------------------------------------------------

    def get_positions(self) -> dict:
        return self._get("/positions")

    def open_position(
        self,
        epic: str,
        direction: str,
        size: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> dict:
        """Open a market position.

        direction: "BUY" or "SELL"
        """
        payload: dict = {
            "epic": epic,
            "direction": direction.upper(),
            "size": size,
            "guaranteedStop": False,
        }
        if stop_loss is not None:
            payload["stopLevel"] = stop_loss
        if take_profit is not None:
            payload["profitLevel"] = take_profit
        return self._post("/positions", payload)

    def close_position(self, deal_id: str) -> dict:
        return self._delete(f"/positions/{deal_id}")

    def update_position_stop(self, deal_id: str, stop_level: float, profit_level: Optional[float] = None) -> dict:
        payload: dict = {"stopLevel": stop_level}
        if profit_level is not None:
            payload["profitLevel"] = profit_level
        return self._put(f"/positions/{deal_id}", payload)

    # ------------------------------------------------------------------
    # Internal HTTP helpers
    # ------------------------------------------------------------------

    @property
    def _auth_headers(self) -> dict:
        if not self._cst or not self._security_token:
            raise CapitalAPIError("Not authenticated. Call create_session() first.")
        return {
            "X-CAP-API-KEY": self.api_key,
            "CST": self._cst,
            "X-SECURITY-TOKEN": self._security_token,
            "Content-Type": "application/json",
        }

    _TIMEOUT = 15  # seconds; prevents indefinite hangs on slow/dead API

    def _put(self, path: str, payload: dict) -> dict:
        response = requests.put(
            f"{self.base_url}{path}", json=payload, headers=self._auth_headers, timeout=self._TIMEOUT
        )
        self._raise_for_status(response)
        return response.json() if response.content else {}

    def _get(self, path: str, params: Optional[dict] = None) -> dict:
        response = requests.get(
            f"{self.base_url}{path}", headers=self._auth_headers, params=params, timeout=self._TIMEOUT
        )
        response = self._reauth_if_needed(response, "GET", path, params=params)
        self._raise_for_status(response)
        return response.json()

    def _post(self, path: str, payload: dict) -> dict:
        response = requests.post(
            f"{self.base_url}{path}", json=payload, headers=self._auth_headers, timeout=self._TIMEOUT
        )
        response = self._reauth_if_needed(response, "POST", path, payload=payload)
        self._raise_for_status(response)
        return response.json()

    def _delete(self, path: str) -> dict:
        response = requests.delete(
            f"{self.base_url}{path}", headers=self._auth_headers, timeout=self._TIMEOUT
        )
        response = self._reauth_if_needed(response, "DELETE", path)
        self._raise_for_status(response)
        return response.json() if response.content else {}

    def _reauth_if_needed(
        self,
        response: requests.Response,
        method: str,
        path: str,
        params: Optional[dict] = None,
        payload: Optional[dict] = None,
    ) -> requests.Response:
        """If the response is a 401 session error, re-authenticate and retry once."""
        if response.status_code != 401:
            return response
        try:
            error_code = response.json().get("errorCode", "")
        except Exception:
            return response
        if "session.token" not in error_code:
            return response

        jitter = random.uniform(1.0, 8.0)
        logger.warning("Session token expired — re-authenticating in %.1fs…", jitter)
        time.sleep(jitter)
        self.create_session()
        logger.info("Re-authenticated successfully — retrying request.")

        if method == "GET":
            return requests.get(f"{self.base_url}{path}", headers=self._auth_headers, params=params, timeout=self._TIMEOUT)
        if method == "POST":
            return requests.post(f"{self.base_url}{path}", json=payload, headers=self._auth_headers, timeout=self._TIMEOUT)
        if method == "DELETE":
            return requests.delete(f"{self.base_url}{path}", headers=self._auth_headers, timeout=self._TIMEOUT)
        return response

    @staticmethod
    def _raise_for_status(response: requests.Response) -> None:
        if not response.ok:
            try:
                detail = response.json()
            except Exception:
                detail = response.text
            raise CapitalAPIError(
                f"HTTP {response.status_code} — {response.url}: {detail}"
            )
