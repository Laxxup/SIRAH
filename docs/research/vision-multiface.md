# Percepción Visual Multirostro

## Evidencia externa

La documentación oficial de OpenCV describe `CascadeClassifier.detectMultiScale`
como una operación que devuelve una lista de rectángulos detectados y su ejemplo
itera todos los rostros, no solo el primero:

- <https://docs.opencv.org/4.x/db/d28/tutorial_cascade_classifier.html>
- <https://docs.opencv.org/4.x/d1/de5/classcv_1_1CascadeClassifier.html>

El código fuente oficial de MediaPipe Face Detector separa `DetectionResult`
como una colección de detecciones y ofrece modos IMAGE, VIDEO y LIVE_STREAM:

- <https://github.com/google-ai-edge/mediapipe/blob/master/mediapipe/tasks/python/vision/face_detector.py>

Face Landmarker también define blendshapes como
`MOUTH_SMILE_LEFT` y `MOUTH_SMILE_RIGHT`, que son una base mejor para expresión
que una cascada Haar de sonrisa:

- <https://github.com/google-ai-edge/mediapipe/blob/master/mediapipe/tasks/python/vision/face_landmarker.py>

## Causa encontrada en SIRAH

`FaceDetector.detect()` podía devolver varios `FaceDetection`, pero
`FaceDetector.analyze()` hacía `faces[0]` y calculaba color y sonrisa únicamente
para ese rostro. El prompt recibía así una sola descripción aunque hubiera dos
personas. Además, la cascada de sonrisa se ejecutaba con parámetros muy
restrictivos y la ROI no estaba adaptada a rostros pequeños.

## Corrección actual

- `analyze()` procesa todos los rectángulos detectados.
- Los rostros se ordenan de izquierda a derecha para mantener identidad visual
  estable entre análisis.
- `VisualContext.face_contexts` conserva color, sonrisa, posición, distancia e
  iluminación por persona.
- El prompt informa número de personas, número de colores distinguibles y una
  línea por persona.
- La detección usa ecualización de histograma, `minNeighbors=5` y `minSize=40`
  para mejorar casos de dos rostros pequeños.
- La ROI de sonrisa usa el tercio inferior de cada rostro y parámetros
  proporcionales a su tamaño.

## Límite conocido

Haar no garantiza reconocer una sonrisa real bajo oclusión, ángulo, poca luz o
rostros pequeños. SIRAH no descarga modelos en runtime y el repositorio no
contiene un modelo Face Landmarker `.task`; por eso la sustitución por
MediaPipe Face Landmarker se mantiene como una integración opt-in porque
requiere modelos locales. No se debe afirmar que la expresión está resuelta
solo porque una cascada o un modelo devuelva un resultado.

## Evolución MediaPipe Tasks

La integración opt-in está implementada en `MediaPipeVision`. Face Landmarker
usa `mouthSmileLeft`/`mouthSmileRight` y Hand Landmarker aporta landmarks para
el conteo de dedos. Los modelos son locales y se descargan manualmente; ver
[`mediapipe-tasks-vision.md`](mediapipe-tasks-vision.md). Haar sigue siendo el
fallback para instalaciones sin modelos.
