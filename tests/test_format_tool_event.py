import sys
from unittest.mock import MagicMock
from dataclasses import dataclass

import pytest

from conftest import _StubPlatformConfig, _StubHomeChannel


@dataclass(frozen=True)
class FakeToolCallChunk:
    tool_name: str
    preview: str = None
    args: dict = None
    index: int = 0


def _patch_stream_events(monkeypatch):
    mod = MagicMock()
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


class TestFormatToolEvent:

    def test_returns_none_for_non_tool_call_chunk(self, adapter, monkeypatch):
        _patch_stream_events(monkeypatch)
        _patch_display(monkeypatch)
        result = adapter.format_tool_event("not a ToolCallChunk", mode="all")
        assert result is None

    def test_all_mode_with_preview(self, adapter, monkeypatch):
        _patch_stream_events(monkeypatch)
        _patch_display(monkeypatch, emoji_map={"web_search": "🔍"})
        event = FakeToolCallChunk(tool_name="web_search", preview="蓝信断连")
        result = adapter.format_tool_event(event, mode="all")
        assert result == "🔍 **web_search**：蓝信断连"

    def test_all_mode_without_preview(self, adapter, monkeypatch):
        _patch_stream_events(monkeypatch)
        _patch_display(monkeypatch, emoji_map={"bash": "💻"})
        event = FakeToolCallChunk(tool_name="bash")
        result = adapter.format_tool_event(event, mode="all")
        assert result == "💻 **bash** ..."

    def test_all_mode_preview_truncation(self, adapter, monkeypatch):
        _patch_stream_events(monkeypatch)
        _patch_display(monkeypatch)
        long_preview = "这是一段非常长的预览文本超过四十个字符需要截断处理"
        event = FakeToolCallChunk(tool_name="tool", preview=long_preview)
        result = adapter.format_tool_event(event, mode="all", preview_max_len=20)
        assert len(result.split("：", 1)[1]) <= 20

    def test_verbose_mode_with_args(self, adapter, monkeypatch):
        _patch_stream_events(monkeypatch)
        _patch_display(monkeypatch, emoji_map={"web_search": "🔍"})
        event = FakeToolCallChunk(
            tool_name="web_search",
            args={"query": "蓝信断连", "limit": 3},
        )
        result = adapter.format_tool_event(event, mode="verbose")
        assert "🔍 **web_search**" in result
        assert "`['query', 'limit']`" in result
        assert "**query**：蓝信断连" in result
        assert "**limit**：3" in result

    def test_verbose_mode_with_preview_no_args(self, adapter, monkeypatch):
        _patch_stream_events(monkeypatch)
        _patch_display(monkeypatch)
        event = FakeToolCallChunk(tool_name="tool", preview="some preview")
        result = adapter.format_tool_event(event, mode="verbose")
        assert result == "⚙️ **tool**：some preview"

    def test_verbose_mode_neither_args_nor_preview(self, adapter, monkeypatch):
        _patch_stream_events(monkeypatch)
        _patch_display(monkeypatch)
        event = FakeToolCallChunk(tool_name="tool")
        result = adapter.format_tool_event(event, mode="verbose")
        assert result == "⚙️ **tool** ..."

    def test_new_mode_same_format_as_all(self, adapter, monkeypatch):
        _patch_stream_events(monkeypatch)
        _patch_display(monkeypatch, emoji_map={"bash": "💻"})
        event = FakeToolCallChunk(tool_name="bash", preview="ls -la")
        result = adapter.format_tool_event(event, mode="new")
        assert result == "💻 **bash**：ls -la"

    def test_verbose_arg_value_truncation(self, adapter, monkeypatch):
        _patch_stream_events(monkeypatch)
        _patch_display(monkeypatch)
        long_val = "x" * 100
        event = FakeToolCallChunk(tool_name="tool", args={"q": long_val})
        result = adapter.format_tool_event(event, mode="verbose", preview_max_len=20)
        assert "**q**：" in result
        val_part = result.split("**q**：", 1)[1].split("\n")[0]
        assert len(val_part) <= 20

    def test_default_emoji_when_no_mapping(self, adapter, monkeypatch):
        _patch_stream_events(monkeypatch)
        _patch_display(monkeypatch, emoji_map={})
        event = FakeToolCallChunk(tool_name="unknown_tool", preview="test")
        result = adapter.format_tool_event(event, mode="all")
        assert result.startswith("⚙️")