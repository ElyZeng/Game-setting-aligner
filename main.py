#!/usr/bin/env python3
"""Game Setting Aligner – entry point.

Run this script to launch the GUI application::

    python main.py
"""

import sys
import os

# Ensure the project root is on the path so that all submodules are importable
_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def main() -> None:
    try:
        from gui import App
    except ImportError as exc:
        print(f"[ERROR] Could not import GUI module: {exc}", file=sys.stderr)
        print("Please install dependencies: pip install -r requirements.txt", file=sys.stderr)
        sys.exit(1)

    app = App()
    app.run()


if __name__ == "__main__":
    main()
