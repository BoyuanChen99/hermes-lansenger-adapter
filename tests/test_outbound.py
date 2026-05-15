import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from conftest import TOKEN_SUCCESS, _StubSendResult, WS_TICKET_URL


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


class TestSendText:
    async def test_private_chat_routes_to_bot_endpoint(self, make_adapter):
        adapter = make_adapter()
        await _ensure_token(adapter)
        adapter._http_client = AsyncMock()

        chat_id = "2285568-user123"
        adapter._chat_type_map[chat_id] = "dm"

        mock_response = _make_http_response({"errCode": 0, "data": {"msgId": "msg-1"}})
        adapter._http_client.post = AsyncMock(return_value=mock_response)

        result = await adapter.send_text(chat_id, "hello world")

        call_args = adapter._http_client.post.call_args
        url = call_args[0][0] if call_args[0] else call_args.kwargs.get("url")
        assert "/v1/bot/messages/create" in url

    async def test_group_chat_routes_to_group_endpoint(self, make_adapter):
        adapter = make_adapter()
        await _ensure_token(adapter)
        adapter._http_client = AsyncMock()

        chat_id = "2285568-group123"
        adapter._chat_type_map[chat_id] = "group"

        mock_response = _make_http_response({"errCode": 0, "data": {"msgId": "msg-2"}})
        adapter._http_client.post = AsyncMock(return_value=mock_response)

        result = await adapter.send_text(chat_id, "hello group")

        call_args = adapter._http_client.post.call_args
        url = call_args[0][0] if call_args[0] else call_args.kwargs.get("url")
        assert "/v1/messages/group/create" in url

    async def test_group_payload_has_groupId(self, make_adapter):
        adapter = make_adapter()
        await _ensure_token(adapter)
        adapter._http_client = AsyncMock()

        chat_id = "2285568-group123"
        adapter._chat_type_map[chat_id] = "group"

        mock_response = _make_http_response({"errCode": 0, "data": {"msgId": "msg-3"}})
        adapter._http_client.post = AsyncMock(return_value=mock_response)

        await adapter.send_text(chat_id, "hello")

        call_args = adapter._http_client.post.call_args
        payload = call_args.kwargs.get("json", {})
        assert payload.get("groupId") == chat_id
        assert "userIdList" not in payload

    async def test_private_payload_has_userIdList(self, make_adapter):
        adapter = make_adapter()
        await _ensure_token(adapter)
        adapter._http_client = AsyncMock()

        chat_id = "2285568-user123"
        adapter._chat_type_map[chat_id] = "dm"

        mock_response = _make_http_response({"errCode": 0, "data": {"msgId": "msg-4"}})
        adapter._http_client.post = AsyncMock(return_value=mock_response)

        await adapter.send_text(chat_id, "hello")

        call_args = adapter._http_client.post.call_args
        payload = call_args.kwargs.get("json", {})
        assert payload.get("userIdList") == [chat_id]
        assert "groupId" not in payload

    async def test_text_with_reminder(self, make_adapter):
        adapter = make_adapter()
        await _ensure_token(adapter)
        adapter._http_client = AsyncMock()

        chat_id = "2285568-group123"
        adapter._chat_type_map[chat_id] = "group"

        mock_response = _make_http_response({"errCode": 0, "data": {"msgId": "msg-5"}})
        adapter._http_client.post = AsyncMock(return_value=mock_response)

        reminder = {"all": True, "userIds": ["user-1"]}
        await adapter.send_text(chat_id, "hello", reminder=reminder)

        call_args = adapter._http_client.post.call_args
        payload = call_args.kwargs.get("json", {})
        assert payload.get("reminder") == reminder

    async def test_unknown_chat_type_defaults_to_private(self, make_adapter):
        adapter = make_adapter()
        await _ensure_token(adapter)
        adapter._http_client = AsyncMock()

        chat_id = "2285568-unknown"
        adapter._chat_type_map = {}

        mock_response = _make_http_response({"errCode": 0, "data": {"msgId": "msg-6"}})
        adapter._http_client.post = AsyncMock(return_value=mock_response)

        await adapter.send_text(chat_id, "hello")

        call_args = adapter._http_client.post.call_args
        url = call_args[0][0] if call_args[0] else call_args.kwargs.get("url")
        assert "/v1/bot/messages/create" in url


