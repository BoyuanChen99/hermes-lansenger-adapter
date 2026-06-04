# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/), and this project adheres to [Semantic Versioning](https://semver.org/).

## [2.6.10] - 2026-06-04

### Bug Fixes (Issue #1 — Code Audit)

- **Bug 1: `_run_async` thread pool deadlock** (tools.py). Replaced `ThreadPoolExecutor(max_workers=1)` fallback with `asyncio.run_coroutine_threadsafe(coro, loop)` — injects coroutines into the gateway's existing event loop instead of spinning a new thread+loop per tool call. Eliminates single-worker queue deadlock and 30s timeout on large file uploads. Timeout raised to 120s.
- **Bug 2: `_chat_type_map` routing failure for unknown chat IDs**. Added `_is_group_chat(chat_id)` helper with heuristic fallback: `group:` prefix → group, otherwise → DM (with warning log). Replaced all 6 `self._chat_type_map.get(chat_id) == "group"` checks.
- **Bug 3: `_persist_chat_type_map` writes on every inbound message**. Introduced `_chat_type_map_dirty` flag — `_persist_chat_type_map()` now skips disk I/O when the map hasn't changed. Persists once at the end of `_on_message` (per-batch) instead of per-event.
- **Bug 4: NOT A BUG**. `send_text_with_media` uses numeric `mediaType` (1/2/3) per Lansenger send API spec; `upload_media_file` uses string type (`video`/`image`/`file`/`audio`) per upload API spec. These are two different APIs with different parameter types — both correct.
- **Bug 5: Ephemeral adapter creates new httpx per tool call**. Introduced `_get_shared_http_client()` singleton with `atexit` cleanup — all tool invocations reuse the same TCP+TLS connection pool. Removed all `await adapter._http_client.aclose()` calls from tool handlers.
- **Bug 6: `_send_image_url_async` lacks separate connect/read timeouts**. Changed `timeout=30` → `httpx.Timeout(10.0, read=60.0)` — 10s connect timeout, 60s read timeout for large image downloads.
- **Bug 7: Approval/confirm/update_prompt cards hardcoded to private endpoint**. Added `_build_send_url(chat_id, token)` and `_build_app_card_payload(chat_id, app_card_data)` helpers. All three card methods now route to the correct endpoint (private vs group) based on `_is_group_chat(chat_id)`.
- **Bug 8: `send_app_card` missing text-indent fix**. Added `_fix_text_indent()` method (regex: `text-indent:0` → `text-indent:0em`) and `_fix_app_card_styles(field, is_body_content=False)` that applies both px→pt conversion and text-indent fix. `bodyContent` now gets `is_body_content=True` so bare-zero text-indent is always fixed.
- **Bug 9: `_probe_duration` truncates to int → duration=0 risk**. Changed `int(float(val))` → `max(1, round(float(val)))` — 0.5s video no longer becomes `duration=0`; minimum duration is 1.

### Code Quality (Issue #1 — Low Priority)

- **Issue 10**: `_escape_html` now also escapes `&` → `&amp;` (prevents misinterpretation as HTML entity references in div-style content).
- **Issue 11**: `_detect_lang` merged double-loop (unicodedata + CJK range) into single loop over CJK Unicode ranges only — removes `unicodedata` dependency and halves iteration count.
- **Issue 12**: Removed redundant `import json` inside `_load_owner_id`, `_save_owner_id`, `_on_message`, `_load_chat_type_map`, `_persist_chat_type_map`, `_convert_font_px_to_pt`, `_get_agent_name`. `json` and `re` now at top-level imports only.
- **Issue 13**: Changed `str | None` → `Optional[str]` in `_prompt_field` for Python <3.10 compatibility.
- **Issue 14**: Token expiry double-offset refactored — `persist_expiry = timestamp + expires_in; cache_expiry = persist_expiry - 300`. No longer `self._token_expiry + 300` confusing restore.

## [2.6.9] - 2026-06-03

### Tool Progress Formatting

