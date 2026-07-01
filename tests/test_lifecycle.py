import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from conftest import (
    WS_ENDPOINT_SUCCESS,
    WS_ENDPOINT_FAILURE,
    WS_TICKET_URL,
    TOKEN_SUCCESS,
)


class TestConnectLifecycle:
    async def test_connect_sets_running_true(self, make_adapter):
        adapter = make_adapter()
        mock_http = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json = MagicMock(return_value=WS_ENDPOINT_SUCCESS)
        mock_response.raise_for_status = MagicMock()
        mock_response.text = json.dumps(WS_ENDPOINT_SUCCESS)
        mock_http.post = AsyncMock(return_value=mock_response)

        with patch("lansenger.ws_lifecycle.httpx.AsyncClient", return_value=mock_http):
            with patch("lansenger.ws_lifecycle.websockets.connect"):
                result = await adapter.connect()

        assert result is True
        assert adapter._running is True

    async def test_connect_returns_false_no_app_id(self, make_adapter):
        adapter = make_adapter(app_id="", app_secret="test")
        result = await adapter.connect()
        assert result is False
        assert adapter._running is False

    async def test_connect_returns_false_no_secret(self, make_adapter):
        adapter = make_adapter(app_id="test", app_secret="")
        result = await adapter.connect()
        assert result is False
        assert adapter._running is False

    async def test_connect_returns_false_ws_endpoint_error(self, make_adapter):
        adapter = make_adapter()
        mock_http = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json = MagicMock(return_value=WS_ENDPOINT_FAILURE)
        mock_response.raise_for_status = MagicMock()
        mock_response.text = json.dumps(WS_ENDPOINT_FAILURE)
        mock_http.post = AsyncMock(return_value=mock_response)

        with patch("lansenger.ws_lifecycle.httpx.AsyncClient", return_value=mock_http):
            result = await adapter.connect()

        assert result is False

    async def test_connect_returns_false_http_error(self, make_adapter):
        adapter = make_adapter()
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(side_effect=Exception("connection refused"))

        with patch("lansenger.ws_lifecycle.httpx.AsyncClient", return_value=mock_http):
            result = await adapter.connect()

        assert result is False

    async def test_disconnect_sets_running_false(self, make_adapter):
        adapter = make_adapter()
        adapter._running = True
        adapter._connected = True
        mock_http = AsyncMock()
        mock_http.aclose = AsyncMock()
        adapter._http_client = mock_http
        adapter._ws_task = None

        await adapter.disconnect()

        assert adapter._running is False
        assert adapter._http_client is None

    async def test_disconnect_closes_http_client(self, make_adapter):
        adapter = make_adapter()
        adapter._running = True
        adapter._connected = True
        mock_http = AsyncMock()
        mock_http.aclose = AsyncMock()
        adapter._http_client = mock_http
        adapter._ws_task = None

        await adapter.disconnect()

        mock_http.aclose.assert_called_once()
        assert adapter._http_client is None


class TestGetWebsocketUrl:
    async def test_success_returns_ws_url(self, make_adapter):
        adapter = make_adapter()
        adapter._http_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json = MagicMock(return_value=WS_ENDPOINT_SUCCESS)
        mock_response.raise_for_status = MagicMock()
        mock_response.text = json.dumps(WS_ENDPOINT_SUCCESS)
        adapter._http_client.post = AsyncMock(return_value=mock_response)

        result = await adapter._get_websocket_url()

        assert result == WS_TICKET_URL
        assert adapter._ws_url == WS_TICKET_URL

    async def test_api_error_returns_none(self, make_adapter):
        adapter = make_adapter()
        adapter._http_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json = MagicMock(return_value=WS_ENDPOINT_FAILURE)
        mock_response.raise_for_status = MagicMock()
        mock_response.text = json.dumps(WS_ENDPOINT_FAILURE)
        adapter._http_client.post = AsyncMock(return_value=mock_response)

        result = await adapter._get_websocket_url()

        assert result is None

    async def test_http_401_returns_none(self, make_adapter):
        import httpx
        adapter = make_adapter()
        adapter._http_client = AsyncMock()

        error_response = MagicMock()
        error_response.text = '{"errCode":401,"errMsg":"Unauthorized"}'
        adapter._http_client.post = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "401 Unauthorized",
                request=MagicMock(),
                response=error_response,
            )
        )

        result = await adapter._get_websocket_url()

        assert result is None

    async def test_network_error_returns_none(self, make_adapter):
        adapter = make_adapter()
        adapter._http_client = AsyncMock()
        adapter._http_client.post = AsyncMock(side_effect=Exception("DNS failure"))

        result = await adapter._get_websocket_url()

        assert result is None


