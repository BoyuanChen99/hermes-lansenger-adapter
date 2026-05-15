[English](README.md) | [简体中文](README.zhHans.md) | [繁体中文](README.zhHant.md) | [繁体中文香港](README.zhHantHK.md) | [Français](README.fr.md)

# Hermes Lansenger Adapter

> 💠 Lansenger gateway adapter + media & message tools plugin for Hermes Agent.

Connects Hermes Agent to Lansenger — an enterprise messaging platform — via WebSocket long-connection for real-time message reception and HTTP API for message delivery.

This repo contains **two plugins**:

| Plugin | Kind | What it does |
|--------|------|-------------|
| `platforms/lansenger/` | platform | Gateway channel adapter — receive & send messages |
| `lansenger-tools/` | standalone (tool) | Agent-callable tools: send messages/cards/files, revoke messages, query groups |

## Features

### Platform Adapter
- **Real-time messaging** via WebSocket long-connection (built-in ping/pong)
- **Markdown support** using `formatText` msgType (with optional @mentions, newer API)
- **Approval cards** — appCard with dynamic in-place status updates after approval/rejection
- **Home channel auto-detection** — first p2p message sets the default delivery target
- **Chat type persistence** — inbound chat_id→group/dm map persisted for cross-process routing
- **Cron delivery** — scheduled notifications via `standalone_sender_fn`
- **User authorization** — allowed users / allow all users via env vars
- **Zero core modification** — pure plugin mode, `git diff HEAD` stays PRISTINE

### Media & Message Tools Plugin
- **lansenger_send_text** — Send plain text with optional @mentions and attachments
- **lansenger_send_markdown** — Send Markdown-formatted text with optional @mentions (newer API, no attachments)
- **lansenger_send_file** — Send any local file/image/video to a specific user or group
- **lansenger_send_image_url** — Send an image from a URL to a specific user or group
- **lansenger_revoke_message** — Revoke a sent Lansenger message (bot/group only)
- **lansenger_send_link_card** — Send a linkCard card message (6 required fields per spec)
- **lansenger_send_app_articles** — Send an appArticles multi-article card
- **lansenger_send_app_card** — Send an appCard rich card with optional dynamic updates
- **lansenger_update_dynamic_card** — Update a dynamic appCard's status in-place
- **lansenger_query_groups** — Query the bot's group ID list
- **Auto media type detection** — images/videos/documents classified by extension
- **Credential gating** — tools hidden when LANSENGER_APP_ID/SECRET not set

## Quick Install

### Via Hermes Plugin Manager (recommended)

```bash
hermes plugins install lansenger-pm/hermes-lansenger-adapter
hermes plugins enable hermes-lansenger-adapter
hermes gateway restart
```

### Manual Install

Clone this repo into `~/.hermes/plugins/`:

```bash
cd ~/.hermes/plugins/
git clone https://github.com/lansenger-pm/hermes-lansenger-adapter.git hermes-lansenger-adapter
hermes plugins enable hermes-lansenger-adapter
hermes gateway restart
```

### Via pip (advanced)

```bash
pip install hermes-lansenger-adapter
hermes plugins enable hermes-lansenger-adapter
hermes gateway restart
```

> **Note:** The bundle auto-expands on first gateway restart. Sub-plugins (`lansenger-platform` and `lansenger-tools`) are automatically copied to `~/.hermes/plugins/`, auto-enabled in `config.yaml`, and loaded in-place — no need to run separate `hermes plugins enable` commands for each sub-plugin.

## Configuration

### Required Environment Variables

Add these to `~/.hermes/.env`:

| Variable | Description | Example |
|----------|-------------|---------|
| `LANSENGER_APP_ID` | Bot App ID | `your-app-id` |
| `LANSENGER_APP_SECRET` | Bot App Secret | `your-app-secret` |

**Credential path:** Lansenger desktop → Contacts → Bots → Personal Bots → click the ℹ️ icon to view credentials (mobile client does not support viewing credentials)

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

These tools let the Agent send messages, files, images, cards, revoke messages, and query groups — all independently callable from the LLM. Credentials are read from env vars (LANSENGER_APP_ID/SECRET), not from `load_gateway_config()`.

