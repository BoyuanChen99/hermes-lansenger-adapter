"""Lansenger media-tools plugin — registration entry point.

Registers tools that allow the Agent to send messages, files, images,
videos, revoke messages, and send card messages directly to Lansenger
users and groups.

Lansenger has multiple message/card types with different capabilities:

  ┌──────────────┬──────────────┬──────────────┬──────────────┐
  │  msgType     │  Markdown    │  @mention    │  Attachments │
  ├──────────────┼──────────────┼──────────────┼──────────────┤
  │  text        │  ✗           │  ✓           │  ✓           │
  │  formatText  │  ✓           │  ✗           │  ✗           │
  │  appArticles │  ✗           │  ✗           │  ✗           │
  │  appCard     │  ✗ (div)     │  ✗           │  ✗           │
  └──────────────┴──────────────┴──────────────┴──────────────┘

- lansenger_send_text:         msgType=text → plain text + optional file/image/video
- lansenger_send_markdown:     msgType=formatText → Markdown text, NO attachments
- lansenger_send_file:         msgType=text → file/image/video only, optional caption
- lansenger_send_image_url:    msgType=text → image from URL, optional caption
- lansenger_revoke_message:    retract previously sent messages
- lansenger_send_link_card:    msgType=linkCard → rich link preview card
- lansenger_send_app_articles: msgType=appArticles → multi-article card (图文卡片)
- lansenger_send_app_card:     msgType=appCard → rich card with dynamic update support
- lansenger_update_dynamic_card: POST → update appCard status in-place
- lansenger_query_groups:      GET → list bot's group IDs

All tools use env vars (LANSENGER_APP_ID / LANSENGER_APP_SECRET) for
credentials, not load_gateway_config(), which fixes the "Lansenger not
configured" error that occurred in the old adapter-embedded handlers.
"""

import logging

from . import schemas, tools

logger = logging.getLogger("lansenger-tools")


def register(ctx):
    """Register Lansenger message, media, card, and management tools."""
    import os
    app_id = os.environ.get("LANSENGER_APP_ID", "").strip()
    app_secret = os.environ.get("LANSENGER_APP_SECRET", "").strip()

    def check_available():
        """Only show tools when Lansenger credentials are configured."""
        return bool(app_id and app_secret)

    # ─── Text message (msgType=text) ─────────────────────────────
    ctx.register_tool(
        name="lansenger_send_text",
        toolset="lansenger-tools",
        schema=schemas.LANSENGER_SEND_TEXT,
        handler=tools.lansenger_send_text,
        description="Send plain text (msgType=text) with optional file/image/video attachment. No Markdown, supports @mentions.",
        check_fn=check_available,
    )

    # ─── Markdown message (msgType=formatText) ───────────────────
    ctx.register_tool(
        name="lansenger_send_markdown",
        toolset="lansenger-tools",
        schema=schemas.LANSENGER_SEND_MARKDOWN,
        handler=tools.lansenger_send_markdown,
        description="Send Markdown-formatted text (msgType=formatText). No @mentions or attachments.",
        check_fn=check_available,
    )

    # ─── File/image/video only (msgType=text, no text body) ──────
    ctx.register_tool(
        name="lansenger_send_file",
        toolset="lansenger-tools",
        schema=schemas.LANSENGER_SEND_FILE,
        handler=tools.lansenger_send_file,
        description="Send a local file/image/video (msgType=text, attachment only). Caption is plain text.",
        check_fn=check_available,
    )

    ctx.register_tool(
        name="lansenger_send_image_url",
        toolset="lansenger-tools",
        schema=schemas.LANSENGER_SEND_IMAGE_URL,
        handler=tools.lansenger_send_image_url,
        description="Send an image from a URL (msgType=text, attachment only). Caption is plain text.",
        check_fn=check_available,
    )

    # ─── Message management ──────────────────────────────────────
    ctx.register_tool(
        name="lansenger_revoke_message",
        toolset="lansenger-tools",
        schema=schemas.LANSENGER_REVOKE_MESSAGE,
        handler=tools.lansenger_revoke_message,
        description="Revoke a previously sent Lansenger (蓝信) message",
        check_fn=check_available,
    )

    # ─── Card messages ───────────────────────────────────────────
    ctx.register_tool(
        name="lansenger_send_link_card",
        toolset="lansenger-tools",
        schema=schemas.LANSENGER_SEND_LINK_CARD,
        handler=tools.lansenger_send_link_card,
        description="Send a linkCard message to a Lansenger (蓝信) user or group",
        check_fn=check_available,
    )

    ctx.register_tool(
        name="lansenger_send_app_articles",
        toolset="lansenger-tools",
        schema=schemas.LANSENGER_SEND_APP_ARTICLES,
        handler=tools.lansenger_send_app_articles,
        description="Send an appArticles (图文卡片) multi-article card to a Lansenger user or group",
        check_fn=check_available,
    )

    ctx.register_tool(
        name="lansenger_send_app_card",
        toolset="lansenger-tools",
        schema=schemas.LANSENGER_SEND_APP_CARD,
        handler=tools.lansenger_send_app_card,
        description="Send an appCard (应用卡片) rich formatted card with optional dynamic update support",
        check_fn=check_available,
    )

    ctx.register_tool(
        name="lansenger_update_dynamic_card",
        toolset="lansenger-tools",
        schema=schemas.LANSENGER_UPDATE_DYNAMIC_CARD,
        handler=tools.lansenger_update_dynamic_card,
        description="Update a dynamic appCard's status in-place (e.g. approval: pending → approved/rejected)",
        check_fn=check_available,
    )

    # ─── Group query ─────────────────────────────────────────────
    ctx.register_tool(
        name="lansenger_query_groups",
        toolset="lansenger-tools",
        schema=schemas.LANSENGER_QUERY_GROUPS,
        handler=tools.lansenger_query_groups,
        description="Query the bot's group ID list on Lansenger (蓝信)",
        check_fn=check_available,
    )

    logger.info(
        "lansenger-tools: registered 10 tools "
        "(credentials: %s)",
        "available" if check_available() else "not configured — tools hidden",
    )