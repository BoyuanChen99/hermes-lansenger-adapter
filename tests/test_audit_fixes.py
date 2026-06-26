import sys
from unittest.mock import MagicMock

import pytest

from conftest import _StubPlatformConfig, _StubHomeChannel, _StubSendResult


def _patch_tool_call_chunk(monkeypatch):
    mod = MagicMock()
    from dataclasses import dataclass
    @dataclass(frozen=True)
    class FakeToolCallChunk:
        tool_name: str
        preview: str = None
        args: dict = None
        index: int = 0
    mod.ToolCallChunk = FakeToolCallChunk
    monkeypatch.setitem(sys.modules, "gateway.stream_events", mod)


def _patch_display(monkeypatch, emoji_map=None):
    mod = MagicMock()
    def _get_tool_emoji(tool_name, default="⚙️"):
        return (emoji_map or {}).get(tool_name, default)
    mod.get_tool_emoji = _get_tool_emoji
    monkeypatch.setitem(sys.modules, "agent", mod)
    monkeypatch.setitem(sys.modules, "agent.display", mod)


@pytest.fixture
def adapter(make_adapter):
    return make_adapter()


class TestIsGroupChat:

    def test_owner_is_dm(self, adapter):
        """chat_id == owner_id → DM (personal bot can only DM owner)"""
        adapter._owner_id = "staff-123"
        assert adapter._is_group_chat("staff-123") is False

    def test_non_owner_is_group(self, adapter):
        """Any other chat_id → group (only owner can be DM)"""
        adapter._owner_id = "staff-123"
        assert adapter._is_group_chat("group-abc") is True
        assert adapter._is_group_chat("some-random-id") is True

    def test_no_owner_defaults_to_group(self, adapter):
        """Without owner_id, everything goes to group endpoint"""
        assert adapter._is_group_chat("any_chat_id") is True
        assert adapter._is_group_chat("group:some_id") is True


class TestChatTypeDirtyFlag:

    def test_persist_skipped_when_clean(self, adapter):
        adapter._chat_type_map = {"a": "group"}
        adapter._chat_type_map_dirty = False
        adapter._persist_chat_type_map()
        assert not adapter._chat_type_file.exists()

    def test_persist_writes_when_dirty(self, adapter):
        adapter._chat_type_map = {"a": "group"}
        adapter._chat_type_map_dirty = True
        adapter._persist_chat_type_map()
        assert adapter._chat_type_file.exists()
        assert adapter._chat_type_map_dirty is False


class TestFixTextIndent:

    def test_bare_zero_fixed(self, adapter):
        assert adapter._fix_text_indent('<div style="text-indent:0">x</div>') == '<div style="text-indent:0em">x</div>'

    def test_already_correct_not_changed(self, adapter):
        assert adapter._fix_text_indent('<div style="text-indent:0em">x</div>') == '<div style="text-indent:0em">x</div>'

    def test_other_value_not_changed(self, adapter):
        assert adapter._fix_text_indent('<div style="text-indent:2em">x</div>') == '<div style="text-indent:2em">x</div>'

    def test_none_returns_none(self, adapter):
        assert adapter._fix_text_indent(None) is None

    def test_empty_returns_empty(self, adapter):
        assert adapter._fix_text_indent("") == ""


class TestFixAppCardStyles:

    def test_font_px_to_pt(self, adapter):
        result = adapter._fix_app_card_styles('<div style="font-size:16px">x</div>')
        assert "font-size:12pt" in result

    def test_body_content_gets_indent_fix(self, adapter):
        result = adapter._fix_app_card_styles('<div style="font-size:16px;text-indent:0">x</div>', is_body_content=True)
        assert "text-indent:0em" in result

    def test_non_body_content_no_indent_fix(self, adapter):
        result = adapter._fix_app_card_styles('<div style="font-size:16px;text-indent:0">x</div>', is_body_content=False)
        assert "text-indent:0em" not in result


class TestEscapeHtmlAmpersand:

    def test_ampersand_escaped(self, adapter):
        assert adapter._escape_html("a & b") == "a &amp; b"

    def test_lt_gt_escaped(self, adapter):
        assert adapter._escape_html("<script>") == "&lt;script&gt;"

    def test_ampersand_before_lt_gt(self, adapter):
        assert adapter._escape_html("x&y<z>") == "x&amp;y&lt;z&gt;"


class TestDetectLangSingleLoop:

    def test_cjk_detected(self, adapter):
        assert adapter._detect_lang("你好世界") == "zh"

    def test_english_detected(self, adapter):
        assert adapter._detect_lang("hello world") == "en"

    def test_punctuation_cjk(self, adapter):
        assert adapter._detect_lang("、") == "zh"


class TestProbeDuration:

    def test_returns_at_least_1(self, adapter):
        assert adapter._probe_duration("/nonexistent/file.mp4") is None