import json
import time
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from conftest import TOKEN_SUCCESS, TOKEN_FAILURE


class TestGetAppToken:
    async def test_fetches_new_token_when_none_cached(self, make_adapter):
        adapter = make_adapter()
        adapter._http_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json = MagicMock(return_value=TOKEN_SUCCESS)
        mock_response.raise_for_status = MagicMock()
        adapter._http_client.get = AsyncMock(return_value=mock_response)

        token = await adapter._get_app_token()

        assert token == "test-app-token-12345"
        assert adapter._app_token == "test-app-token-12345"
        assert adapter._token_expiry > datetime.now().timestamp()

    async def test_uses_cached_token_if_not_expired(self, make_adapter):
        adapter = make_adapter()
        adapter._app_token = "cached-token"
        adapter._token_expiry = datetime.now().timestamp() + 3600

        token = await adapter._get_app_token()

        assert token == "cached-token"
        adapter._http_client is None or adapter._http_client.get.assert_not_called()

    async def test_fetches_new_when_cached_expired(self, make_adapter):
        adapter = make_adapter()
        adapter._app_token = "expired-token"
        adapter._token_expiry = datetime.now().timestamp() - 100
        adapter._http_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.json = MagicMock(return_value=TOKEN_SUCCESS)
        mock_response.raise_for_status = MagicMock()
        adapter._http_client.get = AsyncMock(return_value=mock_response)

        token = await adapter._get_app_token()

        assert token == "test-app-token-12345"

    async def test_loads_from_persisted_file(self, make_adapter):
        adapter = make_adapter()
        adapter._app_token = None
        adapter._token_expiry = 0

        expires_at = datetime.now().timestamp() + 3600
        token_data = {"app_token": "persisted-token", "expires_at": expires_at}
        adapter._token_file.parent.mkdir(parents=True, exist_ok=True)
        adapter._token_file.write_text(json.dumps(token_data))

        token = await adapter._get_app_token()

        assert token == "persisted-token"
        assert adapter._app_token == "persisted-token"

    async def test_fetches_new_when_persisted_expired(self, make_adapter):
        adapter = make_adapter()
        adapter._app_token = None
        adapter._token_expiry = 0
        adapter._http_client = AsyncMock()

        expires_at = datetime.now().timestamp() - 100
        token_data = {"app_token": "old-persisted", "expires_at": expires_at}
        adapter._token_file.parent.mkdir(parents=True, exist_ok=True)
        adapter._token_file.write_text(json.dumps(token_data))

        mock_response = MagicMock()
        mock_response.json = MagicMock(return_value=TOKEN_SUCCESS)
        mock_response.raise_for_status = MagicMock()
        adapter._http_client.get = AsyncMock(return_value=mock_response)

        token = await adapter._get_app_token()

        assert token == "test-app-token-12345"

    async def test_returns_none_on_api_error(self, make_adapter):
        adapter = make_adapter()
        adapter._app_token = None
        adapter._token_expiry = 0
        adapter._http_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.json = MagicMock(return_value=TOKEN_FAILURE)
        mock_response.raise_for_status = MagicMock()
        adapter._http_client.get = AsyncMock(return_value=mock_response)

        token = await adapter._get_app_token()

        assert token is None

    async def test_returns_none_on_http_error(self, make_adapter):
        adapter = make_adapter()
        adapter._app_token = None
        adapter._token_expiry = 0
        adapter._http_client = AsyncMock()
        adapter._http_client.get = AsyncMock(side_effect=Exception("network error"))

        token = await adapter._get_app_token()

        assert token is None

    async def test_persist_token_writes_file(self, make_adapter):
        adapter = make_adapter()

        adapter._persist_token("my-token", datetime.now().timestamp() + 7200)

        content = adapter._token_file.read_text()
        data = json.loads(content)
        assert data["app_token"] == "my-token"
        assert "expires_at" in data

    async def test_early_refresh_buffer(self, make_adapter):
        adapter = make_adapter()
        adapter._http_client = AsyncMock()

        expiresIn = 7200
        expected_expiry = datetime.now().timestamp() + expiresIn - 300

        mock_response = MagicMock()
        mock_response.json = MagicMock(return_value=TOKEN_SUCCESS)
        mock_response.raise_for_status = MagicMock()
        adapter._http_client.get = AsyncMock(return_value=mock_response)

        await adapter._get_app_token()

        assert abs(adapter._token_expiry - expected_expiry) < 5