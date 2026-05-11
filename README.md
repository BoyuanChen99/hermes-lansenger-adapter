# Hermes Lansenger (蓝信) Adapter

> 💠 Lansenger gateway adapter + media tools plugin for Hermes Agent.

Connects Hermes Agent to Lansenger (蓝信) — the enterprise messaging platform by Qianxin (奇安信) — via WebSocket long-connection for real-time message reception and HTTP API for message delivery.

This repo contains **two plugins**:

| Plugin | Kind | What it does |
|--------|------|-------------|
| `platforms/lansenger/` | platform | Gateway channel adapter — receive & send messages |
| `lansenger-media-tools/` | standalone (tool) | Agent-callable tools for sending files/images/videos to specific users |

## Features

### Platform Adapter
- **Real-time messaging** via WebSocket long-connection
- **Markdown support** using `formatText` msgType
- **i18nAppCard** — interactive approval workflow cards
- **Message revoke** — retract previously sent messages
- **linkCard** — rich link preview cards
- **Home channel auto-detection** — first p2p message sets the default delivery target
- **Cron delivery** — scheduled notifications via `standalone_sender_fn`
- **User authorization** — allowed users / allow all users via env vars
- **Zero core modification** — pure plugin mode, `git diff HEAD` stays PRISTINE

### Media Tools Plugin
- **lansenger_send_file** — Send any local file/image/video to a specific user or group
- **lansenger_send_image_url** — Send an image from a URL to a specific user or group
- **Auto media type detection** — images/videos/documents classified by extension
- **Credential gating** — tools hidden when LANSENGER_APP_ID/SECRET not set

## Quick Install

### Via Hermes Plugin Manager (recommended)

```bash
hermes plugins install <your-git-url>
hermes plugins enable lansenger-platform
hermes plugins enable lansenger-media-tools
hermes gateway restart
```

### Manual Install

Clone this repo into `~/.hermes/plugins/`:

```bash
cd ~/.hermes/plugins/
git clone <your-git-url> hermes-lansenger-adapter
hermes plugins enable lansenger-platform
hermes plugins enable lansenger-media-tools
hermes gateway restart
```

### Via pip (advanced)

```bash
pip install hermes-lansenger-adapter
hermes plugins enable lansenger-platform
hermes plugins enable lansenger-media-tools
hermes gateway restart
```

## Configuration

### Required Environment Variables

Add these to `~/.hermes/.env`:

| Variable | Description | Example |
|----------|-------------|---------|
| `LANSENGER_APP_ID` | Bot App ID | `your-app-id` |
| `LANSENGER_APP_SECRET` | Bot App Secret | `your-app-secret` |

**Credential path:** Lansenger client → 通讯录 → 个人机器人 → 创建机器人 → 详情页

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

## Platform-Specific Tools (from adapter)

| Tool | Description |
|------|-------------|
| `lansenger_revoke_message` | 撤回已发送的蓝信消息 🗑️ |
| `lansenger_send_link_card` | 发送蓝信 linkCard 卡片消息 🔗 |

## Media Tools (from lansenger-media-tools)

These tools let the Agent send files, images, and videos to any Lansenger user or group on demand — independent of the gateway's automatic MEDIA: tag extraction.

| Tool | Parameters | Description |
|------|-----------|-------------|
| `lansenger_send_file` | `chat_id`, `file_path`, `caption`?, `media_type`? | Send a local file/image/video to a user or group |
| `lansenger_send_image_url` | `chat_id`, `image_url`, `caption`? | Download image from URL and send as native image |

**Usage examples (Agent prompts):**

```
"Send the report.pdf to user 2285568-abc123"
"Share that chart image with the project group chat"
"Download this URL image and send it to my colleague"
```

**Limitations:**
- File size limit: 2MB (Lansenger API constraint)
- Media captions use plain text (no Markdown) — for Markdown text, send separately
- `lansenger_send_file` auto-detects media_type from extension if not specified

## Architecture

```
hermes plugins install → clone to ~/.hermes/plugins/hermes-lansenger-adapter/
                          ├── platforms/lansenger/            # Gateway adapter
                          │   ├── plugin.yaml                 # manifest (kind: platform)
                          │   ├── __init__.py                  # register() → ctx.register_platform()
                          │   └── adapter.py                   # full adapter + tools (revoke/linkCard)
                          ├── lansenger-media-tools/           # Media sending tools
                          │   ├── plugin.yaml                 # manifest (kind: standalone)
                          │   ├── __init__.py                  # register() → ctx.register_tool()
                          │   ├── schemas.py                   # LLM-facing tool descriptions
                          │   └── tools.py                     # handler implementations
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

### v2.1.0 (2026-05-11)

- 🔄 Migrated to plugin mode — zero core code modification
- ✅ `ctx.register_platform()` for adapter injection
- ✅ `ctx.register_tool()` for revoke / linkCard tools
- ✅ `standalone_sender_fn` for cron delivery
- ✅ Home channel auto-detection
- ✅ User authorization via env vars
- ✅ i18nAppCard approval workflow
- ✅ Media tools plugin — `lansenger_send_file` + `lansenger_send_image_url`

## License

MIT — see [LICENSE](LICENSE).