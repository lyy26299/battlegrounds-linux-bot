#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
[[ "$(uname -s)" == Linux && "$(uname -m)" == x86_64 ]] || { echo 'Requires x86_64 Linux'; exit 1; }
python3 -c 'import sys; assert (3,10) <= sys.version_info[:2] < (3,13), "Use Python 3.10–3.12"'
# System dependencies must first be installed using the commands in README.txt.
for tool in Xvfb xauth xdpyinfo xprop openbox dbus-run-session; do
    command -v "$tool" >/dev/null || { echo "Missing dependency: $tool"; exit 1; }
done
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
printf '%s\n' 'Components installed. Next: install upstream linux-gui, login, configure paths, test.'
