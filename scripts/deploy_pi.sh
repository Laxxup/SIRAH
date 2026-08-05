#!/usr/bin/env bash
# deploy_pi.sh — Install SIRAH Edge Server on Raspberry Pi 4B
# Run this ON the Raspberry Pi.

set -euo pipefail

echo "=== SIRAH Edge Server Installer for Raspberry Pi 4B ==="
echo

# 1. System deps
echo "[1/5] Installing system dependencies..."
sudo apt-get update -qq
sudo apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv \
    piper-tts alsa-utils \
    libcamera0 libcamera-dev \
    python3-opencv || true

# 2. Create venv
echo "[2/5] Creating Python virtual environment..."
python3 -m venv .venv-edge
source .venv-edge/bin/activate

# 3. Install SIRAH
echo "[3/5] Installing SIRAH..."
pip install --upgrade pip
pip install -e .

# 4. Optional: perception support
echo "[4/5] Installing perception (MediaPipe + OpenCV)..."
pip install opencv-python-headless mediapipe numpy || {
    echo "WARNING: MediaPipe install failed. Perception will be simulated."
}

# 5. Start script
cat > run_edge_server.sh << 'SCRIPT'
#!/usr/bin/env bash
source .venv-edge/bin/activate
python3 -c "
import asyncio
from sirah.bridge.pi_server import EdgeServer
async def main():
    server = EdgeServer(host='0.0.0.0', port=8765)
    await server.start()
    print('Edge server running on :8765')
    await asyncio.Event().wait()
asyncio.run(main())
"
SCRIPT
chmod +x run_edge_server.sh

echo
echo "=== Done! ==="
echo "Run the edge server: ./run_edge_server.sh"
echo "Connect from laptop: sirah-console --profile=DEV_DISTRIBUTED"
