# Calibración

`firmware/sirah-eyes/config/calibration.h` es la autoridad física.
`config/actuators.yaml` la espeja para el runtime.

1. Desarma los ojos y coloca el mecanismo donde no pueda atascarse.
2. Cambia un límite físico en `calibration.h`.
3. Ejecuta las pruebas host del firmware.
4. Espeja el valor en `actuators.yaml`.
5. Ejecuta `sirah-calibrate validate` y la suite de pruebas de Python.
6. Registra la fecha, la revisión de hardware y los límites observados en
   `pin-map.md`.

No introduzcas jamás un comando serie de calibración. Los límites siguen siendo
propiedad del firmware.