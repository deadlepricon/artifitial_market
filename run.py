#!/usr/bin/env python3
"""
Launcher for the exchange simulator. Run from project root:
    python run.py

This script adds the project root and src/ to PYTHONPATH so that
exchange_simulator and config can be found without setting PYTHONPATH manually.
"""
import sys
from pathlib import Path

root = Path(__file__).resolve().parent
src = root / "src"
for path in (root, src):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from exchange_simulator.main import run_app

if __name__ == "__main__":
    run_app()
