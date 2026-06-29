"""
Lansenger (蓝信) platform adapter — Hermes Agent plugin version.

Uses Lansenger Smart Bot API for real-time message reception via WebSocket.
Responses are sent via Lansenger's HTTP API.

Requires:
    pip install websockets httpx
    LANSENGER_APP_ID and LANSENGER_APP_SECRET env vars

Configuration in config.yaml:
    platforms:
      lansenger:
        enabled: true
        extra:
          app_id: "your-app-id"        # or LANSENGER_APP_ID env var
          app_secret: "your-secret"    # or LANSENGER_APP_SECRET env var
          api_gateway_url: "https://open.e.lanxin.cn/open/apigw"  # optional

This is a PLUGIN adapter — registered via ctx.register_platform() in the
register(ctx) entry point.  No modifications to core Hermes code are needed.
"""

import asyncio
import itertools
import logging
import json
import os
import re
import subprocess
import tempfile
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path

try:
    import websockets
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False
    websockets = None  # type: ignore[assignment]

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False
    httpx = None  # type: ignore[assignment]

# ── Lazy imports from Hermes core ──────────────────────────────────────────
# These live in the main repo; we import at module level because the gateway
# guarantees the package is on sys.path before the plugin is loaded.
from gateway.config import Platform, PlatformConfig
from gateway.platforms.helpers import MessageDeduplicator
from gateway.platforms.base import (
    BasePlatformAdapter,
    MessageEvent,
    MessageType,
    SendResult,
    cache_image_from_bytes,
    cache_document_from_bytes,
)

logger = logging.getLogger(__name__)

# ── Local module imports ───────────────────────────────────────────────────
from . import commands as _commands

# Constants
MAX_MESSAGE_LENGTH = 4000
RECONNECT_BACKOFF = [2, 5, 10, 30, 60]
INBOUND_SILENCE_TIMEOUT = 1800  # 30min — no inbound WS message for this long = silent death
DEFAULT_API_GATEWAY_URL = "https://open.e.lanxin.cn/open/apigw"

# API Endpoints
API_ENDPOINTS = {
    "auth": {
        "tenant_access_token": "/auth/v3/tenant_access_token/internal",
    },
    "websocket": {
        "endpoint": "/v1/ws/endpoint/create",
    },
    "smart_bot": {
        "private_message": "/v1/bot/messages/create",
        "group_message": "/v1/messages/group/create",
    },
    "app": {
        "upload_media": "/v1/app/medias/create",
    },
    "message": {
        "revoke": "/v1/messages/revoke",
        "dynamic_update": "/v1/messages/dynamic/update",
    },
    "groups": {
        "fetch": "/v2/groups/fetch",
        "info": "/v2/groups/{group_id}/info/fetch",
        "members": "/v2/groups/{group_id}/members/fetch",
        "is_in_group": "/v2/groups/{group_id}/members/is_in_group",
    },
}


# check_requirements is defined at the bottom of this file (near register()).