class TestSendFormatText:
    async def test_formatText_msgType(self, make_adapter):
        adapter = make_adapter()
        await _ensure_token(adapter)
        adapter._http_client = AsyncMock()

        chat_id = "2285568-user123"
        adapter._chat_type_map[chat_id] = "dm"

        mock_response = _make_http_response({"errCode": 0, "data": {"msgId": "msg-f1"}})
        adapter._http_client.post = AsyncMock(return_value=mock_response)

        await adapter.send_format_text(chat_id, "**bold**")

        call_args = adapter._http_client.post.call_args
        payload = call_args.kwargs.get("json", {})
        msg_data = payload.get("msgData", {})
        assert msg_data.get("msgType") == "formatText"
        assert msg_data.get("formatType") == 1

    async def test_formatText_with_reminder(self, make_adapter):
        adapter = make_adapter()
        await _ensure_token(adapter)
        adapter._http_client = AsyncMock()

        chat_id = "2285568-group123"
        adapter._chat_type_map[chat_id] = "group"

        mock_response = _make_http_response({"errCode": 0, "data": {"msgId": "msg-f2"}})
        adapter._http_client.post = AsyncMock(return_value=mock_response)

        reminder = {"all": False, "userIds": ["user-1"], "botIds": []}
        await adapter.send_format_text(chat_id, "**bold**", reminder=reminder)

        call_args = adapter._http_client.post.call_args
        payload = call_args.kwargs.get("json", {})
        assert payload.get("reminder") == reminder


class TestSendLinkCard:
    async def test_6_required_fields_in_payload(self, make_adapter):
        adapter = make_adapter()
        await _ensure_token(adapter)
        adapter._http_client = AsyncMock()

        chat_id = "2285568-user123"
        adapter._chat_type_map[chat_id] = "dm"

        mock_response = _make_http_response({"errCode": 0, "data": {"msgId": "msg-lc1"}})
        adapter._http_client.post = AsyncMock(return_value=mock_response)

        await adapter.send_link_card(
            chat_id,
            title="Project Docs",
            link="https://example.com",
            description="Documentation",
            icon_link="https://example.com/icon.png",
            from_name="Hermes",
            from_icon_link="https://example.com/avatar.png",
        )

        call_args = adapter._http_client.post.call_args
        payload = call_args.kwargs.get("json", {})
        msg_data = payload.get("msgData", {})
        assert msg_data.get("msgType") == "linkCard"
        link_data = msg_data.get("linkCard", {})
        assert link_data.get("title") == "Project Docs"
        assert link_data.get("link") == "https://example.com"
        assert link_data.get("description") == "Documentation"
        assert link_data.get("iconLink") == "https://example.com/icon.png"
        assert link_data.get("fromName") == "Hermes"
        assert link_data.get("fromIconLink") == "https://example.com/avatar.png"

    async def test_missing_required_fields_still_sent(self, make_adapter):
        adapter = make_adapter()
        await _ensure_token(adapter)
        adapter._http_client = AsyncMock()

        chat_id = "2285568-user123"
        adapter._chat_type_map[chat_id] = "dm"

        mock_response = _make_http_response({"errCode": 0, "data": {"msgId": "msg-lc2"}})
        adapter._http_client.post = AsyncMock(return_value=mock_response)

        await adapter.send_link_card(
            chat_id,
            title="T",
            link="https://x.com",
            description=None,
            icon_link=None,
            from_name=None,
            from_icon_link=None,
        )

        call_args = adapter._http_client.post.call_args
        payload = call_args.kwargs.get("json", {})
        msg_data = payload.get("msgData", {})
        link_data = msg_data.get("linkCard", {})
        assert link_data.get("title") == "T"