| Tool | Parameters | Description |
|------|-----------|-------------|
| `lansenger_send_text` | `chat_id`, `content`, `reminder_all`?, `reminder_user_ids`?, `file_path`?, `media_type`? | Send plain text with optional @mentions and attachments |
| `lansenger_send_markdown` | `chat_id`, `content`, `reminder_all`?, `reminder_user_ids`? | Send Markdown-formatted text with optional @mentions (newer API, no attachments) |
| `lansenger_send_file` | `chat_id`, `file_path`, `caption`?, `media_type`? | Send a local file/image/video to a user or group |
| `lansenger_send_image_url` | `chat_id`, `image_url`, `caption`? | Download image from URL and send as native image |
| `lansenger_revoke_message` | `message_ids`, `chat_type`?, `sender_id`? | Revoke a sent message (bot/group only; group requires sender_id) |
| `lansenger_send_link_card` | `chat_id`, `title`, `link`, `description`, `icon_link`, `from_name`, `from_icon_link`, `pc_link`? | Send a linkCard (6 fields required per spec, pc_link optional) |
| `lansenger_send_app_articles` | `chat_id`, `articles` | Send an appArticles multi-article card |
| `lansenger_send_app_card` | `chat_id`, `body_title`, `head_title`?, `is_dynamic`?, `head_status_info`?, ... | Send an appCard rich card with optional dynamic updates |
| `lansenger_update_dynamic_card` | `msg_id`, `head_status_info`?, `is_last_update`? | Update a dynamic appCard's status in-place |
| `lansenger_query_groups` | `page_offset`?, `page_size`? | Query the bot's group ID list |

**Usage examples (Agent prompts):**

```
"Send the report.pdf to user 2285568-abc123"
"Share that chart image with the project group chat"
"Download this URL image and send it to my colleague"
"Revoke the message I just sent to the user"
"Send a link card with the title 'Project Documentation' and link https://..."
"Send an appCard approval card for the dangerous command"
"Update the approval card status to 'approved'"
```

**Limitations:**
- File size limits are determined by the organization's Lansenger configuration (no fixed cap)
- Media captions use plain text (no Markdown) — for Markdown text, send separately
- `lansenger_send_file` auto-detects media_type from extension if not specified
- `lansenger_revoke_message`: only bot/group chat types; group requires sender_id; system message is fixed (not customizable)
- `lansenger_send_link_card`: 6 fields required per API spec (title, description, iconLink, link, fromName, fromIconLink); pc_link optional
- `lansenger_send_markdown` @mentions: newer API capability; older versions silently accept without triggering notification
- Video (mediaType=1) requires 2 mediaIds (video + cover image) per API spec

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
                          │   └── lansenger-messaging/           # skill directory (SKILL.md + references/)
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

## Upgrade

To update to the latest version:

```bash
hermes plugins update hermes-lansenger-adapter
hermes gateway restart
```

## Changelog

### v2.6.4 — appCard div-style per API spec, remove OpenClaw from Hermes plugin

- `_fix_div_style_fields()` now only fixes font-size/text-indent in fields that actually support them per API spec (bodyTitle/SubTitle/Content only)
- Removed font-size/text-indent fixes from signature, fields, links, headStatusInfo.description (not supported by API)
- Removed OpenClaw SSRF troubleshooting section and reference file (not relevant to Hermes plugin)
- Updated schemas.py, SKILL.md, appcard-design-guidelines.md to match API spec field-by-field support
- Fixed Chinese text in English SKILL.md

### v2.6.3 — Bug fixes, expand script auto-installs skill

- Fixed `_running` flag: `connect()` now sets `_running=True` before creating WS task (was silently exiting)
- Fixed missing `import json` at module top-level — `_persist_token()` was silently failing
- Expand script now auto-installs skill to `~/.hermes/skills/lansenger/` alongside sub-plugins
- Removed manual skill installation step from after-install docs

### v2.6.2 — WS logging + doc fixes

- Improved WS connection lifecycle logging: full endpoint response, HTTP error details (status_code/body), reconnect attempt tracking
- Fixed misleading wsEndpoint URL truncation in log (was showing only 4 chars of ticket)
- Rewrote all traditional Chinese translations (zhHant/zhHantHK) eliminating simplified characters; fixed French errors

### v2.6.1 — Message body audit + formatText @mention

- formatText supports @mentions (reminder); older API silently accepts without notification
- Revoke restricted to bot/group; linkCard 6 required fields per spec; appArticles pcUrl optional
- Removed manual WS heartbeat (websockets built-in ping/pong); chat_type_map persisted for group routing

### v2.6.0 — Approval cards with dynamic status updates

- Approval cards with in-place status updates after approval/rejection
- Language detection per user (zh/en)
- Fixed bodyContent indentation: text-indent set to 0

### v2.5.0 — appArticles, appCard, dynamic card update, group routing, group query

- appArticles, appCard, dynamic card update, group routing, group query

### v2.4.2 — Home channel auto-upgrade

- Home channel auto-upgrade (DM > group)

### v2.4.1 — send_update_prompt + dynamic agent signature

- send_update_prompt + dynamic agent signature

### v2.4.0 — Bundle install-time expand + expand script

- Bundle auto-expand on install

### v2.3.2 (2026-05-12)

- Bug fix: `_make_config()` platform param

### v2.3.1 (2026-05-12)

- Bug fix: `_get_adapter_class()` path

### v2.3.0 (2026-05-12)

- Bundle auto-expand + simplified install flow

### v2.2.0 (2026-05-11)

- Reminder (@mentions) support for group chat

### v2.1.0 (2026-05-11)

- Plugin mode migration — zero core modification

## License

MIT — see [LICENSE](LICENSE).