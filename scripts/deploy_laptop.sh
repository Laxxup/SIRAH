#!/usr/bin/env bash
# deploy_laptop.sh — Install SIRAH on laptop/workstation

set -euo pipefail

echo "=== SIRAH Laptop Installer ==="

# 1. Create venv
echo "[1/4] Creating virtual environment..."
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dev deps
echo "[2/4] Installing SIRAH + dev tools..."
pip install --upgrade pip
pip install -e ".[dev]"

# 3. Optional: Groq + perception
echo "[3/4] Installing optional deps..."
pip install -e ".[groq,full]" 2>/dev/null || echo "Some optional deps skipped (OK for dev)."

# 4. Verify
echo "[4/4] Running quick check..."
.venv/bin/python -c "from sirah.factory import build_system; print('SIRAH OK')"
.venv/bin/python -m pytest tests/ -q --tb=short || echo "Some tests may fail without Cortex installed."

echo
echo "=== Done! ==="
echo "Run interactive console: .venv/bin/sirah-console"
echo "Or: .venv/bin/python -c \"import asyncio; from sirah.console import main; asyncio.run(main())\""
