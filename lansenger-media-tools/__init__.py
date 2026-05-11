"""Lansenger media-tools plugin — registration entry point.

Registers lansenger_send_file and lansenger_send_image_url tools
that allow the Agent to send files, images, and videos directly
to Lansenger (蓝信) users and groups.
"""

import logging

from . import schemas, tools

logger = logging.getLogger("lansenger-media-tools")


def register(ctx):
    """Register Lansenger media sending tools."""
    # Check if Lansenger env vars are present
    import os
    app_id = os.environ.get("LANSENGER_APP_ID", "").strip()
    app_secret = os.environ.get("LANSENGER_APP_SECRET", "").strip()

    def check_available():
        """Only show tools when Lansenger credentials are configured."""
        return bool(app_id and app_secret)

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

    logger.info(
        "lansenger-media-tools: registered lansenger_send_file + lansenger_send_image_url "
        "(credentials: %s)",
        "available" if check_available() else "not configured — tools hidden",
    )