# Conversación, visión y percepción

- Estado: En desarrollo
- Validación: TTS validado con dobles; audio físico no validado

## Propósito y alcance

Conversación abarcaría STT, diálogo/LLM, TTS y sincronización de boca. Visión y
percepción abarcarían adquisición, detección o reconocimiento y generación de
eventos genéricos para Cortex.

## Entradas, salidas e interfaces

Entradas posibles: audio e imágenes. Salidas: texto, audio e intenciones o
eventos estructurados. Ninguna interfaz ni proveedor está adoptado.

## Hardware, software y dependencias

Gemini textual y Piper CLI tienen adaptadores concretos. Piper usa un modelo y
reproductor externos; no incluye voces ni valida altavoz físico. No existe
implementación local de Vosk, STT, cámara u OpenCV. Los eventos genéricos de
Cortex no demuestran esas capacidades.

## Seguridad y pruebas

Una intención de LLM nunca puede evitar planificación, seguridad o RobotPort.
Faltan corpus, métricas, privacidad, comportamiento sin red y experimentos
reproducibles.

## Próximos pasos

Validar Piper en audio local. Para entrada de voz, elegir después un caso de uso
push-to-talk medible; no añadir escucha permanente.
