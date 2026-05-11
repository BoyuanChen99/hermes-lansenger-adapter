"""Tool schemas for lansenger-media-tools — what the LLM sees.

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
                    "Max 2MB per file."
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
            "at_user_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Optional list of user IDs to @mention in the message. "
                    "Only works with msgType=text (not formatText)."
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
        "Max 2MB per file. "
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
        "撤回已发送的蓝信消息。"
        "Use this to retract a message previously sent via Lansenger. "
        "You need the message ID(s) to revoke. "
        "For staff/group chat types, sender_id is required."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "message_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "要撤回的消息 ID 列表",
            },
            "chat_type": {
                "type": "string",
                "description": "消息类型: staff, group, notification, account, bot (default: bot)",
                "default": "bot",
            },
            "sender_id": {
                "type": "string",
                "description": "发送者 ID（私聊/群聊时必填）",
            },
            "sys_msg_content": {
                "type": "string",
                "description": "撤回后显示的系统提示内容（默认：'该消息已撤回'）",
            },
        },
        "required": ["message_ids"],
    },
}

LANSENGER_SEND_LINK_CARD = {
    "name": "lansenger_send_link_card",
    "description": (
        "发送蓝信 linkCard 卡片消息。"
        "Use this to send a rich link preview card to a Lansenger user or group. "
        "The card displays a title, description, icon, and clickable link."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "chat_id": {
                "type": "string",
                "description": "接收者用户 ID 或群聊 ID",
            },
            "title": {
                "type": "string",
                "description": "卡片标题（必填）",
            },
            "link": {
                "type": "string",
                "description": "卡片点击链接（必填）",
            },
            "description": {
                "type": "string",
                "description": "卡片描述文本",
            },
            "icon_link": {
                "type": "string",
                "description": "卡片图标图片链接",
            },
            "pc_link": {
                "type": "string",
                "description": "PC 端跳转链接",
            },
            "from_name": {
                "type": "string",
                "description": "卡片来源名称",
            },
            "from_icon_link": {
                "type": "string",
                "description": "来源图标图片链接",
            },
        },
        "required": ["chat_id", "title", "link"],
    },
}