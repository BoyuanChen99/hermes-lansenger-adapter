# 💠 Lansenger Adapter — Post-Install Setup

Two plugins and one skill were installed:

1. **lansenger-platform** — Gateway channel adapter (enables Lansenger as a messaging channel)
2. **lansenger-media-tools** — Agent tools for sending messages, files, images, revoking messages, linkCard cards
3. **lansenger-messaging** — Skill that teaches the Agent how to choose the right Lansenger tool

## Configuration

Add the following to `~/.hermes/config.yaml` under `platforms.lansenger`:

```yaml
platforms:
  lansenger:
    app_id: "YOUR_APP_ID"
    app_secret: "YOUR_APP_SECRET"
    api_gateway_url: "https://open.e.lanxin.cn/open/apigw"   # or your custom gateway URL
```

Or set as environment variables in `~/.hermes/.env`:

```
LANSENGER_APP_ID=YOUR_APP_ID
LANSENGER_APP_SECRET=YOUR_APP_SECRET
LANSENGER_API_GATEWAY_URL=https://open.e.lanxin.cn/open/apigw
```

> 💡 App ID and App Secret can be found in Lansenger (蓝信) → Contacts → Personal Bot (not Workspace)

## Skill Installation

After installing the plugins, copy the skill to Hermes skills directory:

```bash
cp -r lansenger-adapter/skills/lansenger-messaging.md ~/.hermes/skills/lansenger-messaging.md
```

This skill teaches the Agent the Lansenger message type capability boundary (text vs formatText) and provides a decision tree for choosing the correct tool. Without it, the Agent may pick the wrong message type and lose Markdown formatting or attachment support.

## Restart Gateway

After configuration, restart the Hermes gateway:

```bash
hermes gateway restart
```

## Verify

Check that tools are loaded:
- `hermes tools list` should show 6 lansenger-media tools
- The skill should appear in `hermes skills list`

## Tools Overview

```
┌─────────────────────────┬──────────────┬──────────────┬──────────────┐
│  Tool                   │  Markdown    │  @mention    │  Attachments │
├─────────────────────────┼──────────────┼──────────────┼──────────────┤
│  lansenger_send_text    │  ✗           │  ✓           │  ✓           │
│  lansenger_send_markdown│  ✓           │  ✗           │  ✗           │
│  lansenger_send_file    │  ✗           │  —           │  ✓ (only)    │
│  lansenger_send_image_url│ ✗           │  —           │  ✓ (only)    │
│  lansenger_revoke_message│ —           │  —           │  —           │
│  lansenger_send_link_card│ —           │  —           │  —           │
└─────────────────────────┴──────────────┴──────────────┴──────────────┘
```