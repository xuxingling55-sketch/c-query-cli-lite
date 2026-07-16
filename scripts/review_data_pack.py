#!/usr/bin/env python3
"""Stable executable wrapper for the one-click review command."""

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from review_pack.cli import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
