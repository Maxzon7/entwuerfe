"""
========================================================================================
Backward Compatibility Shim: minimal_contract_system.py
========================================================================================
This file is kept at ui_sandbox/minimal_contract_system.py to guarantee 100%
backward compatibility for existing scripts, tests, and CLI invocations.
The authoritative implementation now resides in:
  current_model/ui_sandbox/three_party_contract_lab/
========================================================================================
"""

import sys
import os

from current_model.ui_sandbox.three_party_contract_lab.minimal_contract_system import *
from current_model.ui_sandbox.three_party_contract_lab.minimal_contract_system import (
    main,
    render_minimal_contract_system,
    ThreePartyContract,
)

if __name__ == "__main__":
    main()
