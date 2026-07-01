import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from conftest import _StubSendResult


def _make_http_response(data, status_code=200):
    mock = MagicMock()
    mock.status_code = status_code
    mock.json = MagicMock(return_value=data)
    mock.raise_for_status = MagicMock()
    mock.text = json.dumps(data)
    return mock


async def _ensure_token(adapter):
    adapter._app_token = "test-token"
    adapter._token_expiry = 9999999999.0


class TestUpdateDynamicCardStatus:
    async def test_update_with_head_status_info(self, make_adapter):
        adapter = make_adapter()
        await _ensure_token(adapter)
        adapter._http_client = AsyncMock()

        mock_response = _make_http_response({"errCode": 0})
        adapter._http_client.post = AsyncMock(return_value=mock_response)

        status_info = {"iconLink": "https://icon.com/approved.png", "description": "已批准", "colour": "green"}
        result = await adapter.update_dynamic_card_status(
            msg_id="msg-dc1",
            head_status_info=status_info,
            is_last_update=True,
        )

        assert result.success is True
        call_args = adapter._http_client.post.call_args
        url = call_args[0][0]
        assert "/v1/messages/dynamic/update" in url

        payload = call_args.kwargs.get("json", {})
        assert payload.get("msgId") == "msg-dc1"
        assert payload.get("msgType") == "appCard"
        app_card_update = payload.get("msgData", {}).get("appCardUpdateMsg", {})
        assert app_card_update.get("headStatusInfo") == status_info
        assert app_card_update.get("isLastUpdate") is True

    async def test_update_with_links(self, make_adapter):
        adapter = make_adapter()
        await _ensure_token(adapter)
        adapter._http_client = AsyncMock()

        mock_response = _make_http_response({"errCode": 0})
        adapter._http_client.post = AsyncMock(return_value=mock_response)

        links = [{"title": "查看详情", "url": "https://detail.com"}]
        result = await adapter.update_dynamic_card_status(
            msg_id="msg-dc2",
            links=links,
        )

        call_args = adapter._http_client.post.call_args
        payload = call_args.kwargs.get("json", {})
        app_card_update = payload.get("msgData", {}).get("appCardUpdateMsg", {})
        assert app_card_update.get("links") == links
        assert app_card_update.get("isLastUpdate") is False

    async def test_update_api_error_returns_failure(self, make_adapter):
        adapter = make_adapter()
        await _ensure_token(adapter)
        adapter._http_client = AsyncMock()

        mock_response = _make_http_response({"errCode": 10001, "errMsg": "card not dynamic"})
        adapter._http_client.post = AsyncMock(return_value=mock_response)

        result = await adapter.update_dynamic_card_status(msg_id="msg-dc3")

        assert result.success is False

    async def test_update_http_error_returns_failure(self, make_adapter):
        adapter = make_adapter()
        await _ensure_token(adapter)
        adapter._http_client = AsyncMock()
        adapter._http_client.post = AsyncMock(side_effect=Exception("network error"))

        result = await adapter.update_dynamic_card_status(msg_id="msg-dc4")

        assert result.success is False
        assert result.retryable is True

    async def test_update_no_token_returns_failure(self, make_adapter):
        adapter = make_adapter()
        adapter._app_token = None
        adapter._token_expiry = 0

        with patch("lansenger.adapter.httpx.AsyncClient"):
            result = await adapter.update_dynamic_card_status(msg_id="msg-dc5")

        assert result.success is False
        assert "token" in result.error.lower()


class TestSendI18nAppCard:
    async def test_i18n_app_card_raises_not_implemented(self, make_adapter):
        adapter = make_adapter()

        with pytest.raises(NotImplementedError, match="reserved for future"):
            await adapter.send_i18n_app_card(chat_id="user-1")