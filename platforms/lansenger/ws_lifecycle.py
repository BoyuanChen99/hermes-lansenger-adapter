"""
WebSocket lifecycle mixin for LansengerAdapter.
Handles connect, disconnect, keepalive, watchdog, and reconnection.
"""

import asyncio
import logging
import time
from typing import Optional

try:
    import websockets
except ImportError:
    websockets = None  # type: ignore[assignment]

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore[assignment]

from . import commands as _commands

from ._constants import (
    API_ENDPOINTS,
    INBOUND_SILENCE_TIMEOUT,
    RECONNECT_BACKOFF,
)

WEBSOCKETS_AVAILABLE = websockets is not None
HTTPX_AVAILABLE = httpx is not None

logger = logging.getLogger(__name__)


class WsLifecycleMixin:
    """WebSocket lifecycle methods for LansengerAdapter."""

    # -- Connection lifecycle -----------------------------------------------

    async def connect(self, **kwargs) -> bool:
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

    async def disconnect(self, **kwargs) -> None:
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
