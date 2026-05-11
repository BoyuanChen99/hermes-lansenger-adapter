"""Tool handlers for lansenger-media-tools — send messages, files, images, manage messages via Lansenger API.

Lansenger (蓝信) has TWO distinct message types with different capabilities:

  ┌──────────────┬──────────────┬──────────────┬──────────────┐
  │  msgType     │  Markdown    │  @mention    │  Attachments │
  ├──────────────┼──────────────┼──────────────┼──────────────┤
  │  text        │  ✗           │  ✓           │  ✓           │
  │  formatText  │  ✓           │  ✗           │  ✗           │
  └──────────────┴──────────────┴──────────────┴──────────────┘

This constraint shapes handler implementations:
- send_text:       msgType=text   → plain text + optional file/image/video attachment
- send_markdown:   msgType=formatText → Markdown text, NO attachments
- send_file:       msgType=text   → file/image/video only, optional plain-text caption
- send_image_url:  msgType=text   → image from URL, optional plain-text caption

Design: Uses an ephemeral LansengerAdapter instance per invocation.
Credentials are read from LANSENGER_APP_ID / LANSENGER_APP_SECRET env vars
(not from load_gateway_config), which fixes the "Lansenger not configured"
error that occurred in the old adapter-embedded handlers.
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


def _run_async(coro):
    """Run an async coroutine from a synchronous context.

    Uses asyncio.run() in a fresh event loop, with a thread-pool fallback
    for cases where an event loop is already running (e.g. in gateway mode).
    """
    try:
        return asyncio.run(coro)
    except RuntimeError:
        # asyncio.run() fails inside an existing event loop
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result(timeout=30)


# --- Async implementations (shared by all handlers) ---


async def _create_ephemeral_adapter() -> tuple:
    """Create an ephemeral LansengerAdapter with env-based config.

    Returns (adapter, http_client) tuple. Caller must close http_client.
    """
    import httpx

    LansengerAdapter = _get_adapter_class()
    env_config = _check_env()
    if "error" in env_config:
        raise ValueError(env_config["error"])

    config = _make_config(env_config)
    adapter = LansengerAdapter(config)
    adapter._http_client = httpx.AsyncClient(timeout=30.0)
    return adapter


async def _send_text_async(chat_id: str, content: str,
                            file_path: str = "", media_type: int = 3,
                            at_user_ids: list = None) -> dict:
    """Async: send plain text message (msgType=text), optionally with attachment."""
    adapter = await _create_ephemeral_adapter()
    try:
        if file_path and os.path.isfile(file_path):
            # Upload media first, then send text+media
            media_id = await adapter.upload_media_file(file_path, media_type)
            if media_id:
                result = await adapter.send_text_with_media(
                    chat_id, content, media_type, [media_id]
                )
            else:
                # Upload failed — fall back to pure text
                logger.warning("[Lansenger] Media upload failed, sending plain text only")
                result = await adapter.send_text(chat_id, content)
        else:
            # Pure text, no attachment
            result = await adapter.send_text(chat_id, content)

        await adapter._http_client.aclose()
        return {
            "success": result.success,
            "message_id": result.message_id,
            "error": result.error,
            "platform": "lansenger",
            "msg_type": "text",
        }
    except Exception as e:
        try:
            await adapter._http_client.aclose()
        except Exception:
            pass
        return {"success": False, "error": str(e)}


async def _send_markdown_async(chat_id: str, content: str) -> dict:
    """Async: send Markdown-formatted message (msgType=formatText)."""
    adapter = await _create_ephemeral_adapter()
    try:
        result = await adapter.send_format_text(chat_id, content)
        await adapter._http_client.aclose()
        return {
            "success": result.success,
            "message_id": result.message_id,
            "error": result.error,
            "platform": "lansenger",
            "msg_type": "formatText",
        }
    except Exception as e:
        try:
            await adapter._http_client.aclose()
        except Exception:
            pass
        return {"success": False, "error": str(e)}


async def _send_file_async(chat_id: str, file_path: str, caption: str, media_type: int) -> dict:
    """Async: send file/image/video only (msgType=text, attachment only)."""
    adapter = await _create_ephemeral_adapter()
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
    """Async: download image from URL, then send via send_file."""
    import httpx as _httpx

    try:
        async with _httpx.AsyncClient() as client:
            resp = await client.get(image_url, timeout=30, follow_redirects=True)
            resp.raise_for_status()
            image_bytes = resp.content

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

    try:
        result = await _send_file_async(chat_id, temp_path, caption, media_type=2)
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


async def _revoke_async(message_ids: list, chat_type: str, sender_id: str, sys_msg_content: str) -> dict:
    """Async: create ephemeral adapter, revoke messages, teardown."""
    adapter = await _create_ephemeral_adapter()
    try:
        result = await adapter.revoke_message(
            message_ids=message_ids,
            chat_type=chat_type,
            sender_id=sender_id,
            sys_msg_content=sys_msg_content,
        )
        await adapter._http_client.aclose()
        return {
            "success": result.success,
            "error": result.error,
            "platform": "lansenger",
            "operation": "revoke",
        }
    except Exception as e:
        try:
            await adapter._http_client.aclose()
        except Exception:
            pass
        return {"success": False, "error": str(e)}


async def _send_link_card_async(chat_id: str, title: str, link: str,
                                 description: str = "", icon_link: str = "",
                                 pc_link: str = "", from_name: str = "",
                                 from_icon_link: str = "") -> dict:
    """Async: create ephemeral adapter, send linkCard, teardown."""
    adapter = await _create_ephemeral_adapter()
    try:
        result = await adapter.send_link_card(
            chat_id=chat_id,
            title=title,
            link=link,
            description=description,
            icon_link=icon_link,
            pc_link=pc_link,
            from_name=from_name,
            from_icon_link=from_icon_link,
        )
        await adapter._http_client.aclose()
        return {
            "success": result.success,
            "message_id": result.message_id,
            "error": result.error,
            "platform": "lansenger",
            "operation": "linkCard",
        }
    except Exception as e:
        try:
            await adapter._http_client.aclose()
        except Exception:
            pass
        return {"success": False, "error": str(e)}


# --- Synchronous handlers (called by Hermes tool registry) ---


def lansenger_send_text(args: dict, **kwargs) -> str:
    """Send a plain text message (msgType=text) with optional file/image/video attachment.

    msgType=text supports: plain text, @mentions, file/image/video attachments.
    Does NOT support: Markdown formatting.
    """
    chat_id = args.get("chat_id", "").strip()
    content = args.get("content", "").strip()
    file_path = args.get("file_path", "").strip()
    media_type = args.get("media_type")
    at_user_ids = args.get("at_user_ids") or []

    if not chat_id:
        return json.dumps({"error": "chat_id is required"})
    if not content and not file_path:
        return json.dumps({"error": "content or file_path is required (need at least one)"})

    # Resolve file path
    if file_path:
        if not os.path.isabs(file_path):
            file_path = os.path.abspath(file_path)
        if not os.path.isfile(file_path):
            return json.dumps({"error": f"File not found: {file_path}"})
        if media_type is None:
            media_type = _media_type_from_path(file_path)
        file_size = os.path.getsize(file_path)
        if file_size > 2 * 1024 * 1024:
            return json.dumps({
                "error": f"File too large: {file_size} bytes (Lansenger limit: 2MB)",
            })

    env_result = _check_env()
    if "error" in env_result:
        return json.dumps(env_result)

    try:
        result = _run_async(_send_text_async(chat_id, content, file_path,
                                              media_type or 3, at_user_ids))
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


def lansenger_send_markdown(args: dict, **kwargs) -> str:
    """Send a Markdown-formatted message (msgType=formatText).

    msgType=formatText supports: Markdown formatting.
    Does NOT support: @mentions, file/image/video attachments.
    """
    chat_id = args.get("chat_id", "").strip()
    content = args.get("content", "").strip()

    if not chat_id:
        return json.dumps({"error": "chat_id is required"})
    if not content:
        return json.dumps({"error": "content is required"})

    env_result = _check_env()
    if "error" in env_result:
        return json.dumps(env_result)

    try:
        result = _run_async(_send_markdown_async(chat_id, content))
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


def lansenger_send_file(args: dict, **kwargs) -> str:
    """Send a local file/image/video only (msgType=text, no text body)."""
    chat_id = args.get("chat_id", "").strip()
    file_path = args.get("file_path", "").strip()
    caption = args.get("caption", "").strip()
    media_type = args.get("media_type")

    if not chat_id:
        return json.dumps({"error": "chat_id is required"})
    if not file_path:
        return json.dumps({"error": "file_path is required"})

    if not os.path.isabs(file_path):
        file_path = os.path.abspath(file_path)

    if not os.path.isfile(file_path):
        return json.dumps({"error": f"File not found: {file_path}"})

    if media_type is None:
        media_type = _media_type_from_path(file_path)

    env_result = _check_env()
    if "error" in env_result:
        return json.dumps(env_result)

    file_size = os.path.getsize(file_path)
    if file_size > 2 * 1024 * 1024:
        return json.dumps({
            "error": f"File too large: {file_size} bytes (Lansenger limit: 2MB)",
            "file_path": file_path,
        })

    try:
        result = _run_async(_send_file_async(chat_id, file_path, caption, media_type))
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


def lansenger_send_image_url(args: dict, **kwargs) -> str:
    """Send an image from a URL to a Lansenger user/group."""
    chat_id = args.get("chat_id", "").strip()
    image_url = args.get("image_url", "").strip()
    caption = args.get("caption", "").strip()

    if not chat_id:
        return json.dumps({"error": "chat_id is required"})
    if not image_url:
        return json.dumps({"error": "image_url is required"})

    env_result = _check_env()
    if "error" in env_result:
        return json.dumps(env_result)

    try:
        result = _run_async(_send_image_url_async(chat_id, image_url, caption))
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


def lansenger_revoke_message(args: dict, **kwargs) -> str:
    """撤回已发送的蓝信消息。

    Uses env vars for credentials (fixes "Lansenger not configured" error).
    """
    message_ids = args.get("message_ids", [])
    chat_type = args.get("chat_type", "bot")
    sender_id = args.get("sender_id") or ""
    sys_msg_content = args.get("sys_msg_content") or ""

    if not message_ids:
        return json.dumps({"error": "message_ids is required"})

    env_result = _check_env()
    if "error" in env_result:
        return json.dumps(env_result)

    if chat_type in ("staff", "group") and not sender_id:
        return json.dumps({
            "error": f"chat_type='{chat_type}' requires sender_id",
        })

    try:
        result = _run_async(_revoke_async(message_ids, chat_type, sender_id, sys_msg_content))
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


def lansenger_send_link_card(args: dict, **kwargs) -> str:
    """发送蓝信 linkCard 卡片消息。"""
    chat_id = args.get("chat_id", "").strip()
    title = args.get("title", "").strip()
    link = args.get("link", "").strip()
    description = args.get("description") or ""
    icon_link = args.get("icon_link") or ""
    pc_link = args.get("pc_link") or ""
    from_name = args.get("from_name") or ""
    from_icon_link = args.get("from_icon_link") or ""

    if not chat_id:
        return json.dumps({"error": "chat_id is required"})
    if not title:
        return json.dumps({"error": "title is required"})
    if not link:
        return json.dumps({"error": "link is required"})

    env_result = _check_env()
    if "error" in env_result:
        return json.dumps(env_result)

    try:
        result = _run_async(
            _send_link_card_async(chat_id, title, link, description,
                                  icon_link, pc_link, from_name, from_icon_link)
        )
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})