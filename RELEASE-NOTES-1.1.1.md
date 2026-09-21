# NavTool 1.1.1

**WhatsApp and the Microsoft Store now work with the proxy on.** / **WhatsApp y la Microsoft Store ya funcionan con el proxy encendido.**

## What was wrong / Qué pasaba
Windows does not let Microsoft Store (UWP) apps connect to `127.0.0.1`, where NavTool's proxy listens, so with ⏻ on those
apps looked "blocked". / Windows no deja que las apps de la Tienda (UWP) se conecten a `127.0.0.1`, donde escucha el proxy de
NavTool, y por eso con el ⏻ encendido parecían «bloqueadas».

## New / Novedades
- **🛍 Microsoft Store apps compatibility**: right-click the bar (or the tray icon) → check the apps you use (WhatsApp and the Store
  are pre-selected with one click) → Apply. It needs administrator rights and can be undone from the same window.
  / **🛍 Compatibilidad con apps de la Tienda**: clic derecho en la barra (o en el icono de la bandeja) → marca tus apps
  (WhatsApp y la Tienda con un clic) → Aplicar. Pide permisos de administrador y se deshace desde la misma ventana.
- A one-time notification explains it the first time you turn the proxy on. / Un aviso único lo explica al encender el proxy por primera vez.
- The uninstaller removes the exemptions NavTool created. / El desinstalador quita las excepciones que creó NavTool.

## Safety / Seguridad
Only installed apps are touched; only exemptions created by NavTool are ever removed; no shell is used and package names are
strictly validated. / Solo se tocan apps instaladas, solo se quitan excepciones creadas por NavTool, sin shell y con nombres validados.

## Fixes / Correcciones
- The build script no longer leaves the Windows proxy pointing to a dead port (it made download managers such as IDM fail).
  / El script de compilación ya no deja el proxy apuntando a un puerto muerto (hacía fallar a gestores como IDM).

Full history: [CHANGELOG.md](CHANGELOG.md). / Historial completo: [CHANGELOG.md](CHANGELOG.md).

## Install / Instalación
- `NavTool-Setup-1.1.1.exe` — installer (English by default, Spanish available). / instalador (inglés por defecto, con opción de español).
- `NavTool-Portable-1.1.1.zip` — portable.
- Upgrade over 1.1 keeps your settings. / Actualizar sobre la 1.1 conserva tu configuración.
- The executables are **not code-signed**; SmartScreen may warn ("More info" → "Run anyway"). Check the SHA-256 below.
  / Los ejecutables **no están firmados**; SmartScreen puede avisar. Comprueba el SHA-256.
- Licensed under **GPL-3.0**. / Licencia **GPL-3.0**.
