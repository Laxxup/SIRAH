#!/usr/bin/env bash
# deploy_laptop.sh — Install SIRAH runtime clients on a laptop/workstation

set -euo pipefail

echo "=== SIRAH Laptop Installer ==="

# 1. Create the Python 3.14 environment required by SIRAH.
echo "[1/4] Creating virtual environment..."
python3.14 -m venv .venv
source .venv/bin/activate

# 2. Install dev deps
echo "[2/4] Installing SIRAH + dev tools..."
pip install --upgrade pip
pip install -e ".[dev]"

# 3. Runtime clients do not install device extras.
echo "[3/4] Keeping runtime clients device-free..."

# 4. Verify
echo "[4/4] Running quick check..."
.venv/bin/python -c "import sirah; print('SIRAH client package OK')"
.venv/bin/python -m pytest tests/ -q --tb=short || echo "Some tests may fail without Cortex installed."

echo
echo "=== Done! ==="
echo "Start sirah-runtime separately, then provide SIRAH_RUNTIME_SOCKET and SIRAH_CLI_SECRET."
echo "Run the console client: .venv/bin/sirah-console"
