#!/usr/bin/env python3
"""Pre-expand bundle sub-plugins into ~/.hermes/plugins/ top-level directories.

Run this script after `hermes plugins install lansenger-pm/hermes-lansenger-adapter`
to make the sub-plugins visible to `hermes plugins enable` *before* a gateway restart.

Usage:
    python3 ~/.hermes/plugins/hermes-lansenger-adapter/expand_sub_plugins.py

After running this script, you can enable the sub-plugins individually:
    hermes plugins enable lansenger-platform
    hermes plugins enable lansenger-tools

Alternatively, just restart the gateway — the bundle's register() function
automatically expands, enables, and loads the sub-plugins in-place.
"""

import shutil
import sys
from pathlib import Path

# ── Sub-plugins declared in the bundle manifest ──
_SUB_PLUGINS = {
    "platforms/lansenger": "lansenger-platform",
    "lansenger-tools":     "lansenger-tools",
}


def expand() -> None:
    """Copy each sub-plugin directory into the top-level plugins directory."""
    bundle_dir = Path(__file__).resolve().parent
    plugins_dir = bundle_dir.parent  # ~/.hermes/plugins/

    for sub_rel, sub_name in _SUB_PLUGINS.items():
        src = bundle_dir / sub_rel
        if not src.is_dir():
            print(f"WARNING: Sub-plugin '{sub_name}' not found at {src} — skipping")
            continue

        dest = plugins_dir / sub_name
        if dest.is_dir():
            # Re-expand: remove old and replace with fresh copy
            shutil.rmtree(str(dest))
        shutil.copytree(str(src), str(dest))
        print(f"✓ Expanded '{sub_name}' → {dest}")

    print(f"\nBundle expanded {len(_SUB_PLUGINS)} sub-plugins.")
    print("You can now run:")
    print("  hermes plugins enable lansenger-platform")
    print("  hermes plugins enable lansenger-tools")
    print("Or simply restart the gateway for auto-expand + auto-enable:")


if __name__ == "__main__":
    expand()