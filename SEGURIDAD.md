# TrafficBar – Informe de seguridad

Auditoría del código y de las dependencias, con **pruebas de ataque reales** (no solo lectura de código).
Cada fallo se reprodujo antes de corregirlo y se vuelve a comprobar con `pruebas_seguridad.py`.

## Resumen

| | |
|---|---|
| Ataques reproducidos antes de corregir | **9 de 11** (los otros 2 no eran explotables tal cual) |
| Hallazgos corregidos | **17** (3 altos, 5 medios, 9 bajos) + 2 informativos |
| Suite de seguridad tras las correcciones | **52 de 52** superadas (39 de ataque y robustez + 13 de regresión: que lo normal sigue funcionando) |
| Dependencias con vulnerabilidades conocidas (`pip-audit`) | 0 (antes: 12 avisos en Pillow + 1 en setuptools) |
| Análisis estático (`bandit`, severidad media/alta) | 0 hallazgos |

## Hallazgos y correcciones

### Altos
| ID | Fallo | Cómo se comprobó | Corrección |
|---|---|---|---|
| S1 | **Secuestro del puerto del proxy.** El servidor usaba `SO_REUSEADDR`, que en Windows deja que *otro programa* se enlace al mismo puerto y reciba las conexiones del navegador. | Un segundo socket se enlazó al puerto con éxito. | `SO_EXCLUSIVEADDRUSE`, sin reutilización de dirección, y **puerto aleatorio alto** en cada arranque (`proxy_core.py`). |
| S2 | **Una página hostil congelaba el filtro** (expresión regular con coste cuadrático). Una página de 1 MB: ~14 minutos de CPU. | 46 KB tardaron 1,7 s (extrapolado); una prueba mayor colgó el proceso más de 100 s. | Filtro de coste lineal, expresiones acotadas y tope de 1 MB. Peor caso medido con páginas hostiles de 1 MB: 0,35 s. |
| S3 | **Elevación desde una carpeta modificable.** En modo administrador (Npcap), si TrafficBar vive en una carpeta escribible por tu usuario —o se extrae a `%TEMP%`, como hace un `.exe` único de PyInstaller— cualquier programa tuyo podría alterarlo y ejecutar con permisos elevados. | Revisión de diseño. | Compilación en modo **carpeta** (`--onedir`, sin extraer a temporales), script `Instalar-TrafficBar.ps1` que instala en *Archivos de programa* y verifica permisos, y un aviso antes de elevar si estás fuera de esa ubicación. |

### Medios
| ID | Fallo | Corrección |
|---|---|---|
| S4 | Una descarga HTTP se guardaba **entera en RAM** (+120 MB en la prueba). | Reenvío por trozos (+2 MB). Tope de 64 MB en cuerpos de petición. |
| S5 | *Mapa* y *Sitio* abrían `file://` y leían archivos locales. | Solo `http://` y `https://` (`safety.http_url`). Lecturas y expresiones acotadas. |
| S6 | *Limpiar* borraba la carpeta que dijera la variable `TEMP` y atravesaba uniones (*junctions*) hacia otras carpetas. | Rutas base obtenidas de Windows (no del entorno), comprobación de que siguen dentro, y no se sigue ningún enlace ni unión. |
| S7 | Una respuesta DNS falsa (nunca preguntada) cambiaba el nombre con el que ves un destino. | Solo se aceptan respuestas a una consulta propia, con el mismo id **y del mismo servidor**. |
| S8 | Pillow 12.2.0 con 12 avisos de seguridad; setuptools (solo compilación) con 1. | Pillow 12.3.0, setuptools 83. Versiones fijadas en `requirements.txt`. |

### Bajos
| ID | Fallo | Corrección |
|---|---|---|
| S9 | *Ping* aceptaba opciones como host (`-t` = ping infinito). Se invocaba `ping` sin ruta. | Validación estricta del host; rutas absolutas de `System32` (también para PowerShell). |
| S10 | `Content-Length` inválido mataba el hilo; cuerpos `chunked` podían desincronizar la conexión. | Respuestas controladas 400 / 413 / 501. |
| S11 | Un `config.json` con un tipo equivocado impedía abrir la app. | Saneamiento de todos los valores y límites. |
| S12 | Memoria sin tope (conexiones, cachés DNS, colas) y posibles avalanchas de alertas. | Topes en todo; máximo de 12 alertas cada 10 minutos; `errores.log` limitado a 512 KB. |
| S13 | Nombres con caracteres de control o de dirección de texto (RTL) podían disfrazar un programa (`factura‮gpj.exe`). | `clean_text` en nombres de programas, sitios y respuestas. |
| S14 | El historial (sitios visitados) se guardaba en la carpeta *Roaming*, que se sincroniza en perfiles móviles. | Ahora en `%LOCALAPPDATA%\TrafficBar`, con migración, botón **Borrar todo el historial** y retención de 30 días. |
| S15 | Tras un cierre brusco, el proxy de Windows quedaba apuntando a un puerto predecible que otro programa podía ocupar. | Puerto aleatorio, registro del puerto, restauración al salir (`atexit`) y limpieza al abrir. |
| S16 | Se hacían consultas DNS inverso/RDAP de IPs que nos contactan sin que lo pidiéramos (fuga de información y consumo de memoria). | Solo destinos iniciados por este equipo; la IP se valida antes de armar cualquier URL. |
| S17 | El filtro podía dañar páginas sin *charset* y se inyectaba antes del `<!doctype>` (modo «quirks»). | Recodificación sin pérdidas (latin-1), inyección tras `<head>`, y no se toca contenido comprimido. |

### Informativos
| ID | Nota |
|---|---|
| S18 | Peticiones de página web tipo `GET //host/…` (SSRF/CSRF hacia tu red local): **no explotable** con Python ≥ 3.12, que normaliza esa ruta. Se endurece igualmente exigiendo URL absoluta. |
| S19 | Plantado de `ping.exe` en la carpeta actual: **no reproducible** en este Windows. Se usan rutas absolutas por si acaso. |

## Riesgos que NO se eliminan (decisiones de diseño)

1. **Otro usuario de la misma máquina** (varias sesiones abiertas) puede conectarse al proxy: `127.0.0.1` es compartido entre sesiones y el proxy no tiene contraseña. Está mitigado (puerto aleatorio, enlace exclusivo) pero no autenticado.
2. **Un programa malicioso con tus mismos permisos** puede leer `history.db` y la configuración, cambiar el proxy de Windows o cerrar TrafficBar. TrafficBar no es una defensa contra malware que ya corre como tú. El historial contiene los sitios que visitas: bórralo si no lo quieres.
3. **El contenido HTTPS no se descifra** (a propósito: sin certificado raíz propio). Los filtros de contenido solo actúan en HTTP; en HTTPS se bloquea por dominio. Los nombres que ves (SNI, cabecera HTTP, DNS inverso) los **declara el propio programa o el dueño de la IP** y no están verificados; la IP sí es real. La pantalla lo indica.
4. **Los binarios no están firmados.** Windows SmartScreen puede avisar. `Instalar-TrafficBar.ps1` muestra el SHA-256 al instalar para que puedas comprobarlo después.
5. **Npcap** es un controlador de terceros con privilegios de sistema. Instálalo desde npcap.com, mantenlo al día y usa el modo administrador solo cuando lo necesites.
6. **No hay actualización automática** (evita una vía de ataque, pero los parches los aplicas tú: vuelve a ejecutar `pip-audit` de vez en cuando).
7. **Iniciar con Windows** (opcional, desde el menú de la barra o de la bandeja) escribe una sola entrada en `HKCU\...\Run`: solo tu usuario, sin permisos de administrador y reversible con la misma casilla. Solo está disponible en la versión compilada.
8. **Listas de bloqueo descargables** (Filtros → «Actualizar listas»): TrafficBar se conecta a los sitios de las listas que marques. Una lista externa decide qué se bloquea, así que la descarga está acotada: solo HTTPS con verificación de certificado y sin redirecciones a HTTP, máximo 8 MB y 300.000 dominios, cada línea validada como nombre de dominio (nada de IPs ni comandos), respuestas casi vacías rechazadas, y unos dominios esenciales (GitHub, Microsoft, las propias listas…) y **tus excepciones nunca se bloquean**. Es opcional: la actualización automática está desactivada por defecto. Riesgo residual: si el sitio de una lista fuera comprometido, podría hacerte bloquear sitios legítimos (no ejecutar código); las excepciones lo arreglan en un clic.
9. **«Solo medir»** no bloquea nada y solo guarda contadores en memoria (bytes y número de conexiones); no registra qué sitios visitas más allá de lo que ya guarda el historial.
10. La consulta opcional de *dueño de IP* (RDAP) envía las IPs a `rdap.org`. Está **desactivada** por defecto y avisa antes de activarse.


## Versión 1.1: superficies nuevas y hallazgos

Nuevas funciones y cómo se protegieron (comprobado con `pruebas_funciones.py`, 94 pruebas, además de las 52 de `pruebas_seguridad.py`):

| Función | Riesgo | Medida |
|---|---|---|
| **Bloquear un programa** (Cortafuegos de Windows) | Bloquear algo vital o inyectar argumentos en `netsh` | Solo rutas absolutas a un `.exe` existente; nunca componentes de Windows, procesos protegidos ni a TrafficBar; `netsh` con lista de argumentos (sin shell); reglas con prefijo propio y estado en disco: **no toca reglas ajenas**; confirmación con consecuencias; requiere administrador; reversible (gestor «Bloqueados», caducidad, y el desinstalador las quita). |
| **Packs de idioma** | Un pack hostil (RTL/controles para disfrazar textos, marcadores que rompan el formato, archivo enorme, código de idioma con ruta) | Solo texto: sin `str.format` ni evaluación; se valida y se guarda una copia **limpia** (controles y marcas RTL fuera, marcadores comprobados, 2 MB / 6.000 entradas máx.); el código de idioma solo admite `xx` o `xx-XX` (no puede escribir fuera de la carpeta). |
| **Apps de la Tienda** (exención de loopback) | Exentar una app equivocada o inyectar argumentos; un pedido manipulado para la copia elevada | Solo apps **instaladas** (se comprueba justo antes de aplicar); nombre validado con una expresión estricta; `CheckNetIsolation` con argumentos en lista (sin shell); solo se quitan las exenciones que creó TrafficBar (archivo de estado validado); el pedido para la copia con administrador caduca a los 5 minutos y se borra; confirmación previa; el desinstalador las quita. Riesgo residual: otro programa **del mismo usuario** podría escribir un pedido, pero solo lograría exentar de loopback una app ya instalada. |
| **Cuota mensual** | Datos falsos o avisos repetidos | Usa los contadores de la tarjeta de red; un aviso por umbral y ciclo; configuración saneada. |
| **Créditos / donaciones** | Enlaces peligrosos en `creditos.json` | Solo se muestran enlaces `https://`; nada aparece si no está configurado. |

Hallazgos de esta ronda (encontrados con pruebas, no por lectura):

| ID | Hallazgo | Corrección |
|---|---|---|
| S20 | **Ventana de Tráfico en blanco hasta hacer clic.** Se simulaba la tecla Alt para traerla al frente; Windows lo interpreta como «entrar al menú de la ventana» y entra en un bucle modal. Se notaba al reiniciar como administrador (tras el aviso de UAC). | `bring_to_front()` con `AttachThreadInput`/`SetForegroundWindow` (sin teclas) y repintado forzado de todas las ventanas. |
| S21 | **Recursión sin límite al traducir** textos hostiles con muchas partes variables (`RecursionError`). Lo encontró la prueba adversaria. | Tope de anidamiento y comparador lineal sin expresiones regulares (un texto de 200.000 caracteres se traduce en milisegundos). |
| S22 | **Instalador sin marca UTF-8:** Inno Setup lo leía como ANSI y sus mensajes con tildes salían rotos («¿» → «Â¿»). | `TrafficBar.iss`, `compilar.ps1` e `Instalar-TrafficBar.ps1` guardados con BOM UTF-8. |
| S23 | **La captura perdía la mayor parte del tráfico** en descargas rápidas (scapy: ~4.000 paquetes/s). Con una ISO de 6 GB solo se veía el 6 %. | Lector propio de Npcap (búfer de 16 MB, copia directa): exacto contra los contadores de la tarjeta (966 MB vs 966 MB). Aviso si TrafficBar ve menos del 85 % de la tarjeta. |
| S24 | Con el proxy activo, todo el tráfico de los navegadores aparecía como `TrafficBar.exe`. | El proxy anota qué navegador pidió cada conexión y el monitor muestra su nombre. |

Límite conocido: las reglas del Cortafuegos no se pudieron probar contra Windows real en el entorno de pruebas (exigen
administrador); la lógica y los argumentos se probaron con un cortafuegos simulado. Comprueba el primer bloqueo con un
programa inofensivo.

| S25 | **Menos superficie de ataque:** se eliminaron Scapy, pystray y Pillow (más de 100 archivos de terceros en el ejecutable). Los paquetes de la red los lee ahora `netparse.py` (propio, con comprobación de límites en cada lectura) y la captura `pcap.py` (carga `wpcap.dll` solo por **ruta absoluta** de `System32\Npcap`). | Se comparó con la implementación anterior sobre tráfico variado (TCP/UDP, IPv4/IPv6, VLAN, SNI, HTTP, DNS, fragmentos, ICMP): resultados **idénticos**. Además, 4.000 mensajes DNS/tramas corruptos y bucles de compresión DNS no producen excepciones ni cuelgues. |

Licencias: ver [LICENCIAS-TERCEROS.md](LICENCIAS-TERCEROS.md). Con la retirada de Scapy (GPL-2.0-only) y pystray (LGPL-3.0) ya no hay código de terceros con copyleft en el ejecutable.

## Formas de entrega

| | Instalador (`TrafficBar-Setup-1.0.exe`) | Portable (`TrafficBar-Portable-1.0.zip`) |
|---|---|---|
| Dónde vive | *Archivos de programa* (solo un administrador puede modificarlo) | Donde la extraigas |
| Datos (config., historial) | `%LOCALAPPDATA%\TrafficBar` | Carpeta `Datos` junto al programa |
| Registro de Windows | Solo el inicio automático, si lo eliges (HKCU) | Nada |
| Modo administrador (Npcap) | Seguro (ver S3) | Solo seguro si la carpeta no la puede modificar otro programa tuyo; TrafficBar avisa |
| Desinstalar | Desinstalador propio (pregunta por tus datos) | Borrar la carpeta |

La versión portable se activa con el archivo `portable.flag` junto al programa. El historial contiene los sitios que visitas: no dejes la carpeta `Datos` en un USB que prestes.

Ambas se generan con un solo comando: `powershell -ExecutionPolicy Bypass -File .\compilar.ps1` (resultado en `Output\`).

## Cómo volver a comprobarlo

```bash
python pruebas_seguridad.py                      # 52 pruebas: ataques + regresión (usa carpetas temporales)
python pruebas_funciones.py                      # 94 pruebas: cuota, bloqueo de programas, apps de la Tienda, idiomas, créditos
python -m pip_audit -r requirements.txt          # dependencias con vulnerabilidades conocidas
python -m bandit -r . -ll --exclude ./dist,./build   # análisis estático (severidad media y alta)
```

## Instalación recomendada

```powershell
powershell -ExecutionPolicy Bypass -File .\Instalar-TrafficBar.ps1                    # instala en Archivos de programa
powershell -ExecutionPolicy Bypass -File .\Instalar-TrafficBar.ps1 -InicioConWindows  # además, arranca con tu sesión
powershell -ExecutionPolicy Bypass -File .\Instalar-TrafficBar.ps1 -Desinstalar       # quitar (conserva tu historial)
```
