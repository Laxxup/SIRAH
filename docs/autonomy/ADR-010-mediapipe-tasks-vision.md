# ADR-010: MediaPipe Tasks para expresiones y manos

**Estado:** Accepted
**Fecha:** 2026-08-05

## Contexto

La cascada Haar de sonrisa produce falsos positivos y SIRAH no podía responder
con evidencia al preguntar por dedos. El hardware de referencia es una Pi 4B,
por lo que los modelos deben ser locales, opcionales y no bloquear asyncio.

## Decisión

Usar `FaceLandmarker` para landmarks/blendshapes y `HandLandmarker` para manos,
encapsulados en `MediaPipeVision`. Los modelos se obtienen manualmente y se
resuelven mediante `SIRAH_MODELS_DIR`, `models/` o `~/models/`. Si faltan, el
rostro usa Haar y las manos quedan desactivadas.

La salida sigue siendo texto/contexto estructurado local. MediaPipe no crea
comandos, no llama al hardware y no envía imágenes al proveedor de inteligencia.

## Consecuencias

- La sonrisa usa scores de blendshape y la integración conserva histéresis.
- El conteo de dedos depende de manos visibles y puede ser indeterminado bajo
  oclusión.
- La sonrisa MediaPipe usa una zona muerta entre estados para evitar que el
  ruido del score impida actualizar la expresión; la cadencia de rostros es
  configurable por perfil.
- El color de ropa se toma de una ROI local de hombros, limitada para no mezclar
  personas vecinas; el Web Lab permite inspeccionarla sin enviar imágenes.
- Los modelos no forman parte del wheel/sdist y el despliegue debe instalarlos
  como paso explícito.
- La Pi 4B necesita un smoke de latencia/memoria antes de fijar la cadencia.
