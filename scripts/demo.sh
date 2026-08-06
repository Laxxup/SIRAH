#!/usr/bin/env bash
# demo.sh — SIRAH v2 Interactive Demo
# Muestra conversación con Groq + cambio de mood en tiempo real
set -e

echo "╔══════════════════════════════════════╗"
echo "║      SIRAH v2 — DEMO EN VIVO        ║"
echo "║   Groq Llama 3.3 + Piper TTS        ║"
echo "║   Mood Engine + Autonomía            ║"
echo "╚══════════════════════════════════════╝"
echo ""
echo "Comandos rápidos para el demo:"
echo "  1. Escribe 'Hola' → SIRAH responde (NEUTRAL)"
echo "  2. Escribe '/mood happy' → cambia a HAPPY"
echo "  3. Escribe 'Hola' otra vez → respuesta más cálida"
echo "  4. Escribe '/mood tired' → cambia a TIRED"
echo "  5. Escribe 'Cuéntame algo' → respuesta breve"
echo "  6. Escribe '/mood concerned' → preocupado"
echo "  7. Escribe '/status' → ver estado"
echo "  8. Escribe '/quit' → salir"
echo ""
echo "Iniciando SIRAH..."
echo ""

# Check for GROQ_API_KEY
if [ -z "$GROQ_API_KEY" ]; then
    echo "ERROR: GROQ_API_KEY no está definida."
    echo "Usa: GROQ_API_KEY=gsk_xxxx ./demo.sh"
    echo ""
    echo "Ejecutando con inteligencia de laboratorio (sin API)..."
    sirah-console --intel=laboratory --tts=piper
else
    sirah-console --intel=groq --tts=piper
fi
