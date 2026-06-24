[English](after-install.md) | [简体中文](after-install.zhHans.md) | [繁体中文](after-install.zhHant.md) | [繁体中文香港](after-install.zhHantHK.md) | [Français](after-install.fr.md)

# 💠 Lansenger Adapter — Post-Install Setup

A bundle plugin and two skills were installed:

1. **hermes-lansenger-adapter** — Bundle container (auto-expands into `lansenger-platform` + `lansenger-tools`)
2. **lansenger-messaging** — Skill that teaches the Agent how to choose the right Lansenger tool
3. **lansenger-setup** — Skill that teaches the Agent how to configure the Lansenger plugin

> ⚠️ **Do NOT run `hermes plugins enable lansenger-platform` or `hermes plugins enable lansenger-tools` manually** — the bundle auto-expands and auto-enables both sub-plugins on gateway restart.

## Configuration

### Option A: Interactive setup wizard (recommended)

```bash
hermes setup gateway
```

Select **Lansenger** from the platform list, then paste your App ID, App Secret, and optionally confirm the API Gateway URL.

> 💡 App ID and App Secret can be found in Lansenger desktop → Contacts → Bots → Personal Bots → ℹ️ icon (mobile does not support viewing credentials)

### Option B: config.yaml

```yaml
platforms:
  lansenger:
    enabled: true
    extra:
      app_id: "YOUR_APP_ID"
      app_secret: "YOUR_APP_SECRET"
      api_gateway_url: "https://open.e.lanxin.cn/open/apigw"  # or your custom gateway URL
```

### Option C: .env file

```
LANSENGER_APP_ID=YOUR_APP_ID
LANSENGER_APP_SECRET=YOUR_APP_SECRET
LANSENGER_API_GATEWAY_URL=https://open.e.lanxin.cn/open/apigw
```

## Restart Gateway

```bash
hermes gateway restart
```

## Verify

- `hermes tools list` should show `lansenger-tools` in the Plugin toolsets section
- `hermes plugins list` should show `lansenger-platform` and `lansenger-tools` as enabled

## Group Chat Configuration

All settings use **YAML native booleans** (`true`/`false`, no quotes). Env vars use strings.

### Global settings

```yaml
platforms:
  lansenger:
    extra:
      group_policy: open              # open | allowlist | disabled
      require_mention: true           # @bot required in groups
      auto_mention_reply: false       # auto @sender in group replies
      auto_quote_reply: false         # auto refMsgId in replies (groups + DMs)
```

### Per-group overrides

```yaml
platforms:
  lansenger:
    extra:
      groups:
        "<group_id>":
          enabled: true
          require_mention: false
          auto_mention_reply: true
          auto_quote_reply: true
          allow_from:
            - "<staff_id>"
```

### Decision priority (top-down, first match wins)

1. per-group `enabled: false` → blocked
2. per-group `allow_from` non-empty and sender not in list → blocked
3. per-group `enabled: true` → skip global policy
4. global `group_policy` → `disabled` blocks all / `allowlist` checks groups config map keys
5. global `group_allow_from` (sender-level) non-empty and sender not in list → blocked
6. `require_mention` (per-group > global) is true and `is_at_me=false` and `is_at_all=false` → blocked

## Auto-Reply Features

### autoMentionReply

When enabled, group replies automatically @mention the sender. Uses `fromType` to distinguish:
- `fromType=0` (user) → `reminder.userIds`
- `fromType=1` (app/bot) → `reminder.botIds`

### autoQuoteReply

When enabled, replies automatically include `refMsgId` referencing the inbound message. Works in both group and private chats.

## Slash Commands

On startup, the adapter automatically registers all Hermes built-in and plugin slash commands (e.g. `/help`, `/status`, `/approve`) to the Lansenger Bot API. Commands appear in the Lansenger chat input bar.

### Disable auto-registration

```yaml
platforms:
  lansenger:
    extra:
      commands:
        native: false   # per-profile: disable slash command registration
```

Or globally via env var: `LANSENGER_SLASH_COMMANDS_NATIVE=0`

### Command permissions

Control which chats can see each command:

```yaml
platforms:
  lansenger:
    extra:
      command_permissions:
        approve: owner       # only bot owner can see
        status: everyone     # all chats can see (default)
        restart: disabled    # exclude this command entirely
```

| Permission | Scope |
|-----------|-------|
| `owner` | Owner's private chat only |
| `admin` | Owner + all group admins |
| `everyone` | Owner + all groups (default) |
| `disabled` | Command excluded from registration |

## Dangerous Command Approval

When Hermes detects a dangerous command (e.g. `rm -rf`, `curl | sh`, `chmod 777`), it pauses execution and sends an **approveCard** with clickable buttons. Approve or deny directly by:

- Clicking the buttons on the card
- Replying `/approve`, `/approve session`, `/approve always`, or `/deny`

The card updates in-place showing the decision (e.g. "Allowed once"). Falls back to appCard automatically if the server does not support approveCard.

## Multi-Workspace (Profiles)

Hermes supports multiple isolated workspaces via Profiles:

```bash
hermes profile create bot-prod
hermes profile create bot-test
hermes -p bot-prod gateway start
hermes -p bot-test gateway start
```

Each profile has its own config.yaml, sessions, memories, skills, logs, and data files (token, chat_type, owner).

## Tools Overview

```
┌───────────────────────────────┬──────────────┬──────────────┬──────────────┐
│  Tool                         │  Markdown    │  @mention    │  Attachments │
├───────────────────────────────┼──────────────┼──────────────┼──────────────┤
│  lansenger_send_text          │  ✗           │  ✓           │  ✓           │
│  lansenger_send_markdown      │  ✓           │  ✓ (opt)     │  ✗           │
│  lansenger_send_file          │  ✗           │  —           │  ✓ (only)    │
│  lansenger_send_image_url     │  ✗           │  —           │  ✓ (only)    │
│  lansenger_send_link_card     │  —           │  —           │  —           │
│  lansenger_send_app_articles  │  —           │  —           │  —           │
│  lansenger_send_app_card      │  ✗ (div)     │  —           │  —           │
│  lansenger_update_dynamic_card│  —           │  —           │  —           │
│  lansenger_revoke_message     │  —           │  —           │  —           │
│  lansenger_query_groups       │  —           │  —           │  —           │
└───────────────────────────────┴──────────────┴──────────────┴──────────────┘
```
