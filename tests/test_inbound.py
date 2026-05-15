import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from conftest import WS_TICKET_URL


class TestInboundMessageParsing:
    async def test_text_message_parsed(self, make_adapter):
        adapter = make_adapter()
        adapter.handle_message = AsyncMock()

        raw_msg = json.dumps({
            "events": [{
                "data": {
                    "msgType": "text",
                    "content": "hello world",
                    "msgId": "msg-1",
                    "senderId": "user-1",
                    "chatId": "chat-1",
                    "chatType": "p2pChat",
                    "senderName": "Alice",
                }
            }]
        })

        await adapter._on_message(raw_msg)

        adapter.handle_message.assert_called_once()
        event = adapter.handle_message.call_args[0][0]
        assert "hello world" in event.text
        assert event.message_id == "msg-1"

    async def test_group_message_sets_chat_type_group(self, make_adapter):
        adapter = make_adapter()
        adapter.handle_message = AsyncMock()

        raw_msg = json.dumps({
            "events": [{
                "data": {
                    "msgType": "text",
                    "content": "group msg",
                    "msgId": "msg-g1",
                    "senderId": "user-1",
                    "chatId": "chat-group-1",
                    "chatType": "groupChat",
                    "senderName": "Bob",
                }
            }]
        })

        await adapter._on_message(raw_msg)

        assert adapter._chat_type_map.get("chat-group-1") == "group"

    async def test_private_message_sets_chat_type_dm(self, make_adapter):
        adapter = make_adapter()
        adapter.handle_message = AsyncMock()

        raw_msg = json.dumps({
            "events": [{
                "data": {
                    "msgType": "text",
                    "content": "private msg",
                    "msgId": "msg-p1",
                    "senderId": "user-1",
                    "chatId": "chat-dm-1",
                    "chatType": "p2pChat",
                    "senderName": "Carol",
                }
            }]
        })

        await adapter._on_message(raw_msg)

        assert adapter._chat_type_map.get("chat-dm-1") == "dm"

    async def test_duplicate_message_skipped(self, make_adapter):
        adapter = make_adapter()
        adapter._dedup.is_duplicate = MagicMock(return_value=True)
        adapter.handle_message = AsyncMock()

        raw_msg = json.dumps({
            "events": [{
                "data": {
                    "msgType": "text",
                    "content": "duplicate",
                    "msgId": "msg-dup",
                    "senderId": "user-1",
                    "chatId": "chat-1",
                    "chatType": "p2pChat",
                }
            }]
        })

        await adapter._on_message(raw_msg)

        adapter.handle_message.assert_not_called()

    async def test_language_detection_cjk(self, make_adapter):
        adapter = make_adapter()
        assert adapter._detect_lang("你好世界") == "zh"
        assert adapter._detect_lang("Hello world") == "en"
        assert adapter._detect_lang("混合mixed") == "zh"

    async def test_multiple_events_in_one_message(self, make_adapter):
        adapter = make_adapter()
        adapter.handle_message = AsyncMock()

        raw_msg = json.dumps({
            "events": [
                {
                    "data": {
                        "msgType": "text",
                        "content": "msg1",
                        "msgId": "msg-1",
                        "senderId": "user-1",
                        "chatId": "chat-1",
                        "chatType": "p2pChat",
                    }
                },
                {
                    "data": {
                        "msgType": "text",
                        "content": "msg2",
                        "msgId": "msg-2",
                        "senderId": "user-2",
                        "chatId": "chat-2",
                        "chatType": "groupChat",
                    }
                },
            ]
        })

        await adapter._on_message(raw_msg)

        assert adapter.handle_message.call_count == 2

    async def test_invalid_json_handled(self, make_adapter):
        adapter = make_adapter()
        await adapter._on_message("not valid json{{{")
        adapter.handle_message.assert_not_called()

    async def test_empty_events_handled(self, make_adapter):
        adapter = make_adapter()
        await adapter._on_message(json.dumps({"events": []}))
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

        adapter._persist_chat_type_map()

        content = adapter._chat_type_file.read_text()
        data = json.loads(content)
        assert data.get("chat-group-1") == "group"
        assert data.get("chat-dm-1") == "dm"

    def test_persist_then_load_roundtrip(self, make_adapter):
        adapter = make_adapter()
        adapter._chat_type_map = {"g1": "group", "d1": "dm"}

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

        raw_msg = json.dumps({
            "events": [{
                "data": {
                    "msgType": "text",
                    "content": "hello",
                    "msgId": "msg-1",
                    "senderId": "user-1",
                    "chatId": "chat-group-new",
                    "chatType": "groupChat",
                }
            }]
        })

        await adapter._on_message(raw_msg)

        assert adapter._chat_type_map.get("chat-group-new") == "group"

        content = adapter._chat_type_file.read_text()
        data = json.loads(content)
        assert data.get("chat-group-new") == "group"