# Conversación, visión y percepción

- Estado: Planeado
- Validación: No validado

## Propósito y alcance

Conversación abarcaría STT, diálogo/LLM, TTS y sincronización de boca. Visión y
percepción abarcarían adquisición, detección o reconocimiento y generación de
eventos genéricos para Cortex.

## Entradas, salidas e interfaces

Entradas posibles: audio e imágenes. Salidas: texto, audio e intenciones o
eventos estructurados. Ninguna interfaz ni proveedor está adoptado.

## Hardware, software y dependencias

No se encontró implementación local de Vosk, Piper, Gemini, cámara u OpenCV.
Los puertos vacíos o eventos genéricos de Cortex no demuestran estas
capacidades.

## Seguridad y pruebas

Una intención de LLM nunca puede evitar planificación, seguridad o RobotPort.
Faltan corpus, métricas, privacidad, comportamiento sin red y experimentos
reproducibles.

## Próximos pasos

Elegir primero un caso de uso medible y crear un experimento autocontenido; no
crear una arquitectura de proveedores por anticipado.