class TestRunWs:
    async def test_run_ws_stops_when_not_running(self, make_adapter):
        adapter = make_adapter()
        adapter._running = False

        await adapter._run_ws(WS_TICKET_URL)

    async def test_run_ws_processes_messages(self, make_adapter):
        adapter = make_adapter()
        adapter._on_message = AsyncMock()

        messages = ["msg1", "msg2"]

        class FakeWs:
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                pass
            def __aiter__(self):
                return self
            async def __anext__(self):
                if not adapter._running or not messages:
                    raise StopAsyncIteration
                return messages.pop(0)

        class FakeConnect:
            """Simulates websockets.connect() — awaitable returning ws, also async context manager."""
            def __init__(self, ws):
                self._ws = ws
            def __await__(self):
                async def _connect():
                    return self._ws
                return _connect().__await__()
            async def __aenter__(self):
                await self
                return self._ws
            async def __aexit__(self, *args):
                pass

        adapter._running = True
        fake_ws = FakeWs()
        fake_connect = FakeConnect(fake_ws)

        with patch("lansenger.ws_lifecycle.websockets.connect", return_value=fake_connect):
            adapter._ws_task = asyncio.create_task(adapter._run_ws(WS_TICKET_URL))
            await asyncio.sleep(0.3)
            adapter._running = False
            adapter._ws_task.cancel()
            try:
                await adapter._ws_task
            except (asyncio.CancelledError, StopAsyncIteration):
                pass

        assert adapter._on_message.call_count >= 1

    async def test_run_ws_reconnects_after_disconnect(self, make_adapter):
        adapter = make_adapter()
        adapter._on_message = AsyncMock()
        adapter._get_websocket_url = AsyncMock(return_value="wss://reconnect-url")

        class FakeWsFirst:
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                pass
            def __aiter__(self):
                return self
            async def __anext__(self):
                raise Exception("connection lost")

        class FakeWsSecond:
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                pass
            def __aiter__(self):
                return self
            async def __anext__(self):
                raise StopAsyncIteration

        class FakeConnect:
            def __init__(self, ws):
                self._ws = ws
            def __await__(self):
                async def _connect():
                    return self._ws
                return _connect().__await__()
            async def __aenter__(self):
                await self
                return self._ws
            async def __aexit__(self, *args):
                pass

        ws_sequence = [FakeConnect(FakeWsFirst()), FakeConnect(FakeWsSecond())]
        call_idx = 0

        def connect_side_effect(*args, **kwargs):
            nonlocal call_idx
            ws = ws_sequence[min(call_idx, len(ws_sequence) - 1)]
            call_idx += 1
            return ws

        adapter._running = True

        original_sleep = asyncio.sleep

        async def fast_sleep(delay):
            await original_sleep(min(delay, 0.01))

        with patch("lansenger.ws_lifecycle.websockets.connect", side_effect=connect_side_effect):
            with patch("lansenger.ws_lifecycle.RECONNECT_BACKOFF", [0.01]):
                with patch("lansenger.ws_lifecycle.asyncio.sleep", side_effect=fast_sleep):
                    task = asyncio.create_task(adapter._run_ws(WS_TICKET_URL))
                    await original_sleep(0.3)
                    adapter._running = False
                    task.cancel()
                    try:
                        await task
                    except (asyncio.CancelledError, StopAsyncIteration):
                        pass

        adapter._get_websocket_url.assert_called()

    async def test_run_ws_stops_on_cancel(self, make_adapter):
        adapter = make_adapter()
        adapter._on_message = AsyncMock()

        class InfiniteWs:
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                pass
            def __aiter__(self):
                return self
            async def __anext__(self):
                await asyncio.sleep(1)
                return "ping"

        adapter._running = True

        with patch("lansenger.ws_lifecycle.websockets.connect", return_value=InfiniteWs()):
            task = asyncio.create_task(adapter._run_ws(WS_TICKET_URL))
            await asyncio.sleep(0.05)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


