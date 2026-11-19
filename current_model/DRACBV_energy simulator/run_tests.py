"""
Standalone Test & Isolation Verification Runner
===============================================

Verifies:
  1. Strict Path Isolation: Every imported module (`current_model`, `core`,
     `models`, `ui`, `ui_sandbox`) resolves strictly inside this export folder.
  2. Combined Sandbox Physics, Sizing, Financials, Excel & PDF Regression Suite.
"""

from __future__ import annotations

import os
import sys
import unittest

_ROOT_DIR = os.path.abspath(os.path.dirname(__file__))
if _ROOT_DIR not in sys.path:
    sys.path.insert(0, _ROOT_DIR)

import _bootstrap

STANDALONE_ROOT = _bootstrap.bootstrap_standalone_root()


def verify_strict_standalone_isolation() -> None:
    """Asserts that no imported package resolves outside STANDALONE_ROOT."""
    import current_model
    import current_model.core.csv_parser as csv_mod
    import current_model.models.solar as solar_mod
    import current_model.ui.common.cards as cards_mod
    import current_model.ui_sandbox.Currentsituation_sandbox.engine.consumption_pipeline as pipe_mod
    import current_model.ui_sandbox.Combined_sandbox.combined_sandbox_engine as comb_mod

    checked_modules = {
        "current_model": getattr(current_model, "__file__", ""),
        "core.csv_parser": getattr(csv_mod, "__file__", ""),
        "models.solar": getattr(solar_mod, "__file__", ""),
        "ui.common.cards": getattr(cards_mod, "__file__", ""),
        "Currentsituation_sandbox.engine.consumption_pipeline": getattr(pipe_mod, "__file__", ""),
        "Combined_sandbox.combined_sandbox_engine": getattr(comb_mod, "__file__", ""),
    }

    norm_root = os.path.normcase(os.path.abspath(STANDALONE_ROOT))
    for label, mod_file in checked_modules.items():
        if not mod_file:
            raise AssertionError(f"Module `{label}` has no __file__ attribute.")
        norm_mod = os.path.normcase(os.path.abspath(mod_file))
        common = os.path.commonpath([norm_root, norm_mod])
        if common != norm_root:
            raise AssertionError(
                f"ISOLATION BREACH: `{label}` loaded from `{norm_mod}` instead of `{norm_root}`!"
            )
    print(f"[ISOLATION OK] Verified {len(checked_modules)} package roots inside: {STANDALONE_ROOT}")


def main() -> int:
    print("=" * 72)
    print("DRACBV Energy Simulator - Standalone Verification Suite")
    print("=" * 72)
    verify_strict_standalone_isolation()

    loader = unittest.TestLoader()
    suite = loader.loadTestsFromName("tests.test_combined_sandbox")
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("=" * 72)
    total = result.testsRun
    failures = len(result.failures)
    errors = len(result.errors)
    print(f"Summary: Ran={total}, Failures={failures}, Errors={errors}")
    print("=" * 72)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
