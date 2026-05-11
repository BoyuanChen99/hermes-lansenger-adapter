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
import logging
import os
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

# Constants
MAX_MESSAGE_LENGTH = 4000
RECONNECT_BACKOFF = [2, 5, 10, 30, 60]
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
    },
}


# check_requirements is defined at the bottom of this file (near register()).


class LansengerAdapter(BasePlatformAdapter):
    """Lansenger chatbot adapter using WebSocket long-connection."""

    MAX_MESSAGE_LENGTH = MAX_MESSAGE_LENGTH

    def __init__(self, config: PlatformConfig):
        super().__init__(config, Platform("lansenger"))

        extra = config.extra or {}
        self._app_id: str = extra.get("app_id") or os.getenv("LANSENGER_APP_ID", "")
        self._app_secret: str = extra.get("app_secret") or os.getenv("LANSENGER_APP_SECRET", "")
        self._api_gateway_url: str = extra.get("api_gateway_url") or os.getenv("LANSENGER_API_GATEWAY_URL", DEFAULT_API_GATEWAY_URL)

        # Home channel from PlatformConfig.home_channel (standard Hermes structure)
        self._home_channel_id: Optional[str] = None
        if config.home_channel:
            self._home_channel_id = config.home_channel.chat_id

        self._ws_client: Optional[Any] = None
        self._ws_task: Optional[asyncio.Task] = None
        self._http_client: Optional["httpx.AsyncClient"] = None

        # Message deduplication
        self._dedup = MessageDeduplicator(max_size=1000)

        # Token cache
        self._app_token: Optional[str] = None
        self._token_expiry: float = 0

        # Owner ID (the user who bound the bot)
        self._owner_id: Optional[str] = None
        self._owner_id_file = Path.home() / ".hermes" / "lansenger_owner.json"
        self._load_owner_id()

        # Pairing state
        self._pending_pairings: Dict[str, Dict[str, Any]] = {}

    # -- Connection lifecycle -----------------------------------------------

    async def connect(self) -> bool:
        """Connect to Lansenger via WebSocket."""
        if not WEBSOCKETS_AVAILABLE or not HTTPX_AVAILABLE:
            return False
        if not self._app_id or not self._app_secret:
            return False

        try:
            self._http_client = httpx.AsyncClient(timeout=30.0)

            # Get WebSocket URL
            ws_url = await self._get_websocket_url()
            if not ws_url:
                logger.error("[Lansenger] Failed to get WebSocket URL")
                return False

            self._ws_task = asyncio.create_task(self._run_ws(ws_url))
            self._mark_connected()
            logger.info("[Lansenger] Connected via WebSocket")
            return True
        except Exception as e:
            logger.error("[Lansenger] Failed to connect: %s", e)
            return False

    async def _get_websocket_url(self) -> Optional[str]:
        """Get WebSocket URL from Lansenger API."""
        try:
            url = f"{self._api_gateway_url}{API_ENDPOINTS['websocket']['endpoint']}"
            response = await self._http_client.post(
                url,
                json={"appId": self._app_id, "secret": self._app_secret}
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get("errCode") == 0:
                ws_url = data.get("data", {}).get("wsEndpoint")
                logger.info("[Lansenger] Got WebSocket URL: %s", ws_url[:50] if ws_url else None)
                return ws_url
            else:
                logger.error("[Lansenger] WebSocket endpoint error: %s", data.get("errMsg"))
                return None
        except Exception as e:
            logger.error("[Lansenger] Error getting WebSocket URL: %s", e)
            return None

    async def _run_ws(self, ws_url: str) -> None:
        """Run WebSocket client with auto-reconnection."""
        backoff_idx = 0
        while self._running:
            try:
                logger.debug("[Lansenger] Connecting to WebSocket...")
                async with websockets.connect(ws_url, ping_interval=30, ping_timeout=10) as ws:
                    self._ws_client = ws
                    backoff_idx = 0
                    
                    # Start heartbeat task
                    heartbeat_task = asyncio.create_task(self._heartbeat_loop(ws))
                    
                    try:
                        async for message in ws:
                            await self._on_message(message)
                    finally:
                        # Cancel heartbeat on disconnect
                        heartbeat_task.cancel()
                        try:
                            await heartbeat_task
                        except asyncio.CancelledError:
                            pass
            except asyncio.CancelledError:
                return
            except Exception as e:
                if not self._running:
                    return
                logger.warning("[Lansenger] WebSocket error: %s", e)

            if not self._running:
                return

            delay = RECONNECT_BACKOFF[min(backoff_idx, len(RECONNECT_BACKOFF) - 1)]
            logger.info("[Lansenger] Reconnecting in %ds...", delay)
            await asyncio.sleep(delay)
            backoff_idx += 1

            # Refresh WebSocket URL on reconnect
            ws_url = await self._get_websocket_url() or ws_url
    
    async def _heartbeat_loop(self, ws, interval: int = 25) -> None:
        """Send periodic heartbeat to keep connection alive."""
        logger.info("[Lansenger] Heartbeat task started (interval=%ds)", interval)
        while self._running:
            try:
                await asyncio.sleep(interval)
                if not self._running:
                    break
                # Send a simple ping to keep connection alive
                await ws.ping()
                logger.debug("[Lansenger] Heartbeat ping sent")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("[Lansenger] Heartbeat error: %s", e)
                break

    async def disconnect(self) -> None:
        """Disconnect from Lansenger."""
        self._running = False
        self._mark_disconnected()

        if self._ws_task:
            self._ws_task.cancel()
            try:
                await self._ws_task
            except asyncio.CancelledError:
                pass
            self._ws_task = None

        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

        self._ws_client = None
        self._dedup.clear()
        logger.info("[Lansenger] Disconnected")

    # -- Inbound message processing -----------------------------------------

    def _load_owner_id(self) -> None:
        """Load owner ID from file."""
        try:
            if self._owner_id_file.exists():
                import json
                data = json.loads(self._owner_id_file.read_text())
                self._owner_id = data.get("owner_id")
                if self._owner_id:
                    logger.info("[Lansenger] Loaded owner ID: %s", self._owner_id[:20] if self._owner_id else None)
        except Exception as e:
            logger.warning("[Lansenger] Failed to load owner ID: %s", e)

    def _save_owner_id(self) -> None:
        """Save owner ID to file."""
        try:
            import json
            self._owner_id_file.parent.mkdir(parents=True, exist_ok=True)
            self._owner_id_file.write_text(json.dumps({"owner_id": self._owner_id}, indent=2))
            logger.info("[Lansenger] Saved owner ID: %s", self._owner_id[:20] if self._owner_id else None)
        except Exception as e:
            logger.error("[Lansenger] Failed to save owner ID: %s", e)

    async def _on_message(self, raw_message: str) -> None:
        """Process an incoming Lansenger message."""
        import json

        try:
            data = json.loads(raw_message)
        except json.JSONDecodeError:
            logger.warning("[Lansenger] Invalid JSON message")
            return

        events = data.get("events", [])
        for event_data in events:
            await self._process_event(event_data)

    async def _process_event(self, event_data: Dict[str, Any]) -> None:
        """Process a single event."""
        # Debug: log raw event structure
        msg_data = event_data.get("data", {})
        msg_type = msg_data.get("msgType", "text")
        logger.debug("[Lansenger] Raw event msgType=%s, data keys=%s", msg_type, list(msg_data.keys()) if msg_data else "None")
        
        msg_id = msg_data.get("messageId") or uuid.uuid4().hex

        if self._dedup.is_duplicate(msg_id):
            logger.debug("[Lansenger] Duplicate message %s, skipping", msg_id)
            return

        text = await self._extract_text(msg_data)
        if not text:
            logger.debug("[Lansenger] Empty message (msgType=%s), skipping", msg_type)
            return

        # Chat context
        chat_type = msg_data.get("chatType", "p2p")
        is_group = chat_type == "group"
        sender_id = msg_data.get("from", "")
        chat_id = msg_data.get("conversationId") or sender_id

        # Record owner ID on first p2p message
        if not is_group and not self._owner_id and sender_id:
            self._owner_id = sender_id
            self._save_owner_id()
            logger.info("[Lansenger] Recorded owner ID from first message: %s", sender_id)

        source = self.build_source(
            chat_id=chat_id,
            chat_name=msg_data.get("conversationTitle"),
            chat_type="group" if is_group else "dm",
            user_id=sender_id,
            user_name=msg_data.get("senderName", sender_id),
        )

        timestamp = datetime.now(tz=timezone.utc)

        event = MessageEvent(
            text=text,
            message_type=MessageType.TEXT,
            source=source,
            message_id=msg_id,
            raw_message=msg_data,
            timestamp=timestamp,
        )

        logger.debug("[Lansenger] Message from %s in %s: %s",
                     source.user_name, chat_id[:20] if chat_id else "?", text[:50])
        await self.handle_message(event)

    async def _extract_text(self, msg_data: Dict[str, Any]) -> str:
        """Extract text from message, downloading media if needed.
        
        For image/video/file/voice: downloads first media and returns file path.
        """
        msg_type = msg_data.get("msgType", "text")
        msg_payload = msg_data.get("msgData", {})

        if msg_type == "text":
            return msg_payload.get("text", {}).get("content", "").strip()
        
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

    # -- Token management ---------------------------------------------------

    async def _get_app_token(self) -> Optional[str]:
        """Get or refresh app access token."""
        if self._app_token and datetime.now().timestamp() < self._token_expiry:
            return self._app_token

        # Ensure httpx client exists
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=30.0)

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
            self._token_expiry = datetime.now().timestamp() + expires_in - 300

            logger.info("[Lansenger] Got new access token")
            return self._app_token
        except Exception as e:
            logger.error("[Lansenger] Error getting token: %s", e)
            return None

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

    # -- Outbound message sending -------------------------------------------

    async def send(self, chat_id: str, content: str, **kwargs) -> SendResult:
        """Send a message (alias for send_format_text)."""
        return await self.send_format_text(chat_id, content)

    async def send_typing(self, chat_id: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Send typing indicator (not supported by Lansenger)."""
        pass  # Lansenger doesn't support typing indicators

    async def send_text(self, chat_id: str, content: str, reminder: dict = None) -> SendResult:
        """Send a plain text message, optionally with @mentions (group/staff chat only).
        
        Args:
            chat_id: Recipient user ID or chat ID
            content: Text content
            reminder: Optional dict with 'all' (bool) and 'userIds' (list) for @mentions.
                      Only works in group/staff chat; private chat does not support @mentions.
        """
        token = await self._get_app_token()
        if not token:
            return SendResult(success=False, error="No access token")

        try:
            url = f"{self._api_gateway_url}{API_ENDPOINTS['smart_bot']['private_message']}?app_token={token}"
            text_data = {"content": content}
            if reminder:
                text_data["reminder"] = reminder
            payload = {
                "userIdList": [chat_id],
                "msgType": "text",
                "msgData": {"text": text_data}
            }

            response = await self._http_client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()

            if data.get("errCode") != 0:
                return SendResult(success=False, error=data.get("errMsg"))

            msg_id = data.get("data", {}).get("msgId")
            logger.info("[Lansenger] Text message sent to %s", chat_id)
            return SendResult(success=True, message_id=msg_id, raw_response=data)
        except Exception as e:
            logger.error("[Lansenger] Send text error: %s", e)
            return SendResult(success=False, error=str(e), retryable=True)

    async def send_format_text(self, chat_id: str, content: str) -> SendResult:
        """Send a formatted text message (Markdown support).
        
        Note: formatText does NOT support media attachments.
        Use send_text_with_media() for sending files/images/videos.
        """
        token = await self._get_app_token()
        if not token:
            return SendResult(success=False, error="No access token")

        try:
            url = f"{self._api_gateway_url}{API_ENDPOINTS['smart_bot']['private_message']}?app_token={token}"
            payload = {
                "userIdList": [chat_id],
                "msgType": "formatText",
                "msgData": {
                    "formatText": {
                        "formatType": 1,
                        "text": content
                    }
                }
            }

            response = await self._http_client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()

            if data.get("errCode") != 0:
                return SendResult(success=False, error=data.get("errMsg"))

            msg_id = data.get("data", {}).get("msgId")
            logger.info("[Lansenger] FormatText message sent to %s", chat_id)
            return SendResult(success=True, message_id=msg_id, raw_response=data)
        except Exception as e:
            logger.error("[Lansenger] Send formatText error: %s", e, exc_info=True)
            return SendResult(success=False, error=str(e), retryable=True)

    async def send_text_with_media(self, chat_id: str, content: str, media_type: int, media_ids: List[str], reminder: dict = None) -> SendResult:
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
            url = f"{self._api_gateway_url}{API_ENDPOINTS['smart_bot']['private_message']}?app_token={token}"
            text_data = {
                "content": content,
                "mediaType": media_type,
                "mediaIds": media_ids
            }
            if reminder:
                text_data["reminder"] = reminder
            payload = {
                "userIdList": [chat_id],
                "msgType": "text",
                "msgData": {"text": text_data}
            }

            response = await self._http_client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()

            if data.get("errCode") != 0:
                return SendResult(success=False, error=data.get("errMsg"))

            msg_id = data.get("data", {}).get("msgId")
            logger.info("[Lansenger] Text+media message sent to %s", chat_id)
            return SendResult(success=True, message_id=msg_id, raw_response=data)
        except Exception as e:
            logger.error("[Lansenger] Send text+media error: %s", e)
            return SendResult(success=False, error=str(e), retryable=True)

    async def upload_media_file(self, file_path: str, media_type: int) -> Optional[str]:
        """Upload a media file to Lansenger and return mediaId.
        
        Args:
            file_path: Path to the local file
            media_type: 1=video, 2=image, 3=file
            
        Returns:
            mediaId string on success, None on failure
            
        Note: File size limits are determined by the organization's Lansenger configuration.
        """
        token = await self._get_app_token()
        if not token:
            logger.error("[Lansenger] No access token for media upload")
            return None
        
        try:
            url = f"{self._api_gateway_url}/v1/medias/create?type={media_type}&app_token={token}"
            
            # Read file and prepare multipart form data
            with open(file_path, 'rb') as f:
                file_content = f.read()
            
            # Get filename from path
            filename = os.path.basename(file_path)
            
            # Build multipart form data manually for httpx
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

    async def send_file(self, chat_id: str, file_path: str, caption: str = "", media_type: int = 3) -> SendResult:
        """Send a file/image/video message.
        
        Args:
            chat_id: Recipient user ID
            file_path: Path to the local file
            caption: Optional caption text (plain text, Markdown NOT supported with media)
            media_type: 1=video, 2=image, 3=file (default: 3)
            
        Returns:
            SendResult with success status
            
        Note: Uses msgType='text' which doesn't support Markdown. For Markdown, send separately.
        """
        # Graceful degradation: skip non-existent files instead of crashing
        # (base's extract_local_files can misidentify placeholder paths)
        if not os.path.isfile(file_path):
            logger.warning("[Lansenger] File not found: %s — skipping", file_path)
            return SendResult(success=False, error=f"File not found: {file_path}")

        # Upload file first
        media_id = await self.upload_media_file(file_path, media_type)
        if not media_id:
            return SendResult(success=False, error="Failed to upload file")
        
        # Send message with media attachment (uses msgType='text', not formatText)
        return await self.send_text_with_media(chat_id, caption, media_type=media_type, media_ids=[media_id])

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
        
        try:
            # Download image
            async with httpx.AsyncClient() as client:
                resp = await client.get(image_url, timeout=30)
                resp.raise_for_status()
                image_bytes = resp.content
            
            # Save to temp file
            fd, temp_path = tempfile.mkstemp(suffix='.jpg', prefix='lansenger_image_')
            os.write(fd, image_bytes)
            os.close(fd)
            
            # Determine media type based on content
            media_type = 2  # Default: image
            
            # Send as image
            return await self.send_file(chat_id, temp_path, caption or "", media_type=media_type)
        except Exception as e:
            logger.error("[Lansenger] Send image error: %s", e)
            return SendResult(success=False, error=str(e))

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
        chat_type: str = "bot",
        sender_id: Optional[str] = None
    ) -> SendResult:
        """Revoke previously sent messages.

        Args:
            message_ids: List of message IDs to revoke
            chat_type: Message type enum: staff, group, notification, account, bot
            sender_id: Sender ID; required for private/group chats

        Note: Lansenger displays a fixed system message after revocation.
              The revocation prompt text cannot be customized.
        """
        # Get token
        token = await self._get_app_token()
        if not token:
            return SendResult(success=False, error="Failed to get token")
        
        if chat_type in ["staff", "group"] and not sender_id:
            return SendResult(success=False, error=f"chat_type='{chat_type}' requires sender_id")
        
        try:
            url = f"{self._api_gateway_url}{API_ENDPOINTS['message']['revoke']}?app_token={token}"
            payload = {"chatType": chat_type, "messageIds": message_ids}
            if sender_id:
                payload["senderId"] = sender_id
            
            response = await self._http_client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            
            if data.get("errCode") != 0:
                return SendResult(success=False, error=data.get("errMsg", "Unknown error"))
            
            logger.info("[Lansenger] Message(s) revoked: %s", message_ids)
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
            url = f"{self._api_gateway_url}{API_ENDPOINTS['smart_bot']['private_message']}?app_token={token}"
            payload = {
                "userIdList": [chat_id],
                "msgType": "linkCard",
                "msgData": {
                    "linkCard": {
                        "title": title,
                        "link": link,
                        "description": description or "",
                        "iconLink": icon_link or "",
                        "pcLink": pc_link or "",
                        "fromName": from_name or "",
                        "fromIconLink": from_icon_link or "",
                    }
                }
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
            logger.info("[Lansenger] LinkCard sent to %s, msgId=%s", chat_id, msg_id)
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
        """Send an i18nAppCard approval card with dynamic status support.
        
        Args:
            chat_id: Recipient user ID
            command: The command to approve
            session_key: Session identifier for approval resolution
            description: Reason for approval request
            metadata: Optional metadata (not used currently)
            
        Returns:
            SendResult with message_id for later status updates
        """
        logger.info("[Lansenger] send_exec_approval called for chat_id=%s", chat_id)
        token = await self._get_app_token()
        logger.info("[Lansenger] Token obtained: %s", "yes" if token else "no")
        if not token:
            return SendResult(success=False, error="No access token")
        
        cmd_preview = command[:300] + "..." if len(command) > 300 else command
        
        # Build i18n content for each language
        i18n_head_title = self._build_i18n_obj_full(
            "⚠️ 命令审批",  # zhHans
            "⚠️ 命令審批",  # zhHant
            "⚠️ 命令審批",  # zhHantHK
            "⚠️ Command Approval",  # en
            "⚠️ Approbation de commande"  # fr
        )
        i18n_body_title = self._build_i18n_obj_full(
            "危险命令审批请求",
            "危險命令審批請求",
            "危險命令審批請求",
            "Dangerous Command Approval Request",
            "Demande d'approbation de commande dangereuse"
        )
        i18n_body_sub_title = self._build_i18n_obj_full(
            description,  # User provides description, use as-is
            description,
            description,
            description,
            description
        )
        
        # Build i18n head status info (Pending Approval) - Note: i18nAppCard may not support this field
        # Keeping for future API compatibility, but it may not display
        i18n_head_status_info = self._build_i18n_obj_full(
            '待审批',  # Plain text, no HTML
            '待審批',
            '待審批',
            'Pending',
            'En attente'
        )
        
        # Build body content with session info and command - Plain text only, no HTML
        cmd_section = (
            f"会话 ID: {session_key[:32]}\n"
            f"命令:\n{cmd_preview}"
        )
        cmd_section_zh_hant = (
            f"會話 ID: {session_key[:32]}\n"
            f"命令:\n{cmd_preview}"
        )
        cmd_section_en = (
            f"Session ID: {session_key[:32]}\n"
            f"Command:\n{cmd_preview}"
        )
        cmd_section_fr = (
            f"ID de session: {session_key[:32]}\n"
            f"Commande:\n{cmd_preview}"
        )
        i18n_body_content = self._build_i18n_obj_full(
            cmd_section,
            cmd_section_zh_hant,
            cmd_section_zh_hant,
            cmd_section_en,
            cmd_section_fr
        )
        
        i18n_signature = self._build_i18n_obj_full(
            "Hermes 安全审批系统",
            "Hermes 安全審批系統",
            "Hermes 安全審批系統",
            "Hermes Security Approval",
            "Système d'approbation de sécurité Hermes"
        )
        
        # Build i18n fields for approval options
        import time
        timestamp = int(time.time())
        i18n_fields = [
            {
                "i18nKey": self._build_i18n_obj_full("执行一次", "執行一次", "執行一次", "Execute Once", "Exécuter une fois"),
                "i18nValue": self._build_i18n_obj_full("/approve", "/approve", "/approve", "/approve", "/approve"),
                "timestamp": timestamp
            },
            {
                "i18nKey": self._build_i18n_obj_full("本会话有效", "本會話有效", "本會話有效", "This Session", "Cette session"),
                "i18nValue": self._build_i18n_obj_full("/approve session", "/approve session", "/approve session", "/approve session", "/approve session"),
                "timestamp": timestamp
            },
            {
                "i18nKey": self._build_i18n_obj_full("永久允许", "永久允許", "永久允許", "Always Allow", "Toujours autoriser"),
                "i18nValue": self._build_i18n_obj_full("/approve always", "/approve always", "/approve always", "/approve always", "/approve always"),
                "timestamp": timestamp
            },
            {
                "i18nKey": self._build_i18n_obj_full("拒绝执行", "拒絕執行", "拒絕執行", "Deny", "Refuser"),
                "i18nValue": self._build_i18n_obj_full("/deny", "/deny", "/deny", "/deny", "/deny"),
                "timestamp": timestamp
            }
        ]
        
        try:
            url = f"{self._api_gateway_url}/v1/bot/messages/create?app_token={token}"
            logger.info("[Lansenger] Sending i18nAppCard to %s", chat_id)
            
            # Build i18nAppCard payload with dynamic status support
            # Note: i18nHeadStatusInfo may not be supported by i18nAppCard, keeping for future compatibility
            payload = {
                "userIdList": [chat_id],
                "msgType": "i18nAppCard",
                "msgData": {
                    "i18nAppCard": {
                        "i18nHeadTitle": i18n_head_title,
                        "headIconId": "",
                        "i18nBodyTitle": i18n_body_title,
                        "i18nBodySubTitle": i18n_body_sub_title,
                        "i18nBodyContent": i18n_body_content,
                        "i18nSignature": i18n_signature,
                        "i18nFields": i18n_fields,
                        "i18nLinks": [],
                        "cardLink": "",
                        "pcCardLink": ""
                    }
                }
            }
            
            response = await self._http_client.post(url, json=payload)
            response.raise_for_status()
            
            logger.info("[Lansenger] Response status: %s, content-length: %s", response.status_code, len(response.text))
            logger.info("[Lansenger] Response text (first 500 chars): %s", response.text[:500] if response.text else "EMPTY")
            
            # Check response content - empty response is an error
            if not response.text or len(response.text.strip()) == 0:
                logger.error("[Lansenger] Empty response from API - request may have failed")
                return SendResult(success=False, error="Empty API response", retryable=True)
            
            data = response.json()
            
            if data.get("errCode") != 0:
                logger.error("[Lansenger] API error: errCode=%s, errMsg=%s", data.get("errCode"), data.get("errMsg"))
                return SendResult(success=False, error=data.get("errMsg"))
            
            msg_id = data.get("data", {}).get("msgId")
            logger.info("[Lansenger] appCard approval sent to %s, msgId=%s", chat_id, msg_id)
            return SendResult(success=True, message_id=msg_id, raw_response=data)
            
        except Exception as e:
            logger.error("[Lansenger] Send appCard error: %s", e)
            return SendResult(success=False, error=str(e), retryable=True)

    # ------------------------------------------------------------------
    # Slash-command confirmation (gateway destructive_slash_confirm gate)
    # ------------------------------------------------------------------
    async def send_slash_confirm(
        self,
        chat_id: str,
        title: str,
        message: str,
        session_key: str,
        confirm_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        """Send an i18nAppCard slash-command confirmation card.

        Used by the gateway's ``_maybe_confirm_destructive_slash`` gate for
        /new, /reset, /undo.  Lansenger does not support inline button
        callbacks like Telegram, so this card displays the confirmation
        request with i18nFields showing the text-based reply options
        (/approve → once, /always → always, /cancel → cancel).

        The gateway's text intercept in ``_handle_message`` recognises
        /approve, /always, /cancel replies and routes them through
        ``slash_confirm.resolve()``.

        Returns SendResult(success=True) so the gateway skips the
        redundant text fallback (the card already contains all
        instructions).
        """
        logger.info("[Lansenger] send_slash_confirm: chat_id=%s, title=%s, confirm_id=%s", chat_id, title, confirm_id)
        token = await self._get_app_token()
        if not token:
            return SendResult(success=False, error="No access token")

        # Determine the slash command name from the title (e.g. "/new")
        command_name = title.strip() if title else "unknown"

        i18n_head_title = self._build_i18n_obj_full(
            f"🔄 {command_name} 确认",
            f"🔄 {command_name} 確認",
            f"🔄 {command_name} 確認",
            f"🔄 {command_name} Confirm",
            f"🔄 {command_name} Confirmation"
        )

        i18n_body_title = self._build_i18n_obj_full(
            "会话操作确认请求",
            "會話操作確認請求",
            "會話操作確認請求",
            "Session Action Confirmation",
            "Confirmation d'action de session"
        )

        i18n_body_content = self._build_i18n_obj_full(
            message or "This action will modify your current session.",
            message or "This action will modify your current session.",
            message or "This action will modify your current session.",
            message or "This action will modify your current session.",
            message or "This action will modify your current session."
        )

        i18n_signature = self._build_i18n_obj_full(
            "Hermes 安全审批系统",
            "Hermes 安全審批系統",
            "Hermes 安全審批系統",
            "Hermes Security Approval",
            "Système d'approbation de sécurité Hermes"
        )

        import time
        timestamp = int(time.time())
        i18n_fields = [
            {
                "i18nKey": self._build_i18n_obj_full("确认执行", "確認執行", "確認執行", "Approve Once", "Approuver"),
                "i18nValue": self._build_i18n_obj_full("/approve", "/approve", "/approve", "/approve", "/approve"),
                "timestamp": timestamp,
            },
            {
                "i18nKey": self._build_i18n_obj_full("本会话免确认", "本會話免確認", "本會話免確認", "Always This Session", "Toujours cette session"),
                "i18nValue": self._build_i18n_obj_full("/always", "/always", "/always", "/always", "/always"),
                "timestamp": timestamp,
            },
            {
                "i18nKey": self._build_i18n_obj_full("取消", "取消", "取消", "Cancel", "Annuler"),
                "i18nValue": self._build_i18n_obj_full("/cancel", "/cancel", "/cancel", "/cancel", "/cancel"),
                "timestamp": timestamp,
            },
        ]

        try:
            url = f"{self._api_gateway_url}/v1/bot/messages/create?app_token={token}"
            payload = {
                "userIdList": [chat_id],
                "msgType": "i18nAppCard",
                "msgData": {
                    "i18nAppCard": {
                        "i18nHeadTitle": i18n_head_title,
                        "headIconId": "",
                        "i18nBodyTitle": i18n_body_title,
                        "i18nBodyContent": i18n_body_content,
                        "i18nSignature": i18n_signature,
                        "i18nFields": i18n_fields,
                        "i18nLinks": [],
                        "cardLink": "",
                        "pcCardLink": "",
                    }
                },
            }

            response = await self._http_client.post(url, json=payload)
            response.raise_for_status()

            if not response.text or len(response.text.strip()) == 0:
                logger.error("[Lansenger] Empty response from slash confirm card API")
                return SendResult(success=False, error="Empty API response", retryable=True)

            data = response.json()
            if data.get("errCode") != 0:
                logger.error("[Lansenger] Slash confirm card API error: errCode=%s, errMsg=%s", data.get("errCode"), data.get("errMsg"))
                return SendResult(success=False, error=data.get("errMsg"))

            msg_id = data.get("data", {}).get("msgId")
            logger.info("[Lansenger] Slash confirm card sent to %s, msgId=%s", chat_id, msg_id)
            # Return success=True so gateway skips redundant text fallback.
            # Users reply /approve /always /cancel → gateway intercepts them.
            return SendResult(success=True, message_id=msg_id, raw_response=data)

        except Exception as e:
            logger.error("[Lansenger] Send slash confirm card error: %s", e)
            return SendResult(success=False, error=str(e), retryable=True)

    async def update_approval_status(
        self, chat_id: str, message_id: str,
        status: str, user_name: str = ""
    ) -> SendResult:
        """Update a dynamic i18nAppCard message status.
        
        Args:
            chat_id: Recipient user ID (not used for update, but kept for interface consistency)
            message_id: The message ID to update
            status: One of 'pending', 'approved', 'denied'
            user_name: Name of user who made the decision (not used currently)
            
        Returns:
            SendResult with success status
        """
        token = await self._get_app_token()
        if not token:
            return SendResult(success=False, error="No access token")
        
        try:
            # Lansenger dynamic update API
            url = f"{self._api_gateway_url}/v1/messages/dynamic/update?app_token={token}"
            
            # Status configuration with i18n
            status_config = {
                "pending": {
                    "color": "#FFB116", 
                    "i18n_text": self._build_i18n_obj_full("待审批", "待審批", "待審批", "Pending", "En attente")
                },
                "approved": {
                    "color": "#198754", 
                    "i18n_text": self._build_i18n_obj_full("已批准", "已批准", "已批准", "Approved", "Approuvé")
                },
                "denied": {
                    "color": "#dc3545", 
                    "i18n_text": self._build_i18n_obj_full("已拒绝", "已拒絕", "已拒絕", "Denied", "Refusé")
                }
            }
            
            config = status_config.get(status, status_config["pending"])
            
            # Build update payload for i18nAppCard
            payload = {
                "msgId": message_id,
                "msgType": "i18nAppCard",
                "msgData": {
                    "i18nAppCardUpdateMsg": {
                        "isLastUpdate": (status != "pending"),  # True for final state
                        "headStatusInfo": {
                            "description": f'<div style="color:{config["color"]};text-align:left">{config["i18n_text"]["zhHans"]}</div>',
                            "colour": config["color"]
                        },
                        "i18nHeadStatusInfo": {
                            "description": {
                                "zhHans": f'<div style="color:{config["color"]};text-align:left">{config["i18n_text"]["zhHans"]}</div>',
                                "zhHant": f'<div style="color:{config["color"]};text-align:left">{config["i18n_text"]["zhHans"]}</div>',
                                "zhHantHK": f'<div style="color:{config["color"]};text-align:left">{config["i18n_text"]["zhHans"]}</div>',
                                "en": f'<div style="color:{config["color"]};text-align:left">{config["i18n_text"]["en"]}</div>',
                                "fr": f'<div style="color:{config["color"]};text-align:left">{config["i18n_text"]["en"]}</div>'
                            },
                            "colour": config["color"]
                        }
                    }
                }
            }
            
            response = await self._http_client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            
            if data.get("errCode") != 0:
                return SendResult(success=False, error=data.get("errMsg"))
            
            logger.info("[Lansenger] appCard status updated to %s", status)
            return SendResult(success=True, raw_response=data)
            
        except Exception as e:
            logger.error("[Lansenger] Update appCard error: %s", e)
            return SendResult(success=False, error=str(e), retryable=True)

    def _build_i18n_obj_full(self, zh_hans: str, zh_hant: str, zh_hant_hk: str, en: str, fr: str) -> Dict[str, str]:
        """Build i18n object with all 5 supported languages.
        
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
        """Escape < and > to prevent HTML tag parsing.
        
        Client doesn't support HTML entities like &quot; or &amp;,
        but we need to escape < and > to prevent them from being
        parsed as HTML tags.
        """
        return text.replace("<", "&lt;").replace(">", "&gt;")

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
    app_id = extra.get("app_id") or os.getenv("LANSENGER_APP_ID", "")
    app_secret = extra.get("app_secret") or os.getenv("LANSENGER_APP_SECRET", "")
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
            "Messages have a ~4000 character limit.  i18nAppCard is available for "
            "approval workflows.  Keep responses concise and professional."
        ),
    )


def _interactive_setup():
    """Interactive setup wizard for Lansenger credentials.
    
    Called by `hermes setup gateway` when the user selects Lansenger.
    Prompts for APP_ID, APP_SECRET, and optional API_GATEWAY_URL,
    then writes them to ~/.hermes/.env (idempotent — won't duplicate).
    """
    from pathlib import Path
    
    hermes_home = Path.home() / ".hermes"
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
    
    def _prompt_field(env_key: str, label: str, default: str = "", sensitive: bool = False) -> str | None:
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