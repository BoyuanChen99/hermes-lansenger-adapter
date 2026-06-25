"""Tests for group chat policy enforcement (_check_group_policy) and inbound routing."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# _check_group_policy tests
# ---------------------------------------------------------------------------

class TestCheckGroupPolicy:
    """Tests for the 4-gate group policy decision logic."""

    # -- helpers ----------------------------------------------------------

    def _make_adapter(self, make_adapter, **kw):
        """Create an adapter with specific group policy config."""
        adapter = make_adapter()
        adapter._group_policy = kw.pop("group_policy", "open")
        adapter._group_allow_senders = kw.pop("group_allow_senders", [])
        adapter._groups_config = kw.pop("groups_config", {})
        adapter._require_mention = kw.pop("require_mention", True)
        return adapter

    # -- open mode --------------------------------------------------------

    def test_open_allows_any_group(self, make_adapter):
        adapter = self._make_adapter(make_adapter, group_policy="open")
        assert adapter._check_group_policy("chat-unknown", "user-1", is_at_me=True) is False

    def test_open_allows_with_is_at_all(self, make_adapter):
        """is_at_all should bypass require_mention even in open mode."""
        adapter = self._make_adapter(make_adapter, group_policy="open",
                                     require_mention=True)
        assert adapter._check_group_policy("chat-1", "user-1", is_at_me=False, is_at_all=True) is False

    # -- disabled mode ----------------------------------------------------

    def test_disabled_blocks_all(self, make_adapter):
        adapter = self._make_adapter(make_adapter, group_policy="disabled")
        assert adapter._check_group_policy("chat-1", "user-1", is_at_me=True) is True

    def test_disabled_bypassed_by_per_group_enabled_true(self, make_adapter):
        adapter = self._make_adapter(make_adapter, group_policy="disabled",
            groups_config={"chat-1": {"enabled": True}})
        # per-group enabled=true bypasses global disabled
        assert adapter._check_group_policy("chat-1", "user-1", is_at_me=True) is False

    # -- allowlist mode ---------------------------------------------------

    def test_allowlist_blocks_group_not_in_config(self, make_adapter):
        adapter = self._make_adapter(make_adapter, group_policy="allowlist",
            groups_config={"chat-1": {"enabled": True}})
        assert adapter._check_group_policy("chat-unknown", "user-1", is_at_me=True) is True

    def test_allowlist_allows_group_in_config(self, make_adapter):
        adapter = self._make_adapter(make_adapter, group_policy="allowlist",
            groups_config={"chat-1": {"enabled": True}})
        assert adapter._check_group_policy("chat-1", "user-1", is_at_me=True) is False

    # -- sender-level global whitelist -------------------------------------

    def test_allowlist_sender_not_in_global_whitelist(self, make_adapter):
        adapter = self._make_adapter(make_adapter, group_policy="allowlist",
            group_allow_senders=["user-boss"],
            groups_config={"chat-1": {}})
        assert adapter._check_group_policy("chat-1", "user-rando", is_at_me=True) is True

    def test_allowlist_sender_in_global_whitelist(self, make_adapter):
        adapter = self._make_adapter(make_adapter, group_policy="allowlist",
            group_allow_senders=["user-boss"],
            groups_config={"chat-1": {"enabled": True}})
        assert adapter._check_group_policy("chat-1", "user-boss", is_at_me=True) is False

    def test_allowlist_empty_global_whitelist_allows_all(self, make_adapter):
        """Empty sender whitelist means all senders pass."""
        adapter = self._make_adapter(make_adapter, group_policy="allowlist",
            group_allow_senders=[],
            groups_config={"chat-1": {"enabled": True}})
        assert adapter._check_group_policy("chat-1", "user-anyone", is_at_me=True) is False

    # -- per-group enabled=false ------------------------------------------

    def test_per_group_disabled_overrides_open(self, make_adapter):
        adapter = self._make_adapter(make_adapter, group_policy="open",
            groups_config={"chat-1": {"enabled": False}})
        assert adapter._check_group_policy("chat-1", "user-1", is_at_me=True) is True

    # -- per-group allow_from ---------------------------------------------

    def test_per_group_allow_from_blocks_untlisted_sender(self, make_adapter):
        adapter = self._make_adapter(make_adapter, group_policy="open",
            groups_config={"chat-1": {"allow_from": ["alice", "bob"]}})
        assert adapter._check_group_policy("chat-1", "eve", is_at_me=True) is True

    def test_per_group_allow_from_allows_listed_sender(self, make_adapter):
        adapter = self._make_adapter(make_adapter, group_policy="open",
            groups_config={"chat-1": {"allow_from": ["alice", "bob"]}})
        assert adapter._check_group_policy("chat-1", "alice", is_at_me=True) is False

    def test_per_group_allow_from_empty_allows_all(self, make_adapter):
        adapter = self._make_adapter(make_adapter, group_policy="open",
            groups_config={"chat-1": {"allow_from": []}})
        assert adapter._check_group_policy("chat-1", "anyone", is_at_me=True) is False

    # -- require_mention --------------------------------------------------

    def test_require_mention_blocks_when_not_mentioned(self, make_adapter):
        adapter = self._make_adapter(make_adapter, group_policy="open",
                                     require_mention=True)
        assert adapter._check_group_policy("chat-1", "user-1", is_at_me=False) is True

    def test_require_mention_allows_when_mentioned(self, make_adapter):
        adapter = self._make_adapter(make_adapter, group_policy="open",
                                     require_mention=True)
        assert adapter._check_group_policy("chat-1", "user-1", is_at_me=True) is False

    def test_require_mention_allows_when_at_all(self, make_adapter):
        adapter = self._make_adapter(make_adapter, group_policy="open",
                                     require_mention=True)
        assert adapter._check_group_policy("chat-1", "user-1", is_at_me=False, is_at_all=True) is False

    def test_require_mention_disabled_by_global(self, make_adapter):
        adapter = self._make_adapter(make_adapter, group_policy="open",
                                     require_mention=False)
        assert adapter._check_group_policy("chat-1", "user-1", is_at_me=False) is False

    def test_require_mention_per_group_override(self, make_adapter):
        """Per-group require_mention=false should override global true."""
        adapter = self._make_adapter(make_adapter, group_policy="open",
                                     require_mention=True,
            groups_config={"chat-1": {"require_mention": False}})
        assert adapter._check_group_policy("chat-1", "user-1", is_at_me=False) is False

    def test_require_mention_per_group_override_true(self, make_adapter):
        """Per-group require_mention=true should override global false."""
        adapter = self._make_adapter(make_adapter, group_policy="open",
                                     require_mention=False,
            groups_config={"chat-1": {"require_mention": True}})
        assert adapter._check_group_policy("chat-1", "user-1", is_at_me=False) is True


# ---------------------------------------------------------------------------
# @botName stripping for slash-command detection
# ---------------------------------------------------------------------------

INBOUND_GROUP_AT_ME_DATA = {
    "msgType": "text",
    "msgId": "msg-g1",
    "chatType": "group",
    "groupId": "chat-group-1",
    "from": "user-2",
    "botId": "bot-123",
    "senderName": "Bob",
    "text": {"content": "/status @TestBot"},
    "msgData": {"text": {"content": "/status @TestBot"}},
    "reminder": {
        "isAtMe": True,
        "bots": [{"botId": "bot-123", "botName": "TestBot"}],
    },
}

INBOUND_GROUP_TEXT_DATA = {
    "msgType": "text",
    "msgId": "msg-g2",
    "chatType": "group",
    "groupId": "chat-group-1",
    "from": "user-2",
    "botId": "bot-123",
    "senderName": "Bob",
    "text": {"content": "hello @TestBot"},
    "msgData": {"text": {"content": "hello @TestBot"}},
    "reminder": {
        "isAtMe": True,
        "bots": [{"botId": "bot-123", "botName": "TestBot"}],
    },
}


def _mk_event(event_type, data):
    return {"type": event_type, "data": data}


def _mk_msg(data):
    return json.dumps({"events": [_mk_event("bot_group_message", data)]})


class TestBotNameStripping:
    """@botName stripping should only happen for slash-command detection,
    not for messages passed to the agent."""

    async def test_slash_command_strips_bot_name(self, make_adapter):
        """Slash command with trailing @botName should be recognized."""
        adapter = make_adapter()
        adapter.handle_message = AsyncMock()
        adapter.send = AsyncMock()

        with patch("lansenger.adapter._commands") as mock_cmds:
            mock_cmds.dispatch_slash_command = AsyncMock(return_value="done")
            await adapter._on_message(_mk_msg(INBOUND_GROUP_AT_ME_DATA))
            mock_cmds.dispatch_slash_command.assert_called_once()
            call_args = mock_cmds.dispatch_slash_command.call_args[0]
            # dispatch_slash_command(adapter, text, chat_id, sender_id, is_group)
            assert call_args[1] == "/status"  # stripped text

    async def test_non_command_keeps_bot_name_in_event(self, make_adapter):
        """Non-command messages should pass @botName through to the agent."""
        adapter = make_adapter()
        adapter.handle_message = AsyncMock()

        await adapter._on_message(_mk_msg(INBOUND_GROUP_TEXT_DATA))

        adapter.handle_message.assert_called_once()
        event = adapter.handle_message.call_args[0][0]
        assert "@TestBot" in event.text


# ---------------------------------------------------------------------------
# auto_mention_reply / auto_quote_reply integration
# ---------------------------------------------------------------------------

class TestAutoReplyFeatures:
    """autoMentionReply and autoQuoteReply are per-group overrides with
    global fallbacks."""

    def test_auto_mention_global_defaults(self, make_adapter):
        adapter = make_adapter()
        assert adapter._auto_mention_reply is False

    def test_auto_quote_global_defaults(self, make_adapter):
        adapter = make_adapter()
        assert adapter._auto_quote_reply is False

    def test_auto_mention_env_setting(self, make_adapter, monkeypatch):
        monkeypatch.setenv("LANSENGER_AUTO_MENTION_REPLY", "true")
        adapter = make_adapter()
        assert adapter._auto_mention_reply is True

    def test_auto_quote_env_setting(self, make_adapter, monkeypatch):
        monkeypatch.setenv("LANSENGER_AUTO_QUOTE_REPLY", "true")
        adapter = make_adapter()
        assert adapter._auto_quote_reply is True


# ---------------------------------------------------------------------------
# Per-group config loading
# ---------------------------------------------------------------------------

class TestGroupsConfigLoading:
    """groups_config is loaded from extra.groups and keyed by string chat_id."""

    def test_groups_config_empty_by_default(self, make_adapter):
        adapter = make_adapter()
        assert adapter._groups_config == {}

    def test_groups_config_loaded_from_extra(self, make_adapter):
        extra = {
            "groups": {
                "chat-1": {"enabled": True, "require_mention": False},
                "chat-2": {"enabled": False},
            }
        }
        from lansenger.adapter import LansengerAdapter
        from conftest import _StubPlatformConfig
        config = _StubPlatformConfig(enabled=True, extra=extra)
        adapter = LansengerAdapter(config)
        assert "chat-1" in adapter._groups_config
        assert adapter._groups_config["chat-1"]["enabled"] is True
        assert "chat-2" in adapter._groups_config


# ---------------------------------------------------------------------------
# is_at_all bypass (full integration in _on_message)
# ---------------------------------------------------------------------------

INBOUND_GROUP_AT_ALL_DATA = {
    "msgType": "text",
    "msgId": "msg-at-all",
    "chatType": "group",
    "groupId": "chat-group-1",
    "from": "user-3",
    "botId": "bot-123",
    "senderName": "Charlie",
    "text": {"content": "@all important announcement"},
    "msgData": {"text": {"content": "@all important announcement"}},
    "reminder": {
        "isAtMe": False,
        "isAtAll": True,
    },
}


class TestAtAllBypass:
    """@all messages should pass mention gate even when require_mention=true."""

    async def test_at_all_passes_mention_gate(self, make_adapter):
        adapter = make_adapter()
        adapter._require_mention = True
        adapter.handle_message = AsyncMock()

        with patch("lansenger.adapter._commands") as mock_cmds:
            mock_cmds.dispatch_slash_command = AsyncMock(return_value=None)
            await adapter._on_message(_mk_msg(INBOUND_GROUP_AT_ALL_DATA))

        # should not be blocked by require_mention
        adapter.handle_message.assert_called_once()


# ---------------------------------------------------------------------------
# Approval permission tests
# ---------------------------------------------------------------------------

class TestApprovalPermission:
    """Tests for _check_approval_permission and approval permission logic."""

    def test_owner_has_permission(self, make_adapter):
        """Owner ID should always have approval permission."""
        adapter = make_adapter()
        adapter._owner_id = "user-owner"
        adapter._approval_allow_from = []
        assert adapter._check_approval_permission("user-owner") is True

    def test_non_owner_without_allowlist_denied(self, make_adapter):
        """Non-owner should be denied if not in allowlist."""
        adapter = make_adapter()
        adapter._owner_id = "user-owner"
        adapter._approval_allow_from = []
        assert adapter._check_approval_permission("user-other") is False

    def test_user_in_allowlist_has_permission(self, make_adapter):
        """User in approval_allow_from should have permission."""
        adapter = make_adapter()
        adapter._owner_id = "user-owner"
        adapter._approval_allow_from = ["user-admin", "user-operator"]
        assert adapter._check_approval_permission("user-admin") is True
        assert adapter._check_approval_permission("user-operator") is True

    def test_user_not_in_allowlist_denied(self, make_adapter):
        """User not in allowlist should be denied."""
        adapter = make_adapter()
        adapter._owner_id = "user-owner"
        adapter._approval_allow_from = ["user-admin"]
        assert adapter._check_approval_permission("user-random") is False

    def test_no_owner_id_denies_all(self, make_adapter):
        """If owner_id is not set, only allowlist users can approve."""
        adapter = make_adapter()
        adapter._owner_id = None
        adapter._approval_allow_from = ["user-admin"]
        assert adapter._check_approval_permission("user-admin") is True
        assert adapter._check_approval_permission("user-random") is False

    def test_extract_trigger_sender_from_group_session(self, make_adapter):
        """Group session_key should extract sender_id."""
        adapter = make_adapter()
        session_key = "agent:main:lansenger:group:chat-123:user-trigger"
        result = adapter._extract_trigger_sender_from_session(session_key)
        assert result == "user-trigger"

    def test_extract_trigger_sender_from_dm_session(self, make_adapter):
        """DM session_key should return None (no sender_id in key)."""
        adapter = make_adapter()
        session_key = "agent:main:lansenger:dm:chat-456"
        result = adapter._extract_trigger_sender_from_session(session_key)
        assert result is None

    def test_approval_allow_from_config_loading(self, make_adapter):
        """approval_allow_from should be loaded from config."""
        adapter = make_adapter()
        # Check that the attribute exists and is a list
        assert hasattr(adapter, "_approval_allow_from")
        assert isinstance(adapter._approval_allow_from, list)
