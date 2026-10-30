#!/usr/bin/env bash
# VAULT STL repair on macOS and Linux - repairs the STL meshes of a whole library with numpy (numpy_repair.py)
# and writes a repaired copy of the library.
#   ./vault_stl_repair.sh ~/VAULT ~/VAULT_repaired [--workers 2] [--all] [--only text] [--skip text]
# An interrupted run (Ctrl+C) can be started again - finished files are skipped.
cd "$(dirname "$0")" || exit 1

if [ $# -lt 2 ]; then
  echo "Usage: ./vault_stl_repair.sh ~/VAULT ~/VAULT_repaired [--workers 2] [--all] [--only text] [--skip text]"
  echo "       first folder = your VAULT STL library, second = new folder for the repaired copy"
  exit 1
fi

# Python 3 with numpy: a private .venv next to this script, else python3/python; when numpy cannot be installed
# into the system Python (Homebrew, Debian/Ubuntu - "externally managed"), a .venv is created here
PY=
if [ -x .venv/bin/python ] && .venv/bin/python -c 'import numpy' >/dev/null 2>&1; then
  PY=.venv/bin/python
else
  for c in python3 python; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(sys.version_info < (3, 9))' >/dev/null 2>&1; then
      if "$c" -c 'import numpy' >/dev/null 2>&1; then PY="$c"; break; fi
      [ -z "$BASE" ] && BASE="$c"
    fi
  done
fi
if [ -z "$PY" ] && [ -n "$BASE" ]; then
  echo "Installing numpy into a private environment (.venv next to this script)..."
  if "$BASE" -m venv .venv && .venv/bin/python -m pip install --quiet numpy; then
    PY=.venv/bin/python
  fi
fi
if [ -z "$PY" ]; then
  echo "Python 3.9+ with numpy not found. Install Python 3 (macOS: https://www.python.org/downloads/ or Homebrew;"
  echo "Linux: the python3 and python3-venv packages) and run this script again."
  exit 1
fi

"$PY" vault_stl_repair.py "$@"
CODE=$?
echo
if [ "$CODE" -eq 0 ]; then echo "Finished without errors."; else echo "Finished with code ${CODE} - see the messages above."; fi
exit "$CODE"
