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