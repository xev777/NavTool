# TrafficBar 1.0.0

**NavTool is now TrafficBar.** / **NavTool ahora se llama TrafficBar.**

## What happened / Qué pasó
The name "NavTool" coincided with an unrelated company (NavTool, Inc., automotive video interfaces).
Same app, same GPL-3.0 license, same author, same features — only the name changes, and the version
restarts at 1.0.0 for the new identity. / El nombre "NavTool" coincidía con el de una empresa sin
relación (NavTool, Inc., interfaces de video para autos). Es la misma app, misma licencia GPL-3.0,
mismo autor, mismas funciones — solo cambia el nombre, y la versión reinicia en 1.0.0 para la nueva
identidad.

## What changed / Qué cambió
- New name everywhere: executable (`TrafficBar.exe`), installer, tray icon, window titles, Windows
  Firewall rules, autostart entry, and the GitHub repository (`xev777/TrafficBar` — the old
  `xev777/NavTool` URL redirects automatically). / Nuevo nombre en todas partes: ejecutable
  (`TrafficBar.exe`), instalador, icono de la bandeja, títulos de ventana, reglas del Cortafuegos,
  entrada de inicio automático, y el repositorio de GitHub (la URL anterior redirige sola).
- **New icon and splash screen**: three traffic bars instead of the old "N", and the 3-second startup
  animation's tagline no longer references "navegación" (a NavTool-era pun). / **Icono y pantalla de
  bienvenida nuevos**: tres barras de tráfico en vez de la antigua "N", y el lema de la animación de
  3 segundos ya no menciona "navegación" (un juego de palabras de la época de NavTool).
- **Traffic button LED**: a small green dot next to «📡 Tráfico» lights up only while the per-program
  background capture is actually running (Npcap, administrator) — the button no longer needs to change
  color to show this. / **Punto en el botón de Tráfico**: un punto verde junto a «📡 Tráfico» se
  enciende solo mientras la captura por programa en segundo plano está realmente activa — el botón ya
  no cambia de color para mostrarlo.

## If you had NavTool installed / Si tenías NavTool instalado
Uninstall it first (Settings → Apps → NavTool), then install TrafficBar — they are registered as
separate programs. Your settings and history move automatically the first time TrafficBar runs (from
`%LOCALAPPDATA%\NavTool` to `%LOCALAPPDATA%\TrafficBar`). / Desinstálalo primero (Configuración →
Aplicaciones → NavTool) y luego instala TrafficBar — quedan registrados como programas separados. Tu
configuración e historial se mudan solos la primera vez que abras TrafficBar.

## Notes / Notas
- The executables are still **not code-signed** while the SignPath Foundation application is pending; SmartScreen may
  warn. Check the SHA-256 below. / Los ejecutables **aún no están firmados** mientras la solicitud a SignPath está
  pendiente; SmartScreen puede avisar. Comprueba el SHA-256.
- Licensed under **GPL-3.0**. / Licencia **GPL-3.0**.

Full history: [CHANGELOG.md](CHANGELOG.md). / Historial completo: [CHANGELOG.md](CHANGELOG.md).