- **`format_tool_event` override**: Return Markdown-formatted strings instead of the base class plain-text output. Tool call progress now renders with bold tool names (`**web_search**`), inline code for argument keys (`\`['query', 'limit']\``), and bullet-style argument display in verbose mode. Sent via formatText (msgType=formatText) to leverage Lansenger's Markdown renderer.

  | Mode | Before (plain text) | After (Markdown) |
  |---|---|---|
  | all/new | `🔍 web_search: "蓝信断连"` | `🔍 **web_search**：蓝信断连` |
  | verbose | `🔍 web_search(["query"]) {"query":"蓝信断连","limit":3}` | `🔍 **web_search** \`['query', 'limit']\`\n**query**：蓝信断连\n**limit**：3` |
  | no preview | `🔍 bash...` | `🔍 **bash** ...` |

### extract_local_files — Decision

- **No override**: Default regex-based implementation + existing `send_file`/`send_video` chain already covers the full delivery path:
  - Lansenger-supported image formats (jpg/jpeg/png/webp/gif) → inline preview via `send_file(media_type=2)`
  - Unsupported image formats (bmp/tiff/svg) → file delivery via `send_document(media_type=3)` — still deliverable, just no inline preview
  - Video → `send_video` → `send_file(media_type=1)` with auto cover frame extraction via ffmpeg (`_extract_video_cover`) producing dual mediaIds `[videoId, coverImageId]`
- Images and videos can always be sent as generic files (media_type=3) — the native format only adds inline preview.

## [2.6.8] - 2026-06-03

### Bug Fixes

- **Tempfile leak fix**: `_save_media_temp` and `_extract_video_cover` now clean up temporary files properly — previously, cover images and inbound media temp files were never deleted, causing disk space leaks over long-running sessions.
- **File descriptor cleanup**: `upload_media_file` reads the entire file into memory via `open().read()` and closes the handle immediately; previously the `with open()` block was inside the `files=...` multipart upload, keeping the FD open until the HTTP request completed.
- **Crash guard in send_file**: `send_file` wraps the cover-image upload in `try/finally` to guarantee temp-file cleanup even on upload failure; previously a cover upload exception left the temp file orphaned.

## [2.6.7] - 2026-05-28

### Bug Fixes

- **WS reconnect — stale task reference**: After `_ws_task.cancel()`, the adapter set `_ws_task = None` before the cancelled task finished executing. The `_run_ws` coroutine's `finally` block then set `_connected = False`, but the adapter's `_is_ws_alive()` check compared against `_ws_task is not None and not _ws_task.done()`, causing a false "alive" report during reconnect. Fixed by clearing `_ws_task` only after confirming the task is fully done.
- **WS reconnect — reconnect loop exit**: `_reconnect_ws()` created a new `_ws_task` but didn't reset `_running` flag when the old task was cancelled during an active reconnect. On rare timing, `_run_ws` checked `_running` and exited immediately, silently dropping the connection. Fixed by ensuring `_running` stays True throughout reconnect.
- **WS logging improvements**: Log full endpoint response body on connection failure (previously truncated); log reconnect attempt count and backoff delay; log HTTP error details on ticket fetch failure.

## [2.6.6] - 2026-05-28

### Bug Fixes

- **Silent WS task crash on ticket expiry**: When `get_ws_endpoint()` returned an expired ticket, `_run_ws` raised `websockets.exceptions.InvalidStatusCode` but the async task had no exception handler — the task silently died and `_connected` stayed True forever. Fixed by wrapping the initial connection in a try/except that logs the error and triggers reconnect instead of crashing the task.

## [2.6.5] - 2026-05-26

### Media Upload

- **Switch to `/v1/app/medias/create`**: Previous `/v1/medias/create` API was limited to 1 MB and intended for avatar uploads only. The new endpoint supports files up to 10–20 MB and uses string type parameter (`image`/`video`/`file`/`audio`) instead of numeric media type.
- **Video cover image auto-extraction**: Lansenger video messages require `mediaIds=[videoId, coverImageId]` (2 elements). `send_file(media_type=1)` now auto-extracts the first frame via ffmpeg (`_extract_video_cover`) and uploads it as a cover image, producing the required dual-mediaId payload.
- **ffprobe auto-detection**: `upload_media_file` auto-detects video/image width/height and audio/video duration via ffprobe when not explicitly provided. `_probe_video_size` and `_probe_duration` probe media metadata before upload.
- **`send_video` convenience method**: Wraps `send_file` with `media_type=1` for cleaner agent tool calls.

### Bug Fixes

- **`home_channel` missing platform field**: Gateway startup builds a `SessionSource` from `home_channel`, which requires a `platform` field. When `home_channel` was configured without the field (e.g. from manual config edits), it triggered a `KeyError` crash. Fixed by adding a fallback platform value.

## [2.6.4] - 2026-05-15

### appCard Formatting

- **div-style per API spec**: appCard `description` field now supports div-style inline formatting per Lansenger API specification — `font-size` (px→pt auto-conversion), `text-indent` (must specify unit, e.g. `0em` not bare `0`). Previous implementation used plain text for description and didn't handle unit requirements.
- **headStatusInfo semantics clarification**: `headStatusInfo.description` is plain text only (<30 bytes); `headStatusInfo.colour` controls the status dot color only — these are two independent parts, not mixed.

### Cleanup

- **Remove OpenClaw content**: Strayed OpenClaw-specific configuration examples and references removed from Hermes plugin docs.

## [2.6.3] - 2026-05-15

### Skill & Plugin Installation

- **SKILL restructured to Hermes directory format**: `lansenger-messaging.md` → `lansenger-messaging/SKILL.md + references/`. Slimmed SKILL to ~60 lines of actionable decision rules; detailed API reference moved to `references/` subdirectory.
- **Expand script auto-installs skill**: `__init__.py` auto-expand now copies the `skills/` directory alongside sub-plugins, eliminating manual skill install steps from docs.

### Bug Fixes

- **`import json` missing**: `adapter.py` used `json` module but didn't import it — caused `NameError` on token caching paths.
- **`_running` flag**: Set `_running = True` before creating WS task; without this, `_run_ws` exited immediately because the loop checked `_running` at entry.

### Tests

- **74/74 unit tests passing**: Added test framework covering outbound (text/formatText/linkCard/appArticles/appCard/revoke), media upload, inbound, lifecycle, token, and dynamic card updates.

## [2.6.2] - 2026-05-15

### Bug Fixes

- **WS connection lifecycle logging**: Log full endpoint response on connection (previously truncated wsEndpoint URL); log reconnect attempt tracking; log HTTP error details on ticket fetch failure.

## [2.6.1] - 2026-05-14

### Bug Fixes

- **Message body audit**: Fixed multiple message assembly bugs discovered during API field validation:
  - `linkCard` — added missing required fields (`iconLink`, `imageUrl`)
  - `formatText` — reminder field correctly nested inside `formatText` object (not at top level)
  - `revoke` — `chatType` limited to `bot`/`group` only per API spec (removed invalid `staff` type)
  - Removed duplicate WS heartbeat (ping interval from endpoint response already drives pings)
- **`chat_type_map` persistence**: Chat type (group vs DM) now persisted to `~/.hermes/lansenger_chat_types.json` so ephemeral tools route group messages correctly even after gateway restart.

### Group Chat

- **Group routing for all send methods**: All 6 outbound methods (`send_text`, `send_format_text`, `send_text_with_media`, `send_app_card`, `send_app_articles`, `send_link_card`) now correctly route to the group endpoint (`/v1/messages/group/create`) when `chat_type_map` indicates a group chat.

### Infrastructure

- **appToken persistent caching**: Token now cached in `~/.hermes/lansenger_token.json` with auto-refresh across gateway processes. Eliminates redundant API calls for `tenant_access_token` on every restart.

## [2.6.0] - 2026-05-12

### Approval Workflow

- **Dynamic appCard with in-place status update**: Approval workflow upgraded from static i18nAppCard to dynamic appCard (`isDynamic=true` + `headStatusInfo`). Cards can be updated in-place via `updateDynamicCard` API (`/v1/messages/dynamic/update`) — no need to send a new card when approval state changes.
- **`headStatusInfo` field**: Controls status dot color (`grey`/`green`/`red`) and optional short description (<30 bytes, plain text). Two independent parts — description text + dot color.
- **`lansenger_update_dynamic_card` tool**: Agent-callable tool for updating dynamic card status (pending → approved/denied).

### appCard Formatting

- **font-size px→pt auto-conversion**: Lansenger appCard `font-size` requires pt units; px values render incorrectly. `sendAppCard` now auto-converts CSS `font-size` from px to pt.

### Internationalization

- **User language detection**: Adapter detects per-user language preference (zh/en) from inbound messages and caches it. Approval cards and formatText messages use the detected language for UI labels.
- **Multi-language READMEs**: Added zhHans, zhHant, zhHantHK, French translations with language switcher links.

## [2.5.0] - 2026-05-12

### Rich Message Types

- **appArticles**: Multi-article card with title, summary, and external link per article. Agent tool: `lansenger_send_app_articles`.
- **appCard**: Rich card with head title, body title, div-style content, and optional dynamic status. Agent tool: `lansenger_send_app_card`.
- **Dynamic card update**: In-place status update for previously sent dynamic appCards. Agent tool: `lansenger_update_dynamic_card`.

### Group Chat

- **Group routing**: All send methods route to group endpoint when `chat_type_map` indicates a group chat. Populated from inbound messages.
- **Group ID query**: `lansenger_query_groups` tool for searching groups by name or listing all groups the bot belongs to.

## [2.4.2] - 2026-05-12

### Home Channel

- **Auto-upgrade**: Home channel now auto-upgrades from group to DM when the first DM arrives. Group home channels are less useful for personal bot interactions; DMs provide a more natural primary channel.

## [2.4.1] - 2026-05-12

### Infrastructure

- **send_update_prompt**: Hook for gateway to prompt agent for follow-up updates (e.g. cron-triggered responses).
- **Dynamic agent signature**: Agent response signature includes timestamp and platform metadata for out-of-process delivery.

## [2.4.0] - 2026-05-12

### Bundle & Installation

- **Module-level expand**: Bundle `__init__.py` auto-expands sub-plugins on first import, eliminating the need for a separate expansion step. In-place sub-plugin loading (hyphens → underscores in Python module names).
- **`expand_sub_plugins.py`**: Standalone expansion script for manual or CI-triggered installs.
- **Plugin kind = standalone**: Changed from `bundle` to `standalone` to suppress Hermes "not a valid plugin" warning for the root package.

## [2.3.2] - 2026-05-12

### Bug Fixes

- **PlatformConfig constructor**: Removed invalid `platform` parameter from `PlatformConfig()` call — Hermes core provides the platform object via `register(ctx)`.

## [2.3.1] - 2026-05-12

### Bug Fixes

- **Adapter class loading path**: Fixed module import path for `LansengerAdapter` — was using incorrect package structure.

## [2.3.0] - 2026-05-12

### Plugin Architecture

- **Bundle auto-expand + simplified install**: Single `hermes plugins install` clones the repo and auto-expands both sub-plugins (platform adapter + tools plugin) plus the messaging skill. No manual file copying needed.

## [2.2.0] - 2026-05-11

### Group Chat @Mention

- **Reminder (@mentions)**: `send_text` and `send_text_with_media` support `reminder` field per Lansenger API spec — `reminder_all` (bool) for @all members, `reminder_userIds` (list) for targeted @mentions. Group chat recommended to include @姓名 in text content alongside the reminder field.
- **formatText reminder**: `send_format_text` also supports `reminder` for group @mentions. Newer Lansenger API versions trigger client-side @mention notifications; older versions silently accept the field without effect.

## [2.1.0] - 2026-05-11

### Initial Hermes Plugin Release

- **Plugin mode migration**: Converted from standalone script to Hermes Agent plugin — zero core modification required. Registered via `ctx.register_platform()` in `register(ctx)` entry point.
- **WebSocket inbound**: Long-connection WebSocket for real-time message reception via `/v1/ws/endpoint/create`.
- **HTTP outbound**: Text, formatText (Markdown), image, file, linkCard message types via `/v1/bot/messages/create` (private) and `/v1/messages/group/create` (group).
- **Agent tools**: `lansenger_send_file`, `lansenger_send_image_url`, `lansenger_send_text`, `lansenger_send_markdown` — Agent-callable tools for outbound messaging.
- **lansenger-messaging skill**: SKILL.md teaches the Agent how to choose the right message type based on content characteristics (text vs formatText boundary, media attachment constraints).
- **Token management**: `tenant_access_token` fetch with 2-hour expiry; interactive setup wizard for `hermes setup gateway`.
- **Multi-language READMEs**: English, zhHans, zhHant, zhHantHK, French.