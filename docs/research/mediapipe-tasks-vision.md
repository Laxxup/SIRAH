# MediaPipe Tasks para vision

## Decision

SIRAH usa `MediaPipeVision` cuando encuentra los modelos locales
`face_landmarker.task` y `hand_landmarker.task`. Si el modelo facial falta o
MediaPipe no puede inicializarse, el detector cae a OpenCV Haar. El runtime no
descarga modelos.

La ruta se resuelve en este orden:

1. `SIRAH_MODELS_DIR`.
2. `models/` desde el directorio de trabajo.
3. `~/models/`.

Los modelos se descargan manualmente con
`scripts/download_mediapipe_models.sh` y no se incluyen en wheel/sdist.

## Face Landmarker

`FaceLandmarker` procesa hasta cuatro rostros y entrega landmarks y
blendshapes. SIRAH usa la media de `mouthSmileLeft` y `mouthSmileRight` para
obtener `smile_score`; un umbral inicial de `0.35` produce la señal de sonrisa.
La salida se ordena de izquierda a derecha, igual que la implementación Haar,
y el color de ropa sigue muestreándose debajo de cada bounding box.

Fuente oficial:

- <https://ai.google.dev/edge/mediapipe/solutions/vision/face_landmarker/python>
- <https://github.com/google-ai-edge/mediapipe/blob/master/mediapipe/tasks/python/vision/face_landmarker.py>

## Hand Landmarker

`HandLandmarker` procesa hasta dos manos y entrega 21 landmarks por mano.
SIRAH compara la punta de cada dedo con su articulación PIP y usa la distancia
de la punta del pulgar a la muñeca para estimar dedos extendidos. La salida
incluye lateralidad, dedos individuales y total por mano.

La estimación es válida para manos suficientemente visibles y orientadas hacia
la cámara. Oclusión, giro extremo o dedos fuera del encuadre producen una
respuesta conservadora, no una afirmación inventada por el LLM.

Fuente oficial:

- <https://ai.google.dev/edge/mediapipe/solutions/vision/hand_landmarker/python>
- <https://github.com/google-ai-edge/mediapipe/blob/master/mediapipe/tasks/python/vision/hand_landmarker.py>

## Pi 4B

La laptop de desarrollo tiene margen amplio, pero el despliegue de referencia
es una Raspberry Pi 4B. Por eso la inferencia corre dentro de un executor,
los imports son lazy, la cadencia de VisionLoop es configurable y Haar sigue
siendo fallback. Antes de promoverlo al robot hay que medir latencia y memoria
en la Pi con la cámara final.

La suite no descarga modelos, abre cámaras ni inicializa MediaPipe real: usa
fakes deterministas para probar geometría, blendshapes, histéresis y contratos.
