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
from pathlib import Path

logger = logging.getLogger("hermes-lansenger-adapter")

# ── Sub-plugins declared in the bundle manifest ──
#  Key = relative path inside the bundle repo
#  Value = (target directory name in ~/.hermes/plugins/, Python import path)
_SUB_PLUGINS = {
    "platforms/lansenger": ("lansenger-platform", "platforms.lansenger"),
    "lansenger-tools":     ("lansenger-tools",   "lansenger_tools"),
}


def register(ctx):
    """Expand bundle sub-plugins, auto-enable, and load them in-place."""
    bundle_dir = Path(__file__).resolve().parent
    plugins_dir = bundle_dir.parent  # ~/.hermes/plugins/

    for sub_rel, (sub_name, import_path) in _SUB_PLUGINS.items():
        src = bundle_dir / sub_rel
        if not src.is_dir():
            logger.warning(
                "Bundle sub-plugin '%s' not found at %s — skipping",
                sub_name, src,
            )
            continue

        # ── Step 1: Copy to top-level ──────────────────────────────
        dest = plugins_dir / sub_name
        if dest.is_dir():
            logger.debug("Updating '%s' from %s", sub_name, src)
            shutil.rmtree(str(dest))
        shutil.copytree(str(src), str(dest))
        logger.info("Expanded '%s' → %s", sub_name, dest)

        # ── Step 2: Auto-enable in config.yaml ──────────────────────
        _auto_enable(sub_name)

        # ── Step 3: Load sub-plugin register() in-place ─────────────
        _load_sub_plugin(sub_name, dest, ctx)

    # ── Step 4: Remove bundle from enabled set ──────────────────────
    _auto_disable("hermes-lansenger-adapter")

    logger.info(
        "hermes-lansenger-adapter bundle: expanded and loaded %d sub-plugins",
        len(_SUB_PLUGINS),
    )


def _load_sub_plugin(name: str, directory: Path, ctx) -> None:
    """Import the sub-plugin module and call its ``register(ctx)``."""
    init_file = directory / "__init__.py"
    if not init_file.exists():
        logger.warning("Sub-plugin '%s' has no __init__.py — skipping load", name)
        return

    try:
        spec = importlib.util.spec_from_file_location(
            f"_bundle_sub_{name}",
            str(init_file),
            submodule_search_locations=[str(directory)],
        )
        module = importlib.util.module_from_spec(spec)
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