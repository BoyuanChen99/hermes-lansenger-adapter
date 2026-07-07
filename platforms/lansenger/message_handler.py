"""
Message handling mixin for LansengerAdapter.
Handles inbound message parsing, event processing, group policy, and auto-sethome.
"""

import asyncio
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from gateway.platforms.base import MessageEvent, MessageType

from . import commands as _commands

logger = logging.getLogger(__name__)


class MessageHandlerMixin:
    """Message handling methods for LansengerAdapter."""

    async def _auto_sethome(self, chat_id: str) -> None:
        """Auto-designate the first DM as Lansenger home channel.

        Triggers when no home_channel is configured, or when an existing
        group home is superseded by the first DM (DM > group upgrade).
        Silent: writes config.yaml + env, no user-facing message.
        """
        if self._auto_sethome_done:
            return

        # Check if we should set/upgrade
        _cur_home = self._home_channel_id or ""
        _should_set = (not _cur_home) or _cur_home.startswith("group:")

        # DM seen — no further upgrades needed after this
        self._auto_sethome_done = True

        if not _should_set:
            return

        try:
            from hermes_constants import get_hermes_home
            from utils import atomic_yaml_write
            import yaml

            _home = get_hermes_home()
            config_path = _home / "config.yaml"
            user_config: dict = {}
            if config_path.exists():
                with open(config_path, encoding="utf-8") as f:
                    user_config = yaml.safe_load(f) or {}

            # Write lansenger home_channel into config.yaml
            platforms = user_config.setdefault("platforms", {})
            lansenger = platforms.setdefault("lansenger", {})
            lansenger["home_channel"] = {"platform": "lansenger", "chat_id": chat_id, "name": "Lansenger Home"}
            atomic_yaml_write(config_path, user_config)

            # Update runtime state immediately
            self._home_channel_id = chat_id
            os.environ["LANSENGER_HOME_CHANNEL"] = str(chat_id)

            # Also update the adapter's config.home_channel for runtime
            if hasattr(self, "config") and hasattr(self.config, "home_channel"):
                try:
                    from gateway.config import HomeChannel, Platform
                    self.config.home_channel = HomeChannel(platform=Platform("lansenger"), chat_id=chat_id, name="Lansenger Home")
                except Exception:
                    pass

            logger.info(
                "[Lansenger] Auto-sethome: designated %s as Lansenger home channel",
                chat_id[:30],
            )
        except Exception as e:
            logger.warning("[Lansenger] Auto-sethome failed (non-critical): %s", e)

    async def _register_commands_after_connect(self) -> None:
        """Register slash commands after connection is established.

        Deletes any previously registered commands first, then registers
        fresh copies. Retries up to 3 times with 30s delay on failure
        (handles transient issues like bot temporarily disabled).
        """
        if self._commands_registered:
            return

        if not _commands._native_commands_enabled(self._config_extra):
            logger.info("[Lansenger] Native slash commands disabled, skipping")
            self._commands_registered = True
            return

        try:
            # Wait briefly for owner_id to be loaded from disk
            await asyncio.sleep(1.0)

            # Delete old commands before re-registering
            try:
                await _commands.delete_all_commands(self)
            except Exception:
                pass

            # Retry loop: up to 3 attempts with 30s delay
            for attempt in range(3):
                if self._commands_registered:
                    return
                success = await _commands.register_all_commands(self)
                if success:
                    self._commands_registered = True
                    return
                if attempt < 2:
                    logger.info(
                        "[Lansenger] Command registration attempt %d failed, retrying in 30s...",
                        attempt + 1,
                    )
                    await asyncio.sleep(30)

            logger.info(
                "[Lansenger] Command registration deferred — will retry "
                "when owner is detected"
            )
        except Exception as exc:
            logger.warning("[Lansenger] Command registration failed: %s", exc)

    async def _on_message(self, raw_message: str) -> None:
        """Process an incoming Lansenger message."""
        self._last_inbound_time = time.time()  # any WS data proves inbound channel is alive
        logger.info("[Lansenger] WS raw data received (%d bytes)", len(raw_message) if raw_message else 0)
        try:
            data = json.loads(raw_message)
        except json.JSONDecodeError:
            logger.warning("[Lansenger] Invalid JSON message")
            return

        events = data.get("events", [])
        if events:
            event_types = [e.get("type", "?") for e in events]
            logger.info("[Lansenger] Received %d WS event(s): %s", len(events), event_types)
        for event_data in events:
            await self._process_event(event_data)

        self._persist_chat_type_map()

    async def _process_event(self, event_data: Dict[str, Any]) -> None:
        """Process a single event.

        Handles bot_private_message (DM) and bot_group_message (group chat)
        events per the official Lansenger OpenAPI callback event spec.
        """
        # 1. Handle approveCard button callbacks BEFORE the bot_message filter
        event_type = event_data.get("type", "")
        if event_type == "approve_card_callback":
            await self._handle_approve_card_callback(event_data)
            return

        # 2. Filter by event type — only handle bot message events
        if event_type not in ("bot_private_message", "bot_group_message"):
            # Log FULL raw event for unknown types (e.g. approveCard button callbacks)
            logger.info(
                "[Lansenger] 🔔 UNKNOWN EVENT type=%s — raw data:\n%s",
                event_type,
                json.dumps(event_data, ensure_ascii=False, indent=2),
            )
            return

        is_group = event_type == "bot_group_message"
        msg_data = event_data.get("data", {})
        msg_type = msg_data.get("msgType", "text")

        # 2. Message ID — msgId is carried for both group and private messages
        msg_id = msg_data.get("msgId") or uuid.uuid4().hex
        logger.info("[Lansenger] msg_id=%s (group=%s)", msg_id[:30], is_group)

        # 2a. Log full raw event for approveCard / verifyCard (button-callback observation)
        if msg_type in ("approveCard", "verifyCard"):
            logger.info(
                "[Lansenger] 🎯 %s EVENT — raw data:\n%s",
                msg_type,
                json.dumps(event_data, ensure_ascii=False, indent=2),
            )

        if self._dedup.is_duplicate(msg_id):
            logger.debug("[Lansenger] Duplicate message %s, skipping", msg_id)
            return

        # 3. Self-echo prevention: skip messages sent by our own bot in groups
        sender_id = msg_data.get("from", "")
        self_bot_id: Optional[str] = None
        if is_group:
            self_bot_id = msg_data.get("botId")
            if self_bot_id and sender_id == self_bot_id:
                logger.debug("[Lansenger] Skipping self-echo from bot %s", self_bot_id)
                return

        # 4. Extract message text (handles text, image, video, file, voice, position, card, sticker)
        text = await self._extract_text(msg_data)
        if not text:
            logger.info("[Lansenger] Empty message (msgType=%s), skipping — data keys=%s", msg_type, list(msg_data.keys()))
            # Dump raw msgData for unsupported msgTypes so we can add support
            raw_msg_data = msg_data.get("msgData", {})
            logger.info("[Lansenger] RAW msgData for %s: %s", msg_type, json.dumps(raw_msg_data, ensure_ascii=False))
            return

        # 5. Chat context — group vs private uses different fields
        if is_group:
            chat_id = msg_data.get("groupId") or sender_id
            chat_name = msg_data.get("groupName", "")
            # Reminder / @mention info
            reminder = msg_data.get("reminder", {}) or {}
            is_at_me = bool(reminder.get("isAtMe", False))
            is_at_all = bool(reminder.get("isAtAll", False))
            mentioned_staffs = reminder.get("staffs", []) or []
            mentioned_bots = reminder.get("bots", []) or []
            logger.info("[Lansenger] Group msg parsed: chat=%s from=%s(%s) is_at_me=%s is_at_all=%s bots=%s staffs=%s",
                        chat_id[:20], sender_id[:20], msg_data.get("fromType", "?"), is_at_me, is_at_all,
                        [b.get("botName", "?") for b in mentioned_bots] if isinstance(mentioned_bots, list) else "?",
                        len(mentioned_staffs) if isinstance(mentioned_staffs, list) else "?")

            # Remember our bot's @name for slash-command detection later
            _our_bot_name: Optional[str] = None
            if is_at_me and self_bot_id:
                for bot in mentioned_bots:
                    if isinstance(bot, dict) and bot.get("botId") == self_bot_id:
                        _our_bot_name = bot.get("botName")
                        break
        else:
            chat_id = sender_id
            chat_name = msg_data.get("conversationTitle", "")
            reminder = {}
            is_at_me = False
            is_at_all = False
            mentioned_staffs = []
            mentioned_bots = []

        # 6. Group chat entry policy check (per-group > global)
        if is_group:
            if self._check_group_policy(chat_id, sender_id, is_at_me, is_at_all):
                logger.info("[Lansenger] Group policy BLOCKED: chat=%s sender=%s is_at_me=%s is_at_all=%s group_policy=%s require_mention=%s",
                            chat_id[:20], sender_id[:20], is_at_me, is_at_all, self._group_policy, self._require_mention)
                return

        # 7. Parse quoted message (referenceMsg) if present
        ref_text = self._extract_reference_text(msg_data.get("referenceMsg"))
        if ref_text:
            text = f"[引用消息] {ref_text}\n---\n{text}"

        # 8. Cache chat type for outbound routing
        self._chat_type_map[chat_id] = "group" if is_group else "dm"
        self._chat_type_map_dirty = True

        # 8a. Cache last sender, fromType, and msgId in contextvar for
        # autoMentionReply and reply ref — per-task isolation prevents
        # races when concurrent messages update the global dict.
        from .adapter import _current_sender_cache
        sender_cache = _current_sender_cache.get().copy()
        sender_cache[chat_id] = {
            "sender_id": sender_id,
            "from_type": msg_data.get("fromType", 0),
            "msg_id": msg_id,
        }
        _current_sender_cache.set(sender_cache)
        # Also update legacy dict for non-task-context code paths
        self._chat_last_sender[chat_id] = sender_id
        self._chat_last_from_type[chat_id] = msg_data.get("fromType", 0)
        self._chat_last_msg_id[chat_id] = msg_id

        # 9. Cache user language from message text (for appCard language selection)
        # Read text content from msgData.text.content (not the already-extracted text
        # which includes ref_msg prefix and may have been modified).
        raw_content = msg_data.get("msgData", {}).get("text", {}).get("content", "")
        if raw_content:
            self._user_lang_map[chat_id] = self._detect_lang(raw_content)

        # 10. Record owner ID on first private message
        if not is_group and not self._owner_id and sender_id:
            self._owner_id = sender_id
            self._save_owner_id()
            logger.info("[Lansenger] Recorded owner ID from first message: %s", sender_id)

            # Retry command registration now that owner is known
            if not self._commands_registered:
                try:
                    asyncio.create_task(self._register_commands_after_connect())
                except Exception:
                    pass

        # 11. Auto-sethome: designate the first DM as home channel.
        if not is_group:
            await self._auto_sethome(chat_id)

        # 12. Build source & event
        # For group chats, inject group info into chat_topic for system prompt
        chat_topic: Optional[str] = None
        if is_group:
            cached = self._group_cache.get(chat_id)
            if cached and (time.time() - cached.get("fetched_at", 0)) < self._group_cache_ttl:
                chat_topic = self._build_group_chat_topic(cached)
            else:
                # First message: await group info synchronously for immediate injection
                try:
                    info = await self.get_group_info(chat_id)
                    if "error" not in info:
                        temp_entry = {"info": info, "members": [], "fetched_at": time.time()}
                        chat_topic = self._build_group_chat_topic(temp_entry)
                except Exception as e:
                    logger.debug("[Lansenger] Failed to fetch group info for chat_topic: %s", e)
                # Background: full cache (info + members if ≤100) for future messages
                asyncio.create_task(self._ensure_group_cache(chat_id))

        source = self.build_source(
            chat_id=chat_id,
            chat_name=chat_name or None,
            chat_type="group" if is_group else "dm",
            user_id=sender_id,
            user_name=msg_data.get("senderName", sender_id),
            chat_topic=chat_topic,
            is_bot=msg_data.get("fromType") == 1,
        )

        # Attach group context in raw_message for downstream consumers
        enriched_raw: Dict[str, Any] = dict(msg_data)
        if is_group:
            enriched_raw["_is_at_me"] = is_at_me
            enriched_raw["_is_at_all"] = is_at_all
            enriched_raw["_mentioned_staffs"] = mentioned_staffs
            enriched_raw["_mentioned_bots"] = mentioned_bots
            enriched_raw["_bot_id"] = self_bot_id

        timestamp = datetime.now(tz=timezone.utc)

        event = MessageEvent(
            text=text,
            message_type=MessageType.TEXT,
            source=source,
            message_id=msg_id,
            raw_message=enriched_raw,
            timestamp=timestamp,
        )

        logger.debug("[Lansenger] Message from %s in %s(%s): %s",
                     source.user_name, source.chat_type,
                     chat_id[:20] if chat_id else "?", text[:80])

        # ── Slash command dispatch ──
        # For slash commands, strip trailing @botName first (Lansenger appends
        # "@botName" to group messages). The original text (with @botName) is
        # preserved for non-command messages so the agent sees the full content.
        _cmd_text = text
        if is_group and _our_bot_name:
            at_name = f"@{_our_bot_name}"
            if _cmd_text.endswith(at_name):
                _cmd_text = _cmd_text[: -len(at_name)].strip()
        if _cmd_text.startswith("/"):
            reply = await _commands.dispatch_slash_command(
                self, _cmd_text, chat_id, sender_id, is_group,
            )
            if reply is not None:
                await self.send(chat_id, reply)
                return

        # ── Approval permission gate (before gateway) ──
        # Intercept /approve and /deny in groups before they reach Hermes core.
        # Hermes core has NO permission check on approval — any sender can
        # resolve approvals. We enforce it here at the adapter level.
        if is_group and _cmd_text.startswith("/"):
            cmd = _cmd_text.split()[0].lower() if _cmd_text.split() else ""
            if cmd in ("/approve", "/deny"):
                if not self._check_approval_permission(sender_id):
                    logger.info(
                        "[Lansenger] Approval DENIED: sender=%s not in owner/approval_allow_from",
                        sender_id[:20],
                    )
                    await self.send(
                        chat_id,
                        "您没有审批权限，仅机器人的主人或配置的审批者可以审批危险命令。",
                    )
                    return

        await self.handle_message(event)

        # ── Post-approval card update ──
        # If user sent an /approve or /deny command, update the
        # corresponding card to reflect the resolved status.
        if _cmd_text.startswith("/"):
            await self._maybe_update_approval_card(chat_id, sender_id, _cmd_text, is_group)

    async def _extract_text(self, msg_data: Dict[str, Any]) -> str:
        """Extract text from message, downloading media if needed.
        
        For image/video/file/voice: downloads first media and returns file path.
        """
        msg_type = msg_data.get("msgType", "text")
        msg_payload = msg_data.get("msgData", {})

        if msg_type == "text":
            return msg_payload.get("text", {}).get("content", "").strip()
        
        elif msg_type in ("format", "formatText"):
            # WS event uses "format" (not "formatText") as msgData key
            # Format: {"format": {"formatType": "markdown", "text": "...", "sequence": N}}
            fmt = msg_payload.get("format") or msg_payload.get("formatText", {})
            return fmt.get("text", "") if isinstance(fmt, dict) else ""
        
        elif msg_type == "image":
            media_ids = msg_payload.get("image", {}).get("mediaIds", [])
            if media_ids:
                media_bytes = await self._download_media(media_ids[0])
                if media_bytes:
                    path = await self._save_media_temp(media_bytes, "image")
                    return path if path else "[Image download failed]"
            return "[Image]"
        
        elif msg_type == "video":
            media_ids = msg_payload.get("video", {}).get("mediaIds", [])
            if media_ids:
                media_bytes = await self._download_media(media_ids[0])
                if media_bytes:
                    path = await self._save_media_temp(media_bytes, "video")
                    return path if path else "[Video download failed]"
            return "[Video]"
        
        elif msg_type == "file":
            media_ids = msg_payload.get("file", {}).get("mediaIds", [])
            if media_ids:
                media_bytes = await self._download_media(media_ids[0])
                if media_bytes:
                    path = await self._save_media_temp(media_bytes, "file")
                    return path if path else "[File download failed]"
            return "[File]"
        
        elif msg_type == "voice":
            media_ids = msg_payload.get("voice", {}).get("mediaIds", [])
            if media_ids:
                media_bytes = await self._download_media(media_ids[0])
                if media_bytes:
                    path = await self._save_media_temp(media_bytes, "voice")
                    return path if path else "[Voice download failed]"
            return "[Voice]"
        
        elif msg_type == "position":
            pos = msg_payload.get("position", {})
            name = pos.get("name", "")
            address = pos.get("address", "")
            return f"[Location] {name} {address}" if name or address else "[Location]"
        
        elif msg_type == "card":
            staff_id = msg_payload.get("card", {}).get("staffId", "")
            return f"[Contact Card] {staff_id}" if staff_id else "[Contact Card]"
        
        elif msg_type == "sticker":
            sticker_id = msg_payload.get("sticker", {}).get("stickerId", "")
            return f"[Sticker] {sticker_id}" if sticker_id else "[Sticker]"

        return ""

    @staticmethod
    def _extract_reference_text(reference_msg: Optional[Dict[str, Any]]) -> str:
        """Extract displayable text from a referenceMsg (quoted message).

        Lansenger sends referenceMsg alongside the main message when a user
        replies by quoting an earlier message.  Only the first level is
        returned — the API does not support recursive nested references.

        Returns empty string if reference_msg is None or has no text content.
        """
        if not reference_msg or not isinstance(reference_msg, dict):
            return ""

        msg_type = reference_msg.get("msgType", "text")
        msg_payload = reference_msg.get("msgData", {}) or {}

        if msg_type == "text":
            return msg_payload.get("text", {}).get("content", "").strip()

        if msg_type == "image":
            count = len(msg_payload.get("image", {}).get("mediaIds", []))
            return "[Image]" if count <= 1 else f"[Image: {count}]"

        if msg_type == "video":
            return "[Video]"

        if msg_type == "file":
            count = len(msg_payload.get("file", {}).get("mediaIds", []))
            return "[File]" if count <= 1 else f"[File: {count}]"

        if msg_type == "voice":
            return "[Voice]"

        if msg_type == "position":
            pos = msg_payload.get("position", {})
            name = pos.get("name", "")
            return f"[Location] {name}" if name else "[Location]"

        if msg_type == "card":
            staff_id = msg_payload.get("card", {}).get("staffId", "")
            return f"[Contact Card] {staff_id}" if staff_id else "[Contact Card]"

        return f"[{msg_type}]"

    def _check_group_policy(self, chat_id: str, sender_id: str, is_at_me: bool, is_at_all: bool = False) -> bool:
        """Check if a group message should be blocked by policy.

        Decision order (per-group overrides take precedence over global):

          1. per-group ``enabled: false``          → block
          2. per-group ``allow_from``              → sender must be in list
          3. global ``group_policy``               → disabled/allowlist/open
             - ``disabled``:  block all (unless per-group enabled=true)
             - ``allowlist``: only groups listed in the ``groups`` config map
                              are allowed; if global ``group_allow_from``
                              (sender-level) is non-empty, sender must be in it
             - ``open``:      all groups pass (unless per-group enabled=false)
          4. ``require_mention`` (per-group > global) → block if bot not
             @mentioned and not @all

        Returns True if the message should be dropped (blocked).
        """
        per_group = self._groups_config.get(chat_id, {})

        # Gate 1: per-group enabled=false → explicitly disabled
        if per_group.get("enabled") is False:
            logger.debug("[Lansenger] Group %s disabled per-group, dropping", chat_id[:20])
            return True

        # Gate 2: per-group allow_from → restrict senders within this group
        per_allow = per_group.get("allow_from", [])
        if per_allow and isinstance(per_allow, list) and sender_id not in per_allow:
            logger.debug("[Lansenger] Group %s sender %s not in per-group allow_from, dropping",
                         chat_id[:20], sender_id[:20])
            return True

        # Gate 3: global policy (only when per-group does not explicitly enable)
        per_enabled = per_group.get("enabled")
        if per_enabled is not True:
            if self._group_policy == "disabled":
                logger.debug("[Lansenger] Group policy=disabled, dropping group message from %s", chat_id[:20])
                return True
            if self._group_policy == "allowlist":
                # groups config map keys serve as the group allowlist
                if chat_id not in self._groups_config:
                    logger.debug("[Lansenger] Group %s not in groups config (allowlist mode), dropping", chat_id[:20])
                    return True
                # Global sender-level allowlist
                if self._group_allow_senders and sender_id not in self._group_allow_senders:
                    logger.debug("[Lansenger] Sender %s not in group_allow_from (sender-level), dropping", sender_id[:20])
                    return True

        # Gate 4: require_mention — per-group > global
        if "require_mention" in per_group:
            require_mention = bool(per_group["require_mention"])
        else:
            require_mention = self._require_mention
        if require_mention and not is_at_me:
            # @all bypass: per-group > global (default: true)
            if is_at_all:
                respond_at_all = per_group.get("respond_to_at_all")
                if respond_at_all is None:
                    respond_at_all = self._respond_to_at_all
                if isinstance(respond_at_all, str):
                    respond_at_all = str(respond_at_all).lower() not in ("false", "0", "no")
                if not respond_at_all:
                    logger.debug("[Lansenger] @all message dropped: respond_to_at_all=false, chat=%s", chat_id[:20])
                    return True
            else:
                logger.debug("[Lansenger] requireMention and bot not @mentioned (@all=%s), dropping group message from %s",
                             is_at_all, chat_id[:20])
                return True

        return False  # allowed
