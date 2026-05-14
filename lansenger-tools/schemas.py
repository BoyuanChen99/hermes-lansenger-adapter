"""Tool schemas for lansenger-tools — what the LLM sees.

Lansenger (蓝信) has multiple message/card types with different capabilities:

  ┌──────────────┬──────────────┬──────────────┬──────────────┬──────────────┐
  │  msgType     │  Markdown    │  @mention    │  Attachments │  Group Chat  │
  ├──────────────┼──────────────┼──────────────┼──────────────┼──────────────┤
  │  text        │  ✗           │  ✓           │  ✓           │  ✓           │
  │  formatText  │  ✓           │  ✓           │  ✗           │  ✓           │
  │  appArticles │  ✗           │  ✗           │  ✗           │  ✓           │
  │  appCard     │  ✗ (div)     │  ✗           │  ✗           │  ✓           │
  │  linkCard    │  ✗           │  ✗           │  ✗           │  ✓           │
  └──────────────┴──────────────┴──────────────┴──────────────┴──────────────┘

  All message types support both private and group chat. The adapter auto-routes
  to the correct endpoint based on the chat_id (private → userIdList, group → groupId).

  NOTE: formatText supports @mention (reminder) per the API spec (4.6.4.12),
  with reminder.all, reminder.userIds, and reminder.botIds fields.
  This is a newer API capability — older Lansenger versions silently accept
  the reminder field but do NOT trigger client-side @mention notifications.
  In group chat, it is recommended to include @姓名 in the text content
  when replying to someone. Private chat supports reminder but it is unnecessary.

  Card types:
  - appCard: supports isDynamic + headStatusInfo (dynamic update), single language
  - i18nAppCard: supports 5 languages, no dynamic update, reserved for future use
  - appArticles: multi-article card (图文卡片)
  - linkCard: rich link preview card (description, iconLink, fromName, fromIconLink are required)

This constraint shapes all tool designs below:
- send_text:       msgType=text   → plain text + optional file/image/video attachment
- send_markdown:   msgType=formatText → Markdown text, NO attachments (reminder supported by API but not exposed in tool)
- send_file:       msgType=text   → file/image/video only, optional plain-text caption
- send_image_url:  msgType=text   → image from URL, optional plain-text caption
- revoke_message:  retracts previously sent messages
- send_link_card:  msgType=linkCard → rich link preview card (6 required fields per spec)
- send_app_articles: msgType=appArticles → multi-article card
- send_app_card:    msgType=appCard → rich card with div-style formatting + dynamic update
- update_dynamic_card: POST /v1/messages/dynamic/update → update appCard status
- query_groups:     GET /v2/groups/fetch → list bot's groups
"""

# ─── Text message (msgType=text) ───────────────────────────────────────────
# Supports: plain text, @mentions, file/image/video attachments
# Does NOT support: Markdown formatting

LANSENGER_SEND_TEXT = {
    "name": "lansenger_send_text",
    "description": (
        "Send a text message to a Lansenger (蓝信) user or group. "
        "Uses msgType=text: supports plain text, optional @mentions, and optional "
        "file/image/video attachments. Does NOT support Markdown formatting. "
        "If you need Markdown, use lansenger_send_markdown instead. "
        "In group chats, it is recommended to include @姓名 in the text content "
        "when replying to a specific person, so others know who the message is for. "
        "Private chat also supports @mentions but they are unnecessary (only one participant). "
        "If you need both Markdown AND a file, send them as two separate messages "
        "(lansenger_send_markdown for the formatted text, then lansenger_send_file for the attachment)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "chat_id": {
                "type": "string",
                "description": (
                    "Recipient user ID or group chat ID on Lansenger. "
                    "For private messages, use the user's UID. For groups, use the group chat ID."
                ),
            },
            "content": {
                "type": "string",
                "description": (
                    "Plain text content. No Markdown. In group chat, recommended to include "
                    "@姓名 when replying to someone (e.g. '@张三 查看报告')."
                ),
            },
            "file_path": {
                "type": "string",
                "description": (
                    "Optional local file/image/video to attach. "
                    "If provided, the text serves as a caption for the attachment. "
                    "Supported: images (jpg/png/gif/webp), videos (mp4/mov), documents (pdf/xlsx/docx/zip etc). "
                    "File size limits are determined by the organization's Lansenger configuration."
                ),
            },
            "media_type": {
                "type": "integer",
                "description": (
                    "Media type hint for the attachment: 1=video, 2=image, 3=file/document. "
                    "Auto-detected from file_path extension if omitted. "
                    "NOTE: For video (mediaType=1), the Lansenger API requires 2 media IDs: "
                    "the video file first, then a cover image (first frame). "
                    "This tool auto-uploads the file; if sending video, you may need to "
                    "also upload a cover image separately."
                ),
                "enum": [1, 2, 3],
            },
            "reminder_all": {
                "type": "boolean",
                "description": (
                    "Set to true to @mention all members in a group chat. "
                    "Recommended in group chat when addressing everyone. "
                    "Private chat supports this but it is unnecessary."
                ),
            },
            "reminder_user_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "List of user IDs to @mention in a group chat. "
                    "Recommended in group chat when replying to specific people — "
                    "also include @姓名 in the content text. "
                    "Private chat supports this but it is unnecessary. "
                    "Matches the reminder.userIds field in the Lansenger API."
                ),
            },
        },
        "required": ["chat_id", "content"],
    },
}

