"""Regression tests for first-install / clean-state scenarios.

These tests cover edge cases that historically caused production bugs:
- DM routing before owner_id is known (v2.9.13 fix)
- First inbound DM establishes owner_id and chat_type_map correctly
- chat_type_map persistence survives adapter restarts
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest


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


def _mk_ws_msg(event_type, data):
    return json.dumps({"events": [{"type": event_type, "data": data}]})


def _mk_priv(data):
    return _mk_ws_msg("bot_private_message", data)


DM_MSG_DATA = {
    "msgType": "text",
    "msgId": "msg-first",
    "chatType": "p2p",
    "from": "user-first",
    "conversationId": "chat-dm-first",
    "senderName": "FirstUser",
    "msgData": {"text": {"content": "hello bot"}},
}


class TestFirstInstallScenario:
    """End-to-end: clean-state adapter receives first DM, then sends reply."""

    async def test_first_dm_sets_owner_id_and_reply_routes_to_dm(self, make_adapter):
        """First DM → owner_id set, chat_type_map populated → reply uses DM endpoint."""
        adapter = make_adapter()
        adapter._require_mention = False
        adapter.handle_message = AsyncMock()
        # Force clean state (make_adapter may load owner_id from real disk)
        adapter._owner_id = None
        adapter._chat_type_map = {}
        adapter._chat_type_map_dirty = False

        # Pre-condition: clean state (no owner_id, no chat_type_map)
        assert adapter._owner_id is None
        assert adapter._chat_type_map == {}

        # Step 1: receive first inbound DM
        await adapter._on_message(_mk_priv(DM_MSG_DATA))

        # Verify: owner_id and chat_type_map are set
        assert adapter._owner_id == "user-first"
        assert adapter._chat_type_map.get("user-first") == "dm"

        # Step 2: send reply to the same user
        await _ensure_token(adapter)
        adapter._http_client = AsyncMock()
        mock_resp = _make_http_response({"errCode": 0, "data": {"msgId": "msg-reply"}})
        adapter._http_client.post = AsyncMock(return_value=mock_resp)

        result = await adapter.send_text("user-first", "welcome!")

        # Verify: routed to DM endpoint (not group)
        call_args = adapter._http_client.post.call_args
        url = call_args[0][0] if call_args[0] else call_args.kwargs.get("url")
        assert "/v1/bot/messages/create" in url

    async def test_first_dm_reply_before_owner_saved(self, make_adapter):
        """Reply via chat_type_map works even if owner_id hasn't been persisted yet."""
        adapter = make_adapter()
        adapter._require_mention = False
        adapter.handle_message = AsyncMock()
        # chat_type_map already loaded from disk (simulating previous session)
        adapter._chat_type_map = {"user-first": "dm"}
        # owner_id NOT loaded (simulating first run after clean install)
        adapter._owner_id = None

        await _ensure_token(adapter)
        adapter._http_client = AsyncMock()
        mock_resp = _make_http_response({"errCode": 0, "data": {"msgId": "msg-reply"}})
        adapter._http_client.post = AsyncMock(return_value=mock_resp)

        result = await adapter.send_text("user-first", "hello again")

        call_args = adapter._http_client.post.call_args
        url = call_args[0][0] if call_args[0] else call_args.kwargs.get("url")
        assert "/v1/bot/messages/create" in url

    async def test_group_chat_does_not_overwrite_owner(self, make_adapter):
        """Group messages must NOT set owner_id or mark group chat as dm."""
        adapter = make_adapter()
        adapter._require_mention = False
        adapter.handle_message = AsyncMock()
        # Force clean state
        adapter._owner_id = None
        adapter._chat_type_map = {}
        adapter._chat_type_map_dirty = False

        group_data = {
            "msgType": "text",
            "msgId": "msg-group-first",
            "chatType": "group",
            "from": "user-in-group",
            "conversationId": "chat-group-1",
            "groupId": "group-1",
            "senderName": "GroupUser",
            "msgData": {"text": {"content": "hello from group"}},
        }
        group_msg = _mk_ws_msg("bot_group_message", group_data)

        await adapter._on_message(group_msg)

        # Group message should not set owner_id
        assert adapter._owner_id is None
        # Group chat_id should be marked as "group", not "dm"
        assert adapter._chat_type_map.get("group-1") == "group"
        assert adapter._chat_type_map.get("user-in-group") is None

    async def test_chat_type_map_survives_clean_restart(self, make_adapter):
        """chat_type_map loaded from disk routes correctly without owner_id."""
        adapter = make_adapter()
        # Simulate: adapter restarted, chat_type_map loaded from disk
        adapter._owner_id = None
        adapter._chat_type_map = {"dm-user-1": "dm", "group-1": "group"}

        await _ensure_token(adapter)
        adapter._http_client = AsyncMock()

        # Send to known DM → should use private endpoint
        mock_resp = _make_http_response({"errCode": 0, "data": {"msgId": "msg-dm"}})
        adapter._http_client.post = AsyncMock(return_value=mock_resp)
        await adapter.send_text("dm-user-1", "hi")

        call_args = adapter._http_client.post.call_args
        url = call_args[0][0] if call_args[0] else call_args.kwargs.get("url")
        assert "/v1/bot/messages/create" in url

        # Send to known group → should use group endpoint
        mock_resp2 = _make_http_response({"errCode": 0, "data": {"msgId": "msg-group"}})
        adapter._http_client.post = AsyncMock(return_value=mock_resp2)
        await adapter.send_text("group-1", "hi group")

        call_args2 = adapter._http_client.post.call_args
        url2 = call_args2[0][0] if call_args2[0] else call_args2.kwargs.get("url")
        assert "/v1/messages/group/create" in url2
