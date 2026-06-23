#!/usr/bin/env bash
# polycaption setup (macOS / Linux). Windows: run `setup.bat` or `python setup.py`.
# Cross-platform logic lives in setup.py; this is just a convenience wrapper.
set -euo pipefail
cd "$(dirname "$0")"
if command -v python3 >/dev/null 2>&1; then exec python3 setup.py "$@"; fi
exec python setup.py "$@"
