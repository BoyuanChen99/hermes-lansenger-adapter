---
name: lansenger-messaging
version: 2.6.1
category: lansenger
description: Lansenger messaging strategy — understand text/formatText/appCard/appArticles capability boundary, token management, and credential storage
trigger: When you need to send any message, file, image, card, or notification via Lansenger (蓝信), or when you see a lansenger_* tool in the available tools list.
---

# Lansenger Messaging Strategy

Lansenger (蓝信) has multiple message types with different capabilities. Picking the wrong type causes feature loss (e.g., attachments silently dropped, Markdown not rendered, dynamic updates not working).

## Message Type Capability Matrix

```
┌──────────────┬──────────────┬──────────────┬──────────────┬──────────────┐
│  msgType     │  Markdown    │  @mention    │  Attachments │  Group Chat  │
├──────────────┼──────────────┼──────────────┼──────────────┼──────────────┤
│  text        │  ✗           │  ✓           │  ✓           │  ✓           │
│  formatText  │  ✓           │  ✓           │  ✗           │  ✓           │
│  appArticles │  ✗           │  ✗           │  ✗           │  ✓           │
│  appCard     │  ✗ (div)     │  ✗           │  ✗           │  ✓           │
│  linkCard    │  ✗           │  ✗           │  ✗           │  ✓           │
└──────────────┴──────────────┴──────────────┴──────────────┴──────────────┘
```

NOTE: formatText supports @mention (reminder) per API spec 4.6.4.12, but this
is a newer capability. Older Lansenger versions silently accept the reminder
field without triggering client-side @mention notifications. Newer versions
trigger the notification. In group chat, it is recommended to include @姓名
in the text content (e.g. "@张三 请查看报告") so people know who the reply is for.
Private chat also supports reminder but it is unnecessary (only one participant).

NOTE: linkCard has 6 required fields per API spec 4.6.4.4: title, description,
iconLink, link, fromName, fromIconLink. The `lansenger_send_link_card` schema
enforces all of them.

NOTE: For video (mediaType=1), the API requires 2 mediaIds: [videoId, coverImageId].

All message types support both private and group chat. The adapter auto-routes:
- Private chat → `/v1/bot/messages/create` with `userIdList`
- Group chat → `/v1/messages/group/create` with `groupId`
Group detection uses `_chat_type_map` populated from inbound messages and persisted to `~/.hermes/lansenger_chat_types.json` for cross-process reuse (ephemeral tools load this file).

## Card Type Capability Matrix

```
┌──────────────┬──────────────┬──────────────┬──────────────┐
│  Card Type   │  Multi-lang  │  Dynamic     │  headStatus  │
│              │  (5 langs)   │  Update      │  Info        │
├──────────────┼──────────────┼──────────────┼──────────────┤
│  appCard     │  ✗           │  ✓           │  ✓           │
│  i18nAppCard │  ✓           │  ✗           │  ✗           │
└──────────────┴──────────────┴──────────────┴──────────────┘
```

**Key distinction:**
- **appCard** — supports `isDynamic` + `headStatusInfo` for in-place status updates, but uses a single language per card. Language is detected per user and content is sent in the detected language.
- **i18nAppCard** — supports 5 languages (zhHans/zhHant/zhHantHK/en/fr) in one message, but does NOT support dynamic updates or `headStatusInfo`. **Reserved for future use**.
- **DynamicMsg appCard** — the update payload for appCard (`appCardUpdateMsg`), which updates `headStatusInfo` and `links` in-place. Used after approval/rejection to change card status.
- **appArticles** — multi-article card (图文卡片) with image + title + link per article. No formatting, no dynamic updates.
- **linkCard** — rich link preview card with title, description, icon, and clickable link.

## Tool Selection Decision Tree

### 1. Plain text only (no formatting needed)
→ `lansenger_send_text`
- content = plain text
- skip file_path, reminder_all, and reminder_user_ids
- Example: notifications, simple replies

### 2. Markdown-formatted text (code, tables, lists)
→ `lansenger_send_markdown`
- content = Markdown text
- Optional @mention via reminder_all / reminder_user_ids (newer API, old API silently accepts)
- In group chat, recommended to include @姓名 in text when replying to someone
- Cannot attach files
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

### 7. Link card (single link)
→ `lansenger_send_link_card`
- title + link are required
- description, icon_link, from_name are optional
- Example: share an article, recommend a tool

