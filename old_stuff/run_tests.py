#!/usr/bin/env python
"""
========================================================================================
Automated Test Runner & Health Check Suite (run_tests.py)
========================================================================================

Usage:
------
    python run_tests.py
    (or pytest)

Description:
------------
Discovers and executes all unit, integration, and compilation tests across the project.
Ensures new developments do not introduce regressions or break existing environments.
"""

import sys
import os
import unittest
import time

# Ensure UTF-8 output encoding on Windows consoles
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def main():
    print("=" * 80)
    print("[TEST] RUNNING AUTOMATED TEST & HEALTH CHECK SUITE")
    print(f"[PATH] Workspace Root: {PROJECT_ROOT}")
    print("=" * 80)

    start_time = time.time()

    loader = unittest.TestLoader()
    suite = loader.discover(start_dir=os.path.join(PROJECT_ROOT, "tests"), pattern="test_*.py")

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    elapsed = time.time() - start_time
    print("=" * 80)
    print("TEST SUMMARY:")
    print(f"   * Total Tests Executed: {result.testsRun}")
    print(f"   * Failures: {len(result.failures)}")
    print(f"   * Errors: {len(result.errors)}")
    print(f"   * Execution Time: {elapsed:.3f} seconds")

    if result.wasSuccessful():
        print("[SUCCESS] ALL TESTS PASSED! Environment is stable and ready for development.")
        print("=" * 80)
        return 0
    else:
        print("[FAILED] SOME TESTS FAILED! Please review failure tracebacks above.")
        print("=" * 80)
        return 1


if __name__ == "__main__":
    sys.exit(main())
