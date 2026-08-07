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

Groq/Ollama textual, Piper por API Python y Vosk PTT tienen adaptadores
concretos. Piper usa un modelo externo persistente y `aplay` por la salida del
runtime; Vosk usa modelo y `arecord` externos.
La cámara local usa OpenCV y `MediaPipeVision` opcional; los modelos `.task` se
instalan manualmente y no se descargan en runtime. No se validan altavoz,
micrófono ni cámara del robot físicamente.

El Web Lab expone `/api/overlay` como observabilidad local: entrega bboxes
normalizados de rostros y manos, atributos estabilizados y el resumen textual
actual. La interfaz dibuja esas cajas en un canvas del navegador y muestra el
texto que se añade a la petición de chat. Este endpoint no sube imágenes ni
crea una segunda fuente de estado de percepción.

Las respuestas de texto y voz fuerzan un refresco de percepción antes de
construir el contexto. Las expresiones de blendshapes usan una zona muerta y la
ausencia de rostro requiere observaciones consecutivas para evitar resets
espurios. El color de ropa se obtiene de una ROI de hombros limitada al espacio
entre rostros vecinos, con mediana y fallback de borde.

## Seguridad y pruebas

Una intención de LLM nunca puede evitar planificación, seguridad o RobotPort.
Faltan corpus, métricas de precisión, calibración de manos/expresiones en la
Pi 4B, privacidad y experimentos reproducibles.

## Próximos pasos

Validar Vosk con micrófono local y medir MediaPipe Tasks en la Pi 4B mediante
smokes opt-in. No añadir escucha permanente, wake word ni AEC sin requisitos y
pruebas separados.
