# Validación HIL: pérdida de enlace, watchdog y pose segura

Procedimiento de validación física para el watchdog del firmware ocular
(protocol.md §10) y el comportamiento de ojos degradados del runtime. Requiere
aprobación del operador; no es un gate de CI (ver `docs/testing.md`).

## Alcance

- Watchdog del firmware: tras 3 s sin una línea de comando válida, el firmware
  suaviza la mirada hasta la pose segura CENTER y la mantiene mientras el
  enlace siga caído (§10.2/§10.3). El parpadeo continúa.
- Recuperación del firmware: la primera línea válida tras un timeout emite
  `READY 1` exactamente una vez y el enlace vuelve a la normalidad (§10.4).
- Degradación del runtime: el supervisor del enlace ocular reporta la pérdida
  una sola vez y deja de enviar TARGETs; la app marca ojos DEGRADED y sigue
  corriendo.

## Precondiciones

- ESP32 flasheado con el `platform/main.ino` actual.
- Servos conectados y alimentados desde el rail externo de 5 V (ver `build.md`).
- Host en `/dev/sirah-eyes` (o `/dev/ttyUSB*`), ojos armados vía
  `sirah-runtime --eyes`.

## Procedimiento

1. **Seguimiento de línea base.** Ejecuta el runtime con un rostro a la vista.
   Confirma que la mirada sigue y que las respuestas `STATE` convergen a la
   referencia comandada.
2. **Heartbeat vivo.** Confirma que el supervisor sigue enviando `HEARTBEAT`
   cada 1 s mientras el runtime esté arriba (el firmware sigue siguiendo; el
   watchdog nunca dispara).
3. **Pérdida de enlace.** Desconecta físicamente el cable USB/serie (o el
   ESP32).
   - Confirma que la mirada se suaviza hacia CENTER y se queda ahí mientras el
     cable esté fuera (timeout de watchdog ≤ 3 s).
   - Confirma que el parpadeo continúa durante la ventana de enlace caído.
   - Confirma que el host registra el componente de ojos como DEGRADED
     exactamente una vez y deja de enviar TARGETs (sin tormenta de reintentos).
4. **Recuperación.** Reconecta el cable.
   - Confirma que el firmware emite `READY 1` exactamente una vez.
   - Confirma que el seguimiento se reanuda tan pronto como el runtime envíe
     un `TARGET` nuevo (referencia re-centrada; sin reinicio de ningún lado).
5. **Recuperación con runtime ya degradado.** Con el runtime aún arriba tras
   el paso 3, verifica que el adaptador serie reconecta o que el operador
   reinicia el runtime y los ojos se rearman limpiamente.

## Aceptación

- La mirada nunca se aleja de CENTER mientras el enlace esté caído.
- Sin bucle de reintentos sin límite: a lo sumo una transición DEGRADED y un
  `READY 1` por episodio de pérdida de enlace.
- El parpadeo es independiente del enlace en ambas direcciones.

## Gemelo offline

`tests/integration/test_e2e_offline.py::test_link_loss_safe_pose_recenters_firmware_via_watchdog`
ejerce el mismo contrato contra FakeESP32: seguimiento → corte de enlace →
ojos DEGRADED → watchdog de FakeESP32 suaviza a CENTER. Ejecútala tras
cualquier cambio en el watchdog o en el supervisor del enlace ocular.