# NavTool 1.1.5

**New: telemetry detector.** / **Novedad: detector de telemetría.**

## New / Novedades
- **Telemetry detector**: NavTool now flags when a program on your PC contacts a known
  telemetry/diagnostics server (crash reports, usage statistics it sends to its maker — Microsoft,
  Apple, and common SDKs like Sentry, Mixpanel, Crashlytics...). It only detects and logs it in a new
  **📊 Telemetría detectada** window (tray menu), with its own history — it never blocks the
  connection or the program. Needs per-program monitoring (Npcap), the same one the traffic monitor
  already uses. This does not change what NavTool itself sends: still nothing, ever.
  / **Detector de telemetría**: NavTool avisa cuando un programa de tu PC contacta con un servidor de
  telemetría/diagnóstico conocido (informes de fallos, estadísticas de uso que envía a su fabricante:
  Microsoft, Apple y SDKs comunes como Sentry, Mixpanel, Crashlytics...). Solo lo detecta y lo
  registra en una nueva ventana **📊 Telemetría detectada** (menú de la bandeja), con su propio
  historial — nunca bloquea la conexión ni el programa. Necesita el monitoreo por programa (Npcap),
  el mismo que ya usa el monitor de tráfico. Esto no cambia lo que NavTool mismo envía: sigue sin
  enviar nada, nunca.

## Notes / Notas
- The executables are still **not code-signed** while the SignPath Foundation application is pending; SmartScreen may
  warn. Check the SHA-256 below. / Los ejecutables **aún no están firmados** mientras la solicitud a SignPath está
  pendiente; SmartScreen puede avisar. Comprueba el SHA-256.
- Licensed under **GPL-3.0**. / Licencia **GPL-3.0**.

Full history: [CHANGELOG.md](CHANGELOG.md). / Historial completo: [CHANGELOG.md](CHANGELOG.md).
