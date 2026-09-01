"""
========================================================================================
Unit Tests: Codebase Syntax Compilation (tests/test_syntax_compilation.py)
========================================================================================
"""

import unittest
import py_compile
import glob
import os
import importlib
import sys


class TestSyntaxCompilation(unittest.TestCase):
    """Verifies all Python files compile cleanly without syntax errors or invalid imports."""

    def test_all_python_files_compile(self):
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        pattern = os.path.join(project_root, "**", "*.py")
        files = [
            f for f in glob.glob(pattern, recursive=True)
            if "__pycache__" not in f and ".git" not in f and ".gemini" not in f
        ]

        self.assertTrue(len(files) >= 10, f"Expected multiple Python files, found {len(files)}")

        failed_files = []
        for file_path in files:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                compile(content, file_path, "exec")
            except Exception as err:
                failed_files.append((file_path, str(err)))

        self.assertEqual(
            len(failed_files), 0,
            f"Compilation errors detected in {len(failed_files)} file(s):\n" +
            "\n".join([f"{f}: {err}" for f, err in failed_files])
        )

    def test_all_current_model_modules_import(self):
        """Verifies that all current_model modules can be imported without NameErrors."""
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        if project_root not in sys.path:
            sys.path.insert(0, project_root)

        modules_to_test = [
            "current_model.app",
            "current_model.ui.tab1_consumption.view",
            "current_model.ui.tab1_consumption.synthetic.view",
            "current_model.ui.tab1_consumption.synthetic.forms",
            "current_model.ui.tab1_consumption.synthetic.charts",
            "current_model.ui.tab1_consumption.csv_inspector.view",
            "current_model.ui.tab1_consumption.csv_inspector.forms",
            "current_model.ui.tab1_consumption.csv_inspector.charts",
            "current_model.ui.tab2_contract.view",
            "current_model.ui.tab2_contract.form",
            "current_model.ui.tab2_contract.charts",
            "current_model.ui.tab2_contract.comparison_view",
            "current_model.ui.tab2_contract.comparison_charts",
            "current_model.ui.tab3_solar.view",
            "current_model.ui.tab3_solar.forms",
            "current_model.ui.tab3_solar.charts",
        ]

        for mod_name in modules_to_test:
            try:
                importlib.import_module(mod_name)
            except Exception as e:
                self.fail(f"Failed to import {mod_name}: {e}")


if __name__ == "__main__":
    unittest.main()
