#!/usr/bin/env bash
# Limpieza local: verifica que ningún artefacto generado esté versionado y
# elimina caches de Python (pytest, mypy, ruff, __pycache__, egg-info). No
# toca .venv. Usa la raíz real del repositorio para funcionar en cualquier
# checkout, sin rutas fijas.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

echo "=== SIRAH local cleanup ==="
echo

echo "[1/4] Verificando que no haya artefactos generados versionados..."

TRACKED="$(git ls-files \
  '.mypy_cache/*' \
  '.pytest_cache/*' \
  '.ruff_cache/*' \
  'src/*.egg-info/*' \
  'src/**/*.egg-info/*' \
  '*__pycache__*' \
  '.venv/*')"

if [[ -n "$TRACKED" ]]; then
    echo "ERROR: hay archivos generados versionados:"
    echo "$TRACKED"
    echo
    echo "No se eliminó nada."
    exit 1
fi

echo "✓ Ninguno está versionado."
echo

echo "[2/4] Eliminando caches Python..."
find . \
  -path './.git' -prune -o \
  -path './.worktrees' -prune -o \
  -type d -name '__pycache__' -prune -exec rm -rf {} +

rm -rf \
  .pytest_cache \
  .mypy_cache \
  .ruff_cache \
  src/*.egg-info

echo "✓ Caches eliminados."
echo

echo "[3/4] Manteniendo .venv intacta."
echo "✓ No se tocó el entorno virtual."
echo

echo "[4/4] Estado final:"
git status --short

echo
echo "✓ Limpieza terminada."
