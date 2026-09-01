"""
Automated Test Suite Package (tests)
===================================
Contains automated test suites for data models, core engines, backward compatibility,
and syntax compilation within current_model.
"""

import sys
import os

# Ensure both current_model and parent directory are in sys.path
_this_dir = os.path.abspath(os.path.dirname(__file__))
_current_model_dir = os.path.abspath(os.path.join(_this_dir, ".."))
_parent_dir = os.path.abspath(os.path.join(_current_model_dir, ".."))

for _p in [_current_model_dir, _parent_dir]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

