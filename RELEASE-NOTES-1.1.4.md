# NavTool 1.1.4

**Fixes the bar getting stuck off-screen after disconnecting a monitor.** / **Corrige que la barra quedara fuera de la pantalla al desconectar un monitor.**

## What happened / Qué pasó
NavTool remembers the bar's last position so it reopens where you left it. If that position was on a monitor that
is no longer connected (unplugging an external display, undocking a laptop), the bar opened at coordinates that no
longer exist on any screen — it looked as if NavTool had frozen or wasn't opening, and since the bar has no window
border, there was no way to drag it back. / NavTool recuerda la última posición de la barra para reabrirla en el
mismo sitio. Si esa posición estaba en un monitor ya desconectado (quitar una pantalla externa, desacoplar un
portátil), la barra se abría en coordenadas que ya no existen en ninguna pantalla — parecía que NavTool se había
colgado o no abría, y al no tener borde de ventana no había forma de arrastrarla de vuelta.

## What changed / Qué cambió
- New **"Reset bar position"** item in the tray menu, always available even if the bar itself is invisible — brings
  it back centered on the main monitor. / Nueva opción **"Restaurar posición de la barra"** en el menú de la
  bandeja, disponible aunque la barra esté invisible — la trae de vuelta centrada en el monitor principal.
- Showing the bar (opening NavTool again, or from the tray icon) now checks that its saved position is still on a
  connected monitor and corrects it automatically if not. / Mostrar la barra (al abrir NavTool de nuevo o desde la
  bandeja) ahora comprueba que su posición guardada sigue en un monitor conectado y la corrige sola si no.
- Everything from 1.1.3 is kept (optional PayPal donation link, code-signing preparation). / Se mantiene todo lo de
  la 1.1.3 (donación opcional por PayPal, preparación de la firma de código).

## If the bar is stuck on 1.1.3 or earlier / Si la barra se quedó atascada en la 1.1.3 o anterior
Exit NavTool from the tray icon, open `%LOCALAPPDATA%\NavTool\config.json` in Notepad, set `"bar_x"` and `"bar_y"`
to `null` (and `"bar_dock"` too, if present), save, and reopen NavTool — or just install 1.1.4, which fixes this
for good. / Sal de NavTool desde la bandeja, abre `%LOCALAPPDATA%\NavTool\config.json` con el Bloc de notas, pon
`"bar_x"` y `"bar_y"` en `null` (y `"bar_dock"` si aparece), guarda y vuelve a abrir NavTool — o instala
directamente la 1.1.4, que lo arregla de forma definitiva.

## Notes / Notas
- The executables are still **not code-signed** while the SignPath Foundation application is pending; SmartScreen may
  warn. Check the SHA-256 below. / Los ejecutables **aún no están firmados** mientras la solicitud a SignPath está
  pendiente; SmartScreen puede avisar. Comprueba el SHA-256.
- Licensed under **GPL-3.0**. / Licencia **GPL-3.0**.

Full history: [CHANGELOG.md](CHANGELOG.md). / Historial completo: [CHANGELOG.md](CHANGELOG.md).
