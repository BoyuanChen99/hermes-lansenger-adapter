import json
import os
import tempfile
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


class TestSendTextWithMedia:
    async def test_image_media_payload(self, make_adapter):
        adapter = make_adapter()
        await _ensure_token(adapter)
        adapter._http_client = AsyncMock()

        chat_id = "2285568-user123"
        adapter._owner_id = chat_id  # owner → DM

        mock_response = _make_http_response({"errCode": 0, "data": {"msgId": "msg-img1"}})
        adapter._http_client.post = AsyncMock(return_value=mock_response)

        result = await adapter.send_text_with_media(
            chat_id, "image caption", media_type=2, media_ids=["media-img-1"]
        )

        call_args = adapter._http_client.post.call_args
        payload = call_args.kwargs.get("json", {})
        assert payload.get("msgType") == "text"
        text_data = payload.get("msgData", {}).get("text", {})
        assert text_data.get("mediaType") == 2
        assert text_data.get("mediaIds") == ["media-img-1"]
        assert text_data.get("content") == "image caption"

    async def test_video_requires_two_media_ids(self, make_adapter):
        adapter = make_adapter()
        await _ensure_token(adapter)
        adapter._http_client = AsyncMock()

        chat_id = "2285568-group123"
        adapter._chat_type_map[chat_id] = "group"

        mock_response = _make_http_response({"errCode": 0, "data": {"msgId": "msg-vid1"}})
        adapter._http_client.post = AsyncMock(return_value=mock_response)

        result = await adapter.send_text_with_media(
            chat_id, "video caption", media_type=1, media_ids=["video-id", "cover-id"]
        )

        call_args = adapter._http_client.post.call_args
        payload = call_args.kwargs.get("json", {})
        text_data = payload.get("msgData", {}).get("text", {})
        assert text_data.get("mediaType") == 1
        assert text_data.get("mediaIds") == ["video-id", "cover-id"]
        assert payload.get("groupId") == chat_id

    async def test_file_media_payload(self, make_adapter):
        adapter = make_adapter()
        await _ensure_token(adapter)
        adapter._http_client = AsyncMock()

        chat_id = "2285568-user123"
        adapter._owner_id = chat_id  # owner → DM

        mock_response = _make_http_response({"errCode": 0, "data": {"msgId": "msg-file1"}})
        adapter._http_client.post = AsyncMock(return_value=mock_response)

        result = await adapter.send_text_with_media(
            chat_id, "file description", media_type=3, media_ids=["media-file-1"]
        )

        call_args = adapter._http_client.post.call_args
        payload = call_args.kwargs.get("json", {})
        text_data = payload.get("msgData", {}).get("text", {})
        assert text_data.get("mediaType") == 3
        assert text_data.get("mediaIds") == ["media-file-1"]

    async def test_media_with_reminder(self, make_adapter):
        adapter = make_adapter()
        await _ensure_token(adapter)
        adapter._http_client = AsyncMock()

        chat_id = "2285568-group123"
        adapter._chat_type_map[chat_id] = "group"

        mock_response = _make_http_response({"errCode": 0, "data": {"msgId": "msg-mr1"}})
        adapter._http_client.post = AsyncMock(return_value=mock_response)

        reminder = {"all": True, "userIds": ["user-1"]}
        result = await adapter.send_text_with_media(
            chat_id, "check this", media_type=2, media_ids=["img-1"], reminder=reminder
        )

        call_args = adapter._http_client.post.call_args
        payload = call_args.kwargs.get("json", {})
        text_data = payload.get("msgData", {}).get("text", {})
        assert text_data.get("reminder") == reminder

    async def test_media_group_routes_to_group_endpoint(self, make_adapter):
        adapter = make_adapter()
        await _ensure_token(adapter)
        adapter._http_client = AsyncMock()

        chat_id = "2285568-group123"
        adapter._chat_type_map[chat_id] = "group"

        mock_response = _make_http_response({"errCode": 0, "data": {"msgId": "msg-mg1"}})
        adapter._http_client.post = AsyncMock(return_value=mock_response)

        await adapter.send_text_with_media(chat_id, "test", media_type=2, media_ids=["img-1"])

        call_args = adapter._http_client.post.call_args
        url = call_args[0][0]
        assert "/v1/messages/group/create" in url

    async def test_media_private_routes_to_bot_endpoint(self, make_adapter):
        adapter = make_adapter()
        await _ensure_token(adapter)
        adapter._http_client = AsyncMock()

        chat_id = "2285568-user123"
        adapter._owner_id = chat_id  # owner → DM

        mock_response = _make_http_response({"errCode": 0, "data": {"msgId": "msg-mp1"}})
        adapter._http_client.post = AsyncMock(return_value=mock_response)

        await adapter.send_text_with_media(chat_id, "test", media_type=3, media_ids=["file-1"])

        call_args = adapter._http_client.post.call_args
        url = call_args[0][0]
        assert "/v1/bot/messages/create" in url


