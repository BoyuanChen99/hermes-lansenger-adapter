[English](README.md) | [简体中文](README.zhHans.md) | [繁体中文](README.zhHant.md) | [繁体中文香港](README.zhHantHK.md) | [Français](README.fr.md)

# Hermes Lansenger Adapter

> 💠 Lansenger gateway adapter + media & message tools plugin for Hermes Agent.

Connects Hermes Agent to Lansenger — an enterprise messaging platform — via WebSocket long-connection for real-time message reception and HTTP API for message delivery.

This repo contains **two plugins**:

| Plugin | Kind | What it does |
|--------|------|-------------|
| `platforms/lansenger/` | platform | Gateway channel adapter — receive & send messages |
| `lansenger-tools/` | standalone (tool) | Agent-callable tools: send files/images, revoke messages, send linkCard |

## Features

### Platform Adapter
- **Real-time messaging** via WebSocket long-connection
- **Markdown support** using `formatText` msgType
- **i18nAppCard** — interactive approval workflow cards
- **Home channel auto-detection** — first p2p message sets the default delivery target
- **Cron delivery** — scheduled notifications via `standalone_sender_fn`
- **User authorization** — allowed users / allow all users via env vars
- **Zero core modification** — pure plugin mode, `git diff HEAD` stays PRISTINE

### Media & Message Tools Plugin
- **lansenger_send_text** — Send plain text messages with optional @mentions (group/staff chat only) and attachments
- **lansenger_send_markdown** — Send Markdown-formatted text messages (no attachments or @mentions)
- **lansenger_send_file** — Send any local file/image/video to a specific user or group
- **lansenger_send_image_url** — Send an image from a URL to a specific user or group
- **lansenger_revoke_message** — Revoke a sent Lansenger message 🗑️
- **lansenger_send_link_card** — Send a Lansenger linkCard card message 🔗
- **Auto media type detection** — images/videos/documents classified by extension
- **Credential gating** — tools hidden when LANSENGER_APP_ID/SECRET not set

## Quick Install

### Via Hermes Plugin Manager (recommended)

```bash
hermes plugins install lansenger-pm/hermes-lansenger-adapter
hermes plugins enable lansenger-platform
hermes plugins enable lansenger-tools
hermes gateway restart
```

### Manual Install

Clone this repo into `~/.hermes/plugins/`:

```bash
cd ~/.hermes/plugins/
git clone https://github.com/lansenger-pm/hermes-lansenger-adapter.git hermes-lansenger-adapter
hermes plugins enable lansenger-platform
hermes plugins enable lansenger-tools
hermes gateway restart
```

### Via pip (advanced)

```bash
pip install hermes-lansenger-adapter
hermes plugins enable lansenger-platform
hermes plugins enable lansenger-tools
hermes gateway restart
```

## Configuration

### Required Environment Variables

Add these to `~/.hermes/.env`:

| Variable | Description | Example |
|----------|-------------|---------|
| `LANSENGER_APP_ID` | Bot App ID | `your-app-id` |
| `LANSENGER_APP_SECRET` | Bot App Secret | `your-app-secret` |

**Credential path:** Lansenger desktop → Contacts → Smart Bot → Personal Bot → click the ℹ️ icon to view credentials (mobile client does not support viewing credentials)

### Optional Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `LANSENGER_API_GATEWAY_URL` | API Gateway URL | `https://open.e.lanxin.cn/open/apigw` |
| `LANSENGER_ALLOWED_USERS` | Allowed user IDs (comma-separated) | — |
| `LANSENGER_ALLOW_ALL_USERS` | Allow any user (dev only) | `false` |
| `LANSENGER_HOME_CHANNEL` | Default cron delivery chat ID | Auto-detected |

### config.yaml

```yaml
platforms:
  lansenger:
    enabled: true
```

## Media & Message Tools (from lansenger-tools)

These tools let the Agent send files, images, and videos, revoke messages, and send linkCard cards — all independently callable from the LLM. Credentials are read from env vars (LANSENGER_APP_ID/SECRET), not from `load_gateway_config()`.

