# Changelog / Registro de cambios

## 1.1.1 — 2026-09-21

**New / Novedades**
- **Microsoft Store apps compatibility wizard** (right-click the bar, or the tray menu). Windows forbids Store (UWP) apps
  such as WhatsApp or the Microsoft Store from reaching `127.0.0.1`, so they could not connect while the NavTool proxy was on.
  The wizard lists the installed apps and adds/removes the official *loopback exemption* for the ones you choose.
  It asks for administrator rights, only touches installed apps, only removes exemptions NavTool created, and the
  uninstaller removes them. A one-time notification explains this when you first turn the proxy on.
  / **Asistente de compatibilidad con apps de la Tienda**: WhatsApp, la Microsoft Store y otras apps UWP no podían conectarse
  con el proxy encendido (restricción de Windows). El asistente añade o quita la exención oficial de loopback para las apps
  que elijas, con permisos de administrador, solo sobre apps instaladas y solo quitando lo que NavTool creó.
- Help updated (Tips section). / Ayuda actualizada (sección Consejos).
- 17 new tests (94 in `pruebas_funciones.py`). / 17 pruebas nuevas.

**Fixes / Correcciones**
- Building NavTool no longer leaves the Windows proxy pointing to a dead port (the build script now restores the proxy
  before closing NavTool). That leftover proxy made download managers such as IDM fail with «cannot connect to proxy».
  / El script de compilación ya no deja el proxy de Windows apuntando a un puerto muerto (hacía fallar a gestores como IDM).

## 1.1 — 2026-09-20

**New / Novedades**
- Monthly data quota with warnings at 80 % and 100 %. / Cuota mensual de datos con avisos al 80 % y al 100 %.
- Block a program's Internet access with Windows Firewall rules (1 h, 4 h or until unblocked). / Bloqueo de programas con reglas del Cortafuegos.
- Language packs: English (default) and Spanish included, load more from the app. / Packs de idioma.
- Installer in English with a Spanish option. / Instalador en inglés con opción de español.
- Three bar states, smaller text and windows (configurable), help, About, 3-second intro. / Barra en 3 estados, ventanas más pequeñas, ayuda, «Acerca de», introducción.
- Credits, GPL-3.0 license. / Créditos y licencia GPL-3.0.

**Fixes / Correcciones**
- The traffic monitor lost most packets on fast downloads (a 6 GB ISO showed 6 %). It now reads Npcap directly and the totals
  match the network card exactly. / El monitor perdía la mayoría de paquetes en descargas rápidas.
- The Traffic window stayed blank until clicked (it simulated the Alt key, which Windows treats as «enter the window menu»).
  / La ventana de Tráfico quedaba en blanco hasta hacer clic (simulaba la tecla Alt).
- With the proxy on, browser traffic appeared as `NavTool.exe`; it now shows the real browser. / Con el proxy encendido, todo aparecía como NavTool.exe.
- Installer messages with accents were garbled (missing UTF-8 BOM). / Mensajes del instalador con tildes rotos.
- Hardened language-pack loading against hostile files (nesting limit, no regex). / Carga de packs de idioma reforzada.

**Under the hood / Por dentro**
- Removed Scapy, pystray and Pillow: own Npcap reader (`pcap.py`), packet parser (`netparse.py`) and tray icon (`tray.py`).
  Only `psutil` remains. Installer went from 28.9 MB to 11 MB, and no GPL-incompatible code ships in the executable.
  / Sin Scapy, pystray ni Pillow; instalador de 11 MB.
- `NavTool.exe --diagnostico` checks Npcap, capture and the tray icon. / Modo de diagnóstico.
