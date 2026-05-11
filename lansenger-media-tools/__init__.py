"""Lansenger media-tools plugin — registration entry point.

Registers tools that allow the Agent to send files, images, videos,
revoke messages, and send linkCard cards directly to Lansenger users
and groups.

All tools use env vars (LANSENGER_APP_ID / LANSENGER_APP_SECRET) for
credentials, not load_gateway_config(), which fixes the "Lansenger not
configured" error that occurred in the old adapter-embedded handlers.
"""

import logging

from . import schemas, tools

logger = logging.getLogger("lansenger-media-tools")


def register(ctx):
    """Register Lansenger media and message management tools."""
    # Check if Lansenger credentials are present
    import os
    app_id = os.environ.get("LANSENGER_APP_ID", "").strip()
    app_secret = os.environ.get("LANSENGER_APP_SECRET", "").strip()

    def check_available():
        """Only show tools when Lansenger credentials are configured."""
        return bool(app_id and app_secret)

    # --- Media sending tools ---
    ctx.register_tool(
        name="lansenger_send_file",
        toolset="lansenger-media",
        schema=schemas.LANSENGER_SEND_FILE,
        handler=tools.lansenger_send_file,
        description="Send a local file, image, or video to a Lansenger user or group",
        check_fn=check_available,
    )

    ctx.register_tool(
        name="lansenger_send_image_url",
        toolset="lansenger-media",
        schema=schemas.LANSENGER_SEND_IMAGE_URL,
        handler=tools.lansenger_send_image_url,
        description="Send an image from a URL to a Lansenger user or group",
        check_fn=check_available,
    )

    # --- Message management tools ---
    ctx.register_tool(
        name="lansenger_revoke_message",
        toolset="lansenger-media",
        schema=schemas.LANSENGER_REVOKE_MESSAGE,
        handler=tools.lansenger_revoke_message,
        description="撤回已发送的蓝信消息",
        check_fn=check_available,
    )

    ctx.register_tool(
        name="lansenger_send_link_card",
        toolset="lansenger-media",
        schema=schemas.LANSENGER_SEND_LINK_CARD,
        handler=tools.lansenger_send_link_card,
        description="发送蓝信 linkCard 卡片消息",
        check_fn=check_available,
    )

    logger.info(
        "lansenger-media-tools: registered 4 tools "
        "(lansenger_send_file, lansenger_send_image_url, "
        "lansenger_revoke_message, lansenger_send_link_card) "
        "(credentials: %s)",
        "available" if check_available() else "not configured — tools hidden",
    )