# ---------------------------------------------------------------------------
# _ws_keepalive — application-layer heartbeat for CLOSE_WAIT detection
# ---------------------------------------------------------------------------

class TestWsKeepalive:

    async def test_keepalive_ping_succeeds(self, make_adapter):
        """Normal operation: ws.ping() returns latency, no close triggered."""
        adapter = make_adapter()
        adapter._running = True
        adapter._last_inbound_time = time.time()  # prevent inbound-silence trigger

        mock_ws = MagicMock()
        mock_ws.ping = AsyncMock(return_value=0.015)  # 15ms latency
        mock_ws.close = AsyncMock()

        task = asyncio.create_task(adapter._ws_keepalive(mock_ws, interval=0.05))
        await asyncio.sleep(0.12)  # should fire ~2 pings
        adapter._running = False
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        assert mock_ws.ping.call_count >= 1
        mock_ws.close.assert_not_called()

    async def test_keepalive_stops_when_not_running(self, make_adapter):
        """When _running is False, keepalive should not call ws.ping()."""
        adapter = make_adapter()
        adapter._running = False

        mock_ws = MagicMock()
        mock_ws.ping = AsyncMock()

        task = asyncio.create_task(adapter._ws_keepalive(mock_ws, interval=0.05))
        await asyncio.sleep(0.10)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        mock_ws.ping.assert_not_called()

    async def test_keepalive_ping_timeout_triggers_close(self, make_adapter):
        """When ws.ping() times out, keepalive closes WS for reconnect."""
        adapter = make_adapter()
        adapter._running = True
        adapter._last_inbound_time = time.time()

        mock_ws = MagicMock()
        mock_ws.ping = AsyncMock(side_effect=asyncio.TimeoutError)
        mock_ws.close = AsyncMock()

        task = asyncio.create_task(adapter._ws_keepalive(mock_ws, interval=0.05))
        await asyncio.sleep(0.12)
        adapter._running = False
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        mock_ws.close.assert_called_once()

    async def test_keepalive_ping_exception_triggers_close(self, make_adapter):
        """When ws.ping() raises an exception, keepalive closes WS."""
        adapter = make_adapter()
        adapter._running = True
        adapter._last_inbound_time = time.time()

        mock_ws = MagicMock()
        mock_ws.ping = AsyncMock(side_effect=ConnectionError("socket dead"))
        mock_ws.close = AsyncMock()

        task = asyncio.create_task(adapter._ws_keepalive(mock_ws, interval=0.05))
        await asyncio.sleep(0.12)
        adapter._running = False
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        mock_ws.close.assert_called_once()

    async def test_keepalive_close_swallows_exception(self, make_adapter):
        """If ws.close() itself raises, keepalive should not crash."""
        adapter = make_adapter()
        adapter._running = True
        adapter._last_inbound_time = time.time()

        mock_ws = MagicMock()
        mock_ws.ping = AsyncMock(side_effect=ConnectionError("socket dead"))
        mock_ws.close = AsyncMock(side_effect=RuntimeError("close failed"))

        task = asyncio.create_task(adapter._ws_keepalive(mock_ws, interval=0.05))
        await asyncio.sleep(0.12)
        adapter._running = False
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        mock_ws.close.assert_called_once()

    async def test_keepalive_inbound_silence_triggers_close(self, make_adapter):
        """When no inbound message for > INBOUND_SILENCE_TIMEOUT, keepalive closes WS."""
        adapter = make_adapter()
        adapter._running = True
        adapter._last_inbound_time = 0  # never received any message

        mock_ws = MagicMock()
        mock_ws.ping = AsyncMock(return_value=0.015)  # protocol ping OK
        mock_ws.close = AsyncMock()

        task = asyncio.create_task(adapter._ws_keepalive(mock_ws, interval=0.05))
        await asyncio.sleep(0.12)
        adapter._running = False
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        mock_ws.close.assert_called_once()


# ---------------------------------------------------------------------------
# _ws_watchdog — dead WS task detection and restart
# ---------------------------------------------------------------------------

