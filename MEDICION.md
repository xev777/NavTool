# ¿Cuántos datos ahorra TrafficBar? – Medición

**Respuesta corta:** bloquear publicidad con TrafficBar **casi no reduce los bytes** de una página. Su valor está en
la privacidad, en menos conexiones a terceros y en poder **ver quién consume tu conexión**; no en «gastar menos datos».

## Cómo se midió
`medir_ahorro.py` carga 10 sitios reales con Edge (sin ventana, perfil nuevo = sin caché) **a través del proxy de
TrafficBar** y compara los bytes que pasan por la red con distintas listas de bloqueo. No toca tu configuración ni el
proxy de Windows. Se puede repetir: `python medir_ahorro.py --configs A,B,C,D`.

Sitios: elcomercio.pe, larepublica.pe, infobae.com, marca.com, as.com, cnn.com, bbc.com, nytimes.com,
dailymail.co.uk, forbes.com. Configuraciones: **A** sin bloqueo · **B** lista inicial (27 dominios) ·
**C** incluida + Peter Lowe (≈3.500) · **D** además StevenBlack (≈80.000).

## Resultados (MB por carga)
| Sitio | A sin bloqueo | B | C | D |
|---|---:|---:|---:|---:|
| elcomercio.pe | 5,12 | 5,04 | 5,22 | 5,55 |
| infobae.com | 3,37 | 3,34 | 3,35 | 3,35 |
| marca.com | 5,40 | 5,04 | 6,28 | 5,60 |
| as.com | 4,33 | 4,31 | 4,31 | 4,38 |
| cnn.com | 13,17 | 13,16 | 13,16 | 13,14 |
| bbc.com | 5,09 | 5,14 | 5,14 | 5,12 |
| nytimes.com | 0,38 | 0,38 | 0,37 | 0,38 |
| forbes.com | 13,77 | 13,71 | 13,53 | 13,50 |

Ahorro medio: **B ≈ 1 %**, **C ≈ −4 %**, **D ≈ −4 %** (mediana 0–1 %). Es decir: ninguna diferencia real; las variaciones
(+44 % en marca.com) son ruido entre cargas (vídeos y contenido que cambian).

## Lo que la medición SÍ enseña
- **El peso está en el contenido del propio sitio.** En las 10 cargas: 50,1 MB en 134 servidores; **≈ 75 %** son
  imágenes y vídeo de los propios sitios y de YouTube (p. ej. `media.cnn.com` 11,1 MB, `imageio.forbes.com` 5,3 MB).
  TrafficBar no puede ni debe quitar eso.
- **Publicidad y rastreo pesan poco.** Son muchas conexiones pero pocos bytes (scripts y píxeles pequeños).
  Bloquearlas ayuda a la privacidad y a la limpieza de la página, no al consumo de datos.

## Límite importante de esta prueba (no la uses para afirmar «ahorra 0 %»)
En una carga automática **sin ventana** los sitios casi no cargan su publicidad (esperan el consentimiento de
cookies y detectan que no es un navegador real). Con la lista actuando aparecen incluso más intentos bloqueados
(18 en Forbes) porque al bloquear el gestor de consentimiento el sitio «se rinde» y sí intenta cargarlos. Por eso
esta medición **no representa la publicidad que verías navegando de verdad**. Otras limitaciones: una sola carga por
sitio y configuración, sin desplazarse ni interactuar, y los anuncios cambian en cada visita.

## Cómo saber tu ahorro real
TrafficBar incluye el modo **«Solo medir»** (Filtros): no bloquea nada, pero mientras navegas con normalidad calcula
cuántos bytes iban a servidores de tus listas. **Estadísticas** muestra «X MB de Y MB (Z %)». Con esa medición TrafficBar
aprende el peso medio de una conexión de publicidad y calcula el «ahorro estimado» cuando bloqueas; **sin medición
propia no muestra ninguna cifra** (no se inventa).

## Dónde SÍ hay ahorro posible
Lo que más datos consume suele ser vídeo, descargas, actualizaciones y sincronizaciones de programas. TrafficBar ya te
lo muestra (Tráfico por programa, Historial, alertas de subida). Reducirlo requiere actuar sobre esos programas
(pausar la sincronización, desactivar el reproductor automático, marcar la conexión como «de uso medido» en Windows).
Una mejora futura sería **bloquear o limitar un programa** desde su fila.
