"""Tests for _extract_text and _extract_reference_text media handling."""

from unittest.mock import AsyncMock

import pytest


# ── _extract_text tests ──


class TestExtractText:
    """_extract_text returns (text, media_urls, media_types) with mediaId tagging."""

    async def test_image_returns_media_id_tag_and_media_urls(self, make_adapter):
        adapter = make_adapter()
        adapter._download_media = AsyncMock(return_value=(b"fake-png", "photo.png"))
        adapter._save_media_temp = AsyncMock(return_value="/tmp/test_img.png")

        msg_data = {"msgType": "image", "msgData": {"image": {"mediaIds": ["media-img-001"]}}}
        text, urls, types = await adapter._extract_text(msg_data)
        assert "media-img-001" in text
        assert len(urls) == 1
        assert types == ["image"]

    async def test_image_download_fail_keeps_media_id(self, make_adapter):
        adapter = make_adapter()
        adapter._download_media = AsyncMock(return_value=None)

        msg_data = {"msgType": "image", "msgData": {"image": {"mediaIds": ["media-img-bad"]}}}
        text, urls, types = await adapter._extract_text(msg_data)
        assert "media-img-bad" in text
        assert urls == []

    async def test_file_includes_media_id_in_text(self, make_adapter):
        adapter = make_adapter()
        adapter._download_media = AsyncMock(return_value=(b"data", "doc.txt"))
        adapter._save_media_temp = AsyncMock(return_value="/tmp/test_file.dat")

        msg_data = {"msgType": "file", "msgData": {"file": {"mediaIds": ["media-file-001"]}}}
        text, urls, types = await adapter._extract_text(msg_data)
        assert "media-file-001" in text
        assert urls == []

    async def test_video_returns_media_id_and_tag(self, make_adapter):
        adapter = make_adapter()
        adapter._download_media = AsyncMock(return_value=(b"fake-video", "clip.mp4"))
        adapter._save_media_temp = AsyncMock(return_value="/tmp/test_vid.mp4")

        msg_data = {"msgType": "video", "msgData": {"video": {"mediaIds": ["media-vid-001"]}}}
        text, urls, types = await adapter._extract_text(msg_data)
        assert "media-vid-001" in text
        assert types == ["video"]

    async def test_text_returns_plain_content_no_media(self, make_adapter):
        adapter = make_adapter()
        msg_data = {"msgType": "text", "msgData": {"text": {"content": "plain text"}}}
        text, urls, types = await adapter._extract_text(msg_data)
        assert text == "plain text"
        assert urls == []

    async def test_sticker_includes_sticker_id(self, make_adapter):
        adapter = make_adapter()
        msg_data = {"msgType": "sticker", "msgData": {"sticker": {"stickerId": 888}}}
        text, urls, types = await adapter._extract_text(msg_data)
        assert "888" in text
        assert urls == []


# ── _extract_reference_text tests ──


class TestExtractReferenceText:
    """_extract_reference_text returns (text, media_urls, media_types)."""

    async def test_null_reference_returns_empty(self, make_adapter):
        adapter = make_adapter()
        text, urls, types = await adapter._extract_reference_text(None)
        assert text == ""
        assert urls == []

    async def test_sticker_reference_includes_sticker_id(self, make_adapter):
        adapter = make_adapter()
        ref_msg = {"msgType": "sticker", "msgData": {"sticker": {"stickerId": 12713984}}}
        text, urls, types = await adapter._extract_reference_text(ref_msg)
        assert "12713984" in text
        assert urls == []

    async def test_format_reference_extracts_markdown(self, make_adapter):
        adapter = make_adapter()
        ref_msg = {"msgType": "format", "msgData": {"format": {"text": "**hello**", "formatType": "markdown"}}}
        text, urls, types = await adapter._extract_reference_text(ref_msg)
        assert "**hello**" in text
        assert urls == []

    async def test_image_reference_with_content_and_download(self, make_adapter):
        adapter = make_adapter()
        adapter._download_media = AsyncMock(return_value=(b"fake-png", "ref.png"))
        adapter._save_media_temp = AsyncMock(return_value="/tmp/ref_img.png")

        ref_msg = {"msgType": "image", "msgData": {"image": {"mediaIds": ["media-ref-001"], "content": "看到这个了吗？"}}}
        text, urls, types = await adapter._extract_reference_text(ref_msg)
        assert "media-ref-001" in text
        assert "看到这个了吗？" in text
        assert types == ["image"]

    async def test_image_reference_download_fail_keeps_media_id(self, make_adapter):
        adapter = make_adapter()
        adapter._download_media = AsyncMock(return_value=None)

        ref_msg = {"msgType": "image", "msgData": {"image": {"mediaIds": ["media-ref-bad"]}}}
        text, urls, types = await adapter._extract_reference_text(ref_msg)
        assert "media-ref-bad" in text
        assert urls == []

    async def test_file_reference_content_only(self, make_adapter):
        adapter = make_adapter()
        ref_msg = {"msgType": "file", "msgData": {"file": {"content": "文字文件混排"}}}
        text, urls, types = await adapter._extract_reference_text(ref_msg)
        assert "文字文件混排" in text
        assert urls == []

    async def test_file_reference_with_media_id(self, make_adapter):
        adapter = make_adapter()
        adapter._download_media = AsyncMock(return_value=(b"file-data", "doc.md"))
        adapter._save_media_temp = AsyncMock(return_value="/tmp/ref_file.md")

        ref_msg = {"msgType": "file", "msgData": {"file": {"mediaIds": ["media-file-ref"], "content": ""}}}
        text, urls, types = await adapter._extract_reference_text(ref_msg)
        assert "media-file-ref" in text
        assert urls == []