class TestWsWatchdog:

    def _make_fake_ws_task(self, done=True, exception=None):
        task = MagicMock()
        task.done = MagicMock(return_value=done)
        task.exception = MagicMock(return_value=exception)
        task.cancelled = MagicMock(return_value=False)
        return task

    async def test_watchdog_restarts_dead_task(self, make_adapter):
        """When _ws_task is done, watchdog should call _restart_ws_task."""
        adapter = make_adapter()
        adapter._running = True
        adapter._ws_task = self._make_fake_ws_task(done=True)
        adapter._restart_ws_task = MagicMock()

        task = asyncio.create_task(adapter._ws_watchdog(interval=0.05))
        await asyncio.sleep(0.12)
        adapter._running = False
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        adapter._restart_ws_task.assert_called()

    async def test_watchdog_ignores_running_task(self, make_adapter):
        """When _ws_task is alive, watchdog should not restart."""
        adapter = make_adapter()
        adapter._running = True
        adapter._ws_task = self._make_fake_ws_task(done=False)
        adapter._restart_ws_task = MagicMock()

        task = asyncio.create_task(adapter._ws_watchdog(interval=0.05))
        await asyncio.sleep(0.12)
        adapter._running = False
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        adapter._restart_ws_task.assert_not_called()

    async def test_watchdog_ignores_none_task(self, make_adapter):
        """When _ws_task is None, watchdog should restart."""
        adapter = make_adapter()
        adapter._running = True
        adapter._ws_task = None
        adapter._restart_ws_task = MagicMock()

        task = asyncio.create_task(adapter._ws_watchdog(interval=0.05))
        await asyncio.sleep(0.12)
        adapter._running = False
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        adapter._restart_ws_task.assert_called()

    async def test_watchdog_stops_when_not_running(self, make_adapter):
        """When _running is False, watchdog should not restart."""
        adapter = make_adapter()
        adapter._running = False
        adapter._ws_task = self._make_fake_ws_task(done=True)
        adapter._restart_ws_task = MagicMock()

        task = asyncio.create_task(adapter._ws_watchdog(interval=0.05))
        await asyncio.sleep(0.10)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        adapter._restart_ws_task.assert_not_called()

    async def test_watchdog_handles_runtime_error(self, make_adapter):
        """When _restart_ws_task raises RuntimeError, watchdog logs fatal."""
        adapter = make_adapter()
        adapter._running = True
        adapter._ws_task = self._make_fake_ws_task(done=True)
        adapter._restart_ws_task = MagicMock(side_effect=RuntimeError("Event loop is closed"))
        adapter._write_runtime_status_safe = MagicMock()

        task = asyncio.create_task(adapter._ws_watchdog(interval=0.05))
        await asyncio.sleep(0.12)
        adapter._running = False
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        adapter._write_runtime_status_safe.assert_called_with(
            "fatal", platform_state="fatal",
            error_code="EVENT_LOOP_CLOSED",
            error_message="Event loop is closed",
        )


# ---------------------------------------------------------------------------
# RuntimeError protection — event loop closed scenarios
# ---------------------------------------------------------------------------

class TestRuntimeErrorProtection:

    async def test_on_ws_task_done_handles_get_running_loop_error(self, adapter):
        """When get_running_loop() raises RuntimeError, callback should not crash."""
        adapter._running = True
        adapter._write_runtime_status_safe = MagicMock()

        mock_task = MagicMock()
        mock_task.cancelled.return_value = False
        mock_task.exception.return_value = None

        with patch("asyncio.get_running_loop", side_effect=RuntimeError("no running event loop")):
            adapter._on_ws_task_done(mock_task)

        adapter._write_runtime_status_safe.assert_called_once()
        call_args = adapter._write_runtime_status_safe.call_args[0]
        assert call_args[0] == "fatal"

    def test_restart_ws_task_skips_when_not_running(self, adapter):
        adapter._running = False
        adapter._restart_ws_task()

    def test_restart_ws_task_skips_when_task_alive(self, adapter):
        adapter._running = True

        class FakeTask:
            def done(self):
                return False

        adapter._ws_task = FakeTask()
        adapter._restart_ws_task()