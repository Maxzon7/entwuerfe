"""
========================================================================================
Unit Tests: UI Sandbox Isolation & Integrity (tests/test_ui_sandbox.py)
========================================================================================
Verifies that:
1. ui_sandbox/sandbox_app.py compiles and imports cleanly.
2. The main application (app.py, core, models, ui) never imports from ui_sandbox.
========================================================================================
"""

import unittest
import os
import glob
import ast


class TestUISandboxIsolation(unittest.TestCase):
    """Ensures ui_sandbox exists, compiles cleanly, and remains strictly isolated from production code."""

    def setUp(self):
        this_dir = os.path.dirname(os.path.abspath(__file__))
        self.current_model_dir = os.path.abspath(os.path.join(this_dir, ".."))
        self.sandbox_dir = os.path.join(self.current_model_dir, "ui_sandbox")

    def test_sandbox_directory_and_entrypoint_exist(self):
        """Verifies sandbox directory and main sandbox entrypoints exist."""
        self.assertTrue(os.path.isdir(self.sandbox_dir), "ui_sandbox directory must exist")
        entrypoint = os.path.join(self.sandbox_dir, "sandbox_app.py")
        self.assertTrue(os.path.isfile(entrypoint), "ui_sandbox/sandbox_app.py must exist")

        # 1. Current Situation Lab (improved financial architecture)
        currsit_dir = os.path.join(self.sandbox_dir, "Currentsituation_sandbox")
        self.assertTrue(os.path.isdir(currsit_dir), "ui_sandbox/Currentsituation_sandbox directory must exist")
        currsit_app = os.path.join(currsit_dir, "app.py")
        self.assertTrue(os.path.isfile(currsit_app), "ui_sandbox/Currentsituation_sandbox/app.py must exist")

        # 2. Status Quo 2025 Lab
        sq2025_dir = os.path.join(self.sandbox_dir, "status_quo_2025")
        self.assertTrue(os.path.isdir(sq2025_dir), "ui_sandbox/status_quo_2025 directory must exist")
        sq2025_lab = os.path.join(sq2025_dir, "status_quo_lab.py")
        self.assertTrue(os.path.isfile(sq2025_lab), "ui_sandbox/status_quo_2025/status_quo_lab.py must exist")

        # 3. Monthly Baseline Lab
        monthly_dir = os.path.join(self.sandbox_dir, "monthly_baseline_lab")
        self.assertTrue(os.path.isdir(monthly_dir), "ui_sandbox/monthly_baseline_lab directory must exist")
        monthly_app = os.path.join(monthly_dir, "standalone_monthly_baseline_lab.py")
        self.assertTrue(os.path.isfile(monthly_app), "monthly_baseline_lab/standalone_monthly_baseline_lab.py must exist")

        # 4. Three-Party Contract Lab
        three_party_dir = os.path.join(self.sandbox_dir, "three_party_contract_lab")
        self.assertTrue(os.path.isdir(three_party_dir), "ui_sandbox/three_party_contract_lab directory must exist")
        three_party_app = os.path.join(three_party_dir, "minimal_contract_system.py")
        self.assertTrue(os.path.isfile(three_party_app), "three_party_contract_lab/minimal_contract_system.py must exist")

        # Backward compatibility entrypoint shims in root
        baseline_lab_shim = os.path.join(self.sandbox_dir, "standalone_monthly_baseline_lab.py")
        self.assertTrue(os.path.isfile(baseline_lab_shim), "ui_sandbox/standalone_monthly_baseline_lab.py shim must exist")
        contract_shim = os.path.join(self.sandbox_dir, "minimal_contract_system.py")
        self.assertTrue(os.path.isfile(contract_shim), "ui_sandbox/minimal_contract_system.py shim must exist")

    def test_production_codebase_never_imports_ui_sandbox(self):
        """Strict architectural guard: Main app, core, models, and ui must NEVER import ui_sandbox."""
        prod_patterns = [
            os.path.join(self.current_model_dir, "*.py"),
            os.path.join(self.current_model_dir, "core", "**", "*.py"),
            os.path.join(self.current_model_dir, "models", "**", "*.py"),
            os.path.join(self.current_model_dir, "ui", "**", "*.py"),
        ]

        illegal_imports = []
        for pattern in prod_patterns:
            for py_file in glob.glob(pattern, recursive=True):
                if "ui_sandbox" in py_file or "__pycache__" in py_file:
                    continue
                try:
                    with open(py_file, "r", encoding="utf-8") as f:
                        tree = ast.parse(f.read(), filename=py_file)
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Import):
                            for alias in node.names:
                                if "ui_sandbox" in alias.name:
                                    illegal_imports.append((py_file, alias.name))
                        elif isinstance(node, ast.ImportFrom):
                            if node.module and "ui_sandbox" in node.module:
                                illegal_imports.append((py_file, node.module))
                except Exception as err:
                    self.fail(f"Could not parse {py_file}: {err}")

        self.assertEqual(
            len(illegal_imports), 0,
            f"Illegal imports from ui_sandbox detected in production code: {illegal_imports}"
        )


if __name__ == "__main__":
    unittest.main()
