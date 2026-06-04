import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from conftest import WS_TICKET_URL, _StubSendResult


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


INBOUND_MSG_DATA_PRIVATE = {
    "msgType": "text",
    "messageId": "msg-p1",
    "chatType": "p2p",
    "from": "user-1",
    "conversationId": "chat-dm-1",
    "senderName": "Alice",
    "text": {"content": "private hello"},
    "msgData": {"text": {"content": "private hello"}},
}

INBOUND_MSG_DATA_GROUP = {
    "msgType": "text",
    "messageId": "msg-g1",
    "chatType": "group",
    "from": "user-2",
    "conversationId": "chat-group-1",
    "senderName": "Bob",
    "text": {"content": "group hello"},
    "msgData": {"text": {"content": "group hello"}},
}


class TestInboundMessageParsing:
    async def test_private_message_parsed(self, make_adapter):
        adapter = make_adapter()
        adapter.handle_message = AsyncMock()

        raw_msg = json.dumps({"events": [{"data": INBOUND_MSG_DATA_PRIVATE}]})
        await adapter._on_message(raw_msg)

        adapter.handle_message.assert_called_once()
        event = adapter.handle_message.call_args[0][0]
        assert "private hello" in event.text
        assert event.message_id == "msg-p1"

    async def test_group_message_sets_chat_type_group(self, make_adapter):
        adapter = make_adapter()
        adapter.handle_message = AsyncMock()

        await adapter._on_message(json.dumps({"events": [{"data": INBOUND_MSG_DATA_GROUP}]}))

        assert adapter._chat_type_map.get("chat-group-1") == "group"

    async def test_private_message_sets_chat_type_dm(self, make_adapter):
        adapter = make_adapter()
        adapter.handle_message = AsyncMock()

        await adapter._on_message(json.dumps({"events": [{"data": INBOUND_MSG_DATA_PRIVATE}]}))

        assert adapter._chat_type_map.get("chat-dm-1") == "dm"

    async def test_duplicate_message_skipped(self, make_adapter):
        adapter = make_adapter()
        adapter._dedup.is_duplicate = lambda msg_id: msg_id == "msg-dup"
        adapter.handle_message = AsyncMock()

        dup_data = dict(INBOUND_MSG_DATA_PRIVATE, messageId="msg-dup")
        await adapter._on_message(json.dumps({"events": [{"data": dup_data}]}))

        adapter.handle_message.assert_not_called()

    async def test_language_detection_cjk(self, make_adapter):
        adapter = make_adapter()
        assert adapter._detect_lang("你好世界") == "zh"
        assert adapter._detect_lang("Hello world") == "en"

    async def test_multiple_events_in_one_message(self, make_adapter):
        adapter = make_adapter()
        adapter.handle_message = AsyncMock()

        multi_msg = json.dumps({
            "events": [
                {"data": INBOUND_MSG_DATA_PRIVATE},
                {"data": INBOUND_MSG_DATA_GROUP},
            ]
        })

        await adapter._on_message(multi_msg)
        assert adapter.handle_message.call_count == 2

    async def test_invalid_json_handled(self, make_adapter):
        adapter = make_adapter()
        await adapter._on_message("not valid json{{{")
        adapter.handle_message.assert_not_called()

    async def test_empty_events_handled(self, make_adapter):
        adapter = make_adapter()
        await adapter._on_message(json.dumps({"events": []}))
        adapter.handle_message.assert_not_called()

    async def test_empty_text_message_skipped(self, make_adapter):
        adapter = make_adapter()
        adapter.handle_message = AsyncMock()

        empty_data = {
            "msgType": "text",
            "messageId": "msg-empty",
            "chatType": "p2p",
            "from": "user-1",
            "conversationId": "chat-1",
            "msgData": {"text": {"content": ""}},
        }
        await adapter._on_message(json.dumps({"events": [{"data": empty_data}]}))

        adapter.handle_message.assert_not_called()


class TestChatTypeMapPersistence:
    def test_load_from_file(self, make_adapter):
        adapter = make_adapter()
        data = {"chat-group-1": "group", "chat-dm-1": "dm"}
        adapter._chat_type_file.parent.mkdir(parents=True, exist_ok=True)
        adapter._chat_type_file.write_text(json.dumps(data))

        adapter._load_chat_type_map()

        assert adapter._chat_type_map.get("chat-group-1") == "group"
        assert adapter._chat_type_map.get("chat-dm-1") == "dm"

    def test_persist_to_file(self, make_adapter):
        adapter = make_adapter()
        adapter._chat_type_map = {"chat-group-1": "group", "chat-dm-1": "dm"}
        adapter._chat_type_map_dirty = True

        adapter._persist_chat_type_map()

        content = adapter._chat_type_file.read_text()
        data = json.loads(content)
        assert data.get("chat-group-1") == "group"
        assert data.get("chat-dm-1") == "dm"

    def test_persist_then_load_roundtrip(self, make_adapter):
        adapter = make_adapter()
        adapter._chat_type_map = {"g1": "group", "d1": "dm"}
        adapter._chat_type_map_dirty = True

        adapter._persist_chat_type_map()

        adapter._chat_type_map = {}
        adapter._load_chat_type_map()

        assert adapter._chat_type_map == {"g1": "group", "d1": "dm"}

    def test_missing_file_does_not_crash(self, make_adapter):
        adapter = make_adapter()
        adapter._chat_type_map = {}
        adapter._load_chat_type_map()
        assert adapter._chat_type_map == {}

    async def test_inbound_updates_map_and_persists(self, make_adapter):
        adapter = make_adapter()
        adapter.handle_message = AsyncMock()

        await adapter._on_message(json.dumps({"events": [{"data": INBOUND_MSG_DATA_GROUP}]}))

        assert adapter._chat_type_map.get("chat-group-1") == "group"

        content = adapter._chat_type_file.read_text()
        data = json.loads(content)
        assert data.get("chat-group-1") == "group"