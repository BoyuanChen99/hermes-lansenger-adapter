"""
Token management mixin for LansengerAdapter.
Handles app access token fetch, cache, persistence, and refresh.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional

import httpx

from ._constants import DEFAULT_API_GATEWAY_URL

logger = logging.getLogger(__name__)


class TokenManagerMixin:
    """Token management methods for LansengerAdapter."""

    async def _get_app_token(self) -> Optional[str]:
        """Get or refresh app access token, with persistent caching."""

        if self._app_token and datetime.now().timestamp() < self._token_expiry:
            return self._app_token

        persisted = self._load_persisted_token()
        if persisted and datetime.now().timestamp() < persisted["expires_at"]:
            self._app_token = persisted["app_token"]
            self._token_expiry = persisted["expires_at"]
            logger.info("[Lansenger] Loaded persisted appToken (expires in %ds)",
                        int(persisted["expires_at"] - datetime.now().timestamp()))
            return self._app_token

        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=30.0)

        # Check event loop is alive before making HTTP calls
        try:
            asyncio.get_running_loop()
        except RuntimeError as e:
            logger.error("[Lansenger] Cannot refresh token — event loop not available: %s", e)
            return None

        try:
            url = f"{self._api_gateway_url}/v1/apptoken/create"
            params = {
                "grant_type": "client_credential",
                "appid": self._app_id,
                "secret": self._app_secret
            }
            response = await self._http_client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            if data.get("errCode") != 0:
                logger.error("[Lansenger] Token error: %s", data.get("errMsg"))
                return None

            self._app_token = data.get("data", {}).get("appToken")
            expires_in = data.get("data", {}).get("expiresIn", 7200)
            persist_expiry = datetime.now().timestamp() + expires_in
            self._token_expiry = persist_expiry - 300  # cache expiry: 5min early refresh buffer

            self._persist_token(self._app_token, persist_expiry)

            logger.info("[Lansenger] Got new access token (expires in %ds)", expires_in)
            return self._app_token
        except Exception as e:
            logger.error("[Lansenger] Error getting token: %s", e)
            return None

    def _load_persisted_token(self) -> Optional[Dict[str, Any]]:
        """Load persisted token from ~/.hermes/lansenger_token.json.

        Validates that the stored app_id matches the current bot credentials
        to prevent cross-bot token reuse when switching bots.
        """
        try:
            if not self._token_file.exists():
                return None
            content = self._token_file.read_text(encoding="utf-8")
            data = json.loads(content)
            if "app_token" in data and "expires_at" in data:
                # Validate app_id match to prevent old token reuse after bot switch
                stored_app_id = data.get("app_id", "")
                if stored_app_id and stored_app_id != self._app_id:
                    logger.info(
                        "[Lansenger] Persisted token app_id mismatch "
                        "(stored=%s, current=%s) — discarding old token",
                        stored_app_id[:20], self._app_id[:20],
                    )
                    return None
                return data
        except Exception as e:
            logger.debug("[Lansenger] Failed to load persisted token: %s", e)
        return None

    def _persist_token(self, app_token: str, expires_at: float) -> None:
        """Write token to ~/.hermes/lansenger_token.json for cross-process reuse."""
        try:
            data = {
                "app_token": app_token,
                "expires_at": expires_at,
                "app_id": self._app_id,  # validate on load to prevent cross-bot reuse
            }
            self._token_file.parent.mkdir(parents=True, exist_ok=True)
            self._token_file.write_text(json.dumps(data), encoding="utf-8")
            logger.debug("[Lansenger] Persisted appToken to %s", self._token_file)
        except Exception as e:
            logger.debug("[Lansenger] Failed to persist token: %s", e)
