"""Tool handlers for lansenger-media-tools — send files/images/videos via Lansenger API.

Design: Uses an ephemeral LansengerAdapter instance per invocation.
This avoids holding long-lived connections and works correctly from
synchronous tool handlers by running async code via asyncio.run().
"""

import asyncio
import json
import logging
import os
import tempfile

logger = logging.getLogger("lansenger-media-tools")

# --- Auto-detect media_type from file extension ---
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
_VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".3gp"}


def _media_type_from_path(file_path: str) -> int:
    """Guess media_type (1=video, 2=image, 3=file) from file extension."""
    ext = os.path.splitext(file_path)[1].lower()
    if ext in _IMAGE_EXTS:
        return 2
    if ext in _VIDEO_EXTS:
        return 1
    return 3


_ADAPTER_CLASS = None  # lazy cache


def _get_adapter_class():
    """Lazily import LansengerAdapter from the platform plugin.

    The platform plugin is loaded before tool plugins, so the gateway
    module is available at runtime. We try multiple import paths for
    robustness:
    1. Standard gateway path (Hermes runtime)
    2. User-plugins path (fallback)
    """
    global _ADAPTER_CLASS
    if _ADAPTER_CLASS is not None:
        return _ADAPTER_CLASS

    # Path 1: Hermes runtime — gateway module is loaded
    try:
        from gateway.platforms.lansenger.adapter import LansengerAdapter
        _ADAPTER_CLASS = LansengerAdapter
        logger.debug("Loaded LansengerAdapter from gateway.platforms.lansenger")
        return _ADAPTER_CLASS
    except ImportError:
        pass

    # Path 2: Direct import from user plugins directory
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "lansenger_adapter",
            os.path.expanduser("~/.hermes/plugins/platforms/lansenger/adapter.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _ADAPTER_CLASS = mod.LansengerAdapter
        logger.debug("Loaded LansengerAdapter from ~/.hermes/plugins (direct)")
        return _ADAPTER_CLASS
    except Exception as e:
        logger.error("Cannot load LansengerAdapter: %s", e)
        raise ImportError(
            "LansengerAdapter not found. "
            "Make sure the lansenger-platform plugin is installed and enabled."
        )


def _check_env() -> dict:
    """Verify Lansenger env vars are available. Returns config dict or error."""
    app_id = os.environ.get("LANSENGER_APP_ID", "").strip()
    app_secret = os.environ.get("LANSENGER_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        return {
            "error": (
                "Lansenger credentials not configured. "
                "Set LANSENGER_APP_ID and LANSENGER_APP_SECRET in .env or config.yaml."
            )
        }
    api_gateway = os.environ.get(
        "LANSENGER_API_GATEWAY_URL", "https://open.e.lanxin.cn/open/apigw"
    ).strip()
    return {"app_id": app_id, "app_secret": app_secret, "api_gateway_url": api_gateway}


def _make_config(env_config: dict) -> dict:
    """Build a PlatformConfig-like dict for the ephemeral adapter."""
    return {
        "extra": {
            "app_id": env_config["app_id"],
            "app_secret": env_config["app_secret"],
            "api_gateway_url": env_config["api_gateway_url"],
        }
    }


async def _send_file_async(chat_id: str, file_path: str, caption: str, media_type: int) -> dict:
    """Async implementation: create ephemeral adapter, upload, send, teardown."""
    # Import the adapter — Hermes runtime provides the gateway module;
    # the platform plugin is already loaded when this tool plugin runs.
    LansengerAdapter = _get_adapter_class()

    config = _make_config(_check_env())
    adapter = LansengerAdapter(config)
    adapter._http_client = __import__("httpx").AsyncClient(timeout=30.0)

    try:
        result = await adapter.send_file(chat_id, file_path, caption, media_type)
        await adapter._http_client.aclose()

        if result.success:
            return {
                "success": True,
                "platform": "lansenger",
                "chat_id": chat_id,
                "file_path": file_path,
                "media_type": media_type,
                "message_id": result.message_id,
            }
        else:
            return {"success": False, "error": result.error}
    except Exception as e:
        try:
            await adapter._http_client.aclose()
        except Exception:
            pass
        return {"success": False, "error": str(e)}


async def _send_image_url_async(chat_id: str, image_url: str, caption: str) -> dict:
    """Async implementation: download image from URL, then send via send_image."""
    import httpx as _httpx

    # Download image to temp file
    try:
        async with _httpx.AsyncClient() as client:
            resp = await client.get(image_url, timeout=30, follow_redirects=True)
            resp.raise_for_status()
            image_bytes = resp.content

        # Guess extension from URL or content-type
        ct = resp.headers.get("content-type", "")
        if "png" in ct:
            suffix = ".png"
        elif "gif" in ct:
            suffix = ".gif"
        elif "webp" in ct:
            suffix = ".webp"
        else:
            suffix = ".jpg"

        fd, temp_path = tempfile.mkstemp(suffix=suffix, prefix="lansenger_url_image_")
        os.write(fd, image_bytes)
        os.close(fd)
    except Exception as e:
        return {"success": False, "error": f"Failed to download image: {e}"}

    # Send via send_file (media_type=2 for image)
    try:
        result = await _send_file_async(chat_id, temp_path, caption, media_type=2)
        # Clean up temp file
        try:
            os.remove(temp_path)
        except OSError:
            pass
        return result
    except Exception as e:
        try:
            os.remove(temp_path)
        except OSError:
            pass
        return {"success": False, "error": str(e)}


# --- Synchronous handlers (called by Hermes tool registry) ---


def lansenger_send_file(args: dict, **kwargs) -> str:
    """Send a local file to a Lansenger user/group.

    Handler contract: receive args dict, return JSON string.
    Never raise — catch all exceptions, return error JSON.
    """
    chat_id = args.get("chat_id", "").strip()
    file_path = args.get("file_path", "").strip()
    caption = args.get("caption", "").strip()
    media_type = args.get("media_type")

    if not chat_id:
        return json.dumps({"error": "chat_id is required"})
    if not file_path:
        return json.dumps({"error": "file_path is required"})

    # Resolve relative paths
    if not os.path.isabs(file_path):
        file_path = os.path.abspath(file_path)

    # Check file exists
    if not os.path.isfile(file_path):
        return json.dumps({"error": f"File not found: {file_path}"})

    # Auto-detect media_type if not specified
    if media_type is None:
        media_type = _media_type_from_path(file_path)

    # Check env vars
    env_result = _check_env()
    if "error" in env_result:
        return json.dumps(env_result)

    # Check file size (2MB limit per Lansenger API)
    file_size = os.path.getsize(file_path)
    if file_size > 2 * 1024 * 1024:
        return json.dumps({
            "error": f"File too large: {file_size} bytes (Lansenger limit: 2MB)",
            "file_path": file_path,
        })

    # Run async code in a fresh event loop
    try:
        result = asyncio.run(
            _send_file_async(chat_id, file_path, caption, media_type)
        )
        return json.dumps(result)
    except RuntimeError as e:
        # asyncio.run() can fail if called from within an existing event loop
        # Fallback: use a thread
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                asyncio.run,
                _send_file_async(chat_id, file_path, caption, media_type),
            )
            result = future.result(timeout=30)
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


def lansenger_send_image_url(args: dict, **kwargs) -> str:
    """Send an image from a URL to a Lansenger user/group.

    Handler contract: receive args dict, return JSON string.
    """
    chat_id = args.get("chat_id", "").strip()
    image_url = args.get("image_url", "").strip()
    caption = args.get("caption", "").strip()

    if not chat_id:
        return json.dumps({"error": "chat_id is required"})
    if not image_url:
        return json.dumps({"error": "image_url is required"})

    # Check env vars
    env_result = _check_env()
    if "error" in env_result:
        return json.dumps(env_result)

    # Run async code
    try:
        result = asyncio.run(
            _send_image_url_async(chat_id, image_url, caption)
        )
        return json.dumps(result)
    except RuntimeError:
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                asyncio.run,
                _send_image_url_async(chat_id, image_url, caption),
            )
            result = future.result(timeout=30)
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})