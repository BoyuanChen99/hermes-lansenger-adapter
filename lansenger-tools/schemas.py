"""Tool schemas for lansenger-tools — what the LLM sees.

Lansenger (蓝信) has TWO distinct message types with different capabilities:

  ┌──────────────┬──────────────┬──────────────┬──────────────┐
  │  msgType     │  Markdown    │  @mention    │  Attachments │
  ├──────────────┼──────────────┼──────────────┼──────────────┤
  │  text        │  ✗           │  ✓           │  ✓           │
  │  formatText  │  ✓           │  ✗           │  ✗           │
  └──────────────┴──────────────┴──────────────┴──────────────┘

This constraint shapes all tool designs below:
- send_text:       msgType=text   → plain text + optional file/image/video attachment
- send_markdown:   msgType=formatText → Markdown text, NO attachments
- send_file:       msgType=text   → file/image/video only, optional plain-text caption
- send_image_url:  msgType=text   → image from URL, optional plain-text caption
- revoke_message:  retracts previously sent messages
- send_link_card:  msgType=linkCard → rich link preview card
"""

# ─── Text message (msgType=text) ───────────────────────────────────────────
# Supports: plain text, @mentions, file/image/video attachments
# Does NOT support: Markdown formatting

LANSENGER_SEND_TEXT = {
    "name": "lansenger_send_text",
    "description": (
        "Send a text message to a Lansenger (蓝信) user or group. "
        "Uses msgType=text: supports plain text, @mentions, and optional "
        "file/image/video attachments. Does NOT support Markdown formatting. "
        "If you need Markdown, use lansenger_send_markdown instead. "
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
                "description": "Plain text content. No Markdown support. For Markdown, use lansenger_send_markdown.",
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
                    "Auto-detected from file_path extension if omitted."
                ),
                "enum": [1, 2, 3],
            },
            "reminder_all": {
                "type": "boolean",
                "description": (
                    "Set to true to @mention all members in a group chat. "
                    "Only works with msgType=text in group/staff chat. "
                    "Private chats do not support @mentions."
                ),
            },
            "reminder_user_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Optional list of user IDs to @mention in a group chat. "
                    "Only works with msgType=text in group/staff chat. "
                    "Private chats do not support @mentions. "
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
        "code blocks, lists, links, etc). "
        "Does NOT support @mentions or file/image/video attachments. "
        "If you need to @mention someone, use lansenger_send_text instead. "
        "If you need both Markdown AND a file, send them as two separate messages "
        "(this tool for the formatted text, then lansenger_send_file for the attachment)."
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
            "content": {
                "type": "string",
                "description": (
                    "Markdown-formatted content. "
                    "Supports: headings, bold, italic, code blocks, inline code, "
                    "lists, links, tables. "
                    "Does NOT support: @mentions or attachments."
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
        "Use this to retract a message previously sent via Lansenger. "
        "You need the message ID(s) to revoke. "
        "For staff/group chat types, sender_id is required. "
        "Note: Lansenger displays a fixed system message after revocation — the prompt text cannot be customized."
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
                "description": "Chat type: staff, group, notification, account, bot (default: bot)",
                "default": "bot",
            },
            "sender_id": {
                "type": "string",
                "description": "Sender ID (required for staff/group chat types)",
            },
        },
        "required": ["message_ids"],
    },
}

LANSENGER_SEND_LINK_CARD = {
    "name": "lansenger_send_link_card",
    "description": (
        "Send a linkCard message to a Lansenger (蓝信) user or group. "
        "Use this to send a rich link preview card to a Lansenger user or group. "
        "The card displays a title, description, icon, and clickable link."
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
                "description": "Card title (required)",
            },
            "link": {
                "type": "string",
                "description": "Card click-through link (required)",
            },
            "description": {
                "type": "string",
                "description": "Card description text",
            },
            "icon_link": {
                "type": "string",
                "description": "Card icon image link",
            },
            "pc_link": {
                "type": "string",
                "description": "PC client redirect link",
            },
            "from_name": {
                "type": "string",
                "description": "Card source name",
            },
            "from_icon_link": {
                "type": "string",
                "description": "Source icon image link",
            },
        },
        "required": ["chat_id", "title", "link"],
    },
}