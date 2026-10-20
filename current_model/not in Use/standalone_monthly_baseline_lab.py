"""
========================================================================================
Backward Compatibility Shim: standalone_monthly_baseline_lab.py
========================================================================================
This file is kept at ui_sandbox/standalone_monthly_baseline_lab.py to guarantee 100%
backward compatibility for existing scripts, tests, and CLI invocations.
The authoritative implementation now resides in:
  current_model/ui_sandbox/monthly_baseline_lab/
========================================================================================
"""

import sys
import os

# Delegate directly to monthly_baseline_lab package
from current_model.ui_sandbox.monthly_baseline_lab.standalone_monthly_baseline_lab import *
from current_model.ui_sandbox.monthly_baseline_lab.standalone_monthly_baseline_lab import (
    main,
    render_monthly_baseline_lab,
)

if __name__ == "__main__":
    main()
