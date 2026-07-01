"""
Card mixin for LansengerAdapter.
Handles appCard, appArticles, linkCard, and update prompt messages.
"""

import json
import logging
from typing import Any, Dict, List, Optional

import httpx

from gateway.platforms.base import SendResult

from ._constants import API_ENDPOINTS

logger = logging.getLogger(__name__)


class CardMixin:
    """Card sending methods for LansengerAdapter."""

    async def send_app_articles(
        self,
        chat_id: str,
        articles: List[Dict[str, str]],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        """Send an appArticles (图文卡片) message with multiple article entries.

        Routes to /v1/messages/group/create for group chats,
        /v1/bot/messages/create for private chats.

        Each article dict must contain:
            - imgUrl (required): Image URL
            - title (required): Article title
            - url (required): Content link URL
            Optional:
            - pcUrl: PC content link URL
            - summary: Article summary
            - attach: Mini-app redirect params (ignored by other apps)

        Args:
            chat_id: Recipient user ID or chat ID
            articles: List of article dicts (1+ entries)
            metadata: Optional metadata dict
        """
        if not articles:
            return SendResult(success=False, error="No articles provided")

        token = await self._get_app_token()
        if not token:
            return SendResult(success=False, error="No access token")

        try:
            is_group = self._is_group_chat(chat_id)

            if is_group:
                url = f"{self._api_gateway_url}{API_ENDPOINTS['smart_bot']['group_message']}?app_token={token}"
                payload = {
                    "groupId": chat_id,
                    "msgType": "appArticles",
                    "msgData": {"appArticles": articles},
                }
            else:
                url = f"{self._api_gateway_url}{API_ENDPOINTS['smart_bot']['private_message']}?app_token={token}"
                payload = {
                    "userIdList": [chat_id],
                    "msgType": "appArticles",
                    "msgData": {"appArticles": articles},
                }

            response = await self._http_client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()

            if data.get("errCode") != 0:
                return SendResult(success=False, error=data.get("errMsg"))

            msg_id = data.get("data", {}).get("msgId")
            logger.info("[Lansenger] appArticles sent to %s, msgId=%s (group=%s)", chat_id, msg_id, is_group)
            return SendResult(success=True, message_id=msg_id, raw_response=data)

        except Exception as e:
            logger.error("[Lansenger] Send appArticles error: %s", e)
            return SendResult(success=False, error=str(e), retryable=True)

    async def send_app_card(
        self,
        chat_id: str,
        head_title: str = "",
        body_title: str = "",
        body_sub_title: str = "",
        body_content: str = "",
        signature: str = "",
        fields: Optional[List[Dict[str, str]]] = None,
        links: Optional[List[Dict[str, str]]] = None,
        card_link: str = "",
        pc_card_link: str = "",
        is_dynamic: bool = False,
        head_status_info: Optional[Dict[str, str]] = None,
        staff_id: str = "",
        head_icon_url: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        """Send an appCard (应用卡片) message with rich formatting support.

        NOTE: appCard and i18nAppCard are DIFFERENT message types:
        - appCard: supports isDynamic + headStatusInfo for in-place status
          updates, but uses a SINGLE language (no i18n fields).
        - i18nAppCard: supports 5 languages (zhHans/zhHant/zhHantHK/en/fr)
          but does NOT support dynamic updates or headStatusInfo.
          Reserved for future use (send_i18n_app_card stub below).

        appCard supports div-style HTML formatting (color, font-size, text-align, text-indent).
        font-size MUST use pt unit (e.g. 14pt) — px is rejected by the enterprise API.
        adapter provides _convert_px_to_pt() helper but it is not auto-applied;
        callers must ensure pt units or call the helper explicitly.
        Dynamic cards (is_dynamic=True) can be updated later via update_dynamic_card_status().

        Args:
            chat_id: Recipient user ID or chat ID
            head_title: Card header title
            body_title: Card body title (required, max 600 bytes). Supports div style tags.
            body_sub_title: Card body subtitle (max 1200 bytes). Supports div style tags.
            body_content: Card body content (max 3000 bytes). Supports div style tags.
            signature: Card signature (max 96 bytes). Supports color style.
            fields: List of key/value dicts (max 10 pairs). Supports color style.
            links: List of title/url dicts (max 3 pairs). Title supports color/position.
            card_link: Card click-through link
            pc_card_link: PC client click-through link
            is_dynamic: Enable dynamic card status updates (for approval workflows)
            head_status_info: Dynamic card status info dict with iconLink/description/colour
            staff_id: Staff ID for showing sender avatar
            head_icon_url: Header icon URL
            metadata: Optional metadata dict
        """
        if not body_title:
            return SendResult(success=False, error="body_title is required for appCard")

        token = await self._get_app_token()
        if not token:
            return SendResult(success=False, error="No access token")

        try:
            is_group = self._is_group_chat(chat_id)

            if is_group:
                url = f"{self._api_gateway_url}{API_ENDPOINTS['smart_bot']['group_message']}?app_token={token}"
            else:
                url = f"{self._api_gateway_url}{API_ENDPOINTS['smart_bot']['private_message']}?app_token={token}"

            app_card_data: Dict[str, Any] = {
                "headTitle": self._fix_app_card_styles(head_title),
                "headIconUrl": head_icon_url,
                "isDynamic": is_dynamic,
                "bodyTitle": self._fix_app_card_styles(body_title),
                "cardLink": card_link,
                "pcCardLink": pc_card_link,
            }

            if is_dynamic and not head_status_info:
                head_status_info = {
                    "description": "<div style=\"color:rgba(0,0,0,.47)\">Active</div>",
                    "colour": "rgba(0,0,0,.47)",
                }

            if is_dynamic and head_status_info:
                app_card_data["headStatusInfo"] = head_status_info

            if body_sub_title:
                app_card_data["bodySubTitle"] = self._fix_app_card_styles(body_sub_title)
            if body_content:
                app_card_data["bodyContent"] = self._fix_app_card_styles(body_content, is_body_content=True)
            if signature:
                app_card_data["signature"] = self._fix_app_card_styles(signature)
            if staff_id:
                app_card_data["staffId"] = staff_id
            if fields:
                app_card_data["fields"] = fields
            if links:
                app_card_data["links"] = links

            if is_group:
                payload = {
                    "groupId": chat_id,
                    "msgType": "appCard",
                    "msgData": {"appCard": app_card_data},
                }
            else:
                payload = {
                    "userIdList": [chat_id],
                    "msgType": "appCard",
                    "msgData": {"appCard": app_card_data},
                }

            response = await self._http_client.post(url, json=payload)
            response.raise_for_status()

            if not response.text or len(response.text.strip()) == 0:
                return SendResult(success=False, error="Empty API response for appCard — likely a payload format issue", retryable=True)

            data = response.json()

            if data.get("errCode") != 0:
                return SendResult(success=False, error=data.get("errMsg"))

            msg_id = data.get("data", {}).get("msgId")
            logger.info("[Lansenger] appCard sent to %s, msgId=%s, dynamic=%s, group=%s", chat_id, msg_id, is_dynamic, is_group)
            return SendResult(success=True, message_id=msg_id, raw_response=data)

        except Exception as e:
            logger.error("[Lansenger] Send appCard error: %s", e)
            return SendResult(success=False, error=str(e), retryable=True)

    # ------------------------------------------------------------------
    # i18nAppCard — RESERVED for future use
    # ------------------------------------------------------------------
    # i18nAppCard supports 5 languages (zhHans/zhHant/zhHantHK/en/fr) but
    # does NOT support isDynamic or headStatusInfo.  It cannot be updated
    # in-place after sending.  Currently the approval workflow uses appCard
    # with language detection instead.  When multi-language broadcast
    # (sending the SAME card to users of different languages simultaneously)
    # becomes necessary, implement send_i18n_app_card() here.

    async def send_i18n_app_card(
        self,
        chat_id: str,
        i18n_head_title: Optional[Dict[str, str]] = None,
        head_icon_url: str = "",
        i18n_body_title: Optional[Dict[str, str]] = None,
        i18n_body_sub_title: Optional[Dict[str, str]] = None,
        i18n_body_content: Optional[Dict[str, str]] = None,
        i18n_signature: Optional[Dict[str, str]] = None,
        staff_id: str = "",
        i18n_fields: Optional[List[Dict[str, Any]]] = None,
        i18n_links: Optional[List[Dict[str, Any]]] = None,
        card_link: str = "",
        pc_card_link: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        """Send an i18nAppCard (国际化应用卡片) — RESERVED for future use.

        i18nAppCard supports 5 languages but does NOT support dynamic
        updates (isDynamic) or headStatusInfo.  For approval workflows
        that need in-place status updates, use send_app_card() instead.
        """
        raise NotImplementedError(
            "i18nAppCard is reserved for future use. "
            "For approval cards with dynamic updates, use send_app_card() "
            "with is_dynamic=True and headStatusInfo."
        )

    async def update_dynamic_card_status(
        self,
        msg_id: str,
        head_status_info: Optional[Dict[str, str]] = None,
        links: Optional[List[Dict[str, str]]] = None,
        is_last_update: bool = False,
        chat_id: Optional[str] = None,
    ) -> SendResult:
        """Update a dynamic appCard's status (e.g. approval: pending → approved/rejected).

        The card must have been sent with is_dynamic=True. Uses POST /v1/messages/dynamic/update.

        Args:
            msg_id: The message ID returned from send_app_card (when is_dynamic=True)
            head_status_info: Updated status info dict with iconLink/description/colour
            links: Updated links list (max 3 pairs)
            is_last_update: True = final status update, card becomes static after this
            chat_id: Optional chat_id for private message updates (user_token needed)
        """
        token = await self._get_app_token()
        if not token:
            return SendResult(success=False, error="No access token")

        try:
            # Detect group vs DM for logging and potential future routing
            is_group = self._is_group_chat(chat_id) if chat_id else None
            
            # Build URL: unified endpoint for both group and DM
            url_params = f"app_token={token}"
            url = f"{self._api_gateway_url}{API_ENDPOINTS['message']['dynamic_update']}?{url_params}"

            app_card_update: Dict[str, Any] = {
                "isLastUpdate": is_last_update,
            }
            if head_status_info:
                app_card_update["headStatusInfo"] = head_status_info
            if links:
                app_card_update["links"] = links

            payload = {
                "msgId": msg_id,
                "msgType": "appCard",
                "msgData": {
                    "appCardUpdateMsg": app_card_update,
                },
            }

            response = await self._http_client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()

            if data.get("errCode") != 0:
                return SendResult(success=False, error=data.get("errMsg"))

            logger.info("[Lansenger] Dynamic card %s updated, isLast=%s, group=%s", msg_id, is_last_update, is_group)
            return SendResult(success=True, raw_response=data)

        except Exception as e:
            logger.error("[Lansenger] Update dynamic card error: %s", e)
            return SendResult(success=False, error=str(e), retryable=True)

    async def send_link_card(
        self,
        chat_id: str,
        title: str,
        link: str,
        description: Optional[str] = None,
        icon_link: Optional[str] = None,
        pc_link: Optional[str] = None,
        from_name: Optional[str] = None,
        from_icon_link: Optional[str] = None,
    ) -> SendResult:
        """Send a linkCard card message.

        Routes to /v1/messages/group/create for group chats,
        /v1/bot/messages/create for private chats.

        Args:
            chat_id: Recipient user ID
            title: Card title
            link: Card click-through link
            description: Card description
            icon_link: Card icon image link
            pc_link: PC-side redirect link
            from_name: Source name
            from_icon_link: Source icon image link
        """
        token = await self._get_app_token()
        if not token:
            return SendResult(success=False, error="Failed to get token")

        try:
            is_group = self._is_group_chat(chat_id)

            if is_group:
                url = f"{self._api_gateway_url}{API_ENDPOINTS['smart_bot']['group_message']}?app_token={token}"
            else:
                url = f"{self._api_gateway_url}{API_ENDPOINTS['smart_bot']['private_message']}?app_token={token}"

            link_card_data = {
                "title": title,
                "link": link,
                "description": description or "",
                "iconLink": icon_link or "",
                "pcLink": pc_link or "",
                "fromName": from_name or "",
                "fromIconLink": from_icon_link or "",
            }

            if is_group:
                payload = {
                    "groupId": chat_id,
                    "msgType": "linkCard",
                    "msgData": {"linkCard": link_card_data},
                }
            else:
                payload = {
                    "userIdList": [chat_id],
                    "msgType": "linkCard",
                    "msgData": {"linkCard": link_card_data},
                }

            response = await self._http_client.post(url, json=payload)
            response.raise_for_status()

            if not response.text or len(response.text.strip()) == 0:
                return SendResult(success=False, error="Empty API response", retryable=True)

            data = response.json()

            if data.get("errCode") != 0:
                logger.error("[Lansenger] LinkCard API error: errCode=%s, errMsg=%s",
                             data.get("errCode"), data.get("errMsg"))
                return SendResult(success=False, error=data.get("errMsg", "Unknown error"))

            msg_id = data.get("data", {}).get("msgId")
            logger.info("[Lansenger] LinkCard sent to %s, msgId=%s (group=%s)", chat_id, msg_id, is_group)
            return SendResult(success=True, message_id=msg_id, raw_response=data)
        except Exception as e:
            logger.error("[Lansenger] Send linkCard error: %s", e, exc_info=True)
            return SendResult(success=False, error=str(e), retryable=True)

    async def send_update_prompt(
        self,
        chat_id: str,
        prompt: str,
        default: str = "",
        session_key: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        """Send a dynamic appCard update prompt with /approve /deny reply hints.

        NOTE: This uses appCard (not i18nAppCard).  See send_exec_approval
        docstring for the appCard vs i18nAppCard distinction.

        Uses the user's cached language preference to select content language.

        Used by the gateway's ``/update`` watcher when ``hermes update --gateway``
        needs user input (stash restore, config migration).  Lansenger does not
        support inline button callbacks like Telegram/Discord, so this card
        displays the prompt text with fields showing the text-based reply
        options (/approve → yes, /deny → no).

        The gateway's text intercept recognises /approve, /yes → "y" and
        /deny, /no → "n" and routes them through ``update_prompt.resolve()``.

        Returns SendResult(success=True) so the gateway skips the
        redundant text fallback.
        """
        logger.info(
            "[Lansenger] send_update_prompt: chat_id=%s, prompt=%s, default=%s",
            chat_id, prompt[:80], default,
        )
        token = await self._get_app_token()
        if not token:
            return SendResult(success=False, error="No access token")

        lang = self._get_lang(chat_id)
        prompt_text = prompt or "Update needs your input."
        default_hint = f" (default: {default})" if default else ""
        escaped_prompt = self._escape_html(prompt_text)

        if lang == "zh":
            head_title = "⚕ 更新确认"
            body_title = "更新需要您的输入"
            body_content = f"{escaped_prompt}{default_hint}"
            status_desc = "待确认"
            signature = self._get_agent_signature("zh")
            fields = [
                {"key": "确认执行", "value": "/approve"},
                {"key": "拒绝执行", "value": "/deny"},
            ]
        else:
            head_title = "⚕ Update Confirmation"
            body_title = "Update Needs Your Input"
            body_content = f"{escaped_prompt}{default_hint}"
            status_desc = "Pending"
            signature = self._get_agent_signature("en")
            fields = [
                {"key": "Approve (Yes)", "value": "/approve"},
                {"key": "Deny (No)", "value": "/deny"},
            ]

        head_status_info = {
            "description": self._build_status_div(status_desc, "#FFB116"),
            "colour": "#FFB116",
        }

        try:
            url = self._build_send_url(chat_id, token)
            app_card_data = {
                "headTitle": head_title,
                "headIconUrl": "",
                "isDynamic": True,
                "headStatusInfo": head_status_info,
                "bodyTitle": f'<div style="color:#000;font-size:15pt;text-align:left">{body_title}</div>',
                "bodyContent": f'<div style="color:#000;font-size:13pt;text-align:left;text-indent:0em">{body_content}</div>',
                "signature": f'<div style="color:rgba(0,0,0,.47)">{signature}</div>',
                "fields": fields,
                "cardLink": "",
                "pcCardLink": "",
            }

            payload = self._build_app_card_payload(chat_id, app_card_data)

            response = await self._http_client.post(url, json=payload)
            response.raise_for_status()

            if not response.text or len(response.text.strip()) == 0:
                return SendResult(success=False, error="Empty API response", retryable=True)

            data = response.json()
            if data.get("errCode") != 0:
                logger.error(
                    "[Lansenger] Update prompt appCard API error: errCode=%s, errMsg=%s",
                    data.get("errCode"), data.get("errMsg"),
                )
                return SendResult(success=False, error=data.get("errMsg"))

            msg_id = data.get("data", {}).get("msgId")
            logger.info("[Lansenger] Update prompt appCard sent to %s, msgId=%s", chat_id, msg_id)
            return SendResult(success=True, message_id=msg_id, raw_response=data)

        except Exception as e:
            logger.error("[Lansenger] Send update prompt appCard error: %s", e)
            return SendResult(success=False, error=str(e), retryable=True)
