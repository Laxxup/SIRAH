#!/usr/bin/env bash
# deploy_pi.sh — Prepare the SIRAH runtime and optional local Web Lab client.
# Run this only on a target that already provides Python 3.14, after the source
# is present in /opt/sirah (or set SIRAH_INSTALL_DIR). It installs and
# configures unit files but never enables or starts a system service.

set -euo pipefail

INSTALL_DIR="${SIRAH_INSTALL_DIR:-/opt/sirah}"
PYTHON="python3.14"

echo "=== SIRAH runtime preparation (Python 3.14) ==="
echo

# 1. Never substitute the target interpreter with a lower system Python.
echo "[1/4] Checking Python 3.14..."
if ! command -v "$PYTHON" > /dev/null 2>&1; then
    echo "ERROR: Python 3.14 is required, but python3.14 is unavailable." >&2
    echo "Use a supported target with Python 3.14, then rerun this script." >&2
    exit 1
fi

if [ ! -f "$INSTALL_DIR/pyproject.toml" ]; then
    echo "ERROR: expected SIRAH source at $INSTALL_DIR" >&2
    exit 1
fi

# 2. Install the headless runtime package; no Piper, camera, or hardware extra.
echo "[2/4] Installing sirah-runtime..."
sudo "$PYTHON" -m venv "$INSTALL_DIR/.venv"
sudo "$INSTALL_DIR/.venv/bin/python" -m pip install --upgrade pip
sudo "$INSTALL_DIR/.venv/bin/python" -m pip install -e "$INSTALL_DIR"

# 3. Install service designs and credential-free environment examples.
echo "[3/4] Installing runtime and optional Web Lab client configuration..."
sudo install -d -m 0750 /etc/sirah
sudo install -m 0644 "$INSTALL_DIR/deploy/systemd/sirah-runtime.service" \
    /etc/systemd/system/sirah-runtime.service
sudo install -m 0644 "$INSTALL_DIR/deploy/systemd/sirah-web-lab.service" \
    /etc/systemd/system/sirah-web-lab.service
sudo install -m 0600 "$INSTALL_DIR/deploy/systemd/runtime.env.example" \
    /etc/sirah/runtime.env.example
sudo install -m 0600 "$INSTALL_DIR/deploy/systemd/web-lab.env.example" \
    /etc/sirah/web-lab.env.example
sudo systemctl daemon-reload

# 4. Service account can read the installation and its two private env files.
echo "[4/4] Preparing service account..."
if ! id -u sirah > /dev/null 2>&1; then
    sudo useradd --system --user-group --home-dir /opt/sirah --shell /usr/sbin/nologin sirah
fi
sudo chown -R sirah:sirah "$INSTALL_DIR"

echo
echo "Create /etc/sirah/runtime.env from runtime.env.example and replace secrets."
echo "For optional local Web Lab, create /etc/sirah/web-lab.env from its example."
echo "This script does not run systemctl; review and enable units explicitly."
