#!/bin/bash
# Launch SIRAH fast voice lab (tiny Whisper, VAD, overlap).
cd /home/laxxup/SIRAHv0.2
export PYTHONPATH="src"
[ -f .env ] && set -a && . ./.env && set +a
exec .venv/bin/python scripts/sirah_voice_lab_fast.py \
  --camera /dev/video2 --serial /dev/ttyUSB0 --mic hw:1,0 --speaker default --mirror true "${@:-}"
