"""
Group query mixin for LansengerAdapter.
Handles group listing, info, members, and in-group checks.
"""

import asyncio
import logging
import time
from typing import Any, Dict, Optional

from ._constants import API_ENDPOINTS

logger = logging.getLogger(__name__)


class GroupQueryMixin:
    """Group query methods for LansengerAdapter."""

    async def query_groups(self, page_offset: int = 0, page_size: int = 100) -> Dict[str, Any]:
        """Query the bot's group ID list via GET /v2/groups/fetch.

        Args:
            page_offset: Page number starting from 0 (default 0)
            page_size: Per-page count (max 100, default 100)

        Returns:
            Dict with totalGroupIds (int) and groupIds (list of str)
        """
        token = await self._get_app_token()
        if not token:
            return {"totalGroupIds": 0, "groupIds": []}

        try:
            url = (
                f"{self._api_gateway_url}{API_ENDPOINTS['groups']['fetch']}"
                f"?app_token={token}&page_offset={page_offset}&page_size={page_size}"
            )

            response = await self._http_client.get(url)
            response.raise_for_status()
            data = response.json()

            if data.get("errCode") != 0:
                logger.error("[Lansenger] Query groups error: %s", data.get("errMsg"))
                return {"totalGroupIds": 0, "groupIds": []}

            result = data.get("data", {})
            logger.info("[Lansenger] Queried groups: total=%d", result.get("totalGroupIds", 0))
            return result

        except Exception as e:
            logger.error("[Lansenger] Query groups error: %s", e)
            return {"totalGroupIds": 0, "groupIds": []}

    async def get_group_info(self, group_id: str) -> Dict[str, Any]:
        """Get group basic info via GET /v2/groups/{group_id}/info/fetch.

        Returns group name, description, owner, total members, max members, etc.
        """
        token = await self._get_app_token()
        if not token:
            return {"error": "Failed to get app token"}

        try:
            url = (
                f"{self._api_gateway_url}"
                f"{API_ENDPOINTS['groups']['info'].format(group_id=group_id)}"
                f"?app_token={token}"
            )
            response = await self._http_client.get(url)
            response.raise_for_status()
            data = response.json()

            if data.get("errCode") != 0:
                logger.error("[Lansenger] Get group info error: errCode=%s errMsg=%s",
                             data.get("errCode"), data.get("errMsg"))
                return {"error": data.get("errMsg", "Unknown error")}

            result = data.get("data", {})
            logger.info("[Lansenger] Got group info: name=%s totalMembers=%d",
                        result.get("name", "?"), result.get("totalMembers", 0))
            return result

        except Exception as e:
            logger.error("[Lansenger] Get group info error: %s", e)
            return {"error": str(e)}

    async def get_group_members(self, group_id: str, page_offset: int = 0,
                                page_size: int = 100) -> Dict[str, Any]:
        """Get group member list via GET /v2/groups/{group_id}/members/fetch.

        Returns totalMembers count and members list with staffId, name, orgName, role.
        """
        token = await self._get_app_token()
        if not token:
            return {"error": "Failed to get app token"}

        try:
            url = (
                f"{self._api_gateway_url}"
                f"{API_ENDPOINTS['groups']['members'].format(group_id=group_id)}"
                f"?app_token={token}&page_offset={page_offset}&page_size={page_size}"
            )
            response = await self._http_client.get(url)
            response.raise_for_status()
            data = response.json()

            if data.get("errCode") != 0:
                logger.error("[Lansenger] Get group members error: errCode=%s errMsg=%s",
                             data.get("errCode"), data.get("errMsg"))
                return {"error": data.get("errMsg", "Unknown error")}

            result = data.get("data", {})
            logger.info("[Lansenger] Got group members: total=%d returned=%d",
                        result.get("totalMembers", 0), len(result.get("members", [])))
            return result

        except Exception as e:
            logger.error("[Lansenger] Get group members error: %s", e)
            return {"error": str(e)}

    async def check_in_group(self, group_id: str, staff_id: str = "") -> Dict[str, Any]:
        """Check if a staff or bot is in a group via GET /v2/groups/{group_id}/members/is_in_group.

        Priority: staff_id > user_token > app_token.
        """
        token = await self._get_app_token()
        if not token:
            return {"error": "Failed to get app token"}

        try:
            params = f"app_token={token}"
            if staff_id:
                params += f"&staff_id={staff_id}"
            url = (
                f"{self._api_gateway_url}"
                f"{API_ENDPOINTS['groups']['is_in_group'].format(group_id=group_id)}"
                f"?{params}"
            )
            response = await self._http_client.get(url)
            response.raise_for_status()
            data = response.json()

            if data.get("errCode") != 0:
                logger.error("[Lansenger] Check in group error: errCode=%s errMsg=%s",
                             data.get("errCode"), data.get("errMsg"))
                return {"error": data.get("errMsg", "Unknown error")}

            return data.get("data", {"isInGroup": False})

        except Exception as e:
            logger.error("[Lansenger] Check in group error: %s", e)
            return {"error": str(e)}

    async def _ensure_group_cache(self, group_id: str) -> Optional[Dict[str, Any]]:
        """Ensure group info and members are cached. Returns cache entry or None.

        Fetches group info + members (if total <= 100) on cache miss or expiry.
        Uses per-group-id asyncio.Lock to avoid concurrent duplicate fetches.
        """
        now = time.time()
        cached = self._group_cache.get(group_id)
        if cached and (now - cached.get("fetched_at", 0)) < self._group_cache_ttl:
            return cached

        # Use per-group lock to avoid concurrent fetches for the same group
        if group_id not in self._group_fetch_locks:
            self._group_fetch_locks[group_id] = asyncio.Lock()

        async with self._group_fetch_locks[group_id]:
            # Double-check after acquiring lock
            cached = self._group_cache.get(group_id)
            if cached and (now - cached.get("fetched_at", 0)) < self._group_cache_ttl:
                return cached

            # Fetch group info
            info = await self.get_group_info(group_id)
            if "error" in info:
                logger.warning("[Lansenger] Failed to fetch group info for %s: %s",
                               group_id[:20], info.get("error"))
                return None

            members = []
            total_members = info.get("totalMembers", 0)

            # Only prefetch members if total <= 100
            if 0 < total_members <= 100:
                member_result = await self.get_group_members(group_id)
                if "error" not in member_result:
                    members = member_result.get("members", [])

            entry = {
                "info": info,
                "members": members,
                "fetched_at": time.time(),
            }
            self._group_cache[group_id] = entry
            logger.info("[Lansenger] Group cache updated for %s: name=%s members=%d/%d",
                        group_id[:20], info.get("name", "?"), len(members), total_members)
            return entry

    def _build_group_chat_topic(self, cache_entry: Dict[str, Any]) -> str:
        """Build chat_topic string from cached group info for system prompt injection."""
        info = cache_entry.get("info", {})
        members = cache_entry.get("members", [])

        lines = []
        lines.append(f"群名称: {info.get('name', '未知')}")
        desc = info.get("description", "").strip()
        if desc:
            lines.append(f"群描述: {desc}")
        lines.append(f"群人数: {info.get('totalMembers', 0)} 人 (上限 {info.get('maxMembers', '?')})")
        state = "正常" if info.get("state") == 0 else "已解散"
        lines.append(f"群状态: {state}")

        if members:
            lines.append("群成员:")
            role_labels = {0: "成员", 1: "助理群主", 2: "群主"}
            for m in members:
                name = m.get("name", m.get("staffId", "?"))
                role = role_labels.get(m.get("role", 0), "成员")
                org = m.get("orgName", "")
                if org:
                    lines.append(f"  - {name} ({role}) — {org}")
                else:
                    lines.append(f"  - {name} ({role})")
        else:
            total = info.get("totalMembers", 0)
            if total > 100:
                lines.append(f"群成员过多({total}人)，如需查询具体成员请使用 lansenger_get_group_members 工具。")

        return "\n".join(lines)
