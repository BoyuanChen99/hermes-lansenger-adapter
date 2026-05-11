---
name: lansenger-messaging
version: 2.1.0
category: mlops
description: Lansenger (蓝信) messaging strategy — understand text/formatText capability boundaries, choose the correct tool
trigger: When you need to send any message, file, image, or notification via Lansenger (蓝信), or when you see a lansenger_* tool in the available tools list.
---

# Lansenger Messaging Strategy

Lansenger (蓝信) has two distinct message types with different capabilities. Choosing the wrong type causes lost functionality (attachments not delivered, Markdown not rendered).

## Message Type Capability Matrix

```
┌──────────────┬──────────────┬──────────────┬──────────────┐
│  msgType     │  Markdown    │  @mention    │  Attachments │
├──────────────┼──────────────┼──────────────┼──────────────┤
│  text        │  ✗           │  ✓           │  ✓           │
│  formatText  │  ✓           │  ✗           │  ✗           │
└──────────────┴──────────────┴──────────────┴──────────────┘
```

## Tool Selection Decision Tree

### 1. Send plain text only (no formatting needed)
→ Use `lansenger_send_text`
- Set `content` to plain text
- Do not set `file_path` or `at_user_ids`
- Example: notifications, simple replies

### 2. Send Markdown-formatted text (code, tables, lists, etc.)
→ Use `lansenger_send_markdown`
- Set `content` to Markdown content
- Note: does NOT support @mentions or attachments
- Example: code output, structured reports, step-by-step instructions

### 3. Send text + attachment (file/image/video)
→ Use `lansenger_send_text`
- Set `content` to a plain-text caption
- Set `file_path` to the attachment path
- `media_type` is auto-detected, or manually set (1=video, 2=image, 3=file/document)
- Example: "Here is this week's report" + PDF file

### 4. Need both Markdown + attachment
→ **Send two separate messages:**
1. First use `lansenger_send_markdown` for the formatted text
2. Then use `lansenger_send_file` for the attachment (caption can be just the file name)
- Reason: formatText does not support attachments — a single message cannot combine both
- Example: send a Markdown analysis + accompanying chart image

### 5. Send a pure attachment (no text caption needed)
→ Use `lansenger_send_file`
- Set `file_path` to the file path
- `caption` can be empty or a brief file name
- Example: share a screenshot, send a data file

### 6. Send an image from a URL
→ Use `lansenger_send_image_url`
- Set `image_url` to the image URL
- `caption` can be empty or a brief description
- Example: share an online chart or photo link

### 7. Send a link card
→ Use `lansenger_send_link_card`
- `title` and `link` are required
- `description`, `icon_link`, `from_name` are optional
- Example: share an article link, recommend a tool

### 8. Revoke a message
→ Use `lansenger_revoke_message`
- `message_ids` is required (use the `message_id` returned from a previous send)
- `chat_type` defaults to `bot`
- Staff/group chat types require `sender_id`

## Common Mistakes

| Wrong Approach | Correct Approach |
|---------|---------|
| Use `lansenger_send_text` for Markdown | Use `lansenger_send_markdown` |
| Use `lansenger_send_markdown` with `file_path` | Send two messages: markdown + send_file |
| Use `lansenger_send_file` but want a formatted caption | Captions only support plain text; need formatting → split into two messages |
| Forget to set `chat_id` | `chat_id` is required for all send tools |

## Tips

- If unsure whether the recipient can view Markdown, prefer `lansenger_send_text` (plain text is safest)
- For long Markdown analyses, consider splitting into multiple `lansenger_send_markdown` messages (long messages have poor readability in Lansenger)
- When revoking, `sys_msg_content` lets you customize the revocation notice (default: "This message has been revoked")
- File size limit: 2MB — alert the user if their file exceeds this