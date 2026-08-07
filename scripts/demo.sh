#!/usr/bin/env bash
# demo.sh — SIRAH runtime-client console demo
set -e

if [ -z "${SIRAH_RUNTIME_SOCKET:-}" ] || [ -z "${SIRAH_CLI_SECRET:-}" ]; then
    echo "Set SIRAH_RUNTIME_SOCKET and SIRAH_CLI_SECRET for a running sirah-runtime." >&2
    exit 2
fi

exec sirah-console