# ─── Markdown message (msgType=formatText) ──────────────────────────────────
# Supports: Markdown formatting
# Does NOT support: @mentions, file/image/video attachments

LANSENGER_SEND_MARKDOWN = {
    "name": "lansenger_send_markdown",
    "description": (
        "Send a Markdown-formatted message to a Lansenger (蓝信) user or group. "
        "Uses msgType=formatText: supports Markdown formatting (headings, bold, italic, "
        "code blocks, lists, links, etc) and optional @mentions (reminder). "
        "In group chat, it is recommended to include @姓名 in the text content "
        "when replying to a specific person. Private chat supports @mentions "
        "but they are unnecessary (only one participant). "
        "Older Lansenger versions silently accept the reminder field without "
        "triggering client-side @mention notifications. "
        "Does NOT support file/image/video attachments. "
        "If you need both Markdown AND a file, send them as two separate messages "
        "(this tool for the formatted text, then lansenger_send_file for the attachment)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "chat_id": {
                "type": "string",
                "description": "Recipient user ID or group chat ID on Lansenger.",
            },
            "content": {
                "type": "string",
                "description": (
                    "Markdown-formatted content. "
                    "Supports: headings, bold, italic, code blocks, inline code, "
                    "lists, links, tables. "
                    "In group chat, recommended to include @姓名 when replying to someone "
                    "(e.g. '@张三 请查收报告'). "
                    "Does NOT support: attachments."
                ),
            },
            "reminder_all": {
                "type": "boolean",
                "description": (
                    "Set to true to @mention all members in a group chat. "
                    "Recommended in group chat when addressing everyone. "
                    "Private chat supports this but it is unnecessary. "
                    "Older Lansenger versions silently accept this without triggering notification."
                ),
            },
            "reminder_user_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "List of user IDs to @mention in a group chat. "
                    "Recommended in group chat when replying to specific people — "
                    "also include @姓名 in the content text. "
                    "Private chat supports this but it is unnecessary. "
                    "Older Lansenger versions silently accept this without triggering notification."
                ),
            },
        },
        "required": ["chat_id", "content"],
    },
}

# ─── File/image/video only (msgType=text, no text body) ────────────────────

LANSENGER_SEND_FILE = {
    "name": "lansenger_send_file",
    "description": (
        "Send a local file, image, or video to a Lansenger (蓝信) user or group. "
        "Uses msgType=text with attachment only (no text body). "
        "For text+attachment combo, use lansenger_send_text instead. "
        "Supported: images (jpg/png/gif/webp), videos (mp4/mov/avi), documents (pdf/xlsx/docx/zip etc). "
        "File size limits are determined by the organization's Lansenger configuration. "
        "For sending an image from a URL, use lansenger_send_image_url instead."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "chat_id": {
                "type": "string",
                "description": (
                    "Recipient user ID or group chat ID on Lansenger."
                ),
            },
            "file_path": {
                "type": "string",
                "description": "Absolute or relative path to the local file. Must exist on disk.",
            },
            "caption": {
                "type": "string",
                "description": (
                    "Optional plain-text caption for the file (no Markdown). "
                    "If you need Markdown text alongside a file, "
                    "use lansenger_send_markdown first, then this tool separately."
                ),
            },
            "media_type": {
                "type": "integer",
                "description": (
                    "Media type hint: 1=video, 2=image, 3=file/document (default: auto-detect from extension)."
                ),
                "enum": [1, 2, 3],
            },
        },
        "required": ["chat_id", "file_path"],
    },
}