class TestSendAppArticles:
    async def test_appArticles_payload_structure(self, make_adapter):
        adapter = make_adapter()
        await _ensure_token(adapter)
        adapter._http_client = AsyncMock()

        chat_id = "2285568-user123"
        adapter._chat_type_map[chat_id] = "dm"

        mock_response = _make_http_response({"errCode": 0, "data": {"msgId": "msg-aa1"}})
        adapter._http_client.post = AsyncMock(return_value=mock_response)

        articles = [
            {"imgUrl": "https://img.com/1.png", "title": "Article 1", "url": "https://art.com/1"},
            {"imgUrl": "https://img.com/2.png", "title": "Article 2", "url": "https://art.com/2"},
        ]

        await adapter.send_app_articles(chat_id, articles)

        call_args = adapter._http_client.post.call_args
        payload = call_args.kwargs.get("json", {})
        msg_data = payload.get("msgData", {})
        assert msg_data.get("msgType") == "appArticles"
        assert len(msg_data.get("appArticles", [])) == 2


class TestSendAppCard:
    async def test_appCard_basic_payload(self, make_adapter):
        adapter = make_adapter()
        await _ensure_token(adapter)
        adapter._http_client = AsyncMock()

        chat_id = "2285568-user123"
        adapter._chat_type_map[chat_id] = "dm"

        mock_response = _make_http_response({"errCode": 0, "data": {"msgId": "msg-ac1"}})
        adapter._http_client.post = AsyncMock(return_value=mock_response)

        await adapter.send_app_card(chat_id, body_title="Approval Request")

        call_args = adapter._http_client.post.call_args
        payload = call_args.kwargs.get("json", {})
        msg_data = payload.get("msgData", {})
        assert msg_data.get("msgType") == "appCard"
        assert msg_data.get("appCard", {}).get("bodyTitle") == "Approval Request"

    async def test_dynamic_appCard_auto_adds_headStatusInfo(self, make_adapter):
        adapter = make_adapter()
        await _ensure_token(adapter)
        adapter._http_client = AsyncMock()

        chat_id = "2285568-user123"
        adapter._chat_type_map[chat_id] = "dm"

        mock_response = _make_http_response({"errCode": 0, "data": {"msgId": "msg-ac2"}})
        adapter._http_client.post = AsyncMock(return_value=mock_response)

        await adapter.send_app_card(chat_id, body_title="Dynamic Card", is_dynamic=True)

        call_args = adapter._http_client.post.call_args
        payload = call_args.kwargs.get("json", {})
        msg_data = payload.get("msgData", {})
        assert msg_data.get("appCard", {}).get("isDynamic") is True
        assert "headStatusInfo" in msg_data.get("appCard", {})


class TestRevokeMessage:
    async def test_revoke_bot_type(self, make_adapter):
        adapter = make_adapter()
        await _ensure_token(adapter)
        adapter._http_client = AsyncMock()

        mock_response = _make_http_response({"errCode": 0})
        adapter._http_client.post = AsyncMock(return_value=mock_response)

        result = await adapter.revoke_message(["msg-1"], chat_type="bot")

        call_args = adapter._http_client.post.call_args
        payload = call_args.kwargs.get("json", {})
        assert payload.get("chatType") == "bot"
        assert payload.get("messageIds") == ["msg-1"]

    async def test_revoke_group_type_with_sender_id(self, make_adapter):
        adapter = make_adapter()
        await _ensure_token(adapter)
        adapter._http_client = AsyncMock()

        mock_response = _make_http_response({"errCode": 0})
        adapter._http_client.post = AsyncMock(return_value=mock_response)

        result = await adapter.revoke_message(["msg-2"], chat_type="group", sender_id="sender-1")

        call_args = adapter._http_client.post.call_args
        payload = call_args.kwargs.get("json", {})
        assert payload.get("chatType") == "group"
        assert payload.get("senderId") == "sender-1"

    async def test_revoke_rejects_staff_type(self, make_adapter):
        adapter = make_adapter()
        await _ensure_token(adapter)

        with pytest.raises(ValueError, match="bot or group"):
            await adapter.revoke_message(["msg-3"], chat_type="staff")


class TestQueryGroups:
    async def test_query_groups_success(self, make_adapter):
        adapter = make_adapter()
        await _ensure_token(adapter)
        adapter._http_client = AsyncMock()

        groups_data = {"errCode": 0, "data": {"totalGroupIds": 2, "groupIds": ["g1", "g2"]}}
        mock_response = _make_http_response(groups_data)
        adapter._http_client.get = AsyncMock(return_value=mock_response)

        result = await adapter.query_groups()

        assert result.get("totalGroupIds") == 2
        assert "g1" in result.get("groupIds", [])