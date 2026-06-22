"""Hermes Lansenger Adapter bundle — auto-expands sub-plugins on first load.

When ``hermes plugins install lansenger-pm/hermes-lansenger-adapter`` clones
this repo, the two sub-plugins (``lansenger-platform`` and ``lansenger-tools``)
live *inside* the clone directory.  The ``hermes plugins enable`` command only
checks ``~/.hermes/plugins/`` *direct* children, so it cannot find them there.

This bundle's ``register()`` function solves that by:

1. Copying each sub-plugin directory into ``~/.hermes/plugins/`` at the top
   level (where ``enable`` can see them).
2. Auto-enabling each sub-plugin in ``config.yaml``.
3. Directly importing and calling each sub-plugin's ``register(ctx)`` so
   they are loaded in the *current* gateway session — no second restart
   needed.
4. Removing the bundle itself from the enabled set (it's just a container).

After the first gateway restart, both sub-plugins are fully operational.
"""

import importlib
import importlib.util
import logging
import shutil
import sys
from pathlib import Path

logger = logging.getLogger("hermes-lansenger-adapter")

# ── Sub-plugins declared in the bundle manifest ──
#  Key = relative path inside the bundle repo
#  Value = (target directory name in ~/.hermes/plugins/, Python import path)
_SUB_PLUGINS = {
    "platforms/lansenger": ("lansenger-platform", "platforms.lansenger"),
    "lansenger-tools":     ("lansenger-tools",   "lansenger_tools"),
}

_SKILL_DIRS = ["skills/lansenger-messaging", "skills/lansenger-setup"]
_SKILL_CATEGORY = "lansenger"


# ── Module-level expand ────────────────────────────────────────────
# When Python imports this module (e.g. during gateway plugin loading),
# immediately copy sub-plugin directories to the top-level plugins dir
# so that `hermes plugins enable <name>` can find them even if the user
# runs it in a *later* session (without a restart in between).
#
# This also means that if the gateway imports the bundle module but then
# discovers the sub-plugins *after* expand (i.e. on a second discovery
# pass), they will already be visible at the top level.
#
_expand_done = False


def _expand_sub_plugins() -> None:
    """Copy each sub-plugin directory to ~/.hermes/plugins/ top level
    and install the skill to ~/.hermes/skills/.

    This runs at module-import time so the sub-plugins are visible to
    ``hermes plugins enable`` even before the gateway calls register().
    It is idempotent — subsequent calls re-copy (update) the directories.
    """
    global _expand_done
    bundle_dir = Path(__file__).resolve().parent
    plugins_dir = bundle_dir.parent  # ~/.hermes/plugins/

    for sub_rel, (sub_name, _import_path) in _SUB_PLUGINS.items():
        src = bundle_dir / sub_rel
        if not src.is_dir():
            logger.warning(
                "Bundle sub-plugin '%s' not found at %s — skipping",
                sub_name, src,
            )
            continue

        dest = plugins_dir / sub_name
        if dest.is_dir():
            shutil.rmtree(str(dest))
        shutil.copytree(str(src), str(dest))
        logger.info("Expanded '%s' → %s", sub_name, dest)

    for skill_rel in _SKILL_DIRS:
        skill_src = bundle_dir / skill_rel
        if skill_src.is_dir():
            skills_dir = Path.home() / ".hermes" / "skills" / _SKILL_CATEGORY
            skill_dest = skills_dir / skill_rel.split("/")[-1]
            if skill_dest.is_dir():
                shutil.rmtree(str(skill_dest))
            shutil.copytree(str(skill_src), str(skill_dest))
            logger.info("Installed skill → %s", skill_dest)
        else:
            logger.warning("Skill directory not found at %s — skipping", skill_src)

    _expand_done = True


# Execute expand on first import
if not _expand_done:
    _expand_sub_plugins()


