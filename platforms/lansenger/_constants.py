"""
Shared constants for Lansenger adapter modules.
Import-safe — has no circular dependencies on adapter.py or mixin modules.
"""

MAX_MESSAGE_LENGTH = 4000
RECONNECT_BACKOFF = [2, 5, 10, 30, 60]
INBOUND_SILENCE_TIMEOUT = 1800  # 30min — no inbound WS message for this long = silent death
DEFAULT_API_GATEWAY_URL = "https://open.e.lanxin.cn/open/apigw"

# API Endpoints
API_ENDPOINTS = {
    "auth": {
        "tenant_access_token": "/auth/v3/tenant_access_token/internal",
    },
    "websocket": {
        "endpoint": "/v1/ws/endpoint/create",
    },
    "smart_bot": {
        "private_message": "/v1/bot/messages/create",
        "group_message": "/v1/messages/group/create",
    },
    "app": {
        "upload_media": "/v1/app/medias/create",
    },
    "message": {
        "revoke": "/v1/messages/revoke",
        "dynamic_update": "/v1/messages/dynamic/update",
    },
    "groups": {
        "fetch": "/v2/groups/fetch",
        "info": "/v2/groups/{group_id}/info/fetch",
        "members": "/v2/groups/{group_id}/members/fetch",
        "is_in_group": "/v2/groups/{group_id}/members/is_in_group",
    },
}
