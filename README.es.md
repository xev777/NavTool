# NavTool

**Una barra flotante para Windows que te muestra y controla lo que pasa con tu conexión a Internet**:
cómo cargan las páginas, quién te rastrea y qué programas usan tu red. Funciona con todos los navegadores.

*(English: [README.md](README.md))*

## Qué hace

| | |
|---|---|
| **Barra de carga** | Ve cada conexión de una página mientras carga y **córtala** con un clic (pop-ups, cargas en cadena). |
| **Informe de privacidad** | Una nota (A–F) por página: qué rastreadores contactó y cuáles bloqueó NavTool. |
| **Listas de bloqueo** | Lista incluida, listas opcionales (Peter Lowe / StevenBlack), lista personal y excepciones. |
| **Monitor de red** | Cada programa, con quién habla, cuánto mueve. Captura con Npcap, totales exactos. |
| **Bloquear un programa** | Clic derecho en el monitor → reglas del Cortafuegos de Windows (1 h / 4 h / hasta desbloquear). |
| **Cuota mensual** | Define tu plan y el día de corte: consumo, proyección y avisos al 80 % / 100 %. |
| **Historial y alertas** | Consumo por minuto y por programa, programas nuevos, subidas sostenidas. Solo en tu PC. |
| **Buscador** | Hasta 5 motores, una tecla para buscar en todos. |
| **Idiomas** | Inglés (por defecto) y español incluidos; carga más packs de idioma (`.json`). |
| **Barra** | Grande / mediana / contraída, imán en los bordes, icono en la bandeja, tooltips, multipantalla. |

Todo se ejecuta en tu equipo. **Sin telemetría, sin cuentas, sin actualizaciones automáticas.**

## Instalación

Descarga desde la página de [Releases](../../releases):

* `NavTool-Setup-<versión>.exe` — instalador (inglés por defecto; español en la primera pantalla).
* `NavTool-Portable-<versión>.zip` — portable, no deja rastro en el PC.

Comprueba el SHA-256 de las notas de la versión. Los ejecutables **aún no están firmados**: SmartScreen puede avisar.

El monitor de tráfico necesita [Npcap](https://npcap.com) y permisos de administrador (NavTool no incluye Npcap).

## Ejecutar desde el código

```powershell
python -m pip install -r requirements.txt
python navtool.py
```

Compilar instalador y zip portable (necesita [Inno Setup 6](https://jrsoftware.org/isinfo.php)):

```powershell
powershell -ExecutionPolicy Bypass -File .\compilar.ps1
```

## Pruebas

```powershell
python pruebas_seguridad.py    # 52 pruebas de ataque y regresión
python pruebas_funciones.py    # cuota, bloqueo de programas, idiomas, créditos
```

Más: [SEGURIDAD.md](SEGURIDAD.md) · [MEDICION.md](MEDICION.md) · [TRADUCIR.md](TRADUCIR.md) · [LICENCIAS-TERCEROS.md](LICENCIAS-TERCEROS.md)

## Licencia

Copyright (C) 2026 Fernando Erazo. NavTool es software libre: puedes redistribuirlo y modificarlo según los
términos de la **Licencia Pública General de GNU versión 3** (ver [LICENSE](LICENSE)). Se distribuye con la esperanza de que sea
útil, pero **sin ninguna garantía**.

## Créditos

Diseño y desarrollo: Fernando Erazo ([@xev777](https://github.com/xev777)). Asistencia de programación: Claude (Anthropic).
Componentes de terceros: Npcap (lo instala el usuario), psutil, Python/Tkinter. Ver [LICENCIAS-TERCEROS.md](LICENCIAS-TERCEROS.md).
