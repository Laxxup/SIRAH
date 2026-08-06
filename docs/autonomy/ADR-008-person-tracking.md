# ADR-008: Person Tracking via Face Embeddings

**Estado:** Accepted
**Fecha:** 2026-08-05
**Autores:** SIRAH v2 development

## Contexto

SIRAH necesita reconocer personas específicas para personalizar la interacción:
- "Hola Juan, ¿cómo estás?" vs "Hola, ¿quién eres?"
- Recordar visitas anteriores
- Adaptar temas según preferencias

Opciones evaluadas:
1. Solo contar caras (ya implementado en `FaceDetection`)
2. Embeddings faciales con MediaPipe FaceMesh
3. Reconocimiento con modelos pre-entrenados (FaceNet, ArcFace)
4. Servicio cloud (AWS Rekognition, Azure Face)

## Decisión

Usar **MediaPipe FaceMesh** para generar embeddings faciales locales (128 dimensiones).
Comparar con余弦相似度 (cosine similarity) contra una base de datos local en memoria
(persistencia futura en SQLite).

### Razones

- **Offline:** No depende de servicios cloud ni API keys
- **Rápido:** MediaPipe FaceMesh corre en CPU, ~30ms por frame en Pi 4B
- **Ligero:** Embeddings de 128 floats = 512 bytes por persona
- **Ya tenemos MediaPipe:** instalado como dependencia opcional
- **Benchmark:** InMoov ROS2 usa enfoque similar con OpenCV + embeddings

### Implementación

```python
@dataclass
class PersonProfile:
    face_embedding: tuple[float, ...]  # 128 floats
    name: str
    first_seen: float
    last_seen: float
    visit_count: int
    relationship: str

class PersonTracker:
    def identify(self, face_embedding: tuple[float, ...]) -> PersonProfile | None
    def register(self, embedding: tuple[float, ...], name: str) -> PersonProfile
    def list_known(self) -> tuple[PersonProfile, ...]
    def forget(self, name: str) -> None
```

### Consecuencias

- **Positivo:** Interacción personalizada por persona
- **Positivo:** Sin dependencias cloud
- **Negativo:** Embeddings son volátiles (no persisten entre reinicios — futuro SQLite)
- **Negativo:** MediaPipe FaceMesh es ~2× más pesado que FaceDetection básico

## Referencias

- InMoov ROS2 face recognition: `docs/research/inmoov-ros2-analysis.md`
- MediaPipe FaceMesh: https://developers.google.com/mediapipe/solutions/vision/face_landmarker
