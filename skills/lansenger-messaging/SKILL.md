---
name: lansenger-messaging
description: "Lansenger message type selection and card design guidelines."
version: 2.1.0
category: lansenger
tags: [lansenger, messaging, appcard, group]
---

# Lansenger Messaging Strategy

Lansenger has multiple message types with different capabilities. Picking the wrong type causes feature loss (attachments dropped, Markdown not rendered, dynamic updates broken).

## Message Type Matrix

| msgType | Markdown | @mention | Attachments | Group |
|---------|----------|----------|-------------|-------|
| text | ✗ | ✓ | ✓ | ✓ |
| formatText | ✓ | ✓ (newer) | ✗ | ✓ |
| appArticles | ✗ | ✗ | ✗ | ✓ |
| appCard | ✗ (div-style) | ✗ | ✗ | ✓ |
| approveCard | ✓ (markdown) | ✗ | ✗ | ✓ |
| linkCard | ✗ | ✗ | ✗ | ✓ |

- **formatText @mention**: newer Lansenger triggers client notification; older versions silently accept without triggering. The API automatically prepends `@displayName` to the message based on `reminder.userIds` / `reminder.botIds` — do NOT manually write `@name` in the text content.
- **linkCard** requires 6 fields: title, description, iconLink, link, fromName, fromIconLink.
- **video** requires 2 mediaIds: [videoId, coverImageId].

Auto-routing: private → `/v1/bot/messages/create` (userIdList), group → `/v1/messages/group/create` (groupId).

## Group Context Injection

In group chats, the adapter automatically fetches and injects group information into your system prompt:

- **Group name, description, member count** — always injected
- **Member list** (name, role, org) — injected when group has ≤ 100 members
- **Groups > 100 members** — only member count is injected; use `lansenger_get_group_members` to query specific members
- Group info is cached for 5 minutes

You **do not need to call** `lansenger_get_group_info` or `lansenger_get_group_members` just to know basic group context — it's already in your system prompt. Use these tools only when you need info beyond what's injected (e.g., groups > 100 members, refreshing stale info, or querying groups you're not currently in).

## Card Type Matrix

| Card Type | Multi-lang | Dynamic Update | headStatusInfo |
|-----------|------------|----------------|----------------|
| appCard | ✗ | ✓ | ✓ |
| i18nAppCard | ✓ (5 langs) | ✗ | ✗ (reserved) |
| approveCard | ✗ | ✓ (via dynamic update) | ✓ (head_status) |

**appCard** — single language, supports `isDynamic` + `headStatusInfo` for in-place status updates.
**approveCard** — Markdown body, clickable buttons, supports in-place status updates via `lansenger_update_dynamic_card`.
**i18nAppCard** — 5 languages in one message, no dynamic updates. Reserved for future use.

## Decision Tree

1. **Plain text** → `lansenger_send_text`
2. **Markdown** → `lansenger_send_markdown` (optional reminder for @mention)
2a. **Markdown + @mention** → `lansenger_send_markdown` with `reminder={"all":false,"userIds":["id"]}` (API auto-prepends @displayName; do NOT write @name in text)
3. **Text + attachment** → `lansenger_send_text` with file_path
4. **Markdown + attachment** → two messages: `lansenger_send_markdown` then `lansenger_send_file`
5. **Pure attachment** → `lansenger_send_file`
6. **Image from URL** → `lansenger_send_image_url`
7. **Link card** → `lansenger_send_link_card` (title + link required)
8. **Multi-article card** → `lansenger_send_app_articles`
9. **Approval/confirmation card** → `lansenger_send_app_card`
   ⚠️ Group chat: appCard may fall back to plain text. For group approval, use text + /approve /deny pattern.
   - `is_dynamic=True` + `headStatusInfo` for approval workflows
   - **headStatusInfo** = status dot + text, two independent parts:
     - `description` = text label, supports single `<div style="color:...">` for text color, <30 bytes, no nested divs
     - `colour` = status dot color (e.g. "#FFB116" amber, "#198754" green, "red")
   - Example: `description='<div style="color:#FFB116">Pending</div>', colour="#FFB116"` (Chinese: `待审批`)
   - After approval: `lansenger_update_dynamic_card` to update status in-place
10. **Interactive approve card** → `lansenger_send_approve_card` (clickable buttons, Markdown body)
11. **Update dynamic card** → `lansenger_update_dynamic_card` (msg_id required, is_last_update=True for final)
12. **Revoke message** → `lansenger_revoke_message` (chat_type="bot"/"group"; Lansenger shows fixed system text, not customizable)
13. **List bot's groups** → `lansenger_query_groups` (returns group IDs the bot belongs to)
14. **Get group details** → `lansenger_get_group_info` (name, members count, state — but note: basic info is auto-injected for current group)
15. **Get group members** → `lansenger_get_group_members` (member list with roles; only needed when members not auto-injected, i.e. groups > 100 people)
16. **Check membership** → `lansenger_check_in_group` (verify if a staff/bot is in a specific group)

## Critical Pitfalls

| ❌ Wrong | ✅ Right |
|----------|---------|
| send_text with Markdown | send_markdown |
| send_markdown with file_path | Two messages: markdown + file |
| i18nAppCard for approval | appCard with isDynamic + headStatusInfo |
| text-indent:0 (bare) | text-indent:0em (must have unit) |
| headStatusInfo.description as plain text | Single `<div style="color:...">` allowed, <30 bytes, no nested divs |
| headStatusInfo.colour for text color | colour = dot color only; description div = text color (independent) |
| font-size in fields/links/signature | Only bodyTitle, bodySubTitle, bodyContent support font-size; fields only support color; links.title only color+text-align |
| font-size:14px in bodyTitle/SubTitle/Content | font-size:12pt–36pt (px rejected by enterprise API; lansenger-tools auto-converts px→pt) |
| Message >4000 chars | Split into multiple messages |
| Video mediaIds=[videoId] | video requires mediaIds=[videoId, coverImageId]; upload cover image separately via type=image |
| Video without width/height/duration | Upload type=video requires width, height, duration params |

## Media Upload

Uses `/v1/app/medias/create` (not `/v1/medias/create` — that one is for avatars, 1MB limit only).

- **type** param: `video` / `image` / `file` / `audio` (string, not numeric)
- **Video**: must provide `width`, `height`, `duration` query params on upload; sending video message requires `mediaIds=[videoId, coverImageId]` (cover image must be uploaded separately via `/v1/app/medias/create?type=image`)
- **Image**: optional `width`, `height` query params
- **Audio**: optional `duration` query param
- **Media Upload**: uses `/v1/app/medias/create` (not `/v1/medias/create` — that's for avatars, 1MB limit only).
  - **type** param: `video` / `image` / `file` / `audio` (string, not numeric)
  - **Video**: requires `width`, `height`, `duration` params (auto-detected via ffprobe if available; pass explicitly if ffprobe not installed); requires cover image (2 mediaIds: [videoId, coverImageId])
  - **Image**: optional `width`, `height` params (auto-detected via ffprobe)
  - **Audio**: optional `duration` param (auto-detected via ffprobe)
  - **File size**: image up to 10MB, others up to 20MB (org config may differ)

## Token & Credentials

appToken persisted to `~/.hermes/lansenger_token.json`, auto-refreshed 5min before expiry. Ephemeral tools share token via this file. WS token ≠ HTTP token. Credentials from config.yaml or env vars (LANSENGER_APP_ID/SECRET).

See `references/token-and-credentials.md` for detailed lifecycle and storage format.