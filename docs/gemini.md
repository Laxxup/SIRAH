# Gemini por texto

Gemini es un adaptador opcional de inteligencia conversacional. No ejecuta
funciones físicas: devuelve JSON estructurado y SIRAH vuelve a validar su
coherencia, capacidad y parámetros antes de traducir hacia SIRAH Cortex.

## Instalación y configuración

```bash
python -m pip install ".[gemini]"
export GEMINI_API_KEY="valor-configurado-fuera-del-repositorio"
```

También se admite `GOOGLE_API_KEY`; `GEMINI_API_KEY` tiene precedencia cuando
ambas existen. `SIRAH_GEMINI_MODEL` sustituye el modelo predeterminado
`gemini-3.6-flash`. Este identificador es estable según la documentación de
Google consultada para esta pre-alpha, pero su disponibilidad y cuotas dependen
del proyecto. Ninguna clave debe guardarse en archivos o logs.

## Smoke test vivo opt-in

La prueba normal nunca usa la red. El smoke vivo requiere autorización
explícita:

```bash
SIRAH_RUN_LIVE_GEMINI=1 \
GEMINI_API_KEY="valor-configurado-fuera-del-repositorio" \
python examples/gemini_smoke.py
```

Usa texto no sensible, únicamente `robot.home` y `robot.stop`, y un
`RobotPort` simulado. Muestra la decisión, la capacidad y si fue autorizada,
sin imprimir la clave. La ausencia de configuración, cuota o red se informa
sin convertirla en un fallo de pytest.

## Límites

El contexto se mantiene solo durante la vida del proceso. No hay voz, visión,
hardware real ni memoria persistente. Un error de proveedor, timeout, cuota,
JSON o esquema produce cero movimiento. Las protecciones de contenido
predeterminadas de Gemini no se reducen y no sustituyen la seguridad mecánica.