class LansengerAdapter(BasePlatformAdapter):
    """Lansenger chatbot adapter using WebSocket long-connection."""

    MAX_MESSAGE_LENGTH = MAX_MESSAGE_LENGTH

    def __init__(self, config: PlatformConfig):
        super().__init__(config, Platform("lansenger"))

        extra = config.extra or {}
        # Priority: env var > config.yaml extra (matches Hermes convention)
        self._app_id: str = os.getenv("LANSENGER_APP_ID") or extra.get("app_id", "")
        self._app_secret: str = os.getenv("LANSENGER_APP_SECRET") or extra.get("app_secret", "")
        self._api_gateway_url: str = os.getenv("LANSENGER_API_GATEWAY_URL") or extra.get("api_gateway_url") or DEFAULT_API_GATEWAY_URL
        # Store extra config for commands.py permission lookups
        self._config_extra: dict = extra

        # Home channel from PlatformConfig.home_channel (standard Hermes structure)
        self._home_channel_id: Optional[str] = None
        if config.home_channel:
            self._home_channel_id = config.home_channel.chat_id

        self._ws_client: Optional[Any] = None
        self._ws_task: Optional[asyncio.Task] = None
        self._watchdog_task: Optional[asyncio.Task] = None
        self._http_client: Optional["httpx.AsyncClient"] = None
        self._ws_url: Optional[str] = None
        self._ws_ping_interval: int = 50
        self._last_inbound_time: float = 0.0  # last WS inbound message timestamp

        # Message deduplication
        self._dedup = MessageDeduplicator(max_size=1000)

        # Chat type cache: maps chat_id → "group" or "dm"
        # Populated from inbound messages so outbound can route correctly
        self._chat_type_map: Dict[str, str] = {}
        self._chat_type_map_dirty: bool = False
        _hermes_home = self._resolve_hermes_home()
        self._chat_type_file = _hermes_home / "lansenger_chat_types.json"
        self._load_chat_type_map()

        # User language cache: maps chat_id → "zh" or "en"
        # Populated from inbound messages so approval cards use the right language
        self._user_lang_map: Dict[str, str] = {}

        # Token cache
        self._app_token: Optional[str] = None
        self._token_expiry: float = 0
        self._token_file = _hermes_home / "lansenger_token.json"

        # Owner ID (the user who bound the bot)
        self._owner_id: Optional[str] = None
        self._owner_id_file = _hermes_home / "lansenger_owner.json"
        self._load_owner_id()

        # Auto-sethome: first DM becomes home channel if none configured.
        # If an existing home is a group (group:xxx), the first DM overrides it.
        _existing_home = self._home_channel_id or ""
        self._auto_sethome_done: bool = bool(_existing_home) and not _existing_home.startswith("group:")

        # Pairing state
        self._pending_pairings: Dict[str, Dict[str, Any]] = {}

        # Group chat policy — env var > config.yaml extra (Hermes convention)
        _group_policy = os.getenv("LANSENGER_GROUP_POLICY") or extra.get("group_policy", "open")
        self._group_policy: str = _group_policy if _group_policy in ("open", "allowlist", "disabled") else "open"

        _group_allow_from = os.getenv("LANSENGER_GROUP_ALLOW_FROM") or extra.get("group_allow_from", "")
        self._group_allow_senders: List[str] = [g.strip() for g in _group_allow_from.split(",") if g.strip()] if _group_allow_from else []

        _require_mention = os.getenv("LANSENGER_REQUIRE_MENTION") or extra.get("require_mention", "true")
        self._require_mention: bool = str(_require_mention).lower() in ("true", "1", "yes")

        # Per-group overrides (config.yaml extra.groups only, no env var equivalent)
        # Format: {"chat_id": {"enabled": bool, "require_mention": bool, "allow_from": [sender_ids]}}
        _raw_groups = extra.get("groups", {}) or {}
        self._groups_config: Dict[str, Dict[str, Any]] = {}
        for gid, cfg in _raw_groups.items():
            if isinstance(cfg, dict):
                self._groups_config[str(gid)] = cfg

        # Auto @mention reply in groups
        _auto_mention = os.getenv("LANSENGER_AUTO_MENTION_REPLY") or extra.get("auto_mention_reply", "false")
        self._auto_mention_reply: bool = str(_auto_mention).lower() in ("true", "1", "yes")

        # Auto quote reply (refMsgId) — groups and private chats
        _auto_quote = os.getenv("LANSENGER_AUTO_QUOTE_REPLY") or extra.get("auto_quote_reply", "false")
        self._auto_quote_reply: bool = str(_auto_quote).lower() in ("true", "1", "yes")

        # Respond to @all — whether @all messages bypass require_mention (default: false)
        _respond_at_all = os.getenv("LANSENGER_RESPOND_TO_AT_ALL") or extra.get("respond_to_at_all", "false")
        self._respond_to_at_all: bool = str(_respond_at_all).lower() in ("true", "1", "yes")

        # Approval allow list — who can approve dangerous commands
        # Default: owner_id only. Config can add additional approvers.
        _approval_allow = os.getenv("LANSENGER_APPROVAL_ALLOW_FROM") or extra.get("approval_allow_from", "")
        self._approval_allow_from: List[str] = [a.strip() for a in _approval_allow.split(",") if a.strip()] if _approval_allow else []

        # Last sender per chat (for autoMentionReply)
        self._chat_last_sender: Dict[str, str] = {}
        self._chat_last_from_type: Dict[str, str] = {}
        self._chat_last_msg_id: Dict[str, str] = {}

        # Slash command registration state
        self._commands_registered: bool = False

        # Approval state for approveCard button callbacks
        # approval_id (str) → session_key
        self._approval_state: Dict[str, str] = {}
        self._approval_counter = itertools.count(1)

        # Card type tracking for dynamic status updates
        # msg_id → "approveCard" | "appCard"
        self._card_type_map: Dict[str, str] = {}

        # Pending approval card tracking: session_key → (msg_id, trigger_sender_id)
        # Used to update the card when the user replies /approve or /deny
        # trigger_sender_id is extracted from session_key for permission check
        self._pending_approval_msgs: Dict[str, tuple] = {}
        # approval_id → (msg_id, chat_id) — button callback uses approval_id for precise match
        self._approval_card_msgs: Dict[str, tuple] = {}
        # Persistent approval state (survives gateway restarts)
        self._approvals_file = _hermes_home / "lansenger_approvals.json"
        self._load_approvals()

        # Hermes core gateway approval timeout (seconds, default 300)
        self._gateway_approval_timeout = self._read_gateway_approval_timeout()

        # Group info cache: group_id → {"info": dict, "members": list, "fetched_at": float}
        # Cache TTL: 300s (5 min). Members only prefetched if total <= 100.
        self._group_cache: Dict[str, Dict[str, Any]] = {}
        self._group_cache_ttl: float = 300.0
        # Track in-flight group fetches to avoid concurrent duplicate API calls
        self._group_fetch_locks: Dict[str, asyncio.Lock] = {}

    # -- Connection lifecycle -----------------------------------------------

    async def connect(self) -> bool:
        """Connect to Lansenger via WebSocket."""
        if not WEBSOCKETS_AVAILABLE or not HTTPX_AVAILABLE:
            return False
        if not self._app_id or not self._app_secret:
            return False

        try:
            self._http_client = httpx.AsyncClient(timeout=30.0)

            ws_url = await self._get_websocket_url()
            if not ws_url:
                logger.error("[Lansenger] Failed to get WebSocket URL — check appId/secret and API gateway")
                return False

            self._running = True
            self._ws_task = asyncio.create_task(self._run_ws(ws_url))
            self._ws_task.add_done_callback(self._on_ws_task_done)
            logger.info("[Lansenger] WebSocket task created")

            # Watchdog: periodically check WS task health and restart if dead
            self._watchdog_task = asyncio.create_task(self._ws_watchdog())
            logger.info("[Lansenger] Watchdog task created")

            # Schedule command registration after token is available
            asyncio.create_task(self._register_commands_after_connect())

            return True
        except Exception as e:
            logger.error("[Lansenger] Failed to connect: %s", e)
            return False

    async def _get_websocket_url(self) -> Optional[str]:
        """Get WebSocket URL from Lansenger API (includes ticket with expiresIn)."""
        try:
            url = f"{self._api_gateway_url}{API_ENDPOINTS['websocket']['endpoint']}"
            logger.info("[Lansenger] Requesting WebSocket endpoint from %s", url)
            response = await self._http_client.post(
                url,
                json={"appId": self._app_id, "secret": self._app_secret}
            )
            logger.info("[Lansenger] WS endpoint response: status=%d, body=%s",
                        response.status_code, response.text[:200])
            response.raise_for_status()
            data = response.json()
            
            if data.get("errCode") == 0:
                ws_url = data.get("data", {}).get("wsEndpoint")
                expires_in = data.get("data", {}).get("expiresIn", 7200)
                ping_interval = data.get("data", {}).get("pingInterval", 50)
                logger.info("[Lansenger] Got WS endpoint: url=%s, expiresIn=%ds, pingInterval=%ds",
                            ws_url, expires_in, ping_interval)
                self._ws_url = ws_url
                self._ws_ping_interval = ping_interval
                return ws_url
            else:
                logger.error("[Lansenger] WebSocket endpoint error: errCode=%s, errMsg=%s",
                             data.get("errCode"), data.get("errMsg"))
                return None
        except httpx.HTTPStatusError as e:
            logger.error("[Lansenger] WS endpoint HTTP error: %s (response=%s)",
                         e, e.response.text[:200] if e.response else "n/a")
            return None
        except Exception as e:
            logger.error("[Lansenger] Error getting WebSocket URL: %s", e)
            return None

    async def _recreate_http_client(self) -> None:
        """Close and recreate the httpx client to avoid stale connection pool zombies."""
        if self._http_client is not None:
            try:
                await self._http_client.aclose()
            except Exception:
                pass
        self._http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(10.0, connect=5.0)
        )

    async def _run_ws(self, ws_url: str) -> None:
        """Run WebSocket client with auto-reconnection."""
        self._ws_url = ws_url
        backoff_idx = 0
        try:
            while self._running:
                try:
                    ping_interval = self._ws_ping_interval
                    ping_timeout = max(10, ping_interval // 3)
                    logger.info("[Lansenger] Connecting to WebSocket: %s (ping_interval=%ds, ping_timeout=%ds)",
                                ws_url, ping_interval, ping_timeout)
                    try:
                        ws = await asyncio.wait_for(
                            websockets.connect(ws_url, ping_interval=ping_interval,
                                              ping_timeout=ping_timeout, close_timeout=10,
                                              open_timeout=10),
                            timeout=15,
                        )
                    except asyncio.TimeoutError:
                        logger.error("[Lansenger] WebSocket connect timed out (15s) — server may not accept this ticket, will discard and retry")
                        raise
                    try:
                        async with ws:
                            self._ws_client = ws
                            backoff_idx = 0
                            self._mark_connected()
                            self._last_inbound_time = time.time()  # reset silence timer on connect
                            logger.info("[Lansenger] WebSocket connected (ping_interval=%ds, ping_timeout=%ds)",
                                        ping_interval, ping_timeout)

                            # Application-layer keepalive to detect CLOSE_WAIT zombies
                            keepalive_task = asyncio.create_task(self._ws_keepalive(ws))
                            try:
                                async for message in ws:
                                    await self._on_message(message)
                            finally:
                                keepalive_task.cancel()
                                try:
                                    await keepalive_task
                                except asyncio.CancelledError:
                                    pass
                    except websockets.exceptions.ConnectionClosedOK as e:
                        logger.info("[Lansenger] WebSocket closed normally by server (code=%d)", e.code)
                except asyncio.CancelledError:
                    return
                except websockets.exceptions.InvalidStatusCode as e:
                    if not self._running:
                        return
                    logger.error("[Lansenger] WebSocket rejected: status_code=%d, headers=%s, body=%s",
                                 e.status_code, dict(e.headers) if e.headers else "n/a",
                                 e.body.decode(errors='replace')[:200] if e.body else "n/a")
                except Exception as e:
                    if not self._running:
                        return
                    logger.warning("[Lansenger] WebSocket error: %s (type=%s)", e, type(e).__name__)

                if not self._running:
                    return

                self._ws_client = None
                # Write disconnected status without touching self._running,
                # otherwise the while loop exits and reconnection never happens.
                self._write_runtime_status_safe("disconnected", platform_state="disconnected")
                logger.warning("[Lansenger] WebSocket disconnected, will reconnect")

                delay = RECONNECT_BACKOFF[min(backoff_idx, len(RECONNECT_BACKOFF) - 1)]
                logger.info("[Lansenger] Reconnecting in %ds (attempt %d)...", delay, backoff_idx + 1)

                try:
                    await asyncio.sleep(delay)
                    backoff_idx += 1

                    # Recreate httpx client to avoid stale connection pool zombies
                    await self._recreate_http_client()
                    new_url = await self._get_websocket_url()
                    if new_url:
                        ws_url = new_url
                        self._ws_url = new_url
                        logger.info("[Lansenger] Will reconnect with new WebSocket URL")
                    else:
                        logger.error("[Lansenger] Failed to get new ticket, cannot reconnect — retrying next cycle")
                except RuntimeError as e:
                    msg = str(e)
                    if "Event loop" in msg or "no running event loop" in msg.lower():
                        logger.critical("[Lansenger] Event loop closed — cannot reconnect, adapter is permanently dead (%s)", e)
                        self._write_runtime_status_safe("fatal", platform_state="fatal",
                                                         error_code="EVENT_LOOP_CLOSED",
                                                         error_message=msg)
                        return
                    raise
                except Exception as e:
                    logger.error("[Lansenger] Error getting new ticket: %s (type=%s) — retrying next cycle", e, type(e).__name__)
        except asyncio.CancelledError:
            logger.info("[Lansenger] _run_ws cancelled — exiting")
        except Exception as e:
            logger.critical("[Lansenger] _run_ws crashed unexpectedly: %s (type=%s)", e, type(e).__name__)
            self._ws_client = None
            # Keep _running=True so _on_ws_task_done can schedule a restart
            self._write_runtime_status_safe("disconnected", platform_state="disconnected")

    def _on_ws_task_done(self, task: asyncio.Task) -> None:
        """Callback when _run_ws task finishes — log crashes and restart if unexpected."""
        if task.cancelled():
            logger.info("[Lansenger] WebSocket task was cancelled")
            return
        exc = task.exception()
        if exc is not None:
            logger.critical("[Lansenger] WebSocket task died with unhandled exception: %s (type=%s)", exc, type(exc).__name__)
        if self._running:
            logger.warning("[Lansenger] WebSocket task ended while _running=True — scheduling restart in 30s")
            try:
                asyncio.get_running_loop().call_later(30, self._restart_ws_task)
            except RuntimeError as e:
                logger.critical("[Lansenger] Cannot schedule WS restart — event loop not available: %s", e)
                self._write_runtime_status_safe("fatal", platform_state="fatal",
                                                 error_code="EVENT_LOOP_CLOSED",
                                                 error_message=str(e))

    def _restart_ws_task(self) -> None:
        """Restart the WebSocket task after an unexpected death — fetches fresh ticket."""
        if not self._running:
            logger.info("[Lansenger] Not running — skipping WS restart")
            return
        if self._ws_task is not None and not self._ws_task.done():
            logger.info("[Lansenger] WS task still running — skipping restart")
            return
        logger.warning("[Lansenger] Restarting WebSocket task — fetching fresh ticket")

        async def _restart_with_fresh_ticket():
            await self._recreate_http_client()
            ws_url = await self._get_websocket_url()
            if ws_url:
                self._ws_task = asyncio.create_task(self._run_ws(ws_url))
                self._ws_task.add_done_callback(self._on_ws_task_done)
            else:
                logger.error("[Lansenger] Failed to get fresh ticket for restart — will retry on next cycle")

        asyncio.create_task(_restart_with_fresh_ticket())

    async def _ws_keepalive(self, ws, interval: int = 120) -> None:
        """Application-layer heartbeat to detect zombie connections and silent
        inbound death.

        The websockets library's built-in ping/pong only checks TCP liveness.
        If the remote server closes the connection but the OS socket lingers in
        CLOSE_WAIT, ``async for message in ws`` blocks forever and the lib's
        ping/pong won't fire.

        Two detection mechanisms:
        1. Protocol ping/pong: ws.ping() sends an RFC 6455 ping frame and
           waits for the pong.  If it times out or fails, the connection is
           dead at protocol level → close and reconnect.
        2. Inbound silence: if no WS message has arrived for
           INBOUND_SILENCE_TIMEOUT seconds → the server may be alive at TCP
           level but not delivering messages → close and reconnect.
        """
        try:
            while self._running:
                await asyncio.sleep(interval)
                if not self._running or ws is None:
                    return

                # --- Mechanism 1: Protocol-level ping/pong round-trip ---
                try:
                    latency = await asyncio.wait_for(
                        ws.ping(),
                        timeout=10,
                    )
                    logger.debug("[Lansenger] Keepalive ping OK, latency=%.3fs", latency)
                except asyncio.TimeoutError:
                    logger.warning("[Lansenger] Keepalive ping timed out — closing WS for reconnect")
                    await ws.close()
                    return
                except Exception as e:
                    logger.warning("[Lansenger] Keepalive ping failed: %s — closing WS for reconnect", e)
                    try:
                        await ws.close()
                    except Exception:
                        pass
                    return

                # --- Mechanism 2: Inbound silence (server not delivering messages) ---
                silence_duration = time.time() - self._last_inbound_time
                if silence_duration > INBOUND_SILENCE_TIMEOUT:
                    logger.warning(
                        "[Lansenger] No inbound WS message for %ds (>%ds) — silent death, closing for reconnect",
                        int(silence_duration), INBOUND_SILENCE_TIMEOUT,
                    )
                    await ws.close()
                    return
        except asyncio.CancelledError:
            pass

    async def _ws_watchdog(self, interval: int = 60) -> None:
        """Periodically check WS task health and restart if dead.

        This is a safety net for cases where _on_ws_task_done fails to
        schedule a restart (e.g. event loop closed, callback exception).
        """
        try:
            while self._running:
                await asyncio.sleep(interval)
                if not self._running:
                    return
                if self._ws_task is None or self._ws_task.done():
                    logger.warning("[Lansenger] Watchdog: WS task dead while _running=True, restarting")
                    try:
                        self._restart_ws_task()
                    except RuntimeError as e:
                        logger.critical("[Lansenger] Watchdog: cannot restart WS — event loop not available: %s", e)
                        self._write_runtime_status_safe("fatal", platform_state="fatal",
                                                         error_code="EVENT_LOOP_CLOSED",
                                                         error_message=str(e))
                        return
        except asyncio.CancelledError:
            logger.info("[Lansenger] Watchdog cancelled")
        except RuntimeError as e:
            logger.critical("[Lansenger] Watchdog: event loop unavailable: %s", e)

    async def disconnect(self) -> None:
        """Disconnect from Lansenger."""
        self._running = False
        self._mark_disconnected()

        # Clean up registered slash commands
        if self._commands_registered:
            try:
                await _commands.delete_all_commands(self)
            except Exception as exc:
                logger.warning("[Lansenger] Failed to clean up commands: %s", exc)
            self._commands_registered = False

        if self._ws_task:
            self._ws_task.cancel()
            try:
                await self._ws_task
            except asyncio.CancelledError:
                pass
            self._ws_task = None

        if self._watchdog_task:
            self._watchdog_task.cancel()
            try:
                await self._watchdog_task
            except asyncio.CancelledError:
                pass
            self._watchdog_task = None

        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

        self._ws_client = None
        self._dedup.clear()
        logger.info("[Lansenger] Disconnected")

    # -- Inbound message processing -----------------------------------------

    @staticmethod
    def _resolve_hermes_home() -> Path:
        """Resolve Hermes home directory, respecting HERMES_HOME env var.

        Uses the HERMES_HOME environment variable (set by profiles system)
        so that different profiles get independent token/chat_type/owner files.
        Falls back to ~/.hermes when HERMES_HOME is not set.
        """
        env_home = os.environ.get("HERMES_HOME", "").strip()
        if env_home:
            return Path(env_home)
        return Path.home() / ".hermes"

    def _load_owner_id(self) -> None:
        """Load owner ID from file."""
        try:
            if self._owner_id_file.exists():
                data = json.loads(self._owner_id_file.read_text())
                self._owner_id = data.get("owner_id")
                if self._owner_id:
                    logger.info("[Lansenger] Loaded owner ID: %s", self._owner_id[:20] if self._owner_id else None)
        except Exception as e:
            logger.warning("[Lansenger] Failed to load owner ID: %s", e)

    def _save_owner_id(self) -> None:
        """Save owner ID to file."""
        try:
            self._owner_id_file.parent.mkdir(parents=True, exist_ok=True)
            self._owner_id_file.write_text(json.dumps({"owner_id": self._owner_id}, indent=2))
            logger.info("[Lansenger] Saved owner ID: %s", self._owner_id[:20] if self._owner_id else None)
        except Exception as e:
            logger.error("[Lansenger] Failed to save owner ID: %s", e)

    def _load_approvals(self) -> None:
        """Load persisted approval state from disk.  Cleans expired entries."""
        try:
            if not self._approvals_file.exists():
                return
            data = json.loads(self._approvals_file.read_text(encoding="utf-8"))
            cards = data.get("cards", {})
            now = time.time()
            loaded = 0
            max_counter = 0
            for approval_id_str, info in cards.items():
                expires_at = info.get("expires_at", 0)
                if expires_at > 0 and expires_at < now:
                    logger.debug("[Lansenger] Purging expired approval card: id=%s", approval_id_str)
                    continue
                msg_id = info.get("msg_id", "")
                chat_id = info.get("chat_id", "")
                session_key = info.get("session_key", "")
                trigger_sender_id = info.get("trigger_sender_id")
                card_type = info.get("card_type", "approveCard")

                if not msg_id or not chat_id:
                    continue

                self._approval_state[approval_id_str] = session_key
                self._card_type_map[msg_id] = card_type
                self._approval_card_msgs[approval_id_str] = (msg_id, chat_id)
                if trigger_sender_id and session_key:
                    self._pending_approval_msgs[session_key] = (msg_id, trigger_sender_id)

                # Track max approval_id for counter recovery
                try:
                    aid = int(approval_id_str)
                    if aid > max_counter:
                        max_counter = aid
                except ValueError:
                    pass
                loaded += 1

            # Restore counter so next approval_id continues from max+1
            self._approval_counter = itertools.count(max_counter + 1)

            logger.info("[Lansenger] Loaded %d pending approvals from %s (counter=%d)",
                        loaded, self._approvals_file, max_counter + 1)
        except Exception as e:
            logger.warning("[Lansenger] Failed to load approvals: %s", e)

    def _save_approvals(self) -> None:
        """Persist approval state to disk."""
        try:
            cards: Dict[str, dict] = {}
            for approval_id, (msg_id, chat_id) in self._approval_card_msgs.items():
                session_key = self._approval_state.get(approval_id, "")
                trigger_sender_id = None
                if session_key and session_key in self._pending_approval_msgs:
                    trigger_sender_id = self._pending_approval_msgs[session_key][1]

                cards[approval_id] = {
                    "msg_id": msg_id,
                    "chat_id": chat_id,
                    "session_key": session_key,
                    "trigger_sender_id": trigger_sender_id,
                    "card_type": self._card_type_map.get(msg_id, "approveCard"),
                    "expires_at": time.time() + self._gateway_approval_timeout + 60,
                }

            data = {"version": 1, "cards": cards}
            self._approvals_file.parent.mkdir(parents=True, exist_ok=True)
            self._approvals_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            logger.debug("[Lansenger] Persisted %d approvals to %s", len(cards), self._approvals_file)
        except Exception as e:
            logger.debug("[Lansenger] Failed to persist approvals: %s", e)

    @staticmethod
    def _read_gateway_approval_timeout() -> int:
        """Read Hermes core's approval gateway_timeout from config.  Default 300s."""
        try:
            from hermes_cli.config import load_config
            config = load_config()
            timeout = config.get("approvals", {}).get("gateway_timeout", 300)
            return int(timeout)
        except Exception:
            return 300

    def _load_chat_type_map(self) -> None:
        try:
            if self._chat_type_file.exists():
                data = json.loads(self._chat_type_file.read_text())
                if isinstance(data, dict):
                    self._chat_type_map.update(data)
                    logger.info("[Lansenger] Loaded %d chat type mappings from file", len(data))
        except Exception as e:
            logger.warning("[Lansenger] Failed to load chat type map: %s", e)

    def _persist_chat_type_map(self) -> None:
        if not self._chat_type_map_dirty:
            return
        self._chat_type_map_dirty = False
        try:
            self._chat_type_file.parent.mkdir(parents=True, exist_ok=True)
            self._chat_type_file.write_text(json.dumps(self._chat_type_map, indent=2))
            logger.debug("[Lansenger] Persisted %d chat type mappings", len(self._chat_type_map))
        except Exception as e:
            logger.error("[Lansenger] Failed to persist chat type map: %s", e)

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

        # 8a. Cache last sender, fromType, and msgId for autoMentionReply and reply ref
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

    # -- Token management ---------------------------------------------------

    async def _get_app_token(self) -> Optional[str]:
        """Get or refresh app access token, with persistent caching."""

        if self._app_token and datetime.now().timestamp() < self._token_expiry:
            return self._app_token

        persisted = self._load_persisted_token()
        if persisted and datetime.now().timestamp() < persisted["expires_at"]:
            self._app_token = persisted["app_token"]
            self._token_expiry = persisted["expires_at"]
            logger.info("[Lansenger] Loaded persisted appToken (expires in %ds)",
                        int(persisted["expires_at"] - datetime.now().timestamp()))
            return self._app_token

        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=30.0)

        # Check event loop is alive before making HTTP calls
        try:
            asyncio.get_running_loop()
        except RuntimeError as e:
            logger.error("[Lansenger] Cannot refresh token — event loop not available: %s", e)
            return None

        try:
            url = f"{self._api_gateway_url}/v1/apptoken/create"
            params = {
                "grant_type": "client_credential",
                "appid": self._app_id,
                "secret": self._app_secret
            }
            response = await self._http_client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            if data.get("errCode") != 0:
                logger.error("[Lansenger] Token error: %s", data.get("errMsg"))
                return None

            self._app_token = data.get("data", {}).get("appToken")
            expires_in = data.get("data", {}).get("expiresIn", 7200)
            persist_expiry = datetime.now().timestamp() + expires_in
            self._token_expiry = persist_expiry - 300  # cache expiry: 5min early refresh buffer

            self._persist_token(self._app_token, persist_expiry)

            logger.info("[Lansenger] Got new access token (expires in %ds)", expires_in)
            return self._app_token
        except Exception as e:
            logger.error("[Lansenger] Error getting token: %s", e)
            return None

    def _load_persisted_token(self) -> Optional[Dict[str, Any]]:
        """Load persisted token from ~/.hermes/lansenger_token.json.

        Validates that the stored app_id matches the current bot credentials
        to prevent cross-bot token reuse when switching bots.
        """
        try:
            if not self._token_file.exists():
                return None
            content = self._token_file.read_text(encoding="utf-8")
            data = json.loads(content)
            if "app_token" in data and "expires_at" in data:
                # Validate app_id match to prevent old token reuse after bot switch
                stored_app_id = data.get("app_id", "")
                if stored_app_id and stored_app_id != self._app_id:
                    logger.info(
                        "[Lansenger] Persisted token app_id mismatch "
                        "(stored=%s, current=%s) — discarding old token",
                        stored_app_id[:20], self._app_id[:20],
                    )
                    return None
                return data
        except Exception as e:
            logger.debug("[Lansenger] Failed to load persisted token: %s", e)
        return None

    def _persist_token(self, app_token: str, expires_at: float) -> None:
        """Write token to ~/.hermes/lansenger_token.json for cross-process reuse."""
        try:
            data = {
                "app_token": app_token,
                "expires_at": expires_at,
                "app_id": self._app_id,  # validate on load to prevent cross-bot reuse
            }
            self._token_file.parent.mkdir(parents=True, exist_ok=True)
            self._token_file.write_text(json.dumps(data), encoding="utf-8")
            logger.debug("[Lansenger] Persisted appToken to %s", self._token_file)
        except Exception as e:
            logger.debug("[Lansenger] Failed to persist token: %s", e)

    async def _download_media(self, media_id: str) -> Optional[bytes]:
        """Download media file by media ID. Returns raw file bytes or None."""
        token = await self._get_app_token()
        if not token:
            return None

        try:
            url = f"{self._api_gateway_url}/v1/medias/{media_id}/fetch"
            params = {"app_token": token}
            response = await self._http_client.get(url, params=params)
            response.raise_for_status()
            return response.content
        except Exception as e:
            logger.error("[Lansenger] Download media error: %s", e)
            return None

    async def _save_media_temp(self, media_bytes: bytes, media_type: str = "file") -> str:
        """Save media bytes to temp file, return file path."""
        import tempfile
        
        ext_map = {"image": ".jpg", "video": ".mp4", "file": ".dat", "voice": ".amr"}
        ext = ext_map.get(media_type, ".dat")
        
        # Detect image type from magic bytes
        if media_type == "image" and len(media_bytes) >= 8:
            if media_bytes[:2] == b'\xff\xd8': ext = ".jpg"
            elif media_bytes[:8] == b'\x89PNG\r\n\x1a\n': ext = ".png"
            elif media_bytes[:6] in (b'GIF87a', b'GIF89a'): ext = ".gif"
        
        fd, path = tempfile.mkstemp(suffix=ext, prefix=f"lansenger_{media_type}_")
        try:
            with os.fdopen(fd, 'wb') as f:
                f.write(media_bytes)
            logger.info("[Lansenger] Saved media to %s", path)
            return path
        except Exception as e:
            logger.error("[Lansenger] Save media error: %s", e)
            try: os.unlink(path)
            except: pass
            return ""

    # -- Tool event formatting (formatText / Markdown) ----------------------

    def format_tool_event(self, event: Any, *, mode: str = "all",
                          preview_max_len: int = 40) -> Optional[str]:
        """Return Markdown-formatted tool chrome for Lansenger formatText.

        Overrides the base class plain-text output to leverage Lansenger's
        Markdown renderer (bold tool names, code blocks for args, bullet
        lists for results).
        """
        from gateway.stream_events import ToolCallChunk
        if not isinstance(event, ToolCallChunk):
            return None

        from agent.display import get_tool_emoji
        emoji = get_tool_emoji(event.tool_name, default="⚙️")

        if mode == "verbose":
            if event.args:
                arg_lines = []
                for k, v in event.args.items():
                    val_str = str(v)
                    if preview_max_len > 0 and len(val_str) > preview_max_len:
                        val_str = val_str[:preview_max_len - 3] + "..."
                    arg_lines.append(f"**{k}**：{val_str}")
                header = f"{emoji} **{event.tool_name}** `{list(event.args.keys())}`"
                return header + "\n" + "\n".join(arg_lines)
            if event.preview:
                preview = event.preview
                if preview_max_len > 0 and len(preview) > preview_max_len:
                    preview = preview[:preview_max_len - 3] + "..."
                return f"{emoji} **{event.tool_name}**：{preview}"
            return f"{emoji} **{event.tool_name}** ..."

        preview = event.preview
        if preview:
            cap = preview_max_len if preview_max_len > 0 else 40
            if len(preview) > cap:
                preview = preview[:cap - 3] + "..."
            return f"{emoji} **{event.tool_name}**：{preview}"
        return f"{emoji} **{event.tool_name}** ..."

    def _is_group_chat(self, chat_id: str) -> bool:
        """Check if chat_id is a group chat.

        Personal bots can only DM with the owner. Therefore:
        - chat_id == owner_id → DM (private chat)
        - Everything else → group (either a real group or will fail gracefully)
        """
        if self._owner_id and chat_id == self._owner_id:
            return False
        return True

    # -- Outbound message sending -------------------------------------------

    async def send(self, chat_id: str, content: str, **kwargs) -> SendResult:
        """Send a message (alias for send_format_text).

        Auto-populates reminder with the last sender's ID when
        auto_mention_reply is enabled and this is a group chat.
        Uses userIds for users, botIds for bots based on fromType (0=user, 1=app).
        Explicit reminder kwarg always wins.

        Auto-populates refMsgId when auto_quote_reply is enabled.
        Supports both group and private chats.
        """
        reminder = kwargs.get("reminder")
        if not reminder and self._is_group_chat(chat_id):
            # Check auto_mention_reply: per-group > global
            per_group = self._groups_config.get(chat_id, {})
            auto_mention = per_group.get("auto_mention_reply", self._auto_mention_reply)
            if isinstance(auto_mention, str):
                auto_mention = str(auto_mention).lower() in ("true", "1", "yes")
            if auto_mention:
                last_sender = self._chat_last_sender.get(chat_id)
                if last_sender:
                    from_type = self._chat_last_from_type.get(chat_id, 0)
                    # fromType: 0=user, 1=app (bot)
                    if str(from_type) == "1":
                        reminder = {"botIds": [last_sender]}
                    else:
                        reminder = {"userIds": [last_sender]}

        # Auto quote reply: per-group > global (groups), global only (private)
        ref_msg_id = None
        if self._is_group_chat(chat_id):
            per_group = self._groups_config.get(chat_id, {})
            auto_quote = per_group.get("auto_quote_reply", self._auto_quote_reply)
        else:
            auto_quote = self._auto_quote_reply
        if isinstance(auto_quote, str):
            auto_quote = str(auto_quote).lower() in ("true", "1", "yes")
        if auto_quote:
            ref_msg_id = self._chat_last_msg_id.get(chat_id)

        return await self.send_format_text(chat_id, content, reminder=reminder, ref_msg_id=ref_msg_id)

    async def send_typing(self, chat_id: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Send typing indicator (not supported by Lansenger)."""
        pass  # Lansenger doesn't support typing indicators

    async def send_text(self, chat_id: str, content: str, reminder: dict = None, ref_msg_id: str = None) -> SendResult:
        """Send a plain text message, optionally with @mentions and reply quote.
        
        Routes to /v1/messages/group/create for group chats,
        /v1/bot/messages/create for private chats.
        
        Args:
            chat_id: Recipient user ID or chat ID
            content: Text content. In group chat, recommended to include @姓名
                     when replying to someone (e.g. "@张三 请查收").
            reminder: Optional dict with 'all' (bool), 'userIds' (list), 'botIds' (list) for @mentions.
                      Private chat supports this but it is unnecessary (only one participant).
            ref_msg_id: Optional msgId to quote/reply to.
        """
        token = await self._get_app_token()
        if not token:
            return SendResult(success=False, error="No access token")

        try:
            is_group = self._is_group_chat(chat_id)

            if is_group:
                # Group message: use /v1/messages/group/create
                url = f"{self._api_gateway_url}{API_ENDPOINTS['smart_bot']['group_message']}?app_token={token}"
                text_data = {"content": content}
                if reminder:
                    text_data["reminder"] = reminder
                payload = {
                    "groupId": chat_id,
                    "msgType": "text",
                    "msgData": {"text": text_data},
                }
                if ref_msg_id:
                    payload["refMsgId"] = ref_msg_id
            else:
                # Private message: use /v1/bot/messages/create
                url = f"{self._api_gateway_url}{API_ENDPOINTS['smart_bot']['private_message']}?app_token={token}"
                text_data = {"content": content}
                if reminder:
                    text_data["reminder"] = reminder
                payload = {
                    "userIdList": [chat_id],
                    "msgType": "text",
                    "msgData": {"text": text_data},
                }
                if ref_msg_id:
                    payload["refMsgId"] = ref_msg_id

            response = await self._http_client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()

            if data.get("errCode") != 0:
                return SendResult(success=False, error=data.get("errMsg"))

            msg_id = data.get("data", {}).get("msgId")
            logger.info("[Lansenger] Text message sent to %s (group=%s)", chat_id, is_group)
            return SendResult(success=True, message_id=msg_id, raw_response=data)
        except Exception as e:
            logger.error("[Lansenger] Send text error: %s", e)
            return SendResult(success=False, error=str(e), retryable=True)

    async def send_format_text(self, chat_id: str, content: str, reminder: dict = None, ref_msg_id: str = None) -> SendResult:
            """Send a formatted text message (Markdown support), optionally with @mentions and reply ref.

            Routes to /v1/messages/group/create for group chats,
            /v1/bot/messages/create for private chats.

            Args:
                chat_id: Recipient user ID or chat ID
                content: Markdown-formatted text content.
                reminder: Optional dict with 'all' (bool), 'userIds' (list), and
                          'botIds' (list) for @mentions.
                ref_msg_id: Optional msgId to quote/reply to.
            """
            token = await self._get_app_token()
            if not token:
                return SendResult(success=False, error="No access token")

            try:
                is_group = self._is_group_chat(chat_id)

                format_text_data: Dict[str, Any] = {
                    "formatType": 1,
                    "text": content,
                }
                if reminder:
                    format_text_data["reminder"] = reminder

                if is_group:
                    url = f"{self._api_gateway_url}{API_ENDPOINTS['smart_bot']['group_message']}?app_token={token}"
                    payload = {
                        "groupId": chat_id,
                        "msgType": "formatText",
                        "msgData": {"formatText": format_text_data},
                    }
                    if ref_msg_id:
                        payload["refMsgId"] = ref_msg_id
                else:
                    url = f"{self._api_gateway_url}{API_ENDPOINTS['smart_bot']['private_message']}?app_token={token}"
                    payload = {
                        "userIdList": [chat_id],
                        "msgType": "formatText",
                        "msgData": {"formatText": format_text_data},
                    }
                    if ref_msg_id:
                        payload["refMsgId"] = ref_msg_id

                response = await self._http_client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()

                if data.get("errCode") != 0:
                    return SendResult(success=False, error=data.get("errMsg"))

                msg_id = data.get("data", {}).get("msgId")
                logger.info("[Lansenger] FormatText sent to %s (group=%s, reminder=%s)",
                            chat_id, is_group, bool(reminder))
                return SendResult(success=True, message_id=msg_id, raw_response=data)
            except Exception as e:
                logger.error("[Lansenger] Send formatText error: %s", e, exc_info=True)
                return SendResult(success=False, error=str(e), retryable=True)

    def _probe_video_size(self, file_path: str) -> tuple:
        """Try to extract width/height from video/image via ffprobe."""
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "v:0",
                 "-show_entries", "stream=width,height", "-of", "csv=s=x:p=0",
                 str(file_path)],
                capture_output=True, text=True, timeout=5,
            )
            parts = result.stdout.strip().split("x")
            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                return int(parts[0]), int(parts[1])
        except Exception:
            pass
        return None, None

    def _probe_duration(self, file_path: str) -> Optional[int]:
        """Try to extract duration in seconds via ffprobe."""
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "error",
                 "-show_entries", "format=duration", "-of", "csv=s=x:p=0",
                 str(file_path)],
                capture_output=True, text=True, timeout=5,
            )
            val = result.stdout.strip()
            if val and val.replace(".", "", 1).isdigit():
                return max(1, round(float(val)))
        except Exception:
            pass
        return None

    def _extract_video_cover(self, file_path: str) -> Optional[str]:
        """Extract the first frame of a video as a JPEG cover image using ffmpeg.
        
        Returns the temp file path of the cover image, or None if ffmpeg is unavailable.
        """
        try:
            tmp = tempfile.mktemp(suffix=".jpg")
            result = subprocess.run(
                ["ffmpeg", "-y", "-i", str(file_path),
                 "-vframes", "1", "-f", "image2", tmp],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0 and os.path.isfile(tmp) and os.path.getsize(tmp) > 0:
                return tmp
            try:
                os.unlink(tmp)
            except Exception:
                pass
        except Exception:
            pass
        return None

    async def query_groups(self, page_offset: int = 0, page_size: int = 100) -> Dict[str, Any]:
        """Query the bot's group ID list via GET /v2/groups/fetch.

        Args:
            page_offset: Page number starting from 0 (default 0)
            page_size: Per-page count (max 100, default 100)

        Returns:
            Dict with totalGroupIds (int) and groupIds (list of str)
        """
        token = await self._get_app_token()
        if not token:
            return {"totalGroupIds": 0, "groupIds": []}

        try:
            url = (
                f"{self._api_gateway_url}{API_ENDPOINTS['groups']['fetch']}"
                f"?app_token={token}&page_offset={page_offset}&page_size={page_size}"
            )

            response = await self._http_client.get(url)
            response.raise_for_status()
            data = response.json()

            if data.get("errCode") != 0:
                logger.error("[Lansenger] Query groups error: %s", data.get("errMsg"))
                return {"totalGroupIds": 0, "groupIds": []}

            result = data.get("data", {})
            logger.info("[Lansenger] Queried groups: total=%d", result.get("totalGroupIds", 0))
            return result

        except Exception as e:
            logger.error("[Lansenger] Query groups error: %s", e)
            return {"totalGroupIds": 0, "groupIds": []}

    async def get_group_info(self, group_id: str) -> Dict[str, Any]:
        """Get group basic info via GET /v2/groups/{group_id}/info/fetch.

        Returns group name, description, owner, total members, max members, etc.
        """
        token = await self._get_app_token()
        if not token:
            return {"error": "Failed to get app token"}

        try:
            url = (
                f"{self._api_gateway_url}"
                f"{API_ENDPOINTS['groups']['info'].format(group_id=group_id)}"
                f"?app_token={token}"
            )
            response = await self._http_client.get(url)
            response.raise_for_status()
            data = response.json()

            if data.get("errCode") != 0:
                logger.error("[Lansenger] Get group info error: errCode=%s errMsg=%s",
                             data.get("errCode"), data.get("errMsg"))
                return {"error": data.get("errMsg", "Unknown error")}

            result = data.get("data", {})
            logger.info("[Lansenger] Got group info: name=%s totalMembers=%d",
                        result.get("name", "?"), result.get("totalMembers", 0))
            return result

        except Exception as e:
            logger.error("[Lansenger] Get group info error: %s", e)
            return {"error": str(e)}

    async def get_group_members(self, group_id: str, page_offset: int = 0,
                                page_size: int = 100) -> Dict[str, Any]:
        """Get group member list via GET /v2/groups/{group_id}/members/fetch.

        Returns totalMembers count and members list with staffId, name, orgName, role.
        """
        token = await self._get_app_token()
        if not token:
            return {"error": "Failed to get app token"}

        try:
            url = (
                f"{self._api_gateway_url}"
                f"{API_ENDPOINTS['groups']['members'].format(group_id=group_id)}"
                f"?app_token={token}&page_offset={page_offset}&page_size={page_size}"
            )
            response = await self._http_client.get(url)
            response.raise_for_status()
            data = response.json()

            if data.get("errCode") != 0:
                logger.error("[Lansenger] Get group members error: errCode=%s errMsg=%s",
                             data.get("errCode"), data.get("errMsg"))
                return {"error": data.get("errMsg", "Unknown error")}

            result = data.get("data", {})
            logger.info("[Lansenger] Got group members: total=%d returned=%d",
                        result.get("totalMembers", 0), len(result.get("members", [])))
            return result

        except Exception as e:
            logger.error("[Lansenger] Get group members error: %s", e)
            return {"error": str(e)}

    async def check_in_group(self, group_id: str, staff_id: str = "") -> Dict[str, Any]:
        """Check if a staff or bot is in a group via GET /v2/groups/{group_id}/members/is_in_group.

        Priority: staff_id > user_token > app_token.
        """
        token = await self._get_app_token()
        if not token:
            return {"error": "Failed to get app token"}

        try:
            params = f"app_token={token}"
            if staff_id:
                params += f"&staff_id={staff_id}"
            url = (
                f"{self._api_gateway_url}"
                f"{API_ENDPOINTS['groups']['is_in_group'].format(group_id=group_id)}"
                f"?{params}"
            )
            response = await self._http_client.get(url)
            response.raise_for_status()
            data = response.json()

            if data.get("errCode") != 0:
                logger.error("[Lansenger] Check in group error: errCode=%s errMsg=%s",
                             data.get("errCode"), data.get("errMsg"))
                return {"error": data.get("errMsg", "Unknown error")}

            return data.get("data", {"isInGroup": False})

        except Exception as e:
            logger.error("[Lansenger] Check in group error: %s", e)
            return {"error": str(e)}

    async def _ensure_group_cache(self, group_id: str) -> Optional[Dict[str, Any]]:
        """Ensure group info and members are cached. Returns cache entry or None.

        Fetches group info + members (if total <= 100) on cache miss or expiry.
        Uses per-group-id asyncio.Lock to avoid concurrent duplicate fetches.
        """
        now = time.time()
        cached = self._group_cache.get(group_id)
        if cached and (now - cached.get("fetched_at", 0)) < self._group_cache_ttl:
            return cached

        # Use per-group lock to avoid concurrent fetches for the same group
        if group_id not in self._group_fetch_locks:
            self._group_fetch_locks[group_id] = asyncio.Lock()

        async with self._group_fetch_locks[group_id]:
            # Double-check after acquiring lock
            cached = self._group_cache.get(group_id)
            if cached and (now - cached.get("fetched_at", 0)) < self._group_cache_ttl:
                return cached

            # Fetch group info
            info = await self.get_group_info(group_id)
            if "error" in info:
                logger.warning("[Lansenger] Failed to fetch group info for %s: %s",
                               group_id[:20], info.get("error"))
                return None

            members = []
            total_members = info.get("totalMembers", 0)

            # Only prefetch members if total <= 100
            if 0 < total_members <= 100:
                member_result = await self.get_group_members(group_id)
                if "error" not in member_result:
                    members = member_result.get("members", [])

            entry = {
                "info": info,
                "members": members,
                "fetched_at": time.time(),
            }
            self._group_cache[group_id] = entry
            logger.info("[Lansenger] Group cache updated for %s: name=%s members=%d/%d",
                        group_id[:20], info.get("name", "?"), len(members), total_members)
            return entry

    def _build_group_chat_topic(self, cache_entry: Dict[str, Any]) -> str:
        """Build chat_topic string from cached group info for system prompt injection."""
        info = cache_entry.get("info", {})
        members = cache_entry.get("members", [])

        lines = []
        lines.append(f"群名称: {info.get('name', '未知')}")
        desc = info.get("description", "").strip()
        if desc:
            lines.append(f"群描述: {desc}")
        lines.append(f"群人数: {info.get('totalMembers', 0)} 人 (上限 {info.get('maxMembers', '?')})")
        state = "正常" if info.get("state") == 0 else "已解散"
        lines.append(f"群状态: {state}")

        if members:
            lines.append("群成员:")
            role_labels = {0: "成员", 1: "助理群主", 2: "群主"}
            for m in members:
                name = m.get("name", m.get("staffId", "?"))
                role = role_labels.get(m.get("role", 0), "成员")
                org = m.get("orgName", "")
                if org:
                    lines.append(f"  - {name} ({role}) — {org}")
                else:
                    lines.append(f"  - {name} ({role})")
        else:
            total = info.get("totalMembers", 0)
            if total > 100:
                lines.append(f"群成员过多({total}人)，如需查询具体成员请使用 lansenger_get_group_members 工具。")

        return "\n".join(lines)

    async def send_app_articles(
        self,
        chat_id: str,
        articles: List[Dict[str, str]],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        """Send an appArticles (图文卡片) message with multiple article entries.

        Routes to /v1/messages/group/create for group chats,
        /v1/bot/messages/create for private chats.

        Each article dict must contain:
            - imgUrl (required): Image URL
            - title (required): Article title
            - url (required): Content link URL
            Optional:
            - pcUrl: PC content link URL
            - summary: Article summary
            - attach: Mini-app redirect params (ignored by other apps)

        Args:
            chat_id: Recipient user ID or chat ID
            articles: List of article dicts (1+ entries)
            metadata: Optional metadata dict
        """
        if not articles:
            return SendResult(success=False, error="No articles provided")

        token = await self._get_app_token()
        if not token:
            return SendResult(success=False, error="No access token")

        try:
            is_group = self._is_group_chat(chat_id)

            if is_group:
                url = f"{self._api_gateway_url}{API_ENDPOINTS['smart_bot']['group_message']}?app_token={token}"
                payload = {
                    "groupId": chat_id,
                    "msgType": "appArticles",
                    "msgData": {"appArticles": articles},
                }
            else:
                url = f"{self._api_gateway_url}{API_ENDPOINTS['smart_bot']['private_message']}?app_token={token}"
                payload = {
                    "userIdList": [chat_id],
                    "msgType": "appArticles",
                    "msgData": {"appArticles": articles},
                }

            response = await self._http_client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()

            if data.get("errCode") != 0:
                return SendResult(success=False, error=data.get("errMsg"))

            msg_id = data.get("data", {}).get("msgId")
            logger.info("[Lansenger] appArticles sent to %s, msgId=%s (group=%s)", chat_id, msg_id, is_group)
            return SendResult(success=True, message_id=msg_id, raw_response=data)

        except Exception as e:
            logger.error("[Lansenger] Send appArticles error: %s", e)
            return SendResult(success=False, error=str(e), retryable=True)

    async def send_app_card(
        self,
        chat_id: str,
        head_title: str = "",
        body_title: str = "",
        body_sub_title: str = "",
        body_content: str = "",
        signature: str = "",
        fields: Optional[List[Dict[str, str]]] = None,
        links: Optional[List[Dict[str, str]]] = None,
        card_link: str = "",
        pc_card_link: str = "",
        is_dynamic: bool = False,
        head_status_info: Optional[Dict[str, str]] = None,
        staff_id: str = "",
        head_icon_url: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        """Send an appCard (应用卡片) message with rich formatting support.

        NOTE: appCard and i18nAppCard are DIFFERENT message types:
        - appCard: supports isDynamic + headStatusInfo for in-place status
          updates, but uses a SINGLE language (no i18n fields).
        - i18nAppCard: supports 5 languages (zhHans/zhHant/zhHantHK/en/fr)
          but does NOT support dynamic updates or headStatusInfo.
          Reserved for future use (send_i18n_app_card stub below).

        appCard supports div-style HTML formatting (color, font-size, text-align, text-indent).
        font-size MUST use pt unit (e.g. 14pt) — px is rejected by the enterprise API.
        adapter provides _convert_px_to_pt() helper but it is not auto-applied;
        callers must ensure pt units or call the helper explicitly.
        Dynamic cards (is_dynamic=True) can be updated later via update_dynamic_card_status().

        Args:
            chat_id: Recipient user ID or chat ID
            head_title: Card header title
            body_title: Card body title (required, max 600 bytes). Supports div style tags.
            body_sub_title: Card body subtitle (max 1200 bytes). Supports div style tags.
            body_content: Card body content (max 3000 bytes). Supports div style tags.
            signature: Card signature (max 96 bytes). Supports color style.
            fields: List of key/value dicts (max 10 pairs). Supports color style.
            links: List of title/url dicts (max 3 pairs). Title supports color/position.
            card_link: Card click-through link
            pc_card_link: PC client click-through link
            is_dynamic: Enable dynamic card status updates (for approval workflows)
            head_status_info: Dynamic card status info dict with iconLink/description/colour
            staff_id: Staff ID for showing sender avatar
            head_icon_url: Header icon URL
            metadata: Optional metadata dict
        """
        if not body_title:
            return SendResult(success=False, error="body_title is required for appCard")

        token = await self._get_app_token()
        if not token:
            return SendResult(success=False, error="No access token")

        try:
            is_group = self._is_group_chat(chat_id)

            if is_group:
                url = f"{self._api_gateway_url}{API_ENDPOINTS['smart_bot']['group_message']}?app_token={token}"
            else:
                url = f"{self._api_gateway_url}{API_ENDPOINTS['smart_bot']['private_message']}?app_token={token}"

            app_card_data: Dict[str, Any] = {
                "headTitle": self._fix_app_card_styles(head_title),
                "headIconUrl": head_icon_url,
                "isDynamic": is_dynamic,
                "bodyTitle": self._fix_app_card_styles(body_title),
                "cardLink": card_link,
                "pcCardLink": pc_card_link,
            }

            if is_dynamic and not head_status_info:
                head_status_info = {
                    "description": "<div style=\"color:rgba(0,0,0,.47)\">Active</div>",
                    "colour": "rgba(0,0,0,.47)",
                }

            if is_dynamic and head_status_info:
                app_card_data["headStatusInfo"] = head_status_info

            if body_sub_title:
                app_card_data["bodySubTitle"] = self._fix_app_card_styles(body_sub_title)
            if body_content:
                app_card_data["bodyContent"] = self._fix_app_card_styles(body_content, is_body_content=True)
            if signature:
                app_card_data["signature"] = self._fix_app_card_styles(signature)
            if staff_id:
                app_card_data["staffId"] = staff_id
            if fields:
                app_card_data["fields"] = fields
            if links:
                app_card_data["links"] = links

            if is_group:
                payload = {
                    "groupId": chat_id,
                    "msgType": "appCard",
                    "msgData": {"appCard": app_card_data},
                }
            else:
                payload = {
                    "userIdList": [chat_id],
                    "msgType": "appCard",
                    "msgData": {"appCard": app_card_data},
                }

            response = await self._http_client.post(url, json=payload)
            response.raise_for_status()

            if not response.text or len(response.text.strip()) == 0:
                return SendResult(success=False, error="Empty API response for appCard — likely a payload format issue", retryable=True)

            data = response.json()

            if data.get("errCode") != 0:
                return SendResult(success=False, error=data.get("errMsg"))

            msg_id = data.get("data", {}).get("msgId")
            logger.info("[Lansenger] appCard sent to %s, msgId=%s, dynamic=%s, group=%s", chat_id, msg_id, is_dynamic, is_group)
            return SendResult(success=True, message_id=msg_id, raw_response=data)

        except Exception as e:
            logger.error("[Lansenger] Send appCard error: %s", e)
            return SendResult(success=False, error=str(e), retryable=True)

    # ------------------------------------------------------------------
    # i18nAppCard — RESERVED for future use
    # ------------------------------------------------------------------
    # i18nAppCard supports 5 languages (zhHans/zhHant/zhHantHK/en/fr) but
    # does NOT support isDynamic or headStatusInfo.  It cannot be updated
    # in-place after sending.  Currently the approval workflow uses appCard
    # with language detection instead.  When multi-language broadcast
    # (sending the SAME card to users of different languages simultaneously)
    # becomes necessary, implement send_i18n_app_card() here.

    async def send_i18n_app_card(
        self,
        chat_id: str,
        i18n_head_title: Optional[Dict[str, str]] = None,
        head_icon_url: str = "",
        i18n_body_title: Optional[Dict[str, str]] = None,
        i18n_body_sub_title: Optional[Dict[str, str]] = None,
        i18n_body_content: Optional[Dict[str, str]] = None,
        i18n_signature: Optional[Dict[str, str]] = None,
        staff_id: str = "",
        i18n_fields: Optional[List[Dict[str, Any]]] = None,
        i18n_links: Optional[List[Dict[str, Any]]] = None,
        card_link: str = "",
        pc_card_link: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        """Send an i18nAppCard (国际化应用卡片) — RESERVED for future use.

        i18nAppCard supports 5 languages but does NOT support dynamic
        updates (isDynamic) or headStatusInfo.  For approval workflows
        that need in-place status updates, use send_app_card() instead.
        """
        raise NotImplementedError(
            "i18nAppCard is reserved for future use. "
            "For approval cards with dynamic updates, use send_app_card() "
            "with is_dynamic=True and headStatusInfo."
        )

    async def update_dynamic_card_status(
        self,
        msg_id: str,
        head_status_info: Optional[Dict[str, str]] = None,
        links: Optional[List[Dict[str, str]]] = None,
        is_last_update: bool = False,
        chat_id: Optional[str] = None,
    ) -> SendResult:
        """Update a dynamic appCard's status (e.g. approval: pending → approved/rejected).

        The card must have been sent with is_dynamic=True. Uses POST /v1/messages/dynamic/update.

        Args:
            msg_id: The message ID returned from send_app_card (when is_dynamic=True)
            head_status_info: Updated status info dict with iconLink/description/colour
            links: Updated links list (max 3 pairs)
            is_last_update: True = final status update, card becomes static after this
            chat_id: Optional chat_id for private message updates (user_token needed)
        """
        token = await self._get_app_token()
        if not token:
            return SendResult(success=False, error="No access token")

        try:
            # Detect group vs DM for logging and potential future routing
            is_group = self._is_group_chat(chat_id) if chat_id else None
            
            # Build URL: unified endpoint for both group and DM
            url_params = f"app_token={token}"
            url = f"{self._api_gateway_url}{API_ENDPOINTS['message']['dynamic_update']}?{url_params}"

            app_card_update: Dict[str, Any] = {
                "isLastUpdate": is_last_update,
            }
            if head_status_info:
                app_card_update["headStatusInfo"] = head_status_info
            if links:
                app_card_update["links"] = links

            payload = {
                "msgId": msg_id,
                "msgType": "appCard",
                "msgData": {
                    "appCardUpdateMsg": app_card_update,
                },
            }

            response = await self._http_client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()

            if data.get("errCode") != 0:
                return SendResult(success=False, error=data.get("errMsg"))

            logger.info("[Lansenger] Dynamic card %s updated, isLast=%s, group=%s", msg_id, is_last_update, is_group)
            return SendResult(success=True, raw_response=data)

        except Exception as e:
            logger.error("[Lansenger] Update dynamic card error: %s", e)
            return SendResult(success=False, error=str(e), retryable=True)

    async def send_text_with_media(self, chat_id: str, content: str, media_type: int, media_ids: List[str], reminder: dict = None, ref_msg_id: str = None) -> SendResult:
        """Send a text message with media attachment (file/image/video), optionally with @mentions.
        
        Args:
            chat_id: Recipient user ID or chat ID
            content: Text content (caption)
            media_type: 1=video, 2=image, 3=file
            media_ids: List of media IDs from upload_media_file()
            reminder: Optional dict with 'all' (bool) and 'userIds' (list) for @mentions.
                      Only works in group/staff chat; private chat does not support @mentions.
            
        Note: Uses msgType='text' (not formatText) because formatText doesn't support media.
              Markdown is NOT supported when sending media.
        """
        token = await self._get_app_token()
        if not token:
            return SendResult(success=False, error="No access token")

        try:
            is_group = self._is_group_chat(chat_id)

            if is_group:
                url = f"{self._api_gateway_url}{API_ENDPOINTS['smart_bot']['group_message']}?app_token={token}"
            else:
                url = f"{self._api_gateway_url}{API_ENDPOINTS['smart_bot']['private_message']}?app_token={token}"

            text_data = {
                "content": content,
                "mediaType": media_type,
                "mediaIds": media_ids
            }
            if reminder:
                text_data["reminder"] = reminder

            if is_group:
                payload = {
                    "groupId": chat_id,
                    "msgType": "text",
                    "msgData": {"text": text_data},
                }
                if ref_msg_id:
                    payload["refMsgId"] = ref_msg_id
            else:
                payload = {
                    "userIdList": [chat_id],
                    "msgType": "text",
                    "msgData": {"text": text_data},
                }
                if ref_msg_id:
                    payload["refMsgId"] = ref_msg_id

            response = await self._http_client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()

            if data.get("errCode") != 0:
                return SendResult(success=False, error=data.get("errMsg"))

            msg_id = data.get("data", {}).get("msgId")
            logger.info("[Lansenger] Text+media message sent to %s (group=%s)", chat_id, is_group)
            return SendResult(success=True, message_id=msg_id, raw_response=data)
        except Exception as e:
            logger.error("[Lansenger] Send text+media error: %s", e)
            return SendResult(success=False, error=str(e), retryable=True)

    async def upload_media_file(self, file_path: str, media_type: int,
                                  width: int = None, height: int = None, duration: int = None) -> Optional[str]:
        """Upload a media file to Lansenger and return mediaId.

        Uses /v1/app/medias/create (4.5.4) — supports larger files
        (image up to 10MB, others up to 20MB, per EMC org config).

        Args:
            file_path: Path to the local file
            media_type: 1=video, 2=image, 3=file, 4=audio
            width: Video/image width (auto-detected via ffprobe if not provided)
            height: Video/image height (auto-detected via ffprobe if not provided)
            duration: Video/audio duration in seconds (auto-detected via ffprobe if not provided)

        Returns:
            mediaId string on success, None on failure
        """
        token = await self._get_app_token()
        if not token:
            logger.error("[Lansenger] No access token for media upload")
            return None

        type_map = {1: "video", 2: "image", 3: "file", 4: "audio"}
        type_str = type_map.get(media_type, "file")

        extra_params = {}
        if type_str in ("video", "image"):
            w, h = (width, height) if width and height else self._probe_video_size(file_path)
            if w:
                extra_params["width"] = w
            if h:
                extra_params["height"] = h
        if type_str in ("video", "audio"):
            d = duration or self._probe_duration(file_path)
            if d:
                extra_params["duration"] = d

        try:
            query = f"type={type_str}&app_token={token}"
            for k, v in extra_params.items():
                query += f"&{k}={v}"
            url = f"{self._api_gateway_url}/v1/app/medias/create?{query}"

            with open(file_path, 'rb') as f:
                file_content = f.read()

            filename = os.path.basename(file_path)
            files = {'media': (filename, file_content)}

            response = await self._http_client.post(url, files=files)
            response.raise_for_status()
            data = response.json()

            if data.get("errCode") != 0:
                logger.error("[Lansenger] Upload media error: %s", data.get("errMsg"))
                return None

            media_id = data.get("data", {}).get("mediaId")
            logger.info("[Lansenger] Media uploaded: %s (%s)", filename, media_id)
            return media_id
        except Exception as e:
            logger.error("[Lansenger] Upload media error: %s", e)
            return None

    async def send_file(self, chat_id: str, file_path: str, caption: str = "", media_type: int = 3,
                          width: int = None, height: int = None, duration: int = None) -> SendResult:
        """Send a file/image/video message.
        
        Args:
            chat_id: Recipient user ID
            file_path: Path to the local file
            caption: Optional caption text (plain text, Markdown NOT supported with media)
            media_type: 1=video, 2=image, 3/file, 4=audio (default: 3)
            width: Video/image width (auto-detected via ffprobe if not provided)
            height: Video/image height (auto-detected via ffprobe if not provided)
            duration: Video/audio duration in seconds (auto-detected via ffprobe if not provided)
            
        Returns:
            SendResult with success status
            
        Note: Uses msgType='text' which doesn't support Markdown. For Markdown, send separately.
        """
        if not os.path.isfile(file_path):
            logger.warning("[Lansenger] File not found: %s — skipping", file_path)
            return SendResult(success=False, error=f"File not found: {file_path}")

        media_id = await self.upload_media_file(file_path, media_type,
                                                 width=width, height=height, duration=duration)
        if not media_id:
            return SendResult(success=False, error="Failed to upload file")

        media_ids = [media_id]

        if media_type == 1:
            cover_path = self._extract_video_cover(file_path)
            if cover_path:
                try:
                    cover_id = await self.upload_media_file(cover_path, 2,
                                                             width=width, height=height)
                    if cover_id:
                        media_ids = [media_id, cover_id]
                finally:
                    try:
                        os.unlink(cover_path)
                    except Exception:
                        pass
            else:
                logger.warning("[Lansenger] Could not extract video cover frame — sending with single mediaId")

        return await self.send_text_with_media(chat_id, caption, media_type=media_type, media_ids=media_ids)

    async def send_image_file(self, chat_id: str, image_path: str, caption: Optional[str] = None, **kwargs) -> SendResult:
        """Send a local image file.
        
        Args:
            chat_id: Recipient user ID
            image_path: Path to the local image file
            caption: Optional caption text (plain text, Markdown NOT supported with media)
            
        Returns:
            SendResult with success status
            
        Note: Uses media_type=2 (image) for upload and sending.
        """
        return await self.send_file(chat_id, image_path, caption or "", media_type=2)

    async def send_image(self, chat_id: str, image_url: str, caption: Optional[str] = None, **kwargs) -> SendResult:
        """Send an image by URL.
        
        Note: Downloads image first, then uploads to Lansenger.
        """
        import tempfile
        import httpx
        
        temp_path = None
        try:
            async with httpx.AsyncClient() as client:
                try:
                    resp = await client.get(image_url, timeout=30)
                except httpx.ConnectError as e:
                    return SendResult(success=False, error=f"Image URL unreachable: {image_url} — network error: {e}")
                except httpx.TimeoutException:
                    return SendResult(success=False, error=f"Image URL timed out: {image_url}")
                
                if resp.status_code == 404:
                    return SendResult(success=False, error=f"Image URL not found (404): {image_url}")
                if resp.status_code >= 400:
                    return SendResult(success=False, error=f"Image URL returned HTTP {resp.status_code}: {image_url}")
                
                content_type = resp.headers.get("content-type", "")
                if content_type and not content_type.startswith("image/"):
                    return SendResult(success=False, error=f"URL returned non-image content ({content_type}): {image_url}")
                
                image_bytes = resp.content
            
            fd, temp_path = tempfile.mkstemp(suffix='.jpg', prefix='lansenger_image_')
            os.write(fd, image_bytes)
            os.close(fd)
            
            return await self.send_file(chat_id, temp_path, caption or "", media_type=2)
        except Exception as e:
            logger.error("[Lansenger] Send image error: %s", e)
            return SendResult(success=False, error=str(e))
        finally:
            if temp_path:
                try:
                    os.unlink(temp_path)
                except Exception:
                    pass

    async def send_document(self, chat_id: str, file_path: str, caption: Optional[str] = None, **kwargs) -> SendResult:
        """Send a document file.
        
        Note: Falls back to send_file with media_type=3 (file).
        """
        return await self.send_file(chat_id, file_path, caption or "", media_type=3)

    async def send_video(self, chat_id: str, video_path: str, caption: Optional[str] = None, **kwargs) -> SendResult:
        """Send a video file natively via the platform API.

        Uses send_file with media_type=1 (video).
        """
        return await self.send_file(chat_id, video_path, caption or "", media_type=1)

    async def send_voice(self, chat_id: str, audio_path: str, metadata: Optional[Dict[str, Any]] = None, **kwargs) -> SendResult:
        """Send a voice/audio file.

        Uses send_file with media_type=3 (file) as voice messages
        need a specific format not guaranteed here.
        """
        return await self.send_file(chat_id, audio_path, "", media_type=3)

    async def revoke_message(
        self, 
        message_ids: List[str], 
        chat_id: str = "",
    ) -> SendResult:
        """Revoke previously sent messages.

        Auto-detects chat_type based on chat_id:
        - chat_id == owner_id → "bot" (private chat)
        - otherwise → "group"

        Note: Lansenger displays a fixed system message after revocation.
              Custom sysMsg content/icon is NOT supported. sender_id is not
              required — the API revokes the bot's own messages.
        """
        chat_type = "group" if (chat_id and self._is_group_chat(chat_id)) else "bot"

        token = await self._get_app_token()
        if not token:
            return SendResult(success=False, error="Failed to get token")
        
        try:
            url = f"{self._api_gateway_url}{API_ENDPOINTS['message']['revoke']}?app_token={token}"
            payload = {"chatType": chat_type, "messageIds": message_ids}
            
            response = await self._http_client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            
            if data.get("errCode") != 0:
                return SendResult(success=False, error=data.get("errMsg", "Unknown error"))
            
            logger.info("[Lansenger] Message(s) revoked: %s (chatType=%s)", message_ids, chat_type)
            return SendResult(success=True, message_id=None, raw_response=data)
        except Exception as e:
            logger.error("[Lansenger] Revoke error: %s", e, exc_info=True)
            return SendResult(success=False, error=str(e), retryable=True)

    async def send_link_card(
        self,
        chat_id: str,
        title: str,
        link: str,
        description: Optional[str] = None,
        icon_link: Optional[str] = None,
        pc_link: Optional[str] = None,
        from_name: Optional[str] = None,
        from_icon_link: Optional[str] = None,
    ) -> SendResult:
        """Send a linkCard card message.

        Routes to /v1/messages/group/create for group chats,
        /v1/bot/messages/create for private chats.

        Args:
            chat_id: Recipient user ID
            title: Card title
            link: Card click-through link
            description: Card description
            icon_link: Card icon image link
            pc_link: PC-side redirect link
            from_name: Source name
            from_icon_link: Source icon image link
        """
        token = await self._get_app_token()
        if not token:
            return SendResult(success=False, error="Failed to get token")

        try:
            is_group = self._is_group_chat(chat_id)

            if is_group:
                url = f"{self._api_gateway_url}{API_ENDPOINTS['smart_bot']['group_message']}?app_token={token}"
            else:
                url = f"{self._api_gateway_url}{API_ENDPOINTS['smart_bot']['private_message']}?app_token={token}"

            link_card_data = {
                "title": title,
                "link": link,
                "description": description or "",
                "iconLink": icon_link or "",
                "pcLink": pc_link or "",
                "fromName": from_name or "",
                "fromIconLink": from_icon_link or "",
            }

            if is_group:
                payload = {
                    "groupId": chat_id,
                    "msgType": "linkCard",
                    "msgData": {"linkCard": link_card_data},
                }
            else:
                payload = {
                    "userIdList": [chat_id],
                    "msgType": "linkCard",
                    "msgData": {"linkCard": link_card_data},
                }

            response = await self._http_client.post(url, json=payload)
            response.raise_for_status()

            if not response.text or len(response.text.strip()) == 0:
                return SendResult(success=False, error="Empty API response", retryable=True)

            data = response.json()

            if data.get("errCode") != 0:
                logger.error("[Lansenger] LinkCard API error: errCode=%s, errMsg=%s",
                             data.get("errCode"), data.get("errMsg"))
                return SendResult(success=False, error=data.get("errMsg", "Unknown error"))

            msg_id = data.get("data", {}).get("msgId")
            logger.info("[Lansenger] LinkCard sent to %s, msgId=%s (group=%s)", chat_id, msg_id, is_group)
            return SendResult(success=True, message_id=msg_id, raw_response=data)
        except Exception as e:
            logger.error("[Lansenger] Send linkCard error: %s", e, exc_info=True)
            return SendResult(success=False, error=str(e), retryable=True)

    async def send_to_owner(self, content: str, format: str = "text") -> SendResult:
        """Send a text message to the bot owner (or home_channel if owner not set).
        
        Args:
            content: Message content
            format: 'text' for plain text, 'formatText' for Markdown
        """
        # Use home_channel as fallback if owner_id not set
        target_id = self._owner_id or self._home_channel_id
        if not target_id:
            return SendResult(success=False, error="Owner ID and home_channel not set")
        if format == "formatText":
            return await self.send_format_text(target_id, content)
        return await self.send_text(target_id, content)

    async def send_exec_approval(
        self, chat_id: str, command: str, session_key: str,
        description: str = "dangerous command",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        """Send an approval card for a dangerous command.

        Tries approveCard first (native buttons + text instructions).
        Falls back to appCard if approveCard is not supported.
        """
        logger.info("[Lansenger] send_exec_approval: chat_id=%s, session=%s", chat_id, session_key[:16])

        # ── Step 1: Try native approveCard ──
        try:
            result = await self._send_approve_card(chat_id, command, description, session_key)
            if result.success:
                return result
            logger.info(
                "[Lansenger] approveCard not supported (%s), falling back to appCard",
                result.error,
            )
        except Exception as exc:
            logger.info(
                "[Lansenger] approveCard failed (%s), falling back to appCard",
                exc,
            )

        # ── Step 2: Fall back to dynamic appCard ──
        return await self._send_appcard_approval(chat_id, command, session_key, description)

    async def send_approve_card(
        self, chat_id: str, head_title: str, body_title: str,
        body_content: str = "", fields: Optional[List[dict]] = None,
        buttons: Optional[List[dict]] = None, expire_time: int = 3600,
        head_status: str = "", head_status_color: str = "#FFB116",
    ) -> SendResult:
        """Send a generic approveCard with buttons.

        approveCard is a native Lansenger card type with clickable buttons.
        Unlike appCard, it uses markdown-formatted body content and supports
        button callbacks via WebSocket events.

        Args:
            chat_id: Recipient user ID or group chat ID.
            head_title: Card header title (max 96 bytes).
            body_title: Card body title.
            body_content: Markdown body text.
            fields: [{key, value}] pairs displayed in the card body.
            buttons: [{text, button_theme, callback_info}] button array.
                     button_theme: 1=primary(blue), 2=secondary(white/blue),
                     3=secondary(white/black), 4=danger(red).
                     callback_info: arbitrary string passed back via WebSocket.
            expire_time: Card expiry in seconds (default 3600).
            head_status: Status description shown in card header (max 30 bytes).
            head_status_color: Hex color for status badge (default #FFB116).
        """
        token = await self._get_app_token()
        if not token:
            return SendResult(success=False, error="No access token")

        is_group = self._is_group_chat(chat_id)

        approve_card_data: Dict[str, Any] = {
            "head": {
                "title": head_title[:96],
            },
            "body": {
                "title": body_title,
                "content": {
                    "formatType": 1,  # MARK_DOWN
                    "text": body_content,
                },
            },
            "buttons": buttons or [],
            "expireTime": expire_time,
        }

        if head_status:
            approve_card_data["head"]["headStatus"] = {
                "describe": head_status[:30],
                "statusIcon": 1,
                "colour": head_status_color,
            }

        if fields:
            approve_card_data["body"]["fields"] = fields[:10]

        if is_group:
            payload = {
                "groupId": chat_id,
                "msgType": "approveCard",
                "msgData": {"approveCard": approve_card_data},
            }
            url = f"{self._api_gateway_url}{API_ENDPOINTS['smart_bot']['group_message']}?app_token={token}"
        else:
            payload = {
                "userIdList": [chat_id],
                "msgType": "approveCard",
                "msgData": {"approveCard": approve_card_data},
            }
            url = f"{self._api_gateway_url}{API_ENDPOINTS['smart_bot']['private_message']}?app_token={token}"

        logger.info(
            "[Lansenger] Sending generic approveCard (group=%s): %s",
            is_group, json.dumps(payload, ensure_ascii=False)[:500],
        )

        try:
            response = await self._http_client.post(url, json=payload)
            response.raise_for_status()

            if not response.text or len(response.text.strip()) == 0:
                return SendResult(success=False, error="Empty API response")

            data = response.json()
            err_code = data.get("errCode", -1)
            if err_code != 0:
                logger.warning(
                    "[Lansenger] approveCard API error: errCode=%s, errMsg=%s",
                    err_code, data.get("errMsg", ""),
                )
                return SendResult(success=False, error=data.get("errMsg", f"errCode={err_code}"))

            msg_id = data.get("data", {}).get("msgId")
            if msg_id:
                self._card_type_map[msg_id] = "approveCard"
                logger.info("[Lansenger] ✅ approveCard sent — msg_id=%s", msg_id)
                return SendResult(success=True, message_id=msg_id, raw_response=data)
            else:
                return SendResult(success=False, error="No msgId in response")

        except httpx.HTTPStatusError as exc:
            logger.warning("[Lansenger] approveCard HTTP %s: %s", exc.response.status_code, exc)
            return SendResult(success=False, error=f"HTTP {exc.response.status_code}")
        except Exception as exc:
            logger.warning("[Lansenger] approveCard send error: %s", exc)
            return SendResult(success=False, error=str(exc))

    # ── approveCard (Phase 1 — button-observation) ────────────────────────

    async def _send_approve_card(
        self, chat_id: str, command: str, description: str, session_key: str,
    ) -> SendResult:
        """Send a native Lansenger approveCard with clickable buttons.

        Encodes ``ea:{choice}:{approval_id}`` in each button's ``callbackInfo``
        field so Phase 2 can resolve the approval when button-callback data
        arrives via WebSocket.
        """
        token = await self._get_app_token()
        if not token:
            return SendResult(success=False, error="No access token")

        lang = self._get_lang(chat_id)
        approval_id = str(next(self._approval_counter))
        cmd_preview = command[:500] + "..." if len(command) > 500 else command

        if lang == "zh":
            head_title = "⚠️ 危险命令审批"
            body_title = "以下命令需要审批才能执行"
            body_text = (
                f"**命令:**\n```\n{cmd_preview}\n```\n\n"
                "**审批方式:** 点击下方按钮或回复以下命令:\n"
                "- `/approve` — 批准执行一次\n"
                "- `/approve session` — 本次会话有效\n"
                "- `/approve always` — 永久允许\n"
                "- `/deny` — 拒绝执行"
            )
            status_desc = "待审批"
            fields = [
                {"key": "风险说明", "value": description},
                {"key": "会话 ID", "value": session_key[:32]},
            ]
            btn_once = "批准一次"
            btn_session = "本会话有效"
            btn_always = "永久允许"
            btn_deny = "拒绝"
        else:
            head_title = "⚠️ Command Approval"
            body_title = "Dangerous Command Approval Request"
            body_text = (
                f"**Command:**\n```\n{cmd_preview}\n```\n\n"
                "**How to approve:** Click a button below or reply:\n"
                "- `/approve` — Execute once\n"
                "- `/approve session` — Allow this session\n"
                "- `/approve always` — Always allow\n"
                "- `/deny` — Deny"
            )
            status_desc = "Pending"
            fields = [
                {"key": "Reason", "value": description},
                {"key": "Session ID", "value": session_key[:32]},
            ]
            btn_once = "Allow Once"
            btn_session = "This Session"
            btn_always = "Always"
            btn_deny = "Deny"

        # Compute allowed approvers for group chats
        is_group = self._is_group_chat(chat_id)
        allowed_approvers: Optional[list] = None
        if is_group:
            allowed_approvers = []
            if self._owner_id:
                allowed_approvers.append(self._owner_id)
            for uid in self._approval_allow_from:
                if uid not in allowed_approvers:
                    allowed_approvers.append(uid)

        approve_card_data = {
            "head": {
                "title": head_title,
                "headStatus": {
                    "describe": status_desc,
                    "statusIcon": 1,
                    "colour": "#FFB116",
                },
            },
            "body": {
                "title": body_title,
                "content": {
                    "formatType": 1,  # MARK_DOWN
                    "text": body_text,
                },
                "fields": fields,
            },
            "buttons": [
                {
                    "text": btn_once,
                    "buttonTheme": 1,  # 主按钮 (蓝底白字)
                    "state": 0,
                    "callbackInfo": f"ea:once:{approval_id}",
                    **({"permissionScope": {"permittedStaffs": allowed_approvers}, "prohibitedState": 1} if allowed_approvers else {}),
                },
                {
                    "text": btn_session,
                    "buttonTheme": 2,  # 次按钮 (白底蓝字)
                    "state": 0,
                    "callbackInfo": f"ea:session:{approval_id}:{session_key}",
                    **({"permissionScope": {"permittedStaffs": allowed_approvers}, "prohibitedState": 1} if allowed_approvers else {}),
                },
                {
                    "text": btn_always,
                    "buttonTheme": 3,  # 次按钮 (白底黑字)
                    "state": 0,
                    "callbackInfo": f"ea:always:{approval_id}:{session_key}",
                    **({"permissionScope": {"permittedStaffs": allowed_approvers}, "prohibitedState": 1} if allowed_approvers else {}),
                },
                {
                    "text": btn_deny,
                    "buttonTheme": 4,  # 警告按钮 (红色)
                    "state": 0,
                    "callbackInfo": f"ea:deny:{approval_id}",
                    **({"permissionScope": {"permittedStaffs": allowed_approvers}, "prohibitedState": 1} if allowed_approvers else {}),
                },
            ],
            "expireTime": self._gateway_approval_timeout + 60,  # align with Hermes core gateway_timeout + 60s buffer
        }

        if is_group:
            payload = {
                "groupId": chat_id,
                "msgType": "approveCard",
                "msgData": {"approveCard": approve_card_data},
            }
            url = f"{self._api_gateway_url}{API_ENDPOINTS['smart_bot']['group_message']}?app_token={token}"
        else:
            payload = {
                "userIdList": [chat_id],
                "msgType": "approveCard",
                "msgData": {"approveCard": approve_card_data},
            }
            url = f"{self._api_gateway_url}{API_ENDPOINTS['smart_bot']['private_message']}?app_token={token}"

        logger.info(
            "[Lansenger] Sending approveCard (approval_id=%s, group=%s, expireTime=%ss): %s",
            approval_id, is_group, approve_card_data.get("expireTime"),
            json.dumps(payload, ensure_ascii=False)[:800],
        )

        try:
            response = await self._http_client.post(url, json=payload)
            response.raise_for_status()

            if not response.text or len(response.text.strip()) == 0:
                return SendResult(success=False, error="Empty API response")

            data = response.json()
            err_code = data.get("errCode", -1)
            if err_code != 0:
                logger.warning(
                    "[Lansenger] approveCard API error: errCode=%s, errMsg=%s",
                    err_code, data.get("errMsg", ""),
                )
                return SendResult(success=False, error=data.get("errMsg", f"errCode={err_code}"))

            msg_id = data.get("data", {}).get("msgId")
            if msg_id:
                # Store for Phase 2 callback handling
                self._approval_state[approval_id] = session_key
                self._card_type_map[msg_id] = "approveCard"  # track for dynamic update
                # Extract trigger_sender_id from session_key for permission check
                # session_key format: agent:main:lansenger:group:{chat_id}:{sender_id} or
                #                      agent:main:lansenger:dm:{chat_id}
                trigger_sender_id = self._extract_trigger_sender_from_session(session_key)
                self._pending_approval_msgs[session_key] = (msg_id, trigger_sender_id)
                # Store by approval_id for precise button-callback matching
                self._approval_card_msgs[approval_id] = (msg_id, chat_id)
                self._save_approvals()
                logger.info(
                    "[Lansenger] ✅ approveCard sent — approval_id=%s, msg_id=%s, trigger_sender=%s. "
                    "Buttons: once/session/deny. Waiting for callback via WebSocket...",
                    approval_id, msg_id, trigger_sender_id[:16] if trigger_sender_id else "N/A",
                )
                return SendResult(success=True, message_id=msg_id, raw_response=data)
            else:
                return SendResult(success=False, error="No msgId in response")

        except httpx.HTTPStatusError as exc:
            logger.warning(
                "[Lansenger] approveCard HTTP %s: %s", exc.response.status_code, exc,
            )
            return SendResult(success=False, error=f"HTTP {exc.response.status_code}")
        except Exception as exc:
            logger.warning("[Lansenger] approveCard send error: %s", exc)
            return SendResult(success=False, error=str(exc))

    # ── approveCard button callback handler ────────────────────────────

    async def _handle_approve_card_callback(self, event_data: Dict[str, Any]) -> None:
        """Process ``approve_card_callback`` events from approveCard button clicks.

        Event format::

            {
              "type": "approve_card_callback",
              "data": {
                "eventData": "ea:once:2",
                "staffId": "13107200-K2uBlTReymO6C27owEgC7kJkdIngvlk",
              }
            }

        ``eventData`` is the ``callbackInfo`` from the clicked button:
        ``ea:{choice}:{approval_id}`` or ``ea:{choice}:{approval_id}:{session_key}``.
        """
        callback_data = event_data.get("data", {})
        if not isinstance(callback_data, dict):
            return

        raw_event_data = callback_data.get("eventData", "")
        if not raw_event_data or not raw_event_data.startswith("ea:"):
            logger.warning("[Lansenger] approve_card_callback with unexpected eventData: %s", raw_event_data)
            return

        staff_id = callback_data.get("staffId", "")
        if not staff_id:
            logger.warning("[Lansenger] approve_card_callback missing staffId")
            return

        # Parse ea:{choice}:{approval_id}[:{session_key}]
        parts = raw_event_data.split(":", 1)  # ["ea", "choice:id[:session_key]"]
        if len(parts) < 2:
            return
        suffix = parts[1]  # e.g. "once:2" or "session:2:agent:main:lansenger:dm:..."

        # Split into choice, approval_id, and optional session_key
        colon_idx1 = suffix.find(":")
        if colon_idx1 == -1:
            return
        choice = suffix[:colon_idx1]
        remainder = suffix[colon_idx1 + 1:]

        colon_idx2 = remainder.find(":")
        if colon_idx2 == -1:
            # No session_key in callbackInfo (once/deny): remainder is just approval_id
            approval_id = remainder
            session_key: Optional[str] = None
        else:
            # session_key present (session/always): remainder = "approval_id:session_key"
            approval_id = remainder[:colon_idx2]
            session_key = remainder[colon_idx2 + 1:]

        logger.info(
            "[Lansenger] 🎯 approve_card_callback: choice=%s approval_id=%s staff=%s session=%s",
            choice, approval_id, staff_id[:16], (session_key or "N/A")[:60],
        )

        # Permission check
        if not self._check_approval_permission(staff_id):
            logger.warning(
                "[Lansenger] approve_card_callback permission DENIED: staff=%s",
                staff_id[:16],
            )
            return

        # Look up session_key if not embedded in callbackInfo
        if not session_key:
            session_key = self._approval_state.get(approval_id)
            if not session_key:
                logger.warning(
                    "[Lansenger] approve_card_callback: unknown approval_id=%s (no session_key in _approval_state)",
                    approval_id,
                )
                return

        # ── Resolve approval via Hermes core ──
        try:
            from tools.approval import resolve_gateway_approval
            resolve_gateway_approval(session_key, choice)
        except Exception:
            logger.exception(
                "[Lansenger] Failed to resolve gateway approval for session=%s choice=%s",
                session_key[:60], choice,
            )
            return

        # ── Update the approval card UI (using approval_id for precise match) ──
        card_info = self._approval_card_msgs.get(approval_id)
        if card_info:
            msg_id, chat_id = card_info
            self._approval_card_msgs.pop(approval_id, None)
            # Also clean up the session_key mapping
            self._pending_approval_msgs.pop(session_key, None)
            status = "denied" if choice == "deny" else "approved"
            logger.info(
                "[Lansenger] Updating approval card after button click: msg_id=%s chat=%s choice=%s status=%s",
                msg_id, chat_id[:20], choice, status,
            )
            result = await self.update_approval_status(chat_id, msg_id, status, choice)
            if result.success:
                self._save_approvals()
                logger.info("[Lansenger] Approval card updated: msg_id=%s", msg_id)
            else:
                logger.warning("[Lansenger] Failed to update approval card after button click: %s", result.error)

        logger.info(
            "[Lansenger] ✅ approve_card_callback resolved: choice=%s session=%s",
            choice, session_key[:60],
        )

    # ── Post-approval card updater ──────────────────────────────────────

    async def _maybe_update_approval_card(
        self, chat_id: str, sender_id: str, text: str, is_group: bool,
    ) -> None:
        """Update the approval card if *text* is an /approve or /deny command.

        Hermes resolves the approval internally in its slash command handler,
        but never notifies the adapter to update the card.  This hook fills
        that gap by checking if a pending approval card exists for this chat.

        Permission check: only owner_id or users in approval_allow_from can approve.
        """
        if not text.startswith("/"):
            return
        cmd = text.split()[0].lower().lstrip("/")
        if cmd not in ("approve", "deny"):
            return

        # Parse the approval variant from the suffix
        # /approve           → once
        # /approve session   → session
        # /approve always    → always
        # /deny              → deny
        if cmd == "deny":
            choice = "deny"
        else:
            suffix = text[len("/approve"):].strip().lower()
            if suffix in ("always", "permanent", "permanently"):
                choice = "always"
            elif suffix in ("session", "ses"):
                choice = "session"
            else:
                choice = "once"

        # Reconstruct session_key matching Hermes's build_session_key() format
        chat_type = "group" if is_group else "dm"
        if is_group:
            session_key = f"agent:main:lansenger:{chat_type}:{chat_id}:{sender_id}"
        else:
            session_key = f"agent:main:lansenger:{chat_type}:{chat_id}"

        pending = self._pending_approval_msgs.get(session_key)
        if not pending:
            logger.debug(
                "[Lansenger] No pending approval msg for session=%s (cmd=%s) — skipping card update",
                session_key[:60], cmd,
            )
            return

        msg_id, trigger_sender_id = pending

        # ── Permission check ──
        # Only owner_id or users in approval_allow_from can approve
        if not self._check_approval_permission(sender_id):
            logger.warning(
                "[Lansenger] Approval permission denied: sender=%s is not owner (%s) or in allowlist",
                sender_id[:16], self._owner_id[:16] if self._owner_id else "N/A",
            )
            # Send a brief rejection message
            lang = self._get_lang(chat_id)
            if lang == "zh":
                reject_msg = "⚠️ 您没有审批权限，只有机器人主人或配置的审批者可以审批命令。"
            else:
                reject_msg = "⚠️ You don't have approval permission. Only the bot owner or configured approvers can approve commands."
            await self.send_text(chat_id, reject_msg)
            return

        logger.info(
            "[Lansenger] Updating approval card after /%s (choice=%s): msg_id=%s, session=%s, approver=%s",
            cmd, choice, msg_id, session_key[:60], sender_id[:16],
        )
        result = await self.update_approval_status(chat_id, msg_id, "approved" if cmd == "approve" else "denied", choice)
        if result.success:
            self._pending_approval_msgs.pop(session_key, None)
            # Also clean up approval_card_msgs (find by msg_id)
            for aid, (cid_msg_id, _) in list(self._approval_card_msgs.items()):
                if cid_msg_id == msg_id:
                    self._approval_card_msgs.pop(aid, None)
            self._save_approvals()
        else:
            logger.warning(
                "[Lansenger] Failed to update approval card: %s", result.error,
            )

    # ── appCard fallback (text-based /approve) ────────────────────────────

    async def _send_appcard_approval(
        self, chat_id: str, command: str, session_key: str, description: str,
    ) -> SendResult:
        """Send a dynamic appCard approval card with isDynamic=True.

        NOTE: This uses appCard (not i18nAppCard).  appCard supports
        isDynamic + headStatusInfo for in-place status updates, but does
        NOT support multi-language (i18n).  i18nAppCard supports 5
        languages but cannot be dynamically updated and has no
        headStatusInfo — it is reserved for future use.

        Uses the user's cached language preference (from inbound messages)
        to select card content language.  Default: Chinese.

        After the user replies /approve, /approve session, /approve always,
        or /deny, the gateway intercepts those text replies and calls
        update_approval_status(), which uses the dynamic update API to
        change the card status in-place (待审批 → 已批准/已拒绝).
        """

        lang = self._get_lang(chat_id)
        cmd_preview = command[:300] + "..." if len(command) > 300 else command

        # --- Build appCard content in the user's language ---
        if lang == "zh":
            head_title = "⚠️ 危险命令审批"
            body_title = f"确认 {cmd_preview[:20]}"
            body_sub_title = description
            body_content = f"会话 ID: {session_key[:32]}\n命令:\n{cmd_preview}"
            status_desc = "待审批"
            signature = self._get_agent_signature("zh")
            fields = [
                {"key": "执行一次", "value": "/approve"},
                {"key": "本会话有效", "value": "/approve session"},
                {"key": "永久允许", "value": "/approve always"},
                {"key": "拒绝执行", "value": "/deny"},
            ]
        else:
            head_title = "⚠️ Command Approval"
            body_title = "Dangerous Command Approval Request"
            body_sub_title = description
            body_content = f"Session ID: {session_key[:32]}\nCommand:\n{cmd_preview}"
            status_desc = "Pending"
            signature = self._get_agent_signature("en")
            fields = [
                {"key": "Execute Once", "value": "/approve"},
                {"key": "This Session", "value": "/approve session"},
                {"key": "Always Allow", "value": "/approve always"},
                {"key": "Deny", "value": "/deny"},
            ]

        # Escape HTML in dynamic content to prevent accidental div parsing
        body_content = self._escape_html(body_content)
        body_sub_title = self._escape_html(body_sub_title)

        # Dynamic card: head status info shows "待审批" (amber)
        head_status_info = {
            "description": self._build_status_div(status_desc, "#FFB116"),
            "colour": "#FFB116",
        }

        try:
            url = self._build_send_url(chat_id, token)
            app_card_data = {
                "headTitle": head_title,
                "headIconUrl": "",
                "isDynamic": True,
                "headStatusInfo": head_status_info,
                "bodyTitle": f'<div style="color:#000;font-size:15pt;text-align:left">{body_title}</div>',
                "bodySubTitle": f'<div style="color:rgba(0,0,0,.47);font-size:13pt;text-align:left">{body_sub_title}</div>',
                "bodyContent": f'<div style="color:#000;font-size:13pt;text-align:left;text-indent:0em">{body_content}</div>',
                "signature": f'<div style="color:rgba(0,0,0,.47)">{signature}</div>',
                "fields": fields,
                "cardLink": "",
                "pcCardLink": "",
            }

            payload = self._build_app_card_payload(chat_id, app_card_data)

            response = await self._http_client.post(url, json=payload)
            response.raise_for_status()

            if not response.text or len(response.text.strip()) == 0:
                return SendResult(success=False, error="Empty API response", retryable=True)

            data = response.json()
            if data.get("errCode") != 0:
                return SendResult(success=False, error=data.get("errMsg"))

            msg_id = data.get("data", {}).get("msgId")
            self._card_type_map[msg_id] = "appCard"
            # Extract trigger_sender_id from session_key for permission check
            trigger_sender_id = self._extract_trigger_sender_from_session(session_key)
            self._pending_approval_msgs[session_key] = (msg_id, trigger_sender_id)
            logger.info("[Lansenger] appCard approval sent to %s, msgId=%s, trigger_sender=%s, lang=%s", chat_id, msg_id, trigger_sender_id[:16] if trigger_sender_id else "N/A", lang)
            return SendResult(success=True, message_id=msg_id, raw_response=data)

        except Exception as e:
            logger.error("[Lansenger] Send appCard approval error: %s", e)
            return SendResult(success=False, error=str(e), retryable=True)

    def _build_app_card_payload(self, chat_id: str, app_card_data: Dict[str, Any]) -> Dict[str, Any]:
        """Build the outer payload for an appCard message with correct routing."""
        is_group = self._is_group_chat(chat_id)
        if is_group:
            return {
                "groupId": chat_id,
                "msgType": "appCard",
                "msgData": {"appCard": app_card_data},
            }
        return {
            "userIdList": [chat_id],
            "msgType": "appCard",
            "msgData": {"appCard": app_card_data},
        }

    def _build_send_url(self, chat_id: str, token: str) -> str:
        """Build the correct endpoint URL based on chat type."""
        is_group = self._is_group_chat(chat_id)
        if is_group:
            return f"{self._api_gateway_url}{API_ENDPOINTS['smart_bot']['group_message']}?app_token={token}"
        return f"{self._api_gateway_url}{API_ENDPOINTS['smart_bot']['private_message']}?app_token={token}"
    async def send_slash_confirm(
        self,
        chat_id: str,
        title: str,
        message: str,
        session_key: str,
        confirm_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        """Send a dynamic appCard slash-command confirmation card.

        NOTE: This uses appCard (not i18nAppCard).  See send_exec_approval
        docstring for the appCard vs i18nAppCard distinction.

        Uses the user's cached language preference to select content language.

        Used by the gateway's ``_maybe_confirm_destructive_slash`` gate for
        /new, /reset, /undo.  Lansenger does not support inline button
        callbacks like Telegram, so this card displays the confirmation
        request with fields showing the text-based reply options
        (/approve, /always, /cancel).

        The gateway's text intercept recognises /approve, /always, /cancel
        and routes them through ``slash_confirm.resolve()``.

        Returns SendResult(success=True) so the gateway skips the
        redundant text fallback.
        """
        logger.info("[Lansenger] send_slash_confirm: chat_id=%s, title=%s, confirm_id=%s", chat_id, title, confirm_id)
        token = await self._get_app_token()
        if not token:
            return SendResult(success=False, error="No access token")

        lang = self._get_lang(chat_id)
        command_name = title.strip() if title else "unknown"

        if lang == "zh":
            head_title = f"🔄 {command_name} 确认"
            body_title = "会话操作确认请求"
            body_content = self._escape_html(message or "此操作将修改当前会话。")
            status_desc = "待确认"
            signature = self._get_agent_signature("zh")
            fields = [
                {"key": "确认执行", "value": "/approve"},
                {"key": "本会话免确认", "value": "/always"},
                {"key": "取消", "value": "/cancel"},
            ]
        else:
            head_title = f"🔄 {command_name} Confirm"
            body_title = "Session Action Confirmation"
            body_content = self._escape_html(message or "This action will modify your current session.")
            status_desc = "Pending"
            signature = self._get_agent_signature("en")
            fields = [
                {"key": "Approve Once", "value": "/approve"},
                {"key": "Always This Session", "value": "/always"},
                {"key": "Cancel", "value": "/cancel"},
            ]

        head_status_info = {
            "description": self._build_status_div(status_desc, "#FFB116"),
            "colour": "#FFB116",
        }

        try:
            url = self._build_send_url(chat_id, token)
            app_card_data = {
                "headTitle": head_title,
                "headIconUrl": "",
                "isDynamic": True,
                "headStatusInfo": head_status_info,
                "bodyTitle": f'<div style="color:#000;font-size:15pt;text-align:left">{body_title}</div>',
                "bodyContent": f'<div style="color:#000;font-size:13pt;text-align:left;text-indent:0em">{body_content}</div>',
                "signature": f'<div style="color:rgba(0,0,0,.47)">{signature}</div>',
                "fields": fields,
                "cardLink": "",
                "pcCardLink": "",
            }

            payload = self._build_app_card_payload(chat_id, app_card_data)

            response = await self._http_client.post(url, json=payload)
            response.raise_for_status()

            if not response.text or len(response.text.strip()) == 0:
                return SendResult(success=False, error="Empty API response", retryable=True)

            data = response.json()
            if data.get("errCode") != 0:
                logger.error("[Lansenger] Slash confirm card API error: errCode=%s, errMsg=%s", data.get("errCode"), data.get("errMsg"))
                return SendResult(success=False, error=data.get("errMsg"))

            msg_id = data.get("data", {}).get("msgId")
            logger.info("[Lansenger] Slash confirm appCard sent to %s, msgId=%s", chat_id, msg_id)
            return SendResult(success=True, message_id=msg_id, raw_response=data)

        except Exception as e:
            logger.error("[Lansenger] Send slash confirm appCard error: %s", e)
            return SendResult(success=False, error=str(e), retryable=True)

    async def update_approval_status(
        self, chat_id: str, message_id: str,
        status: str, choice: str = "",
        card_type: str = "",
    ) -> SendResult:
        """Update a dynamic approval card status in-place.

        Supports both approveCard (via ``approveCardUpdateMsg``) and
        appCard (via ``appCardUpdateMsg``).  Card type is auto-detected
        from the internal ``_card_type_map``; defaults to appCard mode
        for backwards compatibility.  Pass ``card_type`` explicitly
        to override auto-detection (e.g. ``"approveCard"``).

        When *choice* is provided (``once``/``session``/``always``/``deny``),
        the card's buttons are replaced with a single greyed-out button
        showing the chosen action (e.g. "已允许执行一次" / "已拒绝执行").

        Args:
            chat_id: Recipient user ID (used to determine language)
            message_id: The message ID of the original card to update
            status: One of 'pending', 'approved', 'denied'
            choice: Optional — 'once', 'session', 'always', 'deny'
        """
        token = await self._get_app_token()
        if not token:
            return SendResult(success=False, error="No access token")

        card_type = card_type or self._card_type_map.get(message_id, "appCard")
        lang = self._get_lang(chat_id)

        try:
            url = f"{self._api_gateway_url}{API_ENDPOINTS['message']['dynamic_update']}?app_token={token}"

            # Status label (short, fits in header)
            if lang == "zh":
                status_text = {"pending": "待审批", "approved": "已批准", "denied": "已拒绝"}.get(status, "待审批")
            else:
                status_text = {"pending": "Pending", "approved": "Approved", "denied": "Denied"}.get(status, "Pending")
            status_color = {"pending": "#FFB116", "approved": "#198754", "denied": "#dc3545"}.get(status, "#FFB116")
            is_final = status != "pending"

            if card_type == "approveCard":
                # Build language-specific result button text
                choice_labels: Dict[str, Dict[str, str]] = {
                    "once":    {"zh": "已允许执行一次", "en": "Allowed once"},
                    "session": {"zh": "已允许本会话有效", "en": "Allowed this session"},
                    "always":  {"zh": "已永久允许", "en": "Allowed permanently"},
                    "deny":    {"zh": "已拒绝执行", "en": "Denied"},
                }
                buttons = []
                if choice and is_final:
                    label = choice_labels.get(choice, {}).get(lang, choice_labels.get(choice, {}).get("en", choice))
                    buttons = [{
                        "text": label,
                        "buttonTheme": 3,  # 次按钮 (白底黑字)
                        "state": 1,        # 禁用
                    }]

                payload = {
                    "msgId": message_id,
                    "msgType": "approveCard",
                    "msgData": {
                        "approveCardUpdateMsg": {
                            "headStatus": {
                                "describe": status_text,
                                "statusIcon": 1,
                                "colour": status_color,
                            },
                            "buttons": buttons,
                        }
                    }
                }
            else:
                # appCardUpdateMsg — dynamic update for appCard (legacy)
                payload = {
                    "msgId": message_id,
                    "msgType": "appCard",
                    "msgData": {
                        "appCardUpdateMsg": {
                            "isLastUpdate": is_final,
                            "headStatusInfo": {
                                "description": self._build_status_div(status_text, status_color),
                                "colour": status_color,
                            },
                        }
                    }
                }

            response = await self._http_client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()

            if data.get("errCode") != 0:
                logger.warning(
                    "[Lansenger] Update card status failed (type=%s): errCode=%s, errMsg=%s",
                    card_type, data.get("errCode"), data.get("errMsg"),
                )
                return SendResult(success=False, error=data.get("errMsg"))

            logger.info(
                "[Lansenger] Card status updated to %s (type=%s, lang=%s, choice=%s)",
                status, card_type, lang, choice or "-",
            )
            return SendResult(success=True, raw_response=data)

        except Exception as e:
            logger.error("[Lansenger] Update appCard status error: %s", e)
            return SendResult(success=False, error=str(e), retryable=True)

    # ------------------------------------------------------------------
    # Update prompt (gateway /update watcher)
    # ------------------------------------------------------------------
    async def send_update_prompt(
        self,
        chat_id: str,
        prompt: str,
        default: str = "",
        session_key: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        """Send a dynamic appCard update prompt with /approve /deny reply hints.

        NOTE: This uses appCard (not i18nAppCard).  See send_exec_approval
        docstring for the appCard vs i18nAppCard distinction.

        Uses the user's cached language preference to select content language.

        Used by the gateway's ``/update`` watcher when ``hermes update --gateway``
        needs user input (stash restore, config migration).  Lansenger does not
        support inline button callbacks like Telegram/Discord, so this card
        displays the prompt text with fields showing the text-based reply
        options (/approve → yes, /deny → no).

        The gateway's text intercept recognises /approve, /yes → "y" and
        /deny, /no → "n" and routes them through ``update_prompt.resolve()``.

        Returns SendResult(success=True) so the gateway skips the
        redundant text fallback.
        """
        logger.info(
            "[Lansenger] send_update_prompt: chat_id=%s, prompt=%s, default=%s",
            chat_id, prompt[:80], default,
        )
        token = await self._get_app_token()
        if not token:
            return SendResult(success=False, error="No access token")

        lang = self._get_lang(chat_id)
        prompt_text = prompt or "Update needs your input."
        default_hint = f" (default: {default})" if default else ""
        escaped_prompt = self._escape_html(prompt_text)

        if lang == "zh":
            head_title = "⚕ 更新确认"
            body_title = "更新需要您的输入"
            body_content = f"{escaped_prompt}{default_hint}"
            status_desc = "待确认"
            signature = self._get_agent_signature("zh")
            fields = [
                {"key": "确认执行", "value": "/approve"},
                {"key": "拒绝执行", "value": "/deny"},
            ]
        else:
            head_title = "⚕ Update Confirmation"
            body_title = "Update Needs Your Input"
            body_content = f"{escaped_prompt}{default_hint}"
            status_desc = "Pending"
            signature = self._get_agent_signature("en")
            fields = [
                {"key": "Approve (Yes)", "value": "/approve"},
                {"key": "Deny (No)", "value": "/deny"},
            ]

        head_status_info = {
            "description": self._build_status_div(status_desc, "#FFB116"),
            "colour": "#FFB116",
        }

        try:
            url = self._build_send_url(chat_id, token)
            app_card_data = {
                "headTitle": head_title,
                "headIconUrl": "",
                "isDynamic": True,
                "headStatusInfo": head_status_info,
                "bodyTitle": f'<div style="color:#000;font-size:15pt;text-align:left">{body_title}</div>',
                "bodyContent": f'<div style="color:#000;font-size:13pt;text-align:left;text-indent:0em">{body_content}</div>',
                "signature": f'<div style="color:rgba(0,0,0,.47)">{signature}</div>',
                "fields": fields,
                "cardLink": "",
                "pcCardLink": "",
            }

            payload = self._build_app_card_payload(chat_id, app_card_data)

            response = await self._http_client.post(url, json=payload)
            response.raise_for_status()

            if not response.text or len(response.text.strip()) == 0:
                return SendResult(success=False, error="Empty API response", retryable=True)

            data = response.json()
            if data.get("errCode") != 0:
                logger.error(
                    "[Lansenger] Update prompt appCard API error: errCode=%s, errMsg=%s",
                    data.get("errCode"), data.get("errMsg"),
                )
                return SendResult(success=False, error=data.get("errMsg"))

            msg_id = data.get("data", {}).get("msgId")
            logger.info("[Lansenger] Update prompt appCard sent to %s, msgId=%s", chat_id, msg_id)
            return SendResult(success=True, message_id=msg_id, raw_response=data)

        except Exception as e:
            logger.error("[Lansenger] Send update prompt appCard error: %s", e)
            return SendResult(success=False, error=str(e), retryable=True)

    def _build_agent_signature_i18n(self) -> Dict[str, str]:
        """Build the i18nSignature with the agent name from SOUL.md (dynamic).

        RESERVED for future i18nAppCard use.  Currently not called by
        any active flow — the approval workflow uses appCard with
        language detection instead.

        Falls back to "Hermes" if SOUL.md cannot be read.  The signature
        format is "{agent_name} 安全系统" / "{agent_name} Security System" etc.
        """
        agent_name = self._read_agent_name_from_soul()

        return self._build_i18n_obj_full(
            f"{agent_name} 安全系统",
            f"{agent_name} 安全系統",
            f"{agent_name} 安全系統",
            f"{agent_name} Security",
            f"{agent_name} Sécurité"
        )

    def _read_agent_name_from_soul(self) -> str:
        """Read the agent display name from SOUL.md.

        Looks for the **Name:** field in the YAML frontmatter or markdown
        body of ~/.hermes/SOUL.md.  Returns "Hermes" as fallback.
        """
        try:
            soul_path = self._resolve_hermes_home() / "SOUL.md"
            if not soul_path.exists():
                return "Hermes"

            content = soul_path.read_text(encoding="utf-8")

            # Try YAML frontmatter first (--- ... ---)
            if content.startswith("---"):
                end = content.find("---", 3)
                if end != -1:
                    frontmatter = content[3:end]
                    # Look for "Name:" in frontmatter
                    for line in frontmatter.split("\n"):
                        line = line.strip()
                        if line.startswith("Name:") or line.startswith("name:"):
                            name = line.split(":", 1)[1].strip()
                            if name:
                                return name

            # Try markdown body — look for **Name:** pattern
            match = re.search(r"\*?\*?Name:?\*?\*?\s*:?\s*(.+)", content, re.IGNORECASE)
            if match:
                name = match.group(1).strip()
                # Strip markdown bold/italic markers
                name = name.replace("*", "").strip()
                if name:
                    return name

            return "Hermes"
        except Exception:
            return "Hermes"

    def _build_i18n_obj_full(self, zh_hans: str, zh_hant: str, zh_hant_hk: str, en: str, fr: str) -> Dict[str, str]:
        """Build i18n object with all 5 supported languages.

        RESERVED for future i18nAppCard use.  Currently not called by
        any active flow — the approval workflow uses appCard with
        language detection (single-language per card) instead.
        
        Args:
            zh_hans: Simplified Chinese text
            zh_hant: Traditional Chinese text
            zh_hant_hk: Traditional Chinese (Hong Kong) text
            en: English text
            fr: French text
            
        Returns:
            Dict with language codes as keys
        """
        return {
            "zhHans": zh_hans,
            "zhHant": zh_hant,
            "zhHantHK": zh_hant_hk,
            "en": en,
            "fr": fr
        }
    
    def _escape_html(self, text: str) -> str:
        """Escape <, >, and & to prevent HTML tag parsing.

        Client doesn't support HTML entities like &quot; or &amp;,
        but we need to escape < and > to prevent them from being
        parsed as HTML tags, and & to prevent misinterpretation
        as entity references.
        """
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def _convert_font_px_to_pt(self, text: str) -> str:
        """Convert font-size px values to pt in div-style HTML strings.

        Lansenger enterprise deployment rejects font-size with px unit.
        1px ≈ 0.75pt. Common sizes: 14px→10.5pt, 16px→12pt, 18px→13.5pt.
        Only converts numeric px values; pt values are left unchanged.
        """
        def _px_to_pt(m):
            px_val = float(m.group(1))
            pt_val = px_val * 0.75
            if pt_val == int(pt_val):
                return f"font-size:{int(pt_val)}pt"
            return f"font-size:{pt_val}pt"
        return re.sub(r'font-size:(\d+(?:\.\d+)?)px', _px_to_pt, text)

    def _fix_text_indent(self, text: str) -> str:
        """Fix bare text-indent:0 to text-indent:0em in div-style strings.

        Lansenger API rejects text-indent without a unit (bare '0').
        Per spec, text-indent only applies to bodyContent.
        """
        if not text:
            return text
        return re.sub(r'text-indent:0(?![\d.em])', 'text-indent:0em', text)

    def _fix_app_card_styles(self, field: str, is_body_content: bool = False) -> str:
        """Apply all div-style fixes for appCard fields.

        Per Lansenger API spec:
        - font-size px→pt: applies to headTitle, bodyTitle, bodySubTitle, bodyContent
        - text-indent bare-0→0em: applies only to bodyContent
        """
        field = self._convert_font_px_to_pt(field)
        if is_body_content:
            field = self._fix_text_indent(field)
        return field

    def _detect_lang(self, text: str) -> str:
        """Detect language from user message text. Returns 'zh' or 'en'.

        Any Chinese character → 'zh'. Only pure non-Chinese text → 'en'.
        """
        for ch in text:
            cp = ord(ch)
            # CJK Unified Ideographs + Extension A + Compatibility Ideographs
            if 0x4E00 <= cp <= 0x9FFF or 0x3400 <= cp <= 0x4DBF or 0xF900 <= cp <= 0xFAFF:
                return "zh"
        return "en"

    def _extract_trigger_sender_from_session(self, session_key: str) -> Optional[str]:
        """Extract trigger_sender_id from session_key.

        session_key format:
        - Group: agent:main:lansenger:group:{chat_id}:{sender_id}
        - DM:    agent:main:lansenger:dm:{chat_id}

        Returns sender_id for group sessions, None for DM sessions.
        """
        parts = session_key.split(":")
        # Format: agent:main:lansenger:{chat_type}:{chat_id}:{sender_id?}
        if len(parts) >= 6 and parts[3] == "group":
            return parts[5]  # sender_id
        return None  # DM session has no sender_id in key

    def _check_approval_permission(self, sender_id: str) -> bool:
        """Check if sender_id has permission to approve commands.

        Permission rules:
        1. owner_id always has permission
        2. users in approval_allow_from list have permission
        3. others are denied

        Returns True if sender has permission, False otherwise.
        """
        # Owner always has permission
        if self._owner_id and sender_id == self._owner_id:
            return True
        # Check allowlist
        if sender_id in self._approval_allow_from:
            return True
        return False

    def _get_lang(self, chat_id: str) -> str:
        """Get cached user language for chat_id, defaulting to 'zh'."""
        return self._user_lang_map.get(chat_id, "zh")

    def _get_agent_signature(self, lang: str = "zh") -> str:
        """Build agent signature string in the given language.

        Reads agent name from SOUL.md and formats it for appCard signature field.
        """
        agent_name = self._read_agent_name_from_soul()
        if lang == "zh":
            return f"{agent_name} 安全系统"
        elif lang == "fr":
            return f"{agent_name} Sécurité"
        else:
            return f"{agent_name} Security"

    def _build_status_div(self, text: str, color: str) -> str:
        """Build div-style text for headStatusInfo.description.

        headStatusInfo = dot + text. 'description' is the text portion,
        supports single div-style color tag (must be <30 bytes).
        'colour' controls the dot color — they are independent.
        No nested divs — API rejects nested div structure.
        """
        return f'<div style="color:{color}">{text}</div>'

    @property
    def owner_id(self) -> Optional[str]:
        """Get the bot owner's user ID."""
        return self._owner_id

    # -- Helper methods -----------------------------------------------------

    def get_chat_info(self, chat_id: str) -> Dict[str, Any]:
        """Get chat info (stub - Lansenger API doesn't provide this)."""
        return {"name": chat_id, "type": "unknown", "chat_id": chat_id}


def check_requirements() -> bool:
    """Check if Lansenger dependencies are available."""
    if not WEBSOCKETS_AVAILABLE:
        logger.warning("[Lansenger] websockets not installed. Run: pip install websockets")
        return False
    if not HTTPX_AVAILABLE:
        logger.warning("[Lansenger] httpx not installed. Run: pip install httpx")
        return False
    return True


def validate_config(config) -> bool:
    """Check if Lansenger is properly configured (env vars or config.yaml extra)."""
    extra = getattr(config, "extra", None) or {}
    # Priority: env var > config.yaml extra (matches Hermes convention)
    app_id = os.getenv("LANSENGER_APP_ID") or extra.get("app_id", "")
    app_secret = os.getenv("LANSENGER_APP_SECRET") or extra.get("app_secret", "")
    return bool(app_id and app_secret)


def is_connected(config) -> bool:
    """Check if Lansenger appears to be connected/enabled."""
    return bool(config and getattr(config, "enabled", False))


def _env_enablement() -> Optional[dict]:
    """Seed PlatformConfig.extra from env vars (for env-only setups).

    Called during _apply_env_overrides BEFORE the adapter is constructed,
    so ``hermes gateway status`` can reflect env-only configuration.
    """
    app_id = os.getenv("LANSENGER_APP_ID")
    app_secret = os.getenv("LANSENGER_APP_SECRET")
    if not app_id or not app_secret:
        return None

    extra = {
        "app_id": app_id,
        "app_secret": app_secret,
    }
    api_url = os.getenv("LANSENGER_API_GATEWAY_URL")
    if api_url:
        extra["api_gateway_url"] = api_url

    home_channel = os.getenv("LANSENGER_HOME_CHANNEL")
    if home_channel:
        return {"extra": extra, "home_channel": {"chat_id": home_channel}}
    return {"extra": extra}


async def _standalone_send(pconfig, chat_id, message, *, thread_id=None,
                           media_files=None, force_document=False) -> dict:
    """Out-of-process delivery for cron jobs when the gateway is not running.

    Creates an ephemeral adapter, sends the message, and tears down.
    """
    if not check_requirements() or not validate_config(pconfig):
        return {"error": "Lansenger dependencies or config not available"}

    _IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}
    _VIDEO_EXTS = {'.mp4', '.mov', '.avi', '.mkv', '.webm', '.3gp'}

    media_files = media_files or []

    try:
        adapter = LansengerAdapter(pconfig)
        # Connect just enough to send (get token + HTTP client)
        adapter._http_client = httpx.AsyncClient(timeout=30.0)

        last_result = None
        # Send caption text as formatText (Markdown)
        if message.strip():
            last_result = await adapter.send(chat_id=chat_id, content=message)
            if not last_result.success:
                await adapter._http_client.aclose()
                return {"error": f"Lansenger send failed: {last_result.error}"}

        # Send each media file
        for media_path, is_voice in media_files:
            if not os.path.exists(media_path):
                await adapter._http_client.aclose()
                return {"error": f"Media file not found: {media_path}"}

            ext = os.path.splitext(media_path)[1].lower()
            if ext in _IMAGE_EXTS:
                last_result = await adapter.send_file(chat_id, media_path, caption="", media_type=2)
            elif ext in _VIDEO_EXTS:
                last_result = await adapter.send_file(chat_id, media_path, caption="", media_type=1)
            else:
                last_result = await adapter.send_file(chat_id, media_path, caption="", media_type=3)

            if not last_result.success:
                await adapter._http_client.aclose()
                return {"error": f"Lansenger media send failed: {last_result.error}"}

        await adapter._http_client.aclose()

        if last_result is None:
            return {"error": "No deliverable text or media"}

        return {
            "success": True,
            "platform": "lansenger",
            "chat_id": chat_id,
            "message_id": last_result.message_id,
        }
    except Exception as e:
        return {"error": f"Lansenger standalone send failed: {e}"}


def register(ctx):
    """Plugin entry point: called by the Hermes plugin system."""
    ctx.register_platform(
        name="lansenger",
        label="Lansenger (蓝信)",
        adapter_factory=lambda cfg: LansengerAdapter(cfg),
        check_fn=check_requirements,
        validate_config=validate_config,
        is_connected=is_connected,
        required_env=["LANSENGER_APP_ID", "LANSENGER_APP_SECRET"],
        install_hint="pip install websockets httpx",
        setup_fn=_interactive_setup,
        # Env-driven auto-configuration
        env_enablement_fn=_env_enablement,
        # Cron home-channel delivery support
        cron_deliver_env_var="LANSENGER_HOME_CHANNEL",
        # Out-of-process cron delivery
        standalone_sender_fn=_standalone_send,
        # Auth env vars
        allowed_users_env="LANSENGER_ALLOWED_USERS",
        allow_all_env="LANSENGER_ALLOW_ALL_USERS",
        # Message limit
        max_message_length=4000,
        # Display
        emoji="💠",
        # Lansenger uses opaque user IDs, not phone numbers
        pii_safe=True,
        allow_update_command=True,
        # LLM guidance
        platform_hint=(
            "You are chatting via Lansenger (蓝信), an enterprise messaging platform. "
            "You can send Markdown-formatted text using the "
            "formatText msgType, and send files/images/videos via send_file().  "
            "Messages have a ~4000 character limit.  Dynamic appCard is used for "
            "approval workflows (status updates in-place).  Keep responses concise and professional."
        ),
    )

    # Register hooks for monitoring and observability
    _register_lansenger_hooks(ctx)


def _register_lansenger_hooks(ctx):
    """Register plugin hooks for Lansenger adapter monitoring.
    
    Hook logging can be controlled via:
        1. Environment variable: LANSENGER_HOOK_LOGGING=true/false
        2. config.yaml: platforms.lansenger.extra.hook_logging: true/false
    
    Priority: env var > config > default (true)
    
    Hermes core invoke_hook kwargs per event:
        pre_tool_call:   tool_name, args, task_id, session_id, tool_call_id,
                         turn_id, api_request_id, middleware_trace
        post_tool_call:  tool_name, args, result, task_id, session_id,
                         tool_call_id, turn_id, api_request_id, duration_ms,
                         status, error_type, error_message
        pre_llm_call:    session_id, task_id, turn_id, user_message,
                         conversation_history, is_first_turn, model, platform,
                         sender_id
        pre_gateway_dispatch: event(MessageEvent), gateway(GatewayRunner),
                                session_store

    Note: on_session_start / on_session_end are context engine methods,
    NOT triggered via invoke_hook — do not register them.
    """
    # Check if hook logging is enabled
    # Priority: env var > config > default (true)
    hook_logging_env = os.getenv("LANSENGER_HOOK_LOGGING", "").lower()
    if hook_logging_env:
        hook_logging_enabled = hook_logging_env in ("true", "1", "yes")
    else:
        # Try to read from config.yaml: platforms.lansenger.extra.hook_logging
        try:
            from hermes_constants import get_hermes_home
            import yaml
            config_path = get_hermes_home() / "config.yaml"
            if config_path.exists():
                with open(config_path, encoding="utf-8") as f:
                    cfg = yaml.safe_load(f) or {}
                hook_logging_cfg = cfg.get("platforms", {}).get("lansenger", {}).get("extra", {}).get("hook_logging")
                if hook_logging_cfg is not None:
                    hook_logging_enabled = bool(hook_logging_cfg)
                else:
                    hook_logging_enabled = True  # default
            else:
                hook_logging_enabled = True  # default
        except Exception:
            hook_logging_enabled = True  # default on error

    def _on_pre_llm_call(**kwargs):
        """Log LLM call initiation (fires per turn, useful as session-start indicator)."""
        if not hook_logging_enabled:
            return
        platform = kwargs.get("platform")
        if platform != "lansenger":
            return
        session_id = str(kwargs.get("session_id", ""))[:16]
        sender_id = kwargs.get("sender_id", "")
        model = kwargs.get("model", "")
        is_first_turn = kwargs.get("is_first_turn", False)
        logger.info(
            "[Lansenger Hook] LLM call: platform=%s, session=%s, sender=%s, model=%s, first_turn=%s",
            platform, session_id, sender_id, model, is_first_turn
        )

    def _on_pre_tool_call(**kwargs):
        """Log tool calls before execution for Lansenger sessions."""
        if not hook_logging_enabled:
            return
        platform = kwargs.get("platform")
        if platform != "lansenger":
            return
        tool_name = kwargs.get("tool_name")
        session_id = str(kwargs.get("session_id", ""))[:16]
        logger.info(
            "[Lansenger Hook] Pre tool call: platform=%s, tool=%s, session=%s",
            platform, tool_name, session_id
        )

    def _on_post_tool_call(**kwargs):
        """Log tool execution results for Lansenger sessions."""
        if not hook_logging_enabled:
            return
        platform = kwargs.get("platform")
        if platform != "lansenger":
            return
        tool_name = kwargs.get("tool_name")
        status = kwargs.get("status")
        session_id = str(kwargs.get("session_id", ""))[:16]
        logger.info(
            "[Lansenger Hook] Post tool call: platform=%s, tool=%s, session=%s, status=%s",
            platform, tool_name, session_id, status
        )

    def _on_pre_gateway_dispatch(**kwargs):
        """Log messages before dispatch to Lansenger gateway."""
        if not hook_logging_enabled:
            return
        event = kwargs.get("event")
        if event is None:
            return
        platform = getattr(event, "platform", None)
        if platform != "lansenger":
            return
        chat_id = getattr(event, "chat_id", None)
        message_type = getattr(event, "message_type", "text")
        logger.info(
            "[Lansenger Hook] Pre gateway dispatch: platform=%s, chat_id=%s, type=%s",
            platform, chat_id, message_type
        )

    # Register hooks: callback(event_name, callable)
    ctx.register_hook("pre_llm_call", _on_pre_llm_call)
    ctx.register_hook("pre_tool_call", _on_pre_tool_call)
    ctx.register_hook("post_tool_call", _on_post_tool_call)
    ctx.register_hook("pre_gateway_dispatch", _on_pre_gateway_dispatch)


def _interactive_setup():
    """Interactive setup wizard for Lansenger credentials.
    
    Called by `hermes setup gateway` when the user selects Lansenger.
    Prompts for APP_ID, APP_SECRET, and optional API_GATEWAY_URL,
    then writes them to ~/.hermes/.env (idempotent — won't duplicate).
    """
    from pathlib import Path
    
    hermes_home = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
    env_file = hermes_home / ".env"
    
    # ANSI colors for terminal output
    CYAN = "\033[36m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"
    
    print()
    print(f"  {CYAN}─── 💠 Lansenger (蓝信) Setup ───{RESET}")
    print()
    print(f"  {YELLOW}Where to find your credentials:{RESET}")
    print(f"  Lansenger desktop → Contacts → Smart Bot → Personal Bot → ℹ️ icon")
    print(f"  (Mobile client does not support viewing credentials)")
    print()
    
    # Read existing .env
    existing_lines = []
    existing_values = {}
    if env_file.exists():
        with open(env_file) as f:
            existing_lines = f.readlines()
        for line in existing_lines:
            if "=" in line and not line.startswith("#"):
                key, _, value = line.partition("=")
                existing_values[key.strip()] = value.strip()
    
    def _prompt_field(env_key: str, label: str, default: str = "", sensitive: bool = False) -> Optional[str]:
        """Prompt for a single env var. Returns new value or None if unchanged."""
        current = existing_values.get(env_key, "")
        if current:
            # Mask sensitive values for display
            display = current if not sensitive else (current[:4] + "****" if len(current) > 4 else "****")
            print(f"  {DIM}Current {label}: {display}{RESET}")
            print(f"  {BOLD}New {label}{RESET} [press Enter to keep current]: ", end="", flush=True)
            new_value = input().strip()
            if not new_value:
                print(f"  {GREEN}✓ Keeping current value{RESET}")
                return None  # unchanged
            return new_value
        else:
            print(f"  {BOLD}{label}:{RESET} ", end="", flush=True)
            new_value = input().strip()
            if not new_value:
                if default:
                    return default
                print(f"  {YELLOW}Skipped — you can set it later in ~/.hermes/.env{RESET}")
                return None
            return new_value
    
    # Prompt for credentials
    app_id = _prompt_field("LANSENGER_APP_ID", "App ID")
    app_secret = _prompt_field("LANSENGER_APP_SECRET", "App Secret", sensitive=True)
    gateway_url = _prompt_field("LANSENGER_API_GATEWAY_URL", "API Gateway URL", default="https://open.e.lanxin.cn/open/apigw")
    
    # Build updated .env content — replace existing keys or append new ones
    changes = {}
    if app_id is not None:
        changes["LANSENGER_APP_ID"] = app_id
    if app_secret is not None:
        changes["LANSENGER_APP_SECRET"] = app_secret
    if gateway_url is not None:
        changes["LANSENGER_API_GATEWAY_URL"] = gateway_url
    
    if changes:
        # Rewrite .env: replace changed keys, keep others intact
        output_lines = []
        keys_replaced = set()
        for line in existing_lines:
            if "=" in line and not line.startswith("#"):
                key = line.split("=")[0].strip()
                if key in changes:
                    output_lines.append(f"{key}={changes[key]}\n")
                    keys_replaced.add(key)
                else:
                    output_lines.append(line)
            else:
                output_lines.append(line)
        
        # Append new keys that weren't in the file before
        for key, value in changes.items():
            if key not in keys_replaced:
                output_lines.append(f"{key}={value}\n")
        
        with open(env_file, "w") as f:
            f.writelines(output_lines)
        
        print()
        print(f"  {GREEN}✓ Credentials saved to ~/.hermes/.env{RESET}")
        print(f"  {GREEN}✓ Run 'hermes gateway restart' to activate{RESET}")
    else:
        print()
        print(f"  {YELLOW}No changes to save.{RESET}")
    
    print()