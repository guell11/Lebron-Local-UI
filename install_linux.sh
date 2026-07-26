#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip wheel setuptools
pip install torch --index-url https://download.pytorch.org/whl/cu128
pip install -r requirements.txt
if [ -f ../Lebron/requirements.txt ]; then pip install -r ../Lebron/requirements.txt; fi
python diagnose.py