### 8. Multi-article card (图文卡片)
→ `lansenger_send_app_articles`
- articles = list of dicts, each with imgUrl, title, url, pcUrl (all required)
- Optional per article: summary
- Example: news digest, article collection, product showcase

### 9. AppCard (approval / confirmation / rich formatted card)
→ `lansenger_send_app_card`
- Use `is_dynamic=True` + `headStatusInfo` for approval workflows
- Language is auto-detected per user (zh/en), content is sent in detected language
- After approval/rejection, use `lansenger_update_dynamic_card` to update `headStatusInfo` in-place
- **bodyContent text-indent must use unit: `0em`** — bare `0` causes API to return empty response
- For multi-article collections, use `lansenger_send_app_articles` instead

### 10. Update dynamic card status
→ `lansenger_update_dynamic_card`
- msg_id from original `lansenger_send_app_card` response is required
- Updates `headStatusInfo` (status text + color) and optionally `links`
- Set `is_last_update=True` for final state (approved/denied) — locks the card from further updates

### 11. Revoke a message
→ `lansenger_revoke_message`
- message_ids is required (from a previous send's response)
- chat_type defaults to "bot"
- staff/group types require sender_id
- **Note:** Lansenger shows a fixed system prompt after revocation — the text cannot be customized

### 12. Query groups
→ `lansenger_query_groups`
- Returns total number of groups and list of group IDs
- Use this to discover available group chat IDs before sending messages to groups
- page_offset (default 1), page_size (default 100, max 100)

## Token Management

All lansenger-tools use HTTP API calls, NOT the WebSocket connection. The appToken is **persisted** to `~/.hermes/lansenger_token.json` for cross-process reuse.

### Token lifecycle

1. First call: sends HTTP GET to `/v1/apptoken/create` → receives appToken (2-hour expiry)
2. Persists `app_token` + `expires_at` (absolute timestamp) to `~/.hermes/lansenger_token.json`
3. Subsequent calls (from any process — gateway or ephemeral tool): load persisted token
4. If persisted token is still valid (>5 min until expiry): reuse it, skip API call
5. If expired or missing: fetch fresh token, persist again
6. Gateway restart: loads persisted token instead of re-fetching

**Key facts:**
- The WebSocket token (used for receiving messages) is different from the HTTP appToken (used for sending)
- Tools always use HTTP — they never touch the WebSocket connection or its token
- Token is shared across the gateway and all ephemeral tool instances via the persistence file
- Ephemeral adapter pre-loads the persisted token before any API call, avoiding redundant `/v1/apptoken/create` requests

## Credential Storage

| Item | Location | Format |
|------|----------|--------|
| APP_ID + APP_SECRET | `~/.hermes/.env` or `config.yaml` platforms.lansenger.extra | LANSENGER_APP_ID / LANSENGER_APP_SECRET env vars |
| API Gateway URL | `~/.hermes/.env` or `config.yaml` platforms.lansenger.extra | LANSENGER_API_GATEWAY_URL (default: `https://open.e.lanxin.cn/open/apigw`) |
| appToken (persisted) | `~/.hermes/lansenger_token.json` | {"app_token": "...", "expires_at": timestamp} — auto-refreshed 5 min before expiry |
| Owner ID | `~/.hermes/lansenger_owner.json` | {"owner_id": "2285568-..."} — auto-set on first bot-to-owner message |
| Chat Type Map | `~/.hermes/lansenger_chat_types.json` | {"<chat_id>": "group"|"dm"} — auto-updated from inbound messages |
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
| Using i18nAppCard for approval workflows | Use appCard with isDynamic + headStatusInfo; i18nAppCard has no dynamic update support |
| Setting text-indent > 0 in bodyContent | Always use text-indent:0em to avoid unwanted indentation |
| Using lansenger_send_link_card for multiple articles | Use lansenger_send_app_articles for multi-article cards |

## Tips

- If unsure whether the recipient can render Markdown, prefer `lansenger_send_text` (plain text is safest)
- For long Markdown analyses, consider splitting into multiple `lansenger_send_markdown` calls (long messages have poor readability in Lansenger)
- File size limits are determined by the organization's Lansenger configuration (not a fixed 2MB cap)
- The ephemeral adapter pattern means each tool call creates a fresh adapter instance — but appToken and chat_type_map are shared across processes via persistence files
- Use `lansenger_query_groups` to discover group IDs before sending to a group — you need the exact group chat ID