| Tool | Parameters | Description |
|------|-----------|-------------|
| `lansenger_send_text` | `chat_id`, `message`, `reminder_all`?, `reminder_user_ids`?, `media_paths`? | Send plain text with optional @mentions (group/staff chat) and attachments |
| `lansenger_send_markdown` | `chat_id`, `message` | Send Markdown-formatted text (no @mentions, no attachments) |
| `lansenger_send_file` | `chat_id`, `file_path`, `caption`?, `media_type`? | Send a local file/image/video to a user or group |
| `lansenger_send_image_url` | `chat_id`, `image_url`, `caption`? | Download image from URL and send as native image |
| `lansenger_revoke_message` | `message_ids`, `chat_type`?, `sender_id`? | Revoke a sent Lansenger message (system prompt is fixed, not customizable) |
| `lansenger_send_link_card` | `chat_id`, `title`, `link`, `description`?, `icon_link`?, `pc_link`?, `from_name`?, `from_icon_link`? | Send a Lansenger linkCard card message |

**Usage examples (Agent prompts):**

```
"Send the report.pdf to user 2285568-abc123"
"Share that chart image with the project group chat"
"Download this URL image and send it to my colleague"
"Revoke the message I just sent to the user"
"Send a link card to the user with the title 'Project Documentation' and link https://..."
```

**Limitations:**
- File size limits are determined by the organization's Lansenger configuration (no fixed cap)
- Media captions use plain text (no Markdown) — for Markdown text, send separately
- `lansenger_send_file` auto-detects media_type from extension if not specified
- `lansenger_revoke_message`: for staff/group chat types, `sender_id` is required

## Architecture

```
hermes plugins install → clone to ~/.hermes/plugins/hermes-lansenger-adapter/
                          ├── plugin.yaml                     # root manifest (kind: bundle)
                          ├── platforms/lansenger/            # Gateway adapter
                          │   ├── plugin.yaml                 # manifest (kind: platform)
                          │   ├── __init__.py                  # register() → ctx.register_platform()
                          │   └── adapter.py                   # full adapter (no tool handlers here)
                          ├── lansenger-tools/           # Media & message tools
                          │   ├── plugin.yaml                 # manifest (kind: standalone)
                          │   ├── __init__.py                  # register() → ctx.register_tool()
                          │   ├── schemas.py                   # LLM-facing tool descriptions
                          │   └── tools.py                     # handler implementations
                          ├── skills/                          # Agent decision-making skill
                          │   └── lansenger-messaging.md       # tool selection strategy + token docs
                          ├── README.md
                          ├── LICENSE
                          ├── VERSION
                          ├── after-install.md
                          ├── pyproject.toml                   # pip entry-point
                          └── .gitignore
```

## Dependencies

- `websockets` — WebSocket client for long-connection
- `httpx` — HTTP client for API calls (also used by media tools)

## Changelog

### v2.2.0 (2026-05-11)

- ✅ Implemented `reminder` (@mentions) for `send_text` and `send_text_with_media` — `reminder_all` (bool, @all members) + `reminder_user_ids` (array, specific users), matching Lansenger API `reminder` object
- ✅ @mentions only work in group/staff chat; private chat does not support them
- ✅ Fixed `at_user_ids` schema field was defined but never passed to adapter methods

### v2.1.0 (2026-05-11)

- 🔄 Migrated to plugin mode — zero core code modification
- ✅ `ctx.register_platform()` for adapter injection
- ✅ `standalone_sender_fn` for cron delivery
- ✅ Home channel auto-detection
- ✅ User authorization via env vars
- ✅ i18nAppCard approval workflow
- ✅ Media & message tools plugin — `lansenger_send_file`, `lansenger_send_image_url`
- ✅ `lansenger_revoke_message` and `lansenger_send_link_card` extracted from adapter to standalone tool plugin
- ✅ Implemented `send_link_card()` method in LansengerAdapter (was previously missing)
- ✅ Fixed revoke/linkCard "Lansenger not configured" error — now reads env vars instead of `load_gateway_config()`

## License

MIT — see [LICENSE](LICENSE).