def register(ctx):
    """Auto-enable and load expanded sub-plugins in-place.

    By the time register() is called, _expand_sub_plugins() has already
    copied the sub-plugins to the top-level plugins directory (module-level
    code above).  This function now:
    1. Auto-enables each sub-plugin in config.yaml
    2. Loads each sub-plugin's register(ctx) in-place
    3. Removes the bundle itself from the enabled set
    """
    bundle_dir = Path(__file__).resolve().parent
    plugins_dir = bundle_dir.parent  # ~/.hermes/plugins/

    # Ensure expand has been done (idempotent — re-copies if needed)
    _expand_sub_plugins()

    for sub_rel, (sub_name, import_path) in _SUB_PLUGINS.items():
        dest = plugins_dir / sub_name
        if not dest.is_dir():
            continue

        # ── Step 1: Auto-enable in config.yaml ──────────────────────
        _auto_enable(sub_name)

        # ── Step 2: Load sub-plugin register() in-place ─────────────
        _load_sub_plugin(sub_name, dest, ctx)

    # ── Step 3: Remove bundle from enabled set ──────────────────────
    _auto_disable("hermes-lansenger-adapter")

    logger.info(
        "hermes-lansenger-adapter bundle: enabled and loaded %d sub-plugins",
        len(_SUB_PLUGINS),
    )


def _load_sub_plugin(name: str, directory: Path, ctx) -> None:
    """Import the sub-plugin module and call its ``register(ctx)``."""
    init_file = directory / "__init__.py"
    if not init_file.exists():
        logger.warning("Sub-plugin '%s' has no __init__.py — skipping load", name)
        return

    # Python module names cannot contain hyphens; convert to underscores.
    safe_mod_name = f"_bundle_sub_{name.replace('-', '_')}"

    try:
        spec = importlib.util.spec_from_file_location(
            safe_mod_name,
            str(init_file),
            submodule_search_locations=[str(directory)],
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[safe_mod_name] = module  # prevent double-import
        spec.loader.exec_module(module)

        register_fn = getattr(module, "register", None)
        if register_fn is None:
            logger.warning("Sub-plugin '%s' has no register() function", name)
            return

        register_fn(ctx)
        logger.info("Loaded sub-plugin '%s' register() in-place", name)
    except Exception as exc:
        logger.warning("Failed to load sub-plugin '%s' in-place: %s", name, exc)


def _auto_enable(name: str) -> None:
    """Add *name* to ``config.yaml`` plugins.enabled list."""
    try:
        from hermes_cli.config import load_config, save_config
        config = load_config()
        plugins_cfg = config.get("plugins", {})
        if not isinstance(plugins_cfg, dict):
            plugins_cfg = {}
            config["plugins"] = plugins_cfg
        enabled = plugins_cfg.get("enabled", [])
        if isinstance(enabled, list) and name not in enabled:
            enabled.append(name)
            plugins_cfg["enabled"] = sorted(enabled)
            save_config(config)
            logger.info("Auto-enabled '%s'", name)
        # Remove from disabled list if present
        disabled = plugins_cfg.get("disabled", [])
        if isinstance(disabled, list) and name in disabled:
            plugins_cfg["disabled"] = [d for d in disabled if d != name]
            save_config(config)
    except Exception as exc:
        logger.warning("Could not auto-enable '%s': %s", name, exc)


def _auto_disable(name: str) -> None:
    """Remove *name* from ``config.yaml`` plugins.enabled list."""
    try:
        from hermes_cli.config import load_config, save_config
        config = load_config()
        plugins_cfg = config.get("plugins", {})
        if not isinstance(plugins_cfg, dict):
            return
        enabled = plugins_cfg.get("enabled", [])
        if isinstance(enabled, list) and name in enabled:
            plugins_cfg["enabled"] = sorted([e for e in enabled if e != name])
            save_config(config)
            logger.info("Removed bundle '%s' from enabled set", name)
    except Exception as exc:
        logger.warning("Could not auto-disable '%s': %s", name, exc)