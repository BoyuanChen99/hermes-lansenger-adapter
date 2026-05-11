"""Tool schemas for lansenger-media-tools — what the LLM sees."""

LANSENGER_SEND_FILE = {
    "name": "lansenger_send_file",
    "description": (
        "Send a local file, image, or video directly to a Lansenger (蓝信) user or group. "
        "Use this when you need to deliver a generated file, report, image, or video to a specific "
        "recipient on Lansenger. The file must exist on the local filesystem. "
        "Supported types: images (jpg/png/gif/webp), videos (mp4/mov/avi), documents (pdf/xlsx/docx/zip etc). "
        "For sending an image from a URL, use lansenger_send_image_url instead."
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
            "file_path": {
                "type": "string",
                "description": (
                    "Absolute or relative path to the local file to send. "
                    "The file must exist on disk."
                ),
            },
            "caption": {
                "type": "string",
                "description": (
                    "Optional caption or description text for the file. "
                    "Note: Lansenger media messages use plain text for captions (no Markdown). "
                    "For Markdown-formatted text, send it separately before or after the file."
                ),
            },
            "media_type": {
                "type": "integer",
                "description": (
                    "Media type hint: 1=video, 2=image, 3=file/document (default: 3). "
                    "Set to 2 for images, 1 for videos, 3 for anything else."
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
        "Send an image from a URL directly to a Lansenger (蓝信) user or group. "
        "Use this when you have an image URL (from web search, API response, etc.) "
        "and need to deliver it as a native Lansenger image message. "
        "The image is downloaded first, then uploaded to Lansenger's media server. "
        "For sending a local file, use lansenger_send_file instead."
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
            "image_url": {
                "type": "string",
                "description": "URL of the image to download and send.",
            },
            "caption": {
                "type": "string",
                "description": "Optional caption text (plain text, no Markdown support for media).",
            },
        },
        "required": ["chat_id", "image_url"],
    },
}

LANSENGER_REVOKE_MESSAGE = {
    "name": "lansenger_revoke_message",
    "description": (
        "撤回已发送的蓝信消息。"
        "Use this to retract a message that was previously sent via Lansenger. "
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