class TestUploadMediaFile:
    async def test_upload_returns_media_id(self, make_adapter):
        adapter = make_adapter()
        await _ensure_token(adapter)
        adapter._http_client = AsyncMock()

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"fake image data")
            temp_path = f.name

        try:
            upload_resp = _make_http_response({"errCode": 0, "data": {"mediaId": "uploaded-media-1"}})
            adapter._http_client.post = AsyncMock(return_value=upload_resp)

            result = await adapter.upload_media_file(temp_path, media_type=2)

            assert result == "uploaded-media-1"
        finally:
            os.unlink(temp_path)

    async def test_upload_api_error_returns_none(self, make_adapter):
        adapter = make_adapter()
        await _ensure_token(adapter)
        adapter._http_client = AsyncMock()

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"fake data")
            temp_path = f.name

        try:
            upload_resp = _make_http_response({"errCode": 10001, "errMsg": "invalid"})
            adapter._http_client.post = AsyncMock(return_value=upload_resp)

            result = await adapter.upload_media_file(temp_path, media_type=2)

            assert result is None
        finally:
            os.unlink(temp_path)

    async def test_upload_http_error_returns_none(self, make_adapter):
        adapter = make_adapter()
        await _ensure_token(adapter)
        adapter._http_client = AsyncMock()
        adapter._http_client.post = AsyncMock(side_effect=Exception("network error"))

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"fake data")
            temp_path = f.name

        try:
            result = await adapter.upload_media_file(temp_path, media_type=2)
            assert result is None
        finally:
            os.unlink(temp_path)


class TestSendFile:
    async def test_send_file_nonexistent_returns_error(self, make_adapter):
        adapter = make_adapter()
        await _ensure_token(adapter)

        result = await adapter.send_file(chat_id="user-1", file_path="/nonexistent/file.pdf")

        assert result.success is False
        assert "not found" in result.error.lower() or "File not found" in result.error

    async def test_send_file_real_file(self, make_adapter):
        adapter = make_adapter()
        await _ensure_token(adapter)
        adapter._http_client = AsyncMock()

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"fake pdf data")
            temp_path = f.name

        try:
            upload_resp = _make_http_response({"errCode": 0, "data": {"mediaId": "m1"}})
            send_resp = _make_http_response({"errCode": 0, "data": {"msgId": "msg-sf1"}})

            adapter._http_client.post = AsyncMock(side_effect=[upload_resp, send_resp])

            result = await adapter.send_file("user-1", temp_path, caption="doc")

            assert result.success is True
            assert result.message_id == "msg-sf1"
        finally:
            os.unlink(temp_path)

    async def test_send_image_file(self, make_adapter):
        adapter = make_adapter()
        await _ensure_token(adapter)
        adapter._http_client = AsyncMock()

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(b"fake jpg data")
            temp_path = f.name

        try:
            upload_resp = _make_http_response({"errCode": 0, "data": {"mediaId": "img-m1"}})
            send_resp = _make_http_response({"errCode": 0, "data": {"msgId": "msg-si1"}})

            adapter._http_client.post = AsyncMock(side_effect=[upload_resp, send_resp])
            adapter._owner_id = "user-1"  # owner → DM

            result = await adapter.send_image_file("user-1", temp_path, caption="photo")

            assert result.success is True
        finally:
            os.unlink(temp_path)