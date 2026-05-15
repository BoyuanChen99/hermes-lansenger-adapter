# Token & Credentials Detail

## Token Lifecycle

1. First call: HTTP GET `/v1/apptoken/create` → appToken (2-hour expiry)
2. Persisted to `~/.hermes/lansenger_token.json` with `app_token` + `expires_at` (absolute timestamp)
3. Subsequent calls (gateway or ephemeral tool): load persisted token
4. If persisted token valid (>5min until expiry): reuse, skip API call
5. If expired or missing: fetch fresh token, persist again
6. Gateway restart: loads persisted token instead of re-fetching

## Key Facts

- WS token (receiving) ≠ HTTP appToken (sending) — different tokens, different purposes
- Tools always use HTTP — never touch WS connection or its token
- Token shared across gateway + ephemeral tool instances via persistence file
- Ephemeral adapter pre-loads persisted token before any API call

## Credential Storage

| Item | Location | Format |
|------|----------|--------|
| APP_ID + SECRET | config.yaml `platforms.lansenger.extra` or env vars | LANSENGER_APP_ID / LANSENGER_APP_SECRET |
| API Gateway URL | config.yaml or env var | LANSENGER_API_GATEWAY_URL (default: https://open.e.lanxin.cn/open/apigw) |
| appToken | ~/.hermes/lansenger_token.json | {"app_token": "...", "expires_at": timestamp} |
| Owner ID | ~/.hermes/lansenger_owner.json | {"owner_id": "2285568-..."} |
| Chat Type Map | ~/.hermes/lansenger_chat_types.json | {"<chat_id>": "group"|"dm"} |
| Home Channel | config.yaml `platforms.lansenger.home_channel` | Standard Hermes home_channel config |

## Credential Resolution Order

1. config.yaml → platforms.lansenger.extra.app_id / app_secret
2. Falls back to env vars LANSENGER_APP_ID / LANSENGER_APP_SECRET from .env