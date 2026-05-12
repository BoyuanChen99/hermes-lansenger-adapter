[English](after-install.md) | [简体中文](after-install.zhHans.md) | [繁体中文](after-install.zhHant.md) | [繁体中文香港](after-install.zhHantHK.md) | [Français](after-install.fr.md)

# 💠 Lansenger Adapter — Post-Install Setup

A bundle plugin and one skill were installed:

1. **hermes-lansenger-adapter** — Bundle container (auto-expands into `lansenger-platform` + `lansenger-tools` on gateway restart)
2. **lansenger-messaging** — Skill that teaches the Agent how to choose the right Lansenger tool

> 💡 The bundle auto-expands on first gateway restart: `lansenger-platform` and `lansenger-tools` are automatically copied to `~/.hermes/plugins/`, auto-enabled in `config.yaml`, and loaded in-place.

## Configuration

### Option A: Interactive setup wizard (recommended)

Run the built-in setup wizard — it guides you through each credential step by step:

```bash
hermes setup gateway
```

Select **Lansenger** from the platform list, then paste your App ID, App Secret, and optionally confirm the API Gateway URL. Already-configured values are shown (secrets are masked) and can be overwritten.

> 💡 App ID and App Secret can be found in Lansenger desktop → Contacts → Smart Bot → Personal Bot → ℹ️ icon (mobile does not support viewing credentials)

### Option B: config.yaml

Add the following to `~/.hermes/config.yaml` under `platforms.lansenger`:

```yaml
platforms:
  lansenger:
    app_id: "YOUR_APP_ID"
    app_secret: "YOUR_APP_SECRET"
    api_gateway_url: "https://open.e.lanxin.cn/open/apigw"   # or your custom gateway URL
```

### Option C: .env file (manual)

Edit `~/.hermes/.env` and add:

```
LANSENGER_APP_ID=YOUR_APP_ID
LANSENGER_APP_SECRET=YOUR_APP_SECRET
LANSENGER_API_GATEWAY_URL=https://open.e.lanxin.cn/open/apigw
```

## Skill Installation

After installing the plugins, install the lansenger-messaging skill (teaches the Agent the message type capability boundary and tool decision tree):

**Option A: From local cloned repo (fastest):**

```bash
mkdir -p ~/.hermes/skills/mlops/lansenger-messaging && cp ~/.hermes/plugins/hermes-lansenger-adapter/skills/lansenger-messaging.md ~/.hermes/skills/mlops/lansenger-messaging/SKILL.md
```

**Option B: From GitHub URL (works without local clone):**

```bash
hermes skills install --force --category messaging https://github.com/lansenger-pm/hermes-lansenger-adapter/raw/main/skills/lansenger-messaging.md
```

Without this skill, the Agent may pick the wrong message type and lose Markdown formatting or attachment support.

## Restart Gateway

After configuration, restart the Hermes gateway:

```bash
hermes gateway restart
```

## Verify

Check that the plugin is loaded:
- `hermes tools list` should show `lansenger-tools` in the Plugin toolsets section
- `hermes plugins list` should show `lansenger-platform` and `lansenger-tools` as enabled (bundle auto-expanded)

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