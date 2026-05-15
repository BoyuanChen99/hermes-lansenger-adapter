#!/usr/bin/env python3
"""Pre-expand bundle sub-plugins and install the skill.

Run this script after `hermes plugins install lansenger-pm/hermes-lansenger-adapter`
to make the sub-plugins and skill available *before* a gateway restart.

Usage:
    python3 ~/.hermes/plugins/hermes-lansenger-adapter/expand_sub_plugins.py

After running this script, you can enable the sub-plugins individually:
    hermes plugins enable lansenger-platform
    hermes plugins enable lansenger-tools

The skill is also installed automatically to ~/.hermes/skills/lansenger/.

Alternatively, just restart the gateway — the bundle's register() function
automatically expands, enables, and loads the sub-plugins in-place, and
this script installs the skill.
"""

import shutil
import sys
from pathlib import Path

# ── Sub-plugins declared in the bundle manifest ──
_SUB_PLUGINS = {
    "platforms/lansenger": "lansenger-platform",
    "lansenger-tools":     "lansenger-tools",
}

_SKILL_DIR = "skills/lansenger-messaging"
_SKILL_CATEGORY = "lansenger"


def expand() -> None:
    """Copy each sub-plugin directory into the top-level plugins directory,
    and install the skill into the skills directory."""
    bundle_dir = Path(__file__).resolve().parent
    plugins_dir = bundle_dir.parent  # ~/.hermes/plugins/

    for sub_rel, sub_name in _SUB_PLUGINS.items():
        src = bundle_dir / sub_rel
        if not src.is_dir():
            print(f"WARNING: Sub-plugin '{sub_name}' not found at {src} — skipping")
            continue

        dest = plugins_dir / sub_name
        if dest.is_dir():
            shutil.rmtree(str(dest))
        shutil.copytree(str(src), str(dest))
        print(f"✓ Expanded '{sub_name}' → {dest}")

    skill_src = bundle_dir / _SKILL_DIR
    if skill_src.is_dir():
        skills_dir = Path.home() / ".hermes" / "skills" / _SKILL_CATEGORY
        dest = skills_dir / _SKILL_DIR.split("/")[-1]
        if dest.is_dir():
            shutil.rmtree(str(dest))
        shutil.copytree(str(skill_src), str(dest))
        print(f"✓ Installed skill → {dest}")
    else:
        print(f"WARNING: Skill directory not found at {skill_src} — skipping")

    print(f"\nBundle expanded {len(_SUB_PLUGINS)} sub-plugins + skill.")
    print("You can now run:")
    print("  hermes plugins enable lansenger-platform")
    print("  hermes plugins enable lansenger-tools")
    print("Or simply restart the gateway for auto-expand + auto-enable.")


if __name__ == "__main__":
    expand()