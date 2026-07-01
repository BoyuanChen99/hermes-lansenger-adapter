"""
i18n and utility mixin for LansengerAdapter.
Handles language detection, HTML escaping, div-style fixing, and agent signature.
"""

import logging
import os
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class I18nUtilsMixin:
    """i18n and utility methods for LansengerAdapter."""

    def _build_agent_signature_i18n(self) -> Dict[str, str]:
        """Build the i18nSignature with the agent name from SOUL.md (dynamic).

        RESERVED for future i18nAppCard use.  Currently not called by
        any active flow — the approval workflow uses appCard with
        language detection instead.

        Falls back to "Hermes" if SOUL.md cannot be read.  The signature
        format is "{agent_name} 安全系统" / "{agent_name} Security System" etc.
        """
        agent_name = self._read_agent_name_from_soul()

        return self._build_i18n_obj_full(
            f"{agent_name} 安全系统",
            f"{agent_name} 安全系統",
            f"{agent_name} 安全系統",
            f"{agent_name} Security",
            f"{agent_name} Sécurité"
        )

    def _read_agent_name_from_soul(self) -> str:
        """Read the agent display name from SOUL.md.

        Looks for the **Name:** field in the YAML frontmatter or markdown
        body of ~/.hermes/SOUL.md.  Returns "Hermes" as fallback.
        """
        try:
            soul_path = self._resolve_hermes_home() / "SOUL.md"
            if not soul_path.exists():
                return "Hermes"

            content = soul_path.read_text(encoding="utf-8")

            # Try YAML frontmatter first (--- ... ---)
            if content.startswith("---"):
                end = content.find("---", 3)
                if end != -1:
                    frontmatter = content[3:end]
                    # Look for "Name:" in frontmatter
                    for line in frontmatter.split("\n"):
                        line = line.strip()
                        if line.startswith("Name:") or line.startswith("name:"):
                            name = line.split(":", 1)[1].strip()
                            if name:
                                return name

            # Try markdown body — look for **Name:** pattern
            match = re.search(r"\*?\*?Name:?\*?\*?\s*:?\s*(.+)", content, re.IGNORECASE)
            if match:
                name = match.group(1).strip()
                # Strip markdown bold/italic markers
                name = name.replace("*", "").strip()
                if name:
                    return name

            return "Hermes"
        except Exception:
            return "Hermes"

    def _build_i18n_obj_full(self, zh_hans: str, zh_hant: str, zh_hant_hk: str, en: str, fr: str) -> Dict[str, str]:
        """Build i18n object with all 5 supported languages.

        RESERVED for future i18nAppCard use.  Currently not called by
        any active flow — the approval workflow uses appCard with
        language detection (single-language per card) instead.

        Args:
            zh_hans: Simplified Chinese text
            zh_hant: Traditional Chinese text
            zh_hant_hk: Traditional Chinese (Hong Kong) text
            en: English text
            fr: French text

        Returns:
            Dict with language codes as keys
        """
        return {
            "zhHans": zh_hans,
            "zhHant": zh_hant,
            "zhHantHK": zh_hant_hk,
            "en": en,
            "fr": fr
        }

    def _escape_html(self, text: str) -> str:
        """Escape &lt;, &gt;, and &amp; to prevent HTML tag parsing.

        Client doesn't support HTML entities like &quot; or &amp;,
        but we need to escape &lt; and &gt; to prevent them from being
        parsed as HTML tags, and &amp; to prevent misinterpretation
        as entity references.
        """
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def _convert_font_px_to_pt(self, text: str) -> str:
        """Convert font-size px values to pt in div-style HTML strings.

        Lansenger enterprise deployment rejects font-size with px unit.
        1px ≈ 0.75pt. Common sizes: 14px→10.5pt, 16px→12pt, 18px→13.5pt.
        Only converts numeric px values; pt values are left unchanged.
        """
        def _px_to_pt(m):
            px_val = float(m.group(1))
            pt_val = px_val * 0.75
            if pt_val == int(pt_val):
                return f"font-size:{int(pt_val)}pt"
            return f"font-size:{pt_val}pt"
        return re.sub(r'font-size:(\d+(?:\.\d+)?)px', _px_to_pt, text)

    def _fix_text_indent(self, text: str) -> str:
        """Fix bare text-indent:0 to text-indent:0em in div-style strings.

        Lansenger API rejects text-indent without a unit (bare '0').
        Per spec, text-indent only applies to bodyContent.
        """
        if not text:
            return text
        return re.sub(r'text-indent:0(?![\d.em])', 'text-indent:0em', text)

    def _fix_app_card_styles(self, field: str, is_body_content: bool = False) -> str:
        """Apply all div-style fixes for appCard fields.

        Per Lansenger API spec:
        - font-size px→pt: applies to headTitle, bodyTitle, bodySubTitle, bodyContent
        - text-indent bare-0→0em: applies only to bodyContent
        """
        field = self._convert_font_px_to_pt(field)
        if is_body_content:
            field = self._fix_text_indent(field)
        return field

    def _detect_lang(self, text: str) -> str:
        """Detect language from user message text. Returns 'zh' or 'en'.

        Any Chinese character → 'zh'. Only pure non-Chinese text → 'en'.
        """
        for ch in text:
            cp = ord(ch)
            # CJK Unified Ideographs + Extension A + Compatibility Ideographs
            if 0x4E00 <= cp <= 0x9FFF or 0x3400 <= cp <= 0x4DBF or 0xF900 <= cp <= 0xFAFF:
                return "zh"
        return "en"

    def _extract_trigger_sender_from_session(self, session_key: str) -> Optional[str]:
        """Extract trigger_sender_id from session_key.

        session_key format:
        - Group: agent:main:lansenger:group:{chat_id}:{sender_id}
        - DM:    agent:main:lansenger:dm:{chat_id}

        Returns sender_id for group sessions, None for DM sessions.
        """
        parts = session_key.split(":")
        # Format: agent:main:lansenger:{chat_type}:{chat_id}:{sender_id?}
        if len(parts) >= 6 and parts[3] == "group":
            return parts[5]  # sender_id
        return None  # DM session has no sender_id in key

    def _check_approval_permission(self, sender_id: str) -> bool:
        """Check if sender_id has permission to approve commands.

        Permission rules:
        1. owner_id always has permission
        2. users in approval_allow_from list have permission
        3. others are denied

        Returns True if sender has permission, False otherwise.
        """
        # Owner always has permission
        if self._owner_id and sender_id == self._owner_id:
            return True
        # Check allowlist
        if sender_id in self._approval_allow_from:
            return True
        return False

    def _get_lang(self, chat_id: str) -> str:
        """Get cached user language for chat_id, defaulting to 'zh'."""
        return self._user_lang_map.get(chat_id, "zh")

    def _get_agent_signature(self, lang: str = "zh") -> str:
        """Build agent signature string in the given language.

        Reads agent name from SOUL.md and formats it for appCard signature field.
        """
        agent_name = self._read_agent_name_from_soul()
        if lang == "zh":
            return f"{agent_name} 安全系统"
        elif lang == "fr":
            return f"{agent_name} Sécurité"
        else:
            return f"{agent_name} Security"

    def _build_status_div(self, text: str, color: str) -> str:
        """Build div-style text for headStatusInfo.description.

        headStatusInfo = dot + text. 'description' is the text portion,
        supports single div-style color tag (must be &lt;30 bytes).
        'colour' controls the dot color — they are independent.
        No nested divs — API rejects nested div structure.
        """
        return f'<div style="color:{color}">{text}</div>'

    @property
    def owner_id(self) -> Optional[str]:
        """Get the bot owner's user ID."""
        return self._owner_id
