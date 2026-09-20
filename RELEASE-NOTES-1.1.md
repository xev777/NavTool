# NavTool 1.1

A floating bar for Windows that shows and controls what happens with your Internet connection.
Una barra flotante para Windows que muestra y controla lo que pasa con tu conexión a Internet.

## New / Novedades
- **Monthly data quota** with warnings at 80 % / 100 %. / **Cuota mensual** con avisos al 80 % y 100 %.
- **Block a program** with Windows Firewall rules (temporary or permanent). / **Bloquear un programa** con el Cortafuegos de Windows.
- **Language packs**: English (default) and Spanish included; load more from the app. / **Packs de idioma**: inglés (por defecto) y español; carga más desde la app.
- Installer in English with Spanish option. / Instalador en inglés con opción de español.
- Bar in 3 states, smaller windows, help, About, 3-second intro. / Barra en 3 estados, ventanas más pequeñas, ayuda, «Acerca de» e introducción de 3 s.
- Traffic monitor now captures **every** packet (exact totals) and shows the real program behind the proxy. / El monitor de tráfico captura **todos** los paquetes (totales exactos) y muestra el programa real tras el proxy.
- **No third-party libraries** for capture/parsing/tray (only `psutil`): 11 MB installer. / Sin librerías de terceros para captura, lectura de paquetes y bandeja (solo `psutil`): instalador de 11 MB.
- Fixes: blank Traffic window after restarting as administrator; installer text encoding. / Correcciones: ventana de Tráfico en blanco tras reiniciar como administrador; codificación del instalador.

## Files / Archivos
| File | SHA-256 |
|---|---|
| `NavTool-Setup-1.1.exe` | (see below / ver abajo) |
| `NavTool-Portable-1.1.zip` | (see below / ver abajo) |

## Notes / Notas
- Requires Windows 10/11. The traffic monitor needs [Npcap](https://npcap.com) and administrator rights. / El monitor de tráfico necesita Npcap y permisos de administrador.
- The executables are **not code-signed**: SmartScreen may show a warning ("More info" → "Run anyway"). Verify the SHA-256 above. / Los ejecutables **no están firmados**: SmartScreen puede avisar; verifica el SHA-256.
- Licensed under **GPL-3.0**. Source: this repository. / Licencia **GPL-3.0**. Código fuente: este repositorio.
- Firewall blocking has been tested with a simulated firewall; please report any issue. / El bloqueo con Cortafuegos se probó con un cortafuegos simulado; avisa si algo falla.