LANSENGER_SEND_IMAGE_URL = {
    "name": "lansenger_send_image_url",
    "description": (
        "Send an image from a URL to a Lansenger (蓝信) user or group. "
        "Uses msgType=text with image attachment only. "
        "The image is downloaded first, then uploaded to Lansenger's media server. "
        "For a local file, use lansenger_send_file instead. "
        "For text+image combo, use lansenger_send_text instead."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "chat_id": {
                "type": "string",
                "description": "Recipient user ID or group chat ID on Lansenger.",
            },
            "image_url": {
                "type": "string",
                "description": "URL of the image to download and send.",
            },
            "caption": {
                "type": "string",
                "description": "Optional plain-text caption (no Markdown).",
            },
        },
        "required": ["chat_id", "image_url"],
    },
}

# ─── Message management ────────────────────────────────────────────────────

LANSENGER_REVOKE_MESSAGE = {
    "name": "lansenger_revoke_message",
    "description": (
        "Revoke a previously sent Lansenger (蓝信) message. "
        "Shows a fixed system message to the receiver indicating the message was revoked. "
        "Only 'bot' (private chat) and 'group' chat types are supported. "
        "For group chat, sender_id is required. "
        "Note: Custom sysMsg text/icon is NOT supported — the system message is fixed."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "message_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of message IDs to revoke",
            },
            "chat_type": {
                "type": "string",
                "description": "'bot' (private bot chat) or 'group' (group chat). Default: bot.",
                "enum": ["bot", "group"],
                "default": "bot",
            },
            "sender_id": {
                "type": "string",
                "description": "Required for group chat (staffId of the sender). Not required for bot type.",
            },
        },
        "required": ["message_ids"],
    },
}

LANSENGER_SEND_LINK_CARD = {
    "name": "lansenger_send_link_card",
    "description": (
        "Send a linkCard message to a Lansenger (蓝信) user or group. "
        "Use this to send a rich link preview card with title, description, icon, and source info. "
        "Per the Lansenger API spec, title, description, iconLink, link, fromName, and fromIconLink "
        "are all required fields. pc_link is optional."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "chat_id": {
                "type": "string",
                "description": "Recipient user ID or group chat ID on Lansenger",
            },
            "title": {
                "type": "string",
                "description": "Card title (required per API spec)",
            },
            "link": {
                "type": "string",
                "description": "Card click-through link (required per API spec)",
            },
            "description": {
                "type": "string",
                "description": "Card description text (required per API spec)",
            },
            "icon_link": {
                "type": "string",
                "description": "Card icon image URL (required per API spec)",
            },
            "from_name": {
                "type": "string",
                "description": "Card source name (required per API spec)",
            },
            "from_icon_link": {
                "type": "string",
                "description": "Source icon image URL (required per API spec)",
            },
            "pc_link": {
                "type": "string",
                "description": "PC client redirect link (optional)",
            },
        },
        "required": ["chat_id", "title", "link", "description", "icon_link", "from_name", "from_icon_link"],
    },
}

LANSENGER_SEND_APP_ARTICLES = {
    "name": "lansenger_send_app_articles",
    "description": (
        "Send an appArticles (图文卡片) multi-article card to a Lansenger (蓝信) user or group. "
        "Each article entry has an image, title, and clickable link. "
        "Use this to share a collection of articles or news items in a single card. "
        "For a single link card, use lansenger_send_link_card instead. "
        "For rich formatted cards with dynamic updates, use lansenger_send_app_card instead."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "chat_id": {
                "type": "string",
                "description": "Recipient user ID or group chat ID on Lansenger",
            },
            "articles": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "imgUrl": {
                            "type": "string",
                            "description": "Article image URL (required)",
                        },
                        "title": {
                            "type": "string",
                            "description": "Article title (required)",
                        },
                        "url": {
                            "type": "string",
                            "description": "Article content link URL (required)",
                        },
                        "pcUrl": {
                            "type": "string",
                            "description": "PC client content link URL (optional per API spec)",
                        },
                        "summary": {
                            "type": "string",
                            "description": "Optional article summary text",
                        },
                    },
                    "required": ["imgUrl", "title", "url"],
                },
                "description": "List of article entries (1 or more). Each must have imgUrl, title, url. pcUrl is optional.",
            },
        },
        "required": ["chat_id", "articles"],
    },
}

