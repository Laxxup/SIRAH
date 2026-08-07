#!/bin/bash
# Launch SIRAH voice lab fully detached so it survives the launching shell.
cd /home/laxxup/SIRAHv0.2
export PYTHONPATH="src"
exec .venv/bin/python scripts/sirah_voice_lab.py \
  --camera /dev/video2 \
  --serial /dev/ttyUSB0 \
  --mic hw:1,0 \
  --speaker default \
  --mirror true
