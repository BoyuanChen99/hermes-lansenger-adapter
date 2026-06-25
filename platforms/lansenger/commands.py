"""
Lansenger Slash Command registration — auto-register Hermes built-in + plugin
commands with the Lansenger Bot API on startup, and clean up on shutdown.

Permission model (configurable via config.yaml extra.command_permissions):
    owner    → scopeType=1 (owner private chat only)
    admin    → scopeType=1 (owner) + scopeType=6 (all group admins)
    everyone → scopeType=1 (owner) + scopeType=5 (all groups)

Commands not listed in command_permissions default to "everyone".

Auto-registration can be disabled via config (priority: per-platform > env > default):
    platforms.lansenger.extra.commands.native: true/false (per-platform)
    LANSENGER_SLASH_COMMANDS_NATIVE=0                     (global env override)
    Default: true
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Lansenger API scope types ──────────────────────────────────────────────
SCOPE_SINGLE_CHAT = 1        # 单个指定聊天
SCOPE_GROUP_ADMINS = 2       # 指定单个群的管理员
SCOPE_GROUP_MEMBER = 3       # 单个指定群的单个成员
SCOPE_ALL_DM = 4             # 所有私聊
SCOPE_ALL_GROUPS = 5         # 所有群
SCOPE_ALL_GROUP_ADMINS = 6   # 所有群管理员
SCOPE_GLOBAL = 7             # 默认全局

# ── Permission → scope mappings ────────────────────────────────────────────
_PERMISSION_SCOPES: Dict[str, List[tuple]] = {
    "owner": [
        (SCOPE_SINGLE_CHAT, True),   # owner private chat
    ],
    "admin": [
        (SCOPE_SINGLE_CHAT, True),   # owner private chat
        (SCOPE_ALL_GROUP_ADMINS, False),  # all group admins
    ],
    "everyone": [
        (SCOPE_SINGLE_CHAT, True),   # owner private chat
        (SCOPE_ALL_GROUPS, False),   # all groups
    ],
}

DEFAULT_PERMISSION = "everyone"

# Config key paths
ENV_SLASH_COMMANDS_NATIVE = "LANSENGER_SLASH_COMMANDS_NATIVE"

# ── Multi-language command descriptions ────────────────────────────────────
# Populated from OpenClaw's BUILTIN_COMMAND_I18N where names overlap,
# plus new translations for Hermes-specific commands.
# Languages: zhHans, zhHant, zhHantHK, en, fr

_I18NEntry = Dict[str, str]

COMMAND_I18N: Dict[str, _I18NEntry] = {
    # ── Session ──
    "start": {
        "zhHans": "确认平台启动通知",
        "zhHant": "確認平台啟動通知",
        "zhHantHK": "確認平台啟動通知",
        "en": "Acknowledge platform start pings.",
        "fr": "Accuser réception des pings de démarrage.",
    },
    "new": {
        "zhHans": "开始新会话",
        "zhHant": "開始新會話",
        "zhHantHK": "開始新會話",
        "en": "Start a new session.",
        "fr": "Démarrer une nouvelle session.",
    },
    "topic": {
        "zhHans": "启用或检查 Telegram 话题会话",
        "zhHant": "啟用或檢查 Telegram 話題會話",
        "zhHantHK": "啟用或檢查 Telegram 話題會話",
        "en": "Enable or inspect Telegram DM topic sessions.",
        "fr": "Activer ou inspecter les sessions de sujets Telegram.",
    },
    "retry": {
        "zhHans": "重试最后一条消息",
        "zhHant": "重試最後一條消息",
        "zhHantHK": "重試最後一條消息",
        "en": "Retry the last message.",
        "fr": "Réessayer le dernier message.",
    },
    "undo": {
        "zhHans": "撤销 N 个用户轮次并重新提问",
        "zhHant": "撤銷 N 個用戶輪次並重新提問",
        "zhHantHK": "撤銷 N 個用戶輪次並重新提問",
        "en": "Back up N user turns and re-prompt.",
        "fr": "Revenir en arrière de N tours et reformuler.",
    },
    "title": {
        "zhHans": "设置当前会话标题",
        "zhHant": "設定當前會話標題",
        "zhHantHK": "設定當前會話標題",
        "en": "Set a title for the current session.",
        "fr": "Définir un titre pour la session.",
    },
    "branch": {
        "zhHans": "分支当前会话（探索不同路径）",
        "zhHant": "分支當前會話（探索不同路徑）",
        "zhHantHK": "分支當前會話（探索不同路徑）",
        "en": "Branch the current session.",
        "fr": "Brancher la session actuelle.",
    },
    "compress": {
        "zhHans": "压缩会话上下文",
        "zhHant": "壓縮會話上下文",
        "zhHantHK": "壓縮會話上下文",
        "en": "Compact the session context.",
        "fr": "Compacter le contexte de session.",
    },
    "rollback": {
        "zhHans": "列出或恢复文件系统检查点",
        "zhHant": "列出或恢復文件系統檢查點",
        "zhHantHK": "列出或恢復文件系統檢查點",
        "en": "List or restore filesystem checkpoints.",
        "fr": "Lister ou restaurer les points de contrôle.",
    },
    "stop": {
        "zhHans": "停止当前运行",
        "zhHant": "停止當前執行",
        "zhHantHK": "停止當前執行",
        "en": "Stop the current run.",
        "fr": "Arrêter l'exécution en cours.",
    },
    "approve": {
        "zhHans": "批准或拒绝执行请求",
        "zhHant": "批准或拒絕執行請求",
        "zhHantHK": "批准或拒絕執行請求",
        "en": "Approve or deny exec requests.",
        "fr": "Approuver ou refuser les demandes d'exécution.",
    },
    "deny": {
        "zhHans": "拒绝危险命令执行",
        "zhHant": "拒絕危險命令執行",
        "zhHantHK": "拒絕危險命令執行",
        "en": "Deny a pending dangerous command.",
        "fr": "Refuser une commande dangereuse en attente.",
    },
    "background": {
        "zhHans": "在后台运行提示词",
        "zhHant": "在後台執行提示詞",
        "zhHantHK": "在後台執行提示詞",
        "en": "Run a prompt in the background.",
        "fr": "Exécuter une invite en arrière-plan.",
    },
    "agents": {
        "zhHans": "显示活动代理和运行任务",
        "zhHant": "顯示活動代理和執行任務",
        "zhHantHK": "顯示活動代理和執行任務",
        "en": "Show active agents and running tasks.",
        "fr": "Afficher les agents actifs et les tâches.",
    },
    "queue": {
        "zhHans": "排队提示词到下一轮",
        "zhHant": "排隊提示詞到下一輪",
        "zhHantHK": "排隊提示詞到下一輪",
        "en": "Queue a prompt for the next turn.",
        "fr": "Mettre en file une invite pour le prochain tour.",
    },
    "steer": {
        "zhHans": "注入消息到下一个工具调用之后",
        "zhHant": "注入消息到下一个工具調用之後",
        "zhHantHK": "注入消息到下一個工具調用之後",
        "en": "Inject a message after the next tool call.",
        "fr": "Injecter un message après le prochain appel d'outil.",
    },
    "goal": {
        "zhHans": "设置会话全局目标",
        "zhHant": "設定會話全局目標",
        "zhHantHK": "設定會話全局目標",
        "en": "Set a standing goal Hermes works on across turns.",
        "fr": "Définir un objectif permanent pour la session.",
    },
    "subgoal": {
        "zhHans": "添加或管理活跃目标的子目标",
        "zhHant": "添加或管理活躍目標的子目標",
        "zhHantHK": "添加或管理活躍目標的子目標",
        "en": "Add or manage extra criteria on the active goal.",
        "fr": "Ajouter ou gérer des critères supplémentaires.",
    },
    "status": {
        "zhHans": "显示当前状态",
        "zhHant": "顯示當前狀態",
        "zhHantHK": "顯示當前狀態",
        "en": "Show current status.",
        "fr": "Afficher l'état actuel.",
    },
    "whoami": {
        "zhHans": "显示你的发送者 ID 和权限",
        "zhHant": "顯示你的發送者 ID 和權限",
        "zhHantHK": "顯示你的發送者 ID 和權限",
        "en": "Show your sender ID and access level.",
        "fr": "Afficher votre identifiant et niveau d'accès.",
    },
    "profile": {
        "zhHans": "显示当前 profile 和主目录",
        "zhHant": "顯示當前 profile 和主目錄",
        "zhHantHK": "顯示當前 profile 和主目錄",
        "en": "Show active profile name and home directory.",
        "fr": "Afficher le profil actif et le répertoire.",
    },
    "sethome": {
        "zhHans": "设此聊天为 home channel",
        "zhHant": "設此聊天為 home channel",
        "zhHantHK": "設此聊天為 home channel",
        "en": "Set this chat as the home channel.",
        "fr": "Définir ce chat comme canal principal.",
    },
    "resume": {
        "zhHans": "恢复之前命名的会话",
        "zhHant": "恢復之前命名的會話",
        "zhHantHK": "恢復之前命名的會話",
        "en": "Resume a previously-named session.",
        "fr": "Reprendre une session nommée précédemment.",
    },
    "sessions": {
        "zhHans": "浏览和恢复之前的会话",
        "zhHant": "瀏覽和恢復之前的會話",
        "zhHantHK": "瀏覽和恢復之前的會話",
        "en": "Browse and resume previous sessions.",
        "fr": "Parcourir et reprendre des sessions précédentes.",
    },

    # ── Configuration ──
    "model": {
        "zhHans": "显示或设置模型",
        "zhHant": "顯示或設定模型",
        "zhHantHK": "顯示或設定模型",
        "en": "Show or set the model.",
        "fr": "Afficher ou définir le modèle.",
    },
    "codex-runtime": {
        "zhHans": "切换 Codex 应用服务器运行时",
        "zhHant": "切換 Codex 應用伺服器執行時",
        "zhHantHK": "切換 Codex 應用伺服器執行時",
        "en": "Toggle codex app-server runtime.",
        "fr": "Basculer le runtime du serveur d'app Codex.",
    },
    "personality": {
        "zhHans": "设置预定义人格",
        "zhHant": "設定預定義人格",
        "zhHantHK": "設定預定義人格",
        "en": "Set a predefined personality.",
        "fr": "Définir une personnalité prédéfinie.",
    },
    "verbose": {
        "zhHans": "切换详细模式",
        "zhHant": "切換詳細模式",
        "zhHantHK": "切換詳細模式",
        "en": "Toggle verbose mode.",
        "fr": "Activer/désactiver le mode verbeux.",
    },
    "footer": {
        "zhHans": "切换回复底部元数据",
        "zhHant": "切換回覆底部元數據",
        "zhHantHK": "切換回覆底部元數據",
        "en": "Toggle runtime-metadata footer on replies.",
        "fr": "Basculer le pied de page des métadonnées.",
    },
    "yolo": {
        "zhHans": "切换 YOLO 模式（跳过审批）",
        "zhHant": "切換 YOLO 模式（跳過審批）",
        "zhHantHK": "切換 YOLO 模式（跳過審批）",
        "en": "Toggle YOLO mode (skip approvals).",
        "fr": "Basculer le mode YOLO (pas d'approbation).",
    },
    "reasoning": {
        "zhHans": "管理推理级别和显示",
        "zhHant": "管理推理級別和顯示",
        "zhHantHK": "管理推理級別和顯示",
        "en": "Manage reasoning effort and display.",
        "fr": "Gérer l'effort de raisonnement et l'affichage.",
    },
    "fast": {
        "zhHans": "切换快速模式",
        "zhHant": "切換快速模式",
        "zhHantHK": "切換快速模式",
        "en": "Toggle fast mode.",
        "fr": "Activer/désactiver le mode rapide.",
    },
    "voice": {
        "zhHans": "切换语音模式",
        "zhHant": "切換語音模式",
        "zhHantHK": "切換語音模式",
        "en": "Toggle voice mode.",
        "fr": "Basculer le mode vocal.",
    },

    # ── Tools & Skills ──
    "memory": {
        "zhHans": "管理待处理记忆 / 切换审批",
        "zhHant": "管理待處理記憶 / 切換審批",
        "zhHantHK": "管理待處理記憶 / 切換審批",
        "en": "Manage pending memories / toggle approval.",
        "fr": "Gérer les mémoires en attente / approbation.",
    },
    "bundles": {
        "zhHans": "列出技能包（别名）",
        "zhHant": "列出技能包（別名）",
        "zhHantHK": "列出技能包（別名）",
        "en": "List skill bundles (aliases).",
        "fr": "Lister les lots de compétences (alias).",
    },
    "suggestions": {
        "zhHans": "查看建议的自动化",
        "zhHant": "查看建議的自動化",
        "zhHantHK": "查看建議的自動化",
        "en": "Review suggested automations.",
        "fr": "Examiner les automatisations suggérées.",
    },
    "blueprint": {
        "zhHans": "从蓝图模板设置自动化",
        "zhHant": "從藍圖模板設定自動化",
        "zhHantHK": "從藍圖模板設定自動化",
        "en": "Set up an automation from a blueprint.",
        "fr": "Configurer une automatisation depuis un plan.",
    },
    "curator": {
        "zhHans": "后台技能维护（状态/运行/归档）",
        "zhHant": "後台技能維護（狀態/執行/歸檔）",
        "zhHantHK": "後台技能維護（狀態/執行/歸檔）",
        "en": "Background skill maintenance.",
        "fr": "Maintenance des compétences en arrière-plan.",
    },
    "reload-mcp": {
        "zhHans": "从配置重新加载 MCP 服务器",
        "zhHant": "從配置重新加載 MCP 伺服器",
        "zhHantHK": "從配置重新加載 MCP 伺服器",
        "en": "Reload MCP servers from config.",
        "fr": "Recharger les serveurs MCP depuis la config.",
    },
    "reload-skills": {
        "zhHans": "重新扫描技能目录",
        "zhHant": "重新掃描技能目錄",
        "zhHantHK": "重新掃描技能目錄",
        "en": "Re-scan skills directory.",
        "fr": "Re-analyser le répertoire des compétences.",
    },

    # ── Info ──
    "commands": {
        "zhHans": "浏览所有命令和技能",
        "zhHant": "瀏覽所有命令和技能",
        "zhHantHK": "瀏覽所有命令和技能",
        "en": "Browse all commands and skills.",
        "fr": "Parcourir toutes les commandes et compétences.",
    },
    "help": {
        "zhHans": "显示可用命令",
        "zhHant": "顯示可用命令",
        "zhHantHK": "顯示可用命令",
        "en": "Show available commands.",
        "fr": "Afficher les commandes disponibles.",
    },
    "restart": {
        "zhHans": "优雅重启网关",
        "zhHant": "優雅重啟網關",
        "zhHantHK": "優雅重啟網關",
        "en": "Gracefully restart the gateway.",
        "fr": "Redémarrer la passerelle proprement.",
    },
    "usage": {
        "zhHans": "显示用量页脚或费用摘要",
        "zhHant": "顯示用量頁腳或費用摘要",
        "zhHantHK": "顯示用量頁腳或費用摘要",
        "en": "Usage footer or cost summary.",
        "fr": "Pied de page d'utilisation ou résumé des coûts.",
    },
    "credits": {
        "zhHans": "显示积分余额和充值",
        "zhHant": "顯示積分餘額和充值",
        "zhHantHK": "顯示積分餘額和充值",
        "en": "Show credit balance and top up.",
        "fr": "Afficher le solde de crédits et recharger.",
    },
    "insights": {
        "zhHans": "显示用量分析和洞察",
        "zhHant": "顯示用量分析和洞察",
        "zhHantHK": "顯示用量分析和洞察",
        "en": "Show usage insights and analytics.",
        "fr": "Afficher les analyses d'utilisation.",
    },
    "platform": {
        "zhHans": "暂停/恢复/列出网关平台",
        "zhHant": "暫停/恢復/列出網關平台",
        "zhHantHK": "暫停/恢復/列出網關平台",
        "en": "Pause, resume, or list gateway platforms.",
        "fr": "Suspendre, reprendre ou lister les plateformes.",
    },
    "update": {
        "zhHans": "更新 Hermes 到最新版本",
        "zhHant": "更新 Hermes 到最新版本",
        "zhHantHK": "更新 Hermes 到最新版本",
        "en": "Update Hermes to the latest version.",
        "fr": "Mettre à jour Hermes vers la dernière version.",
    },
    "version": {
        "zhHans": "显示 Hermes 版本",
        "zhHant": "顯示 Hermes 版本",
        "zhHantHK": "顯示 Hermes 版本",
        "en": "Show Hermes Agent version.",
        "fr": "Afficher la version de Hermes Agent.",
    },
    "debug": {
        "zhHans": "上传调试报告并获取分享链接",
        "zhHant": "上傳調試報告並獲取分享鏈接",
        "zhHantHK": "上傳除錯報告並獲取分享連結",
        "en": "Upload debug report and get shareable links.",
        "fr": "Téléverser un rapport de débogage.",
    },

    # ── Aliases (same translations as canonical names) ──
    "bg": {
        "zhHans": "在后台运行提示词",
        "zhHant": "在後台執行提示詞",
        "zhHantHK": "在後台執行提示詞",
        "en": "Run a prompt in the background.",
        "fr": "Exécuter une invite en arrière-plan.",
    },
    "bp": {
        "zhHans": "从蓝图模板设置自动化",
        "zhHant": "從藍圖模板設定自動化",
        "zhHantHK": "從藍圖模板設定自動化",
        "en": "Set up an automation from a blueprint.",
        "fr": "Configurer une automatisation depuis un plan.",
    },
    "btw": {
        "zhHans": "在后台运行提示词",
        "zhHant": "在後台執行提示詞",
        "zhHantHK": "在後台執行提示詞",
        "en": "Run a prompt in the background.",
        "fr": "Exécuter une invite en arrière-plan.",
    },
    "codex_runtime": {
        "zhHans": "切换 Codex 应用服务器运行时",
        "zhHant": "切換 Codex 應用伺服器執行時",
        "zhHantHK": "切換 Codex 應用伺服器執行時",
        "en": "Toggle codex app-server runtime.",
        "fr": "Basculer le runtime du serveur d'app Codex.",
    },
    "fork": {
        "zhHans": "分支当前会话（探索不同路径）",
        "zhHant": "分支當前會話（探索不同路徑）",
        "zhHantHK": "分支當前會話（探索不同路徑）",
        "en": "Branch the current session.",
        "fr": "Brancher la session actuelle.",
    },
    "kanban": {
        "zhHans": "多 profile 协作看板（任务、链接、评论）",
        "zhHant": "多 profile 協作看板（任務、連結、評論）",
        "zhHantHK": "多 profile 協作看板（任務、連結、評論）",
        "en": "Multi-profile collaboration board.",
        "fr": "Tableau de collaboration multi-profils.",
    },
    "q": {
        "zhHans": "排队提示词到下一轮",
        "zhHant": "排隊提示詞到下一輪",
        "zhHantHK": "排隊提示詞到下一輪",
        "en": "Queue a prompt for the next turn.",
        "fr": "Mettre en file une invite pour le prochain tour.",
    },
    "reload_mcp": {
        "zhHans": "从配置重新加载 MCP 服务器",
        "zhHant": "從配置重新加載 MCP 伺服器",
        "zhHantHK": "從配置重新加載 MCP 伺服器",
        "en": "Reload MCP servers from config.",
        "fr": "Recharger les serveurs MCP depuis la config.",
    },
    "reload_skills": {
        "zhHans": "重新扫描技能目录",
        "zhHant": "重新掃描技能目錄",
        "zhHantHK": "重新掃描技能目錄",
        "en": "Re-scan skills directory.",
        "fr": "Re-analyser le répertoire des compétences.",
    },
    "reset": {
        "zhHans": "开始新会话",
        "zhHant": "開始新會話",
        "zhHantHK": "開始新會話",
        "en": "Start a new session.",
        "fr": "Démarrer une nouvelle session.",
    },
    "set_home": {
        "zhHans": "设此聊天为 home channel",
        "zhHant": "設此聊天為 home channel",
        "zhHantHK": "設此聊天為 home channel",
        "en": "Set this chat as the home channel.",
        "fr": "Définir ce chat comme canal principal.",
    },
    "set-home": {
        "zhHans": "设此聊天为 home channel",
        "zhHant": "設此聊天為 home channel",
        "zhHantHK": "設此聊天為 home channel",
        "en": "Set this chat as the home channel.",
        "fr": "Définir ce chat comme canal principal.",
    },
    "suggest": {
        "zhHans": "查看建议的自动化",
        "zhHant": "查看建議的自動化",
        "zhHantHK": "查看建議的自動化",
        "en": "Review suggested automations.",
        "fr": "Examiner les automatisations suggérées.",
    },
    "tasks": {
        "zhHans": "显示活动代理和运行任务",
        "zhHant": "顯示活動代理和執行任務",
        "zhHantHK": "顯示活動代理和執行任務",
        "en": "Show active agents and running tasks.",
        "fr": "Afficher les agents actifs et les tâches.",
    },
    "v": {
        "zhHans": "显示 Hermes 版本",
        "zhHant": "顯示 Hermes 版本",
        "zhHantHK": "顯示 Hermes 版本",
        "en": "Show Hermes Agent version.",
        "fr": "Afficher la version de Hermes Agent.",
    },
}


def _native_commands_enabled(config_extra: dict) -> bool:
    """Check whether native slash command auto-registration is enabled.

    Priority: per-platform config > global env var > default (true).

    - ``config_extra.commands.native`` — per-platform override
    - ``LANSENGER_SLASH_COMMANDS_NATIVE`` env var — global override
      (set to ``"0"``, ``"false"``, or ``"no"`` to disable)
    - Default: ``True``
    """
    # 1. Per-platform config (deep key lookup)
    commands_cfg = config_extra.get("commands")
    if isinstance(commands_cfg, dict):
        native_val = commands_cfg.get("native")
        if native_val is not None:
            return bool(native_val)

    # 2. Global env override
    env_val = os.getenv(ENV_SLASH_COMMANDS_NATIVE, "").strip().lower()
    if env_val in ("0", "false", "no", "off"):
        return False
    if env_val in ("1", "true", "yes", "on"):
        return True

    # 3. Default
    return True


def _get_builtin_commands() -> Dict[str, dict]:
    """Return Hermes built-in commands suitable for gateway platforms.

    Reads :data:`hermes_cli.commands.COMMAND_REGISTRY` and filters out
    ``cli_only`` commands (which only work in the CLI, not on messaging
    platforms).  ``gateway_only`` commands are included — they are
    registered as ``owner``-level by default.

    Returns ``{command_name: {description, gateway_only, ...}}``.
    Returns an empty dict on any error.
    """
    try:
        from hermes_cli.commands import COMMAND_REGISTRY
    except Exception:
        logger.debug("[Lansenger] Could not import COMMAND_REGISTRY", exc_info=True)
        return {}

    result: Dict[str, dict] = {}
    for cmd in COMMAND_REGISTRY:
        if getattr(cmd, "cli_only", False):
            continue  # CLI-only commands can't work on messaging platforms
        result[cmd.name] = {
            "description": getattr(cmd, "description", ""),
            "gateway_only": getattr(cmd, "gateway_only", False),
        }
        # Also register aliases
        for alias in getattr(cmd, "aliases", ()):
            if alias not in result:
                result[alias] = {
                    "description": getattr(cmd, "description", ""),
                    "gateway_only": getattr(cmd, "gateway_only", False),
                }
    return result


def _get_plugin_commands() -> Dict[str, dict]:
    """Lazily import and return all plugin-registered slash commands.

    Returns a dict of ``{command_name: {handler, description, plugin, args_hint}}``.
    Returns an empty dict on any error so callers degrade gracefully.
    """
    try:
        from hermes_cli.plugins import get_plugin_commands
        return get_plugin_commands() or {}
    except Exception:
        logger.debug("[Lansenger] Could not import get_plugin_commands", exc_info=True)
        return {}


def _get_all_commands() -> Dict[str, dict]:
    """Combine built-in + plugin commands.

    Plugin commands take precedence when a name collides (unlikely —
    Hermes's ``register_command`` already rejects built-in name collisions).
    """
    builtins = _get_builtin_commands()
    plugins = _get_plugin_commands()
    # Plugin overrides built-in (if collision ever occurs)
    merged = dict(builtins)
    merged.update(plugins)
    return merged


def _resolve_default_permissions(commands: Dict[str, dict]) -> Dict[str, str]:
    """Derive default permission levels from command metadata.

    - ``gateway_only`` → ``"owner"`` (only the bot owner can use these)
    - Everything else → ``"everyone"``
    """
    perms: Dict[str, str] = {}
    for name, meta in commands.items():
        if meta.get("gateway_only"):
            perms[name] = "owner"
        else:
            perms[name] = "everyone"
    return perms


def resolve_command_permissions(commands: Dict[str, dict], config_extra: dict) -> Dict[str, str]:
    """Map each command name to its permission level.

    1. Start with default permissions from command metadata.
    2. Override with ``config_extra.command_permissions`` where present.

    Supports ``"disabled"`` as a special permission value — the command will be
    excluded from registration entirely for this profile.
    """
    defaults = _resolve_default_permissions(commands)
    perm_config = config_extra.get("command_permissions", {}) or {}
    if not isinstance(perm_config, dict):
        perm_config = {}

    result: Dict[str, str] = {}
    for cmd_name in commands:
        # User override wins over default
        user_perm = perm_config.get(cmd_name)
        if user_perm == "disabled":
            logger.info("[Lansenger] Command '/%s' disabled for this profile, skipping", cmd_name)
            continue
        perm = user_perm if user_perm else defaults.get(cmd_name, DEFAULT_PERMISSION)
        if perm not in _PERMISSION_SCOPES:
            logger.warning(
                "[Lansenger] Unknown permission '%s' for command '/%s', falling back to '%s'",
                perm, cmd_name, DEFAULT_PERMISSION,
            )
            perm = DEFAULT_PERMISSION
        result[cmd_name] = perm
    return result


def _build_description_i18n(cmd_name: str) -> Dict[str, str]:
    """Build the ``description_i18n`` dict for a command name.

    Pulls from :data:`COMMAND_I18N` if the command has a translation entry;
    otherwise returns an empty dict (Lansenger will fall back to ``description``).
    """
    entry = COMMAND_I18N.get(cmd_name)
    if not entry:
        return {}
    return dict(entry)  # shallow copy


def build_command_payloads(
    commands: Dict[str, dict],
    permissions: Dict[str, str],
    owner_id: str,
) -> List[Dict[str, Any]]:
    """Build a list of Lansenger API request payloads grouped by (scopeType, needs_owner).

    Each command entry includes ``description`` and ``description_i18n``
    (zhHans/zhHant/zhHantHK/en/fr) for Lansenger's native UI.
    """
    # Group commands by (scopeType, needs_owner_id)
    scoped: Dict[tuple, List[Dict[str, Any]]] = {}
    for cmd_name, cmd_meta in commands.items():
        perm = permissions.get(cmd_name, DEFAULT_PERMISSION)
        scope_list = _PERMISSION_SCOPES.get(perm, _PERMISSION_SCOPES[DEFAULT_PERMISSION])
        description = cmd_meta.get("description", f"Run /{cmd_name}")

        entry: Dict[str, Any] = {
            "command": cmd_name,
            "description": description[:100],
        }
        i18n = _build_description_i18n(cmd_name)
        if i18n:
            entry["description_i18n"] = i18n

        for scope_type, needs_owner in scope_list:
            key = (scope_type, needs_owner)
            scoped.setdefault(key, []).append(entry)

    # Build payloads
    payloads: List[Dict[str, Any]] = []
    for (scope_type, needs_owner), cmd_list in scoped.items():
        payload: Dict[str, Any] = {
            "scopeType": scope_type,
            "commands": cmd_list,
        }
        if needs_owner and owner_id:
            payload["chatId"] = owner_id
            payload["chatType"] = "staff"
        payloads.append(payload)

    return payloads


async def register_all_commands(adapter: Any) -> bool:
    """Collect all built-in + plugin commands and register them with Lansenger API.

    Called after the adapter's WebSocket connects successfully.
    Returns True if all registrations succeeded, False otherwise.

    If owner_id is not yet known (first message hasn't arrived), the
    registration is deferred and will retry when the owner is detected.
    """
    extra = getattr(adapter, "_config_extra", {}) or {}
    if not _native_commands_enabled(extra):
        logger.info("[Lansenger] Native slash commands disabled")
        return False

    commands = _get_all_commands()
    if not commands:
        logger.info("[Lansenger] No commands to register (built-in + plugin)")
        return True

    owner_id = getattr(adapter, "_owner_id", None)
    if not owner_id:
        logger.info(
            "[Lansenger] Owner ID not yet known — skipping command registration "
            "(will retry when owner is detected)"
        )
        return False

    permissions = resolve_command_permissions(commands, extra)
    payloads = build_command_payloads(commands, permissions, owner_id)

    token = await adapter._get_app_token()
    if not token:
        logger.error("[Lansenger] Cannot register commands: no app token")
        return False

    api_gateway = adapter._api_gateway_url
    http_client = adapter._http_client
    if not http_client:
        logger.error("[Lansenger] Cannot register commands: no HTTP client")
        return False

    # Counters for summary
    total = sum(len(p["commands"]) for p in payloads)
    scoped_count = 0
    all_ok = True

    for i, payload in enumerate(payloads):
        scope_type = payload.get("scopeType")
        cmd_names = [c["command"] for c in payload.get("commands", [])]
        i18n_count = sum(1 for c in payload.get("commands", []) if c.get("description_i18n"))
        logger.info(
            "[Lansenger] Registering %d commands with scopeType=%d (%d with i18n): %s",
            len(cmd_names), scope_type, i18n_count,
            cmd_names[:5] + (["..."] if len(cmd_names) > 5 else []),
        )

        try:
            url = f"{api_gateway}/v1/bot/commands/create?app_token={token}"
            response = await http_client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()

            if data.get("errCode") != 0:
                logger.error(
                    "[Lansenger] Failed to register commands (scopeType=%d): errCode=%s, errMsg=%s",
                    scope_type, data.get("errCode"), data.get("errMsg"),
                )
                all_ok = False
            else:
                scoped_count += 1
                logger.info(
                    "[Lansenger] Registered %d commands with scopeType=%d successfully",
                    len(cmd_names), scope_type,
                )
        except Exception as exc:
            logger.error(
                "[Lansenger] Error registering commands (scopeType=%d): %s",
                scope_type, exc,
            )
            all_ok = False

    logger.info(
        "[Lansenger] Command registration summary: %d commands in %d/%d scopes %s",
        total, scoped_count, len(payloads),
        "OK" if all_ok else "with errors",
    )
    return all_ok


async def delete_all_commands(adapter: Any) -> bool:
    """Delete all commands registered by this bot from Lansenger.

    Called during adapter disconnect. Deletes commands for all scopes
    that were previously registered (owner private chat, all groups, all group admins).
    """
    extra = getattr(adapter, "_config_extra", {}) or {}
    if not _native_commands_enabled(extra):
        logger.debug("[Lansenger] Native slash commands disabled, skipping cleanup")
        return True

    owner_id = getattr(adapter, "_owner_id", None)

    token = await adapter._get_app_token()
    if not token:
        logger.debug("[Lansenger] Cannot delete commands: no app token")
        return False

    api_gateway = adapter._api_gateway_url
    http_client = adapter._http_client
    if not http_client:
        logger.debug("[Lansenger] Cannot delete commands: no HTTP client")
        return False

    # Delete for each scope type that might have been registered
    scopes_to_clear = [
        (SCOPE_SINGLE_CHAT, True),        # owner private chat
        (SCOPE_ALL_GROUPS, False),        # all groups
        (SCOPE_ALL_GROUP_ADMINS, False),  # all group admins
    ]

    all_ok = True
    for scope_type, needs_owner in scopes_to_clear:
        payload: Dict[str, Any] = {"scopeType": scope_type}
        if needs_owner and owner_id:
            payload["chatId"] = owner_id
            payload["chatType"] = "staff"
        elif needs_owner and not owner_id:
            continue  # never registered without owner

        try:
            url = f"{api_gateway}/v1/bot/commands/delete?app_token={token}"
            logger.info("[Lansenger] Deleting commands for scopeType=%d", scope_type)
            response = await http_client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()

            if data.get("errCode") != 0:
                logger.warning(
                    "[Lansenger] Failed to delete commands (scopeType=%d): errCode=%s, errMsg=%s",
                    scope_type, data.get("errCode"), data.get("errMsg"),
                )
                all_ok = False
            else:
                logger.info("[Lansenger] Deleted commands for scopeType=%d", scope_type)
        except Exception as exc:
            logger.warning(
                "[Lansenger] Error deleting commands (scopeType=%d): %s",
                scope_type, exc,
            )
            all_ok = False

    return all_ok


async def dispatch_slash_command(adapter: Any, text: str, chat_id: str, sender_id: str,
                                 is_group: bool) -> Optional[str]:
    """Try to dispatch *text* as a plugin slash command.

    If *text* starts with ``/`` and matches a registered plugin command,
    executes the handler and returns the result text. Returns None if
    the text is not a recognized plugin command (caller should proceed
    with normal LLM processing).

    The caller is responsible for sending the returned text as a reply.
    """
    if not text.startswith("/"):
        return None

    # Parse: "/cmd arg1 arg2" → name="cmd", raw_args="arg1 arg2"
    parts = text[1:].split(maxsplit=1)
    cmd_name = parts[0].lower().strip()
    raw_args = parts[1] if len(parts) > 1 else ""

    # Only plugin commands have handlers — built-in commands go to LLM
    commands = _get_plugin_commands()
    cmd_meta = commands.get(cmd_name)
    if not cmd_meta:
        return None  # not a recognized plugin command — let LLM handle

    handler = cmd_meta.get("handler")
    if not handler:
        logger.warning("[Lansenger] Command '/%s' has no handler", cmd_name)
        return None

    # Check permissions for the caller
    all_cmds = _get_all_commands()
    extra = getattr(adapter, "_config_extra", {}) or {}
    permissions = resolve_command_permissions(all_cmds, extra)
    perm = permissions.get(cmd_name, DEFAULT_PERMISSION)
    owner_id = getattr(adapter, "_owner_id", None)

    if not _check_execute_permission(perm, sender_id, owner_id, is_group):
        logger.info(
            "[Lansenger] Permission denied: /%s (perm=%s) for sender=%s (is_group=%s)",
            cmd_name, perm, sender_id, is_group,
        )
        return f"❌ 你没有权限使用 /{cmd_name} 命令。"

    logger.info(
        "[Lansenger] Dispatching slash command '/%s' args=%r from sender=%s",
        cmd_name, raw_args, sender_id,
    )

    try:
        import asyncio
        if asyncio.iscoroutinefunction(handler):
            result = await handler(raw_args)
        else:
            result = handler(raw_args)
    except Exception as exc:
        logger.error("[Lansenger] Command '/%s' handler error: %s", cmd_name, exc)
        return f"❌ 命令 /{cmd_name} 执行出错：{exc}"

    return result if result else None


def _check_execute_permission(perm: str, sender_id: str, owner_id: Optional[str],
                              is_group: bool) -> bool:
    """Check if *sender_id* can execute a command with permission level *perm*.

    - owner: only the owner (sender == owner_id) can execute, anywhere
    - admin: owner can execute anywhere; group admins TBD (Lansenger doesn't
      expose admin status in callback events, so we only check owner_id for now)
    - everyone: anyone can execute
    """
    if perm == "everyone":
        return True

    if perm == "owner":
        return bool(owner_id) and sender_id == owner_id

    if perm == "admin":
        # Lansenger callback events don't include admin status.
        # For group messages, we allow if the sender is the owner.
        # (scopeType=6 already limits visibility to admins in the Lansenger UI,
        # so anyone who can see the command can execute it.)
        if is_group:
            return True  # scopeType=6 already filtered visibility
        return bool(owner_id) and sender_id == owner_id

    return False