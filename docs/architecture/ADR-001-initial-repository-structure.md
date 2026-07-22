# ADR-001: Initial SIRAH repository structure

- Estado: Provisional
- Fecha: 2026-07-22

## Contexto

El repositorio anterior contiene Cortex y una sola integración externa real:
una previsualización Velxio de saludo con un servo. No se encontró código local
activo de conversación, cámara, PCA9685 ni controlador facial completo. Aún no
se ha decidido proceso, lenguaje, paquete, GUI ni mecanismo de integración.

## Decisión

Crear una semilla mínima con documentación y experimentos reales. No crear
raíces vacías ni `src/sirah/`. El experimento Velxio se copia para preservar el
origen mientras Cortex conserva su historia; una migración posterior podrá
retirarlo de Cortex mediante un commit explícito.

La dirección de dependencia es SIRAH → Cortex. La integración técnica queda
pendiente.

## Trazabilidad del experimento Velxio

- commit de origen en Cortex:
  `ea10d96f3a58cb6b6ccde4ab01bc7ac7ac32c52f`;
- commit de copia en SIRAH:
  `8462538c0293a03375b9479a99f51e2d240b2495`.

Los seis artefactos de sesión, sketch, ZIP y exportación Velxio coinciden
exactamente por SHA-256 entre ambos repositorios. El `README.md` de Cortex era
vacío; el de SIRAH se enriqueció deliberadamente con propósito, estado,
validación, seguridad, procedencia y decisión, y es la versión documental
autoritativa. Esta diferencia no altera el artefacto experimental preservado.

## Alternativas

### A. Árbol completo desde ahora

`subsystems/`, `adapters/`, `firmware/`, `experiments/` y `tests/` facilitarían
una vista futura, pero hoy crearían responsabilidades vacías, sugerirían
estabilidad inexistente y obligarían a elegir una forma de aplicación.

### B. Semilla mínima de documentación, firmware y experimentos

Es cercana a la decisión, pero `firmware/` tampoco está justificado: el único
sketch comprobado es una demostración simulada, no firmware estable ni validado
en hardware.

### C. Documentación + experimento comprobado (elegida)

Representa exactamente el trabajo actual, permite varios lenguajes y conserva
un camino barato de promoción sin duplicar Cortex.

## Consecuencias

La navegación es honesta y pequeña. Habrá una reorganización al promover el
primer componente, pero será guiada por contratos y evidencia reales. Los
detalles eléctricos quedan fuera de Cortex.

## Condiciones de revisión

Revisar cuando exista al menos uno de estos hechos:

- lógica estable de una capacidad independiente de dispositivos;
- un cliente concreto Serial, MQTT, HTTP, Vosk, Piper o Gemini;
- firmware cargado y validado en un microcontrolador;
- pruebas compartidas que necesiten una raíz estable;
- decisión adoptada sobre empaquetado, procesos o integración con Cortex.
