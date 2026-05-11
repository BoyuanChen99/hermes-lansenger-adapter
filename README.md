# Hermes Lansenger (蓝信) Platform Adapter

> 💠 Lansenger gateway adapter plugin for Hermes Agent.

Connects Hermes Agent to Lansenger (蓝信) — the enterprise messaging platform by Qianxin (奇安信) — via WebSocket long-connection for real-time message reception and HTTP API for message delivery.

## Features

- **Real-time messaging** via WebSocket long-connection
- **Markdown support** using `formatText` msgType
- **Media delivery** — images, videos, documents via `send_file()`
- **i18nAppCard** — interactive approval workflow cards
- **Message revoke** — retract previously sent messages
- **linkCard** — rich link preview cards
- **Home channel auto-detection** — first p2p message sets the default delivery target
- **Cron delivery** — scheduled notifications via `standalone_sender_fn`
- **User authorization** — allowed users / allow all users via env vars
- **Zero core modification** — pure plugin mode, `git diff HEAD` stays PRISTINE

## Quick Install

### Via Hermes Plugin Manager (recommended)

```bash
hermes plugins install <your-git-url>
hermes plugins enable lansenger-platform
hermes gateway restart
```

### Manual Install

Clone this repo into `~/.hermes/plugins/`:

```bash
cd ~/.hermes/plugins/
git clone <your-git-url> hermes-lansenger-adapter
hermes plugins enable lansenger-platform
hermes gateway restart
```

### Via pip (advanced)

```bash
pip install hermes-lansenger-adapter
hermes plugins enable lansenger-platform
hermes gateway restart
```

## Configuration

### Required Environment Variables

Add these to `~/.hermes/.env`:

| Variable | Description | Example |
|----------|-------------|---------|
| `LANSENGER_APP_ID` | Bot App ID | `your-app-id` |
| `LANSENGER_APP_SECRET` | Bot App Secret | `your-app-secret` |

**Credential path:** Lansenger client → 工作台 → 个人机器人 → 创建机器人 → 详情页

### Optional Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `LANSENGER_API_GATEWAY_URL` | API Gateway URL | `https://apigw.lx.qianxin.com` |
| `LANSENGER_ALLOWED_USERS` | Allowed user IDs (comma-separated) | — |
| `LANSENGER_ALLOW_ALL_USERS` | Allow any user (dev only) | `false` |
| `LANSENGER_HOME_CHANNEL` | Default cron delivery chat ID | Auto-detected |

### config.yaml

```yaml
platforms:
  lansenger:
    enabled: true
```

## Platform-Specific Tools

After installing, the following tools become available when connected to Lansenger:

| Tool | Description |
|------|-------------|
| `lansenger_revoke_message` | 回已发送的蓝信消息 🗑️ |
| `lansenger_send_link_card` | 发送蓝信 linkCard 卡片消息 🔗 |

## Architecture

```
hermes plugins install → clone to ~/.hermes/plugins/
                          ├── platforms/lansenger/
                          │   ├── plugin.yaml          # manifest (kind: platform)
                          │   ├── __init__.py           # register() entry point
                          │   └── adapter.py            # full adapter + tools
```

The plugin uses Hermes's `PluginContext.register_platform()` API to inject the adapter into the gateway, and `PluginContext.register_tool()` for platform-specific tools. No core code is modified.

## Dependencies

The adapter requires these Python packages (installed automatically):

- `websockets` — WebSocket client for long-connection
- `httpx` — HTTP client for API calls

## Changelog

### v2.1.0 (2026-05-11)

- 🔄 Migrated to plugin mode — zero core code modification
- ✅ `ctx.register_platform()` for adapter injection
- ✅ `ctx.register_tool()` for revoke / linkCard tools
- ✅ `standalone_sender_fn` for cron delivery
- ✅ Home channel auto-detection
- ✅ User authorization via env vars
- ✅ i18nAppCard approval workflow

## License

MIT — see [LICENSE](LICENSE).