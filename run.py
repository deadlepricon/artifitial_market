#!/usr/bin/env python3
"""
Entry script for the exchange simulator.
Usage:
  python run.py           -- live mode (Binance + synthetic book)
  python run.py --simulation  -- simulation only (synthetic, higher volatility/drift)
"""

import argparse
import sys
from pathlib import Path

# Ensure src is on path
_root = Path(__file__).resolve().parent
_src = _root / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_root))
    sys.path.insert(0, str(_src))


def main() -> None:
    parser = argparse.ArgumentParser(description="Exchange simulator")
    parser.add_argument(
        "--simulation",
        action="store_true",
        help="Run in simulation mode (synthetic only, no Binance; higher volatility and drift)",
    )
    args = parser.parse_args()

    from exchange_simulator.logging.events import configure_logging
    from exchange_simulator.main import run_app

    configure_logging()
    run_app(simulation=args.simulation)


if __name__ == "__main__":
    main()
