import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from conftest import (
    WS_ENDPOINT_SUCCESS,
    WS_ENDPOINT_FAILURE,
    WS_TICKET_URL,
    TOKEN_SUCCESS,
)


class TestConnectLifecycle:
    async def test_connect_sets_running_true(self, make_adapter):
        adapter = make_adapter()
        mock_http = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json = MagicMock(return_value=WS_ENDPOINT_SUCCESS)
        mock_response.raise_for_status = MagicMock()
        mock_response.text = json.dumps(WS_ENDPOINT_SUCCESS)
        mock_http.post = AsyncMock(return_value=mock_response)

        with patch("lansenger.adapter.httpx.AsyncClient", return_value=mock_http):
            with patch("lansenger.adapter.websockets.connect"):
                result = await adapter.connect()

        assert result is True
        assert adapter._running is True

    async def test_connect_returns_false_no_app_id(self, make_adapter):
        adapter = make_adapter(app_id="", app_secret="test")
        result = await adapter.connect()
        assert result is False
        assert adapter._running is False

    async def test_connect_returns_false_no_secret(self, make_adapter):
        adapter = make_adapter(app_id="test", app_secret="")
        result = await adapter.connect()
        assert result is False
        assert adapter._running is False

    async def test_connect_returns_false_ws_endpoint_error(self, make_adapter):
        adapter = make_adapter()
        mock_http = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json = MagicMock(return_value=WS_ENDPOINT_FAILURE)
        mock_response.raise_for_status = MagicMock()
        mock_response.text = json.dumps(WS_ENDPOINT_FAILURE)
        mock_http.post = AsyncMock(return_value=mock_response)

        with patch("lansenger.adapter.httpx.AsyncClient", return_value=mock_http):
            result = await adapter.connect()

        assert result is False

    async def test_connect_returns_false_http_error(self, make_adapter):
        adapter = make_adapter()
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(side_effect=Exception("connection refused"))

        with patch("lansenger.adapter.httpx.AsyncClient", return_value=mock_http):
            result = await adapter.connect()

        assert result is False

    async def test_disconnect_sets_running_false(self, make_adapter):
        adapter = make_adapter()
        adapter._running = True
        adapter._connected = True
        mock_http = AsyncMock()
        mock_http.aclose = AsyncMock()
        adapter._http_client = mock_http
        adapter._ws_task = None

        await adapter.disconnect()

        assert adapter._running is False
        assert adapter._http_client is None

    async def test_disconnect_closes_http_client(self, make_adapter):
        adapter = make_adapter()
        adapter._running = True
        adapter._connected = True
        mock_http = AsyncMock()
        mock_http.aclose = AsyncMock()
        adapter._http_client = mock_http
        adapter._ws_task = None

        await adapter.disconnect()

        mock_http.aclose.assert_called_once()
        assert adapter._http_client is None


class TestGetWebsocketUrl:
    async def test_success_returns_ws_url(self, make_adapter):
        adapter = make_adapter()
        adapter._http_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json = MagicMock(return_value=WS_ENDPOINT_SUCCESS)
        mock_response.raise_for_status = MagicMock()
        mock_response.text = json.dumps(WS_ENDPOINT_SUCCESS)
        adapter._http_client.post = AsyncMock(return_value=mock_response)

        result = await adapter._get_websocket_url()

        assert result == WS_TICKET_URL
        assert adapter._ws_url == WS_TICKET_URL

    async def test_api_error_returns_none(self, make_adapter):
        adapter = make_adapter()
        adapter._http_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json = MagicMock(return_value=WS_ENDPOINT_FAILURE)
        mock_response.raise_for_status = MagicMock()
        mock_response.text = json.dumps(WS_ENDPOINT_FAILURE)
        adapter._http_client.post = AsyncMock(return_value=mock_response)

        result = await adapter._get_websocket_url()

        assert result is None

    async def test_http_401_returns_none(self, make_adapter):
        import httpx
        adapter = make_adapter()
        adapter._http_client = AsyncMock()

        error_response = MagicMock()
        error_response.text = '{"errCode":401,"errMsg":"Unauthorized"}'
        adapter._http_client.post = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "401 Unauthorized",
                request=MagicMock(),
                response=error_response,
            )
        )

        result = await adapter._get_websocket_url()

        assert result is None

    async def test_network_error_returns_none(self, make_adapter):
        adapter = make_adapter()
        adapter._http_client = AsyncMock()
        adapter._http_client.post = AsyncMock(side_effect=Exception("DNS failure"))

        result = await adapter._get_websocket_url()

        assert result is None


class TestRunWs:
    async def test_run_ws_stops_when_not_running(self, make_adapter):
        adapter = make_adapter()
        adapter._running = False

        await adapter._run_ws(WS_TICKET_URL)

    async def test_run_ws_processes_messages(self, make_adapter):
        adapter = make_adapter()
        adapter._on_message = AsyncMock()

        messages = ["msg1", "msg2"]

        class FakeWs:
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                pass
            def __aiter__(self):
                return self
            async def __anext__(self):
                if not adapter._running or not messages:
                    raise StopAsyncIteration
                return messages.pop(0)

        adapter._running = True
        fake_ws = FakeWs()

        with patch("lansenger.adapter.websockets.connect", return_value=fake_ws):
            adapter._ws_task = asyncio.create_task(adapter._run_ws(WS_TICKET_URL))
            await asyncio.sleep(0.3)
            adapter._running = False
            adapter._ws_task.cancel()
            try:
                await adapter._ws_task
            except (asyncio.CancelledError, StopAsyncIteration):
                pass

        assert adapter._on_message.call_count >= 1