     1|     1|     1|[English](README.md) | [简体中文](README.zhHans.md) | [繁体中文](README.zhHant.md) | [繁体中文香港](README.zhHantHK.md) | [Français](README.fr.md)
     2|     2|     2|
     3|     3|     3|# Hermes Lansenger Adapter
     4|     4|     4|
     5|     5|     5|> 💠 Lansenger gateway adapter + media & message tools plugin for Hermes Agent.
     6|     6|     6|
     7|     7|     7|Connects Hermes Agent to Lansenger — an enterprise messaging platform — via WebSocket long-connection for real-time message reception and HTTP API for message delivery.
     8|     8|     8|
     9|     9|     9|This repo contains **two plugins**:
    10|    10|    10|
    11|    11|    11|| Plugin | Kind | What it does |
    12|    12|    12||--------|------|-------------|
    13|    13|    13|| `platforms/lansenger/` | platform | Gateway channel adapter — receive & send messages |
    14|    14|    14|| `lansenger-tools/` | standalone (tool) | Agent-callable tools: send files/images, revoke messages, send linkCard |
    15|    15|    15|
    16|    16|    16|## Features
    17|    17|    17|
    18|    18|    18|### Platform Adapter
    19|    19|    19|- **Real-time messaging** via WebSocket long-connection
    20|    20|    20|- **Markdown support** using `formatText` msgType
    21|    21|    21|- **i18nAppCard** — interactive approval workflow cards
    22|    22|    22|- **Home channel auto-detection** — first p2p message sets the default delivery target
    23|    23|    23|- **Cron delivery** — scheduled notifications via `standalone_sender_fn`
    24|    24|    24|- **User authorization** — allowed users / allow all users via env vars
    25|    25|    25|- **Zero core modification** — pure plugin mode, `git diff HEAD` stays PRISTINE
    26|    26|    26|
    27|    27|    27|### Media & Message Tools Plugin
    28|    28|    28|- **lansenger_send_text** — Send plain text messages with optional @mentions (group/staff chat only) and attachments
    29|    29|    29|- **lansenger_send_markdown** — Send Markdown-formatted text messages (no attachments or @mentions)
    30|    30|    30|- **lansenger_send_file** — Send any local file/image/video to a specific user or group
    31|    31|    31|- **lansenger_send_image_url** — Send an image from a URL to a specific user or group
    32|    32|    32|- **lansenger_revoke_message** — Revoke a sent Lansenger message 🗑️
    33|    33|    33|- **lansenger_send_link_card** — Send a Lansenger linkCard card message 🔗
    34|    34|    34|- **Auto media type detection** — images/videos/documents classified by extension
    35|    35|    35|- **Credential gating** — tools hidden when LANSENGER_APP_ID/SECRET not set
    36|    36|    36|
    37|    37|    37|## Quick Install
    38|    38|    38|
    39|    39|    39|### Via Hermes Plugin Manager (recommended)
    40|    40|    40|
    41|    41|    41|```bash
    42|    42|    42|hermes plugins install lansenger-pm/hermes-lansenger-adapter
    43|    43|    43|hermes plugins enable hermes-lansenger-adapter
    44|    44|    44|hermes gateway restart
    45|    45|    45|```
    46|    46|    46|
    47|    47|    47|### Manual Install
    48|    48|    48|
    49|    49|    49|Clone this repo into `~/.hermes/plugins/`:
    50|    50|    50|
    51|    51|    51|```bash
    52|    52|    52|cd ~/.hermes/plugins/
    53|    53|    53|git clone https://github.com/lansenger-pm/hermes-lansenger-adapter.git hermes-lansenger-adapter
    54|    54|    54|hermes plugins enable hermes-lansenger-adapter
    55|    55|    55|hermes gateway restart
    56|    56|    56|```
    57|    57|    57|
    58|    58|    58|### Via pip (advanced)
    59|    59|    59|
    60|    60|    60|```bash
    61|    61|    61|pip install hermes-lansenger-adapter
    62|    62|    62|hermes plugins enable hermes-lansenger-adapter
    63|    63|    63|hermes gateway restart
    64|    64|    64|```
    65|    65|    65|
    66|    66|    66|> **Note:** The bundle auto-expands on first gateway restart. Sub-plugins (`lansenger-platform` and `lansenger-tools`) are automatically copied to `~/.hermes/plugins/`, auto-enabled in `config.yaml`, and loaded in-place — no need to run separate `hermes plugins enable` commands for each sub-plugin.
    67|    67|    67|
    68|    68|    68|## Configuration
    69|    69|    69|
    70|    70|    70|### Required Environment Variables
    71|    71|    71|
    72|    72|    72|Add these to `~/.hermes/.env`:
    73|    73|    73|
    74|    74|    74|| Variable | Description | Example |
    75|    75|    75||----------|-------------|---------|
    76|    76|    76|| `LANSENGER_APP_ID` | Bot App ID | `your-app-id` |
    77|    77|    77|| `LANSENGER_APP_SECRET` | Bot App Secret | `your-app-secret` |
    78|    78|    78|
    79|    79|    79|**Credential path:** Lansenger desktop → Contacts → Bots → Personal Bots → click the ℹ️ icon to view credentials (mobile client does not support viewing credentials)
    80|    80|    80|
    81|    81|    81|### Optional Environment Variables
    82|    82|    82|
    83|    83|    83|| Variable | Description | Default |
    84|    84|    84||----------|-------------|---------|
    85|    85|    85|| `LANSENGER_API_GATEWAY_URL` | API Gateway URL | `https://open.e.lanxin.cn/open/apigw` |
    86|    86|    86|| `LANSENGER_ALLOWED_USERS` | Allowed user IDs (comma-separated) | — |
    87|    87|    87|| `LANSENGER_ALLOW_ALL_USERS` | Allow any user (dev only) | `false` |
    88|    88|    88|| `LANSENGER_HOME_CHANNEL` | Default cron delivery chat ID | Auto-detected |
    89|    89|    89|
    90|    90|    90|### config.yaml
    91|    91|    91|
    92|    92|    92|```yaml
    93|    93|    93|platforms:
    94|    94|    94|  lansenger:
    95|    95|    95|    enabled: true
    96|    96|    96|```
    97|    97|    97|
    98|    98|    98|## Media & Message Tools (from lansenger-tools)
    99|    99|    99|
   100|   100|   100|These tools let the Agent send files, images, and videos, revoke messages, and send linkCard cards — all independently callable from the LLM. Credentials are read from env vars (LANSENGER_APP_ID/SECRET), not from `load_gateway_config()`.
   101|   101|   101|
   102|   102|   102|| Tool | Parameters | Description |
   103|   103|   103||------|-----------|-------------|
   104|   104|   104|| `lansenger_send_text` | `chat_id`, `message`, `reminder_all`?, `reminder_user_ids`?, `media_paths`? | Send plain text with optional @mentions (group/staff chat) and attachments |
   105|   105|   105|| `lansenger_send_markdown` | `chat_id`, `message` | Send Markdown-formatted text (no @mentions, no attachments) |
   106|   106|   106|| `lansenger_send_file` | `chat_id`, `file_path`, `caption`?, `media_type`? | Send a local file/image/video to a user or group |
   107|   107|   107|| `lansenger_send_image_url` | `chat_id`, `image_url`, `caption`? | Download image from URL and send as native image |
   108|   108|   108|| `lansenger_revoke_message` | `message_ids`, `chat_type`?, `sender_id`? | Revoke a sent Lansenger message (system prompt is fixed, not customizable) |
   109|   109|   109|| `lansenger_send_link_card` | `chat_id`, `title`, `link`, `description`?, `icon_link`?, `pc_link`?, `from_name`?, `from_icon_link`? | Send a Lansenger linkCard card message |
   110|   110|   110|
   111|   111|   111|**Usage examples (Agent prompts):**
   112|   112|   112|
   113|   113|   113|```
   114|   114|   114|"Send the report.pdf to user 2285568-abc123"
   115|   115|   115|"Share that chart image with the project group chat"
   116|   116|   116|"Download this URL image and send it to my colleague"
   117|   117|   117|"Revoke the message I just sent to the user"
   118|   118|   118|"Send a link card to the user with the title 'Project Documentation' and link https://..."
   119|   119|   119|```
   120|   120|   120|
   121|   121|   121|**Limitations:**
   122|   122|   122|- File size limits are determined by the organization's Lansenger configuration (no fixed cap)
   123|   123|   123|- Media captions use plain text (no Markdown) — for Markdown text, send separately
   124|   124|   124|- `lansenger_send_file` auto-detects media_type from extension if not specified
   125|   125|   125|- `lansenger_revoke_message`: for staff/group chat types, `sender_id` is required
   126|   126|   126|
   127|   127|   127|## Architecture
   128|   128|   128|
   129|   129|   129|```
   130|   130|   130|hermes plugins install → clone to ~/.hermes/plugins/hermes-lansenger-adapter/
   131|   131|   131|                          ├── plugin.yaml                     # root manifest (kind: bundle)
   132|   132|   132|                          ├── platforms/lansenger/            # Gateway adapter
   133|   133|   133|                          │   ├── plugin.yaml                 # manifest (kind: platform)
   134|   134|   134|                          │   ├── __init__.py                  # register() → ctx.register_platform()
   135|   135|   135|                          │   └── adapter.py                   # full adapter (no tool handlers here)
   136|   136|   136|                          ├── lansenger-tools/           # Media & message tools
   137|   137|   137|                          │   ├── plugin.yaml                 # manifest (kind: standalone)
   138|   138|   138|                          │   ├── __init__.py                  # register() → ctx.register_tool()
   139|   139|   139|                          │   ├── schemas.py                   # LLM-facing tool descriptions
   140|   140|   140|                          │   └── tools.py                     # handler implementations
   141|   141|   141|                          ├── skills/                          # Agent decision-making skill
   142|   142|   142|                          │   └── lansenger-messaging.md       # tool selection strategy + token docs
   143|   143|   143|                          ├── README.md
   144|   144|   144|                          ├── LICENSE
   145|   145|   145|                          ├── VERSION
   146|   146|   146|                          ├── after-install.md
   147|   147|   147|                          ├── pyproject.toml                   # pip entry-point
   148|   148|   148|                          └── .gitignore
   149|   149|   149|```
   150|   150|   150|
   151|   151|   151|## Dependencies
   152|   152|   152|
   153|   153|   153|- `websockets` — WebSocket client for long-connection
   154|   154|   154|- `httpx` — HTTP client for API calls (also used by media tools)
   155|   155|   155|
   156|   156|   156|## Upgrade
   157|   157|   157|
   158|   158|   158|To update to the latest version:
   159|   159|   159|
   160|   160|   160|```bash
   161|   161|   161|hermes plugins update hermes-lansenger-adapter
   162|   162|   162|hermes gateway restart
   163|   163|   163|```
   164|   164|   164|
   165|   165|   165|## Changelog
   166|   166|   166|
   167|   167|   167|### v2.6.0 — Approval workflow upgrade: i18nAppCard → dynamic appCard
   168|   168|   168|
   169|   169|   169|- **Dynamic appCard with isDynamic=True**: Approval, slash-confirm, and update-prompt cards now use appCard instead of i18nAppCard, enabling in-place status updates (待审批 → 已批准/已拒绝) instead of sending duplicate cards.
   170|   170|   170|- **Language detection from inbound messages**: `_user_lang_map` caches per-chat language (zh/en) from CJK heuristic. Cards auto-select Chinese or English content based on the user's recent messages. Default: Chinese.
   171|   171|   171|- **update_approval_status → appCardUpdateMsg**: Status updates now use `msgType="appCard"` + `appCardUpdateMsg` (was `i18nAppCardUpdateMsg`). The same card visually changes status in-place.
   172|   172|   172|- **New helpers**: `_detect_lang()`, `_get_lang()`, `_get_agent_signature(lang)`, `_build_status_div(text, color)`.
   173|   173|   173|- **`_build_i18n_obj_full` and `_build_agent_signature_i18n` retained** but no longer used by approval flows — preserved for potential future i18n use.
   174|   174|   174|
   175|   175|   175|
   176|   176|   176|### v2.5.0 — appArticles, appCard, dynamic card update, group routing, group query
   177|   177|   177|
   178|   178|   178|- **appArticles (图文卡片)**: Send multi-article cards with imgUrl/title/summary/url/pcUrl fields. New adapter method `send_app_articles()` and tool `lansenger_send_app_articles`.
   179|   179|   179|- **appCard (应用卡片)**: Send rich-format cards with div-style HTML (color, font-size, text-align, text-indent). Supports dynamic cards (is_dynamic=true) for approval workflows. New adapter method `send_app_card()` and tool `lansenger_send_app_card`.
   180|   180|   180|- **Dynamic card update**: Update dynamic appCard status via POST /v1/messages/dynamic/update. New adapter method `update_dynamic_card_status()` and tool `lansenger_update_dynamic_card`.
   181|   181|   181|- **Group message routing**: `send_text()` now routes to /v1/messages/group/create for group chats (detected from inbound chat_type_map cache), and /v1/bot/messages/create for private chats.
   182|   182|   182|- **Group ID query**: Query bot's group list via GET /v2/groups/fetch. New adapter method `query_groups()` and tool `lansenger_query_groups`.
   183|   183|   183|- **_chat_type_map**: New inbound cache that maps chat_id → "group"/"dm" for outbound routing.
   184|   184|   184|- **API_ENDPOINTS**: Added `message.dynamic_update` and `groups.fetch` entries.
   185|   185|   185|- **tools.py docstring**: Updated message type matrix with appArticles and appCard.
   186|   186|   186|
   187|   187|   187|
   188|   188|   188|### v2.4.2 — Home channel auto-upgrade
   189|   189|   189|
   190|   190|   190|- **Auto-sethome**: The first DM conversation is automatically designated as the Lansenger home channel. If no `home_channel` is configured, or an existing one is a group chat, the first DM overrides it (DM > group upgrade). Writes `config.yaml` and `os.environ` silently, no user-facing message. Follows Yuanbao's `AutoSetHomeMiddleware` pattern. Initialized in `__init__` as `_auto_sethome_done: bool = bool(existing_home) and not existing_home.startswith("group:")`.
   191|   191|   191|
   192|   192|   192|- **Dynamic agent signature** (from v2.4.1): `_build_agent_signature_i18n()` now used in all three i18nAppCard methods.
   193|   193|   193|
   194|   194|   194|### v2.4.1 — send_update_prompt + dynamic agent signature
   195|   195|   195|
   196|   196|   196|- **send_update_prompt**: New i18nAppCard method for the gateway `/update` watcher. Displays the prompt text with /approve and /deny reply hints in i18nFields. The gateway's text intercept routes /approve → "y" and /deny → "n" to `update_prompt.resolve()`. Lansenger lacks inline button callbacks (like Telegram/Discord), so text-based replies are the only option.
   197|   197|   197|
   198|   198|   198|- **Dynamic agent signature**: All i18nAppCard cards (send_update_prompt, send_exec_approval, send_slash_confirm) now use `_build_agent_signature_i18n()` which reads the agent name from `~/.hermes/SOUL.md` dynamically. Falls back to "Hermes" if SOUL.md cannot be read. No more hardcoded "Hermes 安全审批系统" — the signature now reflects the actual agent persona.
   199|   199|   199|
   200|   200|   200|### v2.4.0 — Bundle install-time expand + expand script
   201|   201|   201|
   202|   202|   202|- **Module-level expand**: Sub-plugins (`lansenger-platform`, `lansenger-tools`) are now copied to `~/.hermes/plugins/` top level at **import time**, not just in `register()`. This means they're visible to `hermes plugins enable` even if a gateway restart hasn't happened yet (but you still need a restart to load them).
   203|   203|   203|
   204|   204|   204|- **expand_sub_plugins.py**: Standalone script for pre-restart expansion. Run `python3 ~/.hermes/plugins/hermes-lansenger-adapter/expand_sub_plugins.py` after install to make sub-plugins discoverable by `hermes plugins enable` before the first gateway restart.
   205|   205|   205|
   206|   206|   206|- **After-install docs**: All 5 language versions now explicitly warn: *do NOT manually `hermes plugins enable` the sub-plugins* — the bundle auto-expands and auto-enables them on restart. The expand script is offered as an alternative for pre-restart enable.
   207|   207|   207|
   242|   242|   242|## License
   243|   243|   243|
   244|   244|   244|MIT — see [LICENSE](LICENSE).