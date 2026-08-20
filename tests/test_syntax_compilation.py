"""
========================================================================================
Unit Tests: Codebase Syntax Compilation (tests/test_syntax_compilation.py)
========================================================================================
"""

import unittest
import py_compile
import glob
import os


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
                py_compile.compile(file_path, doraise=True)
            except Exception as err:
                failed_files.append((file_path, str(err)))

        self.assertEqual(
            len(failed_files), 0,
            f"Compilation errors detected in {len(failed_files)} file(s):\n" +
            "\n".join([f"{f}: {err}" for f, err in failed_files])
        )


if __name__ == "__main__":
    unittest.main()