LANSENGER_SEND_APP_CARD = {
    "name": "lansenger_send_app_card",
    "description": (
        "Send an appCard (应用卡片) rich formatted card to a Lansenger (蓝信) user or group. "
        "appCard supports div-style HTML formatting (color, font-size, text-align, text-indent) "
        "in bodyTitle, bodySubTitle, bodyContent, and signature fields. "
        "Set is_dynamic=true to enable in-place status updates via lansenger_update_dynamic_card "
        "(e.g. approval workflows: pending → approved/rejected). "
        "bodyContent text-indent must always be 0em (bare 0 causes API failure)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "chat_id": {
                "type": "string",
                "description": "Recipient user ID or group chat ID on Lansenger",
            },
            "body_title": {
                "type": "string",
                "description": (
                    "Card body title (required, max 600 bytes). "
                    "Supports div-style: color, font-size, text-align."
                ),
            },
            "head_title": {
                "type": "string",
                "description": "Card header title (max 96 bytes)",
            },
            "body_sub_title": {
                "type": "string",
                "description": (
                    "Card body subtitle (max 1200 bytes). "
                    "Supports div-style: color, font-size, text-align."
                ),
            },
            "body_content": {
                "type": "string",
                "description": (
                    "Card body content (max 3000 bytes). "
                    "Supports div-style: color, font-size, text-align, text-indent. "
                    "Always use text-indent:0em to avoid unwanted indentation."
                ),
            },
            "signature": {
                "type": "string",
                "description": "Card signature line (max 96 bytes). Supports color.",
            },
            "fields": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "key": {"type": "string"},
                        "value": {"type": "string"},
                    },
                },
                "description": (
                    "Key-value pairs (max 10 pairs). "
                    "Key max 18 bytes, value max 192 bytes per pair. "
                    "Both support color div-style."
                ),
            },
            "links": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "url": {"type": "string"},
                    },
                },
                "description": "Link entries (max 3 pairs). Title supports color and text-align.",
            },
            "is_dynamic": {
                "type": "boolean",
                "description": (
                    "Enable dynamic card updates (default: false). "
                    "When true, the card can be updated in-place via lansenger_update_dynamic_card."
                ),
                "default": False,
            },
            "head_status_info": {
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "Status description (max 30 bytes, required when is_dynamic=true). Supports color div-style.",
                    },
                    "colour": {
                        "type": "string",
                        "description": "Solid circle status color (e.g. #FFB116 amber, #198754 green, #dc3545 red)",
                    },
                    "iconLink": {
                        "type": "string",
                        "description": "Status icon URL",
                    },
                },
                "description": "Dynamic card status info. Required when is_dynamic=true.",
            },
            "card_link": {
                "type": "string",
                "description": "Card click-through link",
            },
            "pc_card_link": {
                "type": "string",
                "description": "PC client click-through link",
            },
            "staff_id": {
                "type": "string",
                "description": "Staff openId for showing sender avatar",
            },
            "head_icon_url": {
                "type": "string",
                "description": "Header icon URL",
            },
        },
        "required": ["chat_id", "body_title"],
    },
}

LANSENGER_UPDATE_DYNAMIC_CARD = {
    "name": "lansenger_update_dynamic_card",
    "description": (
        "Update a dynamic appCard's status in-place (e.g. approval: pending → approved/rejected). "
        "The card must have been sent with is_dynamic=true via lansenger_send_app_card. "
        "Uses the Lansenger dynamic update API to change headStatusInfo and optionally links."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "msg_id": {
                "type": "string",
                "description": "The message ID from the original lansenger_send_app_card response (required)",
            },
            "head_status_info": {
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "Updated status description (max 30 bytes). Supports color div-style.",
                    },
                    "colour": {
                        "type": "string",
                        "description": "Updated status color (e.g. #198754 green for approved, #dc3545 red for rejected)",
                    },
                    "iconLink": {
                        "type": "string",
                        "description": "Updated status icon URL",
                    },
                },
                "description": "Updated status info for the card header.",
            },
            "links": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "url": {"type": "string"},
                    },
                },
                "description": "Updated link entries (max 3 pairs). Title supports color and text-align.",
            },
            "is_last_update": {
                "type": "boolean",
                "description": (
                    "True = final state update, card becomes static and cannot be updated further "
                    "(default: false). Set true for approved/rejected final states."
                ),
                "default": False,
            },
        },
        "required": ["msg_id"],
    },
}

LANSENGER_QUERY_GROUPS = {
    "name": "lansenger_query_groups",
    "description": (
        "Query the bot's group ID list on Lansenger (蓝信). "
        "Returns the total number of groups and a list of group IDs. "
        "Use this to discover available group chat IDs before sending messages to groups."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "page_offset": {
                "type": "integer",
                "description": "Page number (default: 1)",
                "default": 1,
            },
            "page_size": {
                "type": "integer",
                "description": "Number of groups per page (max 100, default: 100)",
                "default": 100,
            },
        },
    },
}