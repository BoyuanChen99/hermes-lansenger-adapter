---
name: lansenger-messaging
version: 2.4.0
category: lansenger
description: Lansenger messaging strategy — understand text/formatText capability boundary, token management, and credential storage
trigger: When you need to send any message, file, image, or notification via Lansenger (蓝信), or when you see a lansenger_* tool in the available tools list.
---

# Lansenger Messaging Strategy

Lansenger (蓝信) has two distinct message types with different capabilities. Picking the wrong type causes feature loss (e.g., attachments silently dropped, Markdown not rendered).

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

### 1. Plain text only (no formatting needed)
→ `lansenger_send_text`
- content = plain text
- skip file_path, reminder_all, and reminder_user_ids
- Example: notifications, simple replies

### 2. Markdown-formatted text (code, tables, lists)
→ `lansenger_send_markdown`
- content = Markdown text
- Cannot @mention, cannot attach files
- Example: code output, structured reports, step-by-step instructions

### 3. Text + attachment (file/image/video)
→ `lansenger_send_text`
- content = plain text caption
- file_path = local file path
- media_type auto-detected, or manually set (1=video, 2=image, 3=file)
- Example: "Here is this week's report" + PDF file

### 4. Markdown + attachment (need both)
→ **Send TWO separate messages:**
1. `lansenger_send_markdown` for the formatted text
2. `lansenger_send_file` for the attachment (caption can be the filename)
- Reason: formatText cannot carry attachments — one message cannot do both
- Example: a Markdown analysis + a chart image

### 5. Pure attachment (no text needed)
→ `lansenger_send_file`
- file_path = path
- caption can be empty or just the filename
- Example: send a screenshot, send a data file

### 6. Image from URL
→ `lansenger_send_image_url`
- image_url = URL
- caption can be empty or a brief description
- Example: send an online chart URL

### 7. Link card
→ `lansenger_send_link_card`
- title + link are required
- description, icon_link, from_name are optional
- Example: share an article, recommend a tool

### 8. Revoke a message
→ `lansenger_revoke_message`
- message_ids is required (from a previous send's response)
- chat_type defaults to "bot"
- staff/group types require sender_id
- **Note:** Lansenger shows a fixed system prompt after revocation — the text cannot be customized

## Token Management

All lansenger-tools use HTTP API calls, NOT the WebSocket connection. Each tool call:

1. Creates an ephemeral LansengerAdapter instance
2. Calls `_get_app_token()` which sends an HTTP GET to `/v1/apptoken/create` with app_id + app_secret
3. Receives an appToken with a 2-hour expiry (7200s, refreshed 5 min before expiry)
4. Uses the token in the actual API call
5. Tears down the ephemeral adapter after the call

**Key facts:**
- The WebSocket token (used for receiving messages) is different from the HTTP appToken (used for sending)
- Tools always use HTTP — they never touch the WebSocket connection or its token
- Token is cached per ephemeral adapter instance (auto-refreshed before expiry)
- No manual token management is needed — the adapter handles it internally

## Credential Storage

| Item | Location | Format |
|------|----------|--------|
| APP_ID + APP_SECRET | `~/.hermes/.env` or `config.yaml` platforms.lansenger.extra | LANSENGER_APP_ID / LANSENGER_APP_SECRET env vars |
| API Gateway URL | `~/.hermes/.env` or `config.yaml` platforms.lansenger.extra | LANSENGER_API_GATEWAY_URL (default: `https://open.e.lanxin.cn/open/apigw`) |
| Owner ID | `~/.hermes/lansenger_owner.json` | {"owner_id": "2285568-..."} — auto-set on first bot-to-owner message |
| Home Channel | `config.yaml` platforms.lansenger.home_channel | Standard Hermes home_channel config |

**Credential resolution order:**
1. `config.yaml` → platforms.lansenger.extra.app_id / app_secret
2. Falls back to env vars LANSENGER_APP_ID / LANSENGER_APP_SECRET from `.env`

## Common Mistakes

| Wrong | Right |
|-------|-------|
| `lansenger_send_text` with Markdown content | Use `lansenger_send_markdown` |
| `lansenger_send_markdown` with file_path | Send two separate messages: markdown + send_file |
| `lansenger_send_file` expecting formatted caption | Captions are plain text only; split into two messages for formatting |
| Forgetting chat_id | chat_id is required for ALL send tools |
| Expecting custom revocation text | Lansenger shows a fixed system message — not customizable |

## Tips

- If unsure whether the recipient can render Markdown, prefer `lansenger_send_text` (plain text is safest)
- For long Markdown analyses, consider splitting into multiple `lansenger_send_markdown` calls (long messages have poor readability in Lansenger)
- File size limits are determined by the organization's Lansenger configuration (not a fixed 2MB cap)
- The ephemeral adapter pattern means each tool call is independent — no state carries over between calls