# Changelog / Registro de cambios

## 1.1.5 — 2026-09-23

**New / Novedades**
- **Telemetry detector**: NavTool now flags when a program on your PC contacts a known
  telemetry/diagnostics server (crash reports, usage statistics sent to its maker). It only detects
  and logs it in a new **📊 Telemetría detectada** window (tray menu) with its own history — it never
  blocks the connection or the program. Needs per-program monitoring (Npcap) already used by the
  traffic monitor. This does not change what NavTool itself sends: still nothing, ever.
  / **Detector de telemetría**: NavTool avisa cuando un programa de tu PC contacta con un servidor de
  telemetría/diagnóstico conocido (informes de fallos, estadísticas de uso que envía a su fabricante).
  Solo lo detecta y lo registra en una nueva ventana **📊 Telemetría detectada** (menú de la bandeja)
  con su propio historial — nunca bloquea la conexión ni el programa. Necesita el monitoreo por
  programa (Npcap) que ya usa el monitor de tráfico. Esto no cambia lo que NavTool mismo envía: sigue
  sin enviar nada, nunca.

## 1.1.4 — 2026-09-23

**Fixes / Correcciones**
- **The bar could open off-screen and get stuck there** if its last position was on a monitor that is no longer
  connected (e.g. after undocking a laptop or unplugging an external display) — it looked as if NavTool had
  frozen or wasn't opening. The tray menu now has **"Reset bar position"**, which brings it back to the main
  monitor, and showing the bar (from the tray icon or from another launch) now re-checks that its position is
  still on a connected monitor. / **La barra podía abrirse fuera de la pantalla y quedarse así** si su última
  posición estaba en un monitor ya desconectado (por ejemplo, al quitar una pantalla externa) — parecía que
  NavTool se había colgado o no abría. El menú de la bandeja ahora tiene **"Restaurar posición de la barra"**,
  que la trae de vuelta al monitor principal, y mostrar la barra (desde la bandeja o al abrir NavTool de nuevo)
  ahora comprueba que su posición sigue estando en un monitor conectado.

## 1.1.3 — 2026-09-21

**Preparing code signing / Preparando la firma de código**
- Builds now run on GitHub Actions (`.github/workflows/build.yml`), a requirement of the SignPath Foundation free signing program.
  / Las compilaciones se hacen en GitHub Actions (requisito de la firma gratuita de SignPath Foundation).
- The executable and installer carry version metadata (product, version, author, license). / El ejecutable y el instalador llevan metadatos de versión.
- New `CODE_SIGNING_POLICY.md` and `PRIVACY.md`. / Nuevas políticas de firma y de privacidad.
- `compilar.ps1` never closes the NavTool you have installed or running (only the one from its own build folder).
  / `compilar.ps1` ya no cierra el NavTool que tengas instalado o en uso.

**New / Novedades**
- Optional donation link (PayPal) in the About screen and the README — off unless configured, never shown as a
  pop-up. / Enlace de donación opcional (PayPal) en «Acerca de» y el README — apagado salvo que se configure, nunca en una ventana emergente.

## 1.1.2 — 2026-09-21

**Fixes / Correcciones**
- **Microsoft Defender flagged NavTool 1.1.1 as malware** (`Behavior:Win32/Impact.A!ml`) and quarantined `NavTool.exe` right after
  installing. Cause: the Store-apps wizard relaunched NavTool **elevated with a hidden window**, a pattern antivirus engines
  associate with malware. It now uses a normal (visible) elevation prompt. Bisected by building 1.1 (clean), 1.1.1 (flagged) and
  1.1.1 with only that change (clean).
  / **Defender marcó la 1.1.1 como malware** y puso `NavTool.exe` en cuarentena tras instalar. Causa: el asistente de la Tienda
  relanzaba NavTool con permisos elevados y **ventana oculta**. Ahora usa el aviso de administrador normal.
- **The build now scans the executable with Defender and refuses to continue if it is flagged**, and a test forbids hidden
  elevations. / **La compilación analiza el ejecutable con Defender y se detiene si lo marca**; una prueba prohíbe elevaciones ocultas.
- **If you installed 1.1.1:** uninstall it (Start menu → NavTool → Uninstall, or Settings → Apps), reboot the shortcut leftovers,
  and install 1.1.2. / **Si instalaste la 1.1.1:** desinstálala e instala la 1.1.2.

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
