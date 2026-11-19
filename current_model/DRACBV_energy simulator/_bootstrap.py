"""
Standalone Import Bootstrap (DRACBV Energy Simulator)
====================================================

Ensures all package imports (`core.*`, `models.*`, `ui.*`, `ui_sandbox.*`, and
`current_model.*`) resolve strictly from this standalone folder, regardless of
what directory name it has or whether it lives inside a parent checkout.
"""

from __future__ import annotations

import os
import sys
import types


def get_standalone_root() -> str:
    """Returns the normalized absolute directory containing this standalone app."""
    return os.path.abspath(os.path.dirname(__file__))


def bootstrap_standalone_root() -> str:
    """
    Pins `sys.path` and `sys.modules["current_model"]` exclusively to this standalone folder.
    Strips any parent or grandparent paths so a surrounding checkout cannot shadow files.
    """
    root = get_standalone_root()
    ui_sandbox_dir = os.path.join(root, "ui_sandbox")
    parent_dir = os.path.abspath(os.path.join(root, ".."))
    grandparent_dir = os.path.abspath(os.path.join(parent_dir, ".."))

    excluded = {
        os.path.normcase(parent_dir),
        os.path.normcase(grandparent_dir),
    }

    cleaned_path = []
    seen = set()
    for raw_entry in sys.path:
        if not raw_entry:
            continue
        abs_entry = os.path.normcase(os.path.abspath(raw_entry))
        if abs_entry in excluded or abs_entry in seen:
            continue
        seen.add(abs_entry)
        cleaned_path.append(raw_entry)

    # Ensure root precedes ui_sandbox_dir and everything else
    for entry in (ui_sandbox_dir, root):
        norm_entry = os.path.normcase(entry)
        cleaned_path = [
            p for p in cleaned_path if os.path.normcase(os.path.abspath(p)) != norm_entry
        ]
        cleaned_path.insert(0, entry)

    sys.path[:] = cleaned_path

    expected_init = os.path.join(root, "__init__.py")
    existing = sys.modules.get("current_model")
    needs_alias = True
    if existing is not None:
        existing_file = getattr(existing, "__file__", "") or ""
        if existing_file and os.path.normcase(os.path.abspath(existing_file)) == os.path.normcase(expected_init):
            needs_alias = False

    if needs_alias:
        for mod_name in list(sys.modules.keys()):
            if mod_name == "current_model" or mod_name.startswith("current_model."):
                del sys.modules[mod_name]

        pkg = types.ModuleType("current_model")
        pkg.__file__ = expected_init
        pkg.__path__ = [root]
        pkg.__package__ = "current_model"
        sys.modules["current_model"] = pkg

    return root
