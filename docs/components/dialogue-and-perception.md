# Conversación, visión y percepción

- Estado: En desarrollo
- Validación: TTS y Vosk PTT validados con dobles; micrófono no validado

## Propósito y alcance

Conversación abarcaría STT, diálogo/LLM, TTS y sincronización de boca. Visión y
percepción abarcarían adquisición, detección o reconocimiento y generación de
eventos genéricos para Cortex.

## Entradas, salidas e interfaces

Entradas posibles: audio e imágenes. Salidas: texto, audio e intenciones o
eventos estructurados. Ninguna interfaz ni proveedor está adoptado.

## Hardware, software y dependencias

Gemini textual, Piper CLI y Vosk PTT tienen adaptadores concretos. Piper usa un
modelo y reproductor externos; Vosk usa modelo y `arecord` externos. No se
incluyen modelos ni se validan altavoz o micrófono físicos. No existe
implementación local de cámara u OpenCV.

## Seguridad y pruebas

Una intención de LLM nunca puede evitar planificación, seguridad o RobotPort.
Faltan corpus, métricas, privacidad, comportamiento sin red y experimentos
reproducibles.

## Próximos pasos

Validar Vosk con micrófono local mediante el smoke opt-in. No añadir escucha
permanente, wake word ni AEC sin requisitos y pruebas separados.
