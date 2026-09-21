"""Ayuda de NavTool: introducción animada de 3 segundos, guía de uso y «Acerca de»."""
import json
import math
import os
import sys
import tkinter as tk
import webbrowser

from i18n import tr
from safety import monitor_work_area

VERSION = "1.1.1"
BG, PANEL, FG, MUTED, ACC = "#1b2a41", "#0f1a2b", "#e8eef7", "#8ea3bd", "#3fa9f5"
CREDITOS = {"autor": "Fernando", "repo": "", "licencia": "", "donaciones": []}
try:        # creditos.json (junto a la app): autor, enlace del código fuente y donaciones opcionales
    _ruta = os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))), "creditos.json")
    with open(_ruta, encoding="utf-8") as _f:
        _d = json.load(_f)
    for _k in CREDITOS:
        if isinstance(_d.get(_k), type(CREDITOS[_k])):
            CREDITOS[_k] = _d[_k]
except (OSError, ValueError):
    pass
SPLASH_MS = 3000
FRAME_MS = 30


# --------------------------------------------------------------------- introducción animada
class Splash(tk.Toplevel):
    """Ventana sin bordes, centrada, que dura 3 s: aparece con fundido, muestra anillos que se
    expanden (la «señal» de la red), el nombre y una barra de progreso, y se desvanece.
    Un clic la cierra antes."""
    W, H = 460, 260

    def __init__(self, master, on_done=None):
        super().__init__(master, bg=BG)
        self.on_done = on_done
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        try:
            self.attributes("-alpha", 0.0)
        except tk.TclError:
            pass
        x, y = master.winfo_x() + master.winfo_width() // 2, master.winfo_y() + 40
        l, t, r, b = monitor_work_area(x, y)
        self.geometry(f"{self.W}x{self.H}+{l + (r - l - self.W) // 2}+{t + (b - t - self.H) // 2}")
        self.cv = tk.Canvas(self, width=self.W, height=self.H, bg=BG, highlightthickness=1,
                            highlightbackground=ACC, cursor="hand2")
        self.cv.pack()
        self.cv.bind("<Button-1>", lambda e: self._finish())
        self.t0 = None
        self.done = False
        self._frame()

    def _frame(self):
        if self.done:
            return
        import time
        now = time.time()
        if self.t0 is None:
            self.t0 = now
        el = (now - self.t0) * 1000
        if el >= SPLASH_MS:
            return self._finish()
        try:
            a = min(el / 400, (SPLASH_MS - el) / 400, 1.0)      # fundido de entrada y de salida
            self.attributes("-alpha", max(0.0, a))
        except tk.TclError:
            pass
        self._draw(el)
        self.after(FRAME_MS, self._frame)

    def _draw(self, el):
        c, cx, cy = self.cv, self.W // 2, 100
        c.delete("all")
        # anillos que se expanden desde el logotipo
        for i in range(3):
            ph = ((el / 1100) + i / 3) % 1.0
            r = 22 + ph * 62
            shade = int(0x3f * (1 - ph) + 0x1b * ph), int(0xa9 * (1 - ph) + 0x2a * ph), \
                int(0xf5 * (1 - ph) + 0x41 * ph)
            c.create_oval(cx - r, cy - r, cx + r, cy + r, outline="#%02x%02x%02x" % shade, width=2)
        # puntos de «tráfico» orbitando
        for k in range(5):
            ang = el / 380 + k * 2 * math.pi / 5
            px, py = cx + 62 * math.cos(ang), cy + 62 * math.sin(ang) * 0.55
            c.create_oval(px - 3, py - 3, px + 3, py + 3, fill="#ffa94d", width=0)
        pulse = 1 + 0.06 * math.sin(el / 140)
        rr = 20 * pulse
        c.create_oval(cx - rr, cy - rr, cx + rr, cy + rr, fill=ACC, width=0)
        c.create_oval(cx - rr * .55, cy - rr * .55, cx + rr * .55, cy + rr * .55, fill=BG, width=0)
        c.create_oval(cx - rr * .25, cy - rr * .25, cx + rr * .25, cy + rr * .25, fill="#e8eef7", width=0)
        # nombre escrito letra a letra y lema
        name = "NavTool"
        n = min(len(name), int(el / 110))
        c.create_text(cx, 184, text=name[:n], fill=FG, font=("Segoe UI", 24, "bold"))
        if el > 900:
            c.create_text(cx, 212, text="Tu navegación y tu red, a la vista y bajo control",
                          fill=MUTED, font=("Segoe UI", 9))
        # barra de progreso con mensajes de arranque
        frac = min(el / SPLASH_MS, 1.0)
        c.create_rectangle(60, 236, self.W - 60, 240, fill="#27405f", width=0)
        c.create_rectangle(60, 236, 60 + (self.W - 120) * frac, 240, fill=ACC, width=0)
        msg = "Preparando el proxy…" if frac < .4 else (
            "Iniciando el monitor de red…" if frac < .75 else "Listo")
        c.create_text(60, 226, text=msg, fill=MUTED, font=("Segoe UI", 8), anchor="w")

    def _finish(self):
        if self.done:
            return
        self.done = True
        cb = self.on_done
        try:
            self.destroy()
        except tk.TclError:
            pass
        if cb:
            cb()


# ------------------------------------------------------------------------------ contenido
# Cada sección: lista de (estilo, texto). Estilos: h = título, p = párrafo, b = viñeta, n = nota.
SECCIONES = {}


def _sec(nombre, *items):
    SECCIONES[nombre] = items


_sec("Introducción",
     ("h", "¿Qué es NavTool?"),
     ("p", "NavTool es una barra flotante para Windows que te muestra y controla lo que pasa "
           "con tu conexión a Internet: cómo cargan las páginas, quién te rastrea y qué programas "
           "usan tu red. Funciona con todos los navegadores (Chrome, Edge, Firefox, Opera, Brave…)."),
     ("h", "¿Para qué sirve? (el objetivo)"),
     ("b", "Ver cómo se carga una página, conexión por conexión, y CORTAR la carga con un clic "
           "(útil contra ventanas emergentes y cargas en cadena)."),
     ("b", "Bloquear publicidad y rastreadores conocidos, y saber cuántos hubo en cada página."),
     ("b", "Entender el tráfico de tu equipo: qué programa habla con qué servidor y cuántos datos "
           "mueve, en lenguaje claro."),
     ("b", "Recibir alertas cuando algo inusual sube muchos datos o un programa nuevo se conecta."),
     ("b", "Buscar en hasta 5 buscadores desde la propia barra."),
     ("n", "Todo ocurre en tu equipo. NavTool no envía tus datos a ningún servidor ni tiene telemetría."))

_sec("Cómo funciona",
     ("h", "Dos piezas trabajando juntas"),
     ("p", "1) El PROXY LOCAL (botón ⏻). Cuando lo enciendes, NavTool se coloca entre tus navegadores "
           "e Internet. Por eso puede medir la carga de las páginas, bloquear dominios y generar el "
           "informe de privacidad. Al apagarlo, Windows recupera su configuración anterior."),
     ("p", "2) El MONITOR DE RED (botón 📡 Tráfico). Usa Npcap para observar los paquetes que entran "
           "y salen del equipo, de CUALQUIER programa, aunque no pase por el proxy (gestores de "
           "descargas, actualizaciones, juegos…). Necesita Npcap y permisos de administrador."),
     ("h", "Lo que NavTool puede y no puede hacer"),
     ("b", "HTTPS: NavTool NO descifra las páginas seguras (no instala certificados). En HTTPS bloquea "
           "por nombre de servidor; los filtros de contenido (pop-ups, scripts…) solo actúan en HTTP."),
     ("b", "Los nombres de destino que ves los declara el programa o el dueño de la IP; la IP sí es real."),
     ("b", "Bloquear publicidad casi no reduce los datos consumidos: su valor es la privacidad y la "
           "limpieza de las páginas. El peso real está en vídeos e imágenes de los propios sitios."),
     ("b", "NavTool no es un antivirus ni un cortafuegos: te informa y filtra, no reemplaza a esos programas."),
     ("h", "Datos y privacidad"),
     ("p", "El historial (sitios, alertas, consumo por minuto) se guarda solo en tu equipo y se "
           "conserva 30 días (los totales de tráfico, 62). Puedes borrarlo cuando quieras desde 🕘 Historial."))

_sec("Paso a paso",
     ("h", "Primeros pasos"),
     ("n", "1.  Enciende ⏻: la barra pasa a «ON» y el botón se pone verde. Ahora tus navegadores "
           "pasan por NavTool (puede que debas reiniciar el navegador la primera vez)."),
     ("n", "2.  Navega con normalidad. La barra de carga se llena mientras cargan las páginas. "
           "Haz clic en ella para desplegar el panel con cada conexión."),
     ("n", "3.  ✂ Cortar: si una página abre ventanas emergentes o no deja de cargar, pulsa ✂. "
           "Se cortan todas las conexiones en curso y se rechazan las nuevas durante 4 segundos."),
     ("n", "4.  📋 Informe: al terminar una carga te da una nota (A–F) de privacidad, con los "
           "rastreadores encontrados. Puedes bloquear dominios o «Permitir» los que rompan una página."),
     ("h", "Ver toda tu red"),
     ("n", "5.  📡 Tráfico: instala Npcap (npcap.com) y abre NavTool como administrador. Verás cada "
           "programa, a quién se conecta, cuánto sube y baja, y las consultas DNS. El total que "
           "muestra es lo que realmente pasó por tu tarjeta de red."),
     ("n", "6.  🚫 Bloquear un programa: en 📡 Tráfico, clic derecho sobre su fila → «Bloquear el acceso "
           "a Internet…». NavTool crea reglas en el Cortafuegos de Windows (1 hora, 4 horas o hasta que "
           "lo desbloquees). Los programas bloqueados se ven y se liberan en 🚫 Bloqueados. Nunca bloquea "
           "componentes de Windows ni a NavTool."),
     ("n", "7.  🕘 Historial: sitios visitados, consumo por programa y ALERTAS (subidas sostenidas, "
           "programas nuevos). El número naranja indica alertas sin leer."),
     ("n", "8.  📅 Cuota mensual: clic derecho en la barra → «Cuota mensual de datos…». Indica los GB de "
           "tu plan y el día en que empieza tu ciclo: verás lo gastado, lo que te queda por día y si a este "
           "ritmo te pasarás. Te avisa al llegar al 80 % y al 100 %."),
     ("h", "Ajustes y herramientas"),
     ("n", "9.  🛡 Filtros: elige qué bloquear (dominios, pop-ups, sonido…). Puedes descargar listas "
           "de bloqueo, añadir tus propios dominios y excepciones, y activar «Solo medir» para ver "
           "cuántos datos se habrían ahorrado sin bloquear nada."),
     ("n", "10. Buscador: escribe y pulsa Enter. Con el menú ▾ cambias de motor o buscas en todos a la "
           "vez (Mayús+Enter). Edita hasta 5 motores."),
     ("n", "11. Herramientas: 📊 Estadísticas · 🧹 Limpiar archivos temporales · 🗺 Mapa del sitio · "
           "📶 Ping / Traceroute · ℹ Información del sitio."),
     ("h", "La barra"),
     ("n", "12. Arrástrala: se pega a los bordes de la pantalla (imán) y las ventanas se abren junto a ella."),
     ("n", "13. El botón ◂ tiene 3 pasos: grande → mediano (compacto) → contraída del todo (píldora); "
           "un clic en la píldora la abre de nuevo en grande. Clic derecho: tamaño de textos y ventanas, "
           "anclar arriba o abajo, contraer sola, iniciar con Windows."),
     ("n", "14. Cerrar la ventana solo oculta la barra: NavTool sigue en la bandeja del sistema, junto al "
           "reloj. Para salir del todo, usa el icono de la bandeja → Salir."),
     ("n", "15. 🌐 Idioma: clic derecho en la barra → «Idioma / Language». Puedes cargar más packs de "
           "idioma (.json) o exportar la plantilla para traducir NavTool a tu idioma."),
     ("n", "Pasa el ratón sobre cualquier botón para ver una explicación."))

_sec("Consejos",
     ("h", "Si algo no funciona"),
     ("b", "Una página se ve rota: abre 📋 Informe, selecciona el dominio y pulsa «Permitir»."),
     ("b", "Un navegador no filtra: comprueba que ⏻ esté en ON y reinicia el navegador. Si usa su propia "
           "configuración de proxy o una VPN, puede saltarse NavTool (el monitor 📡 sí lo verá)."),
     ("b", "📡 Tráfico no arranca: instala Npcap desde npcap.com y abre NavTool como administrador."),
     ("b", "Con el proxy encendido, WhatsApp o la Microsoft Store (apps de la Tienda) no conectan: es una "
           "restricción de Windows. Clic derecho en la barra → «Compatibilidad con apps de la Tienda…» y marca "
           "esas apps."),
     ("b", "Si cierras NavTool de forma brusca, la próxima vez que se abra limpia el proxy de Windows solo."),
     ("h", "Cómo leer las cifras"),
     ("b", "NavTool muestra los tamaños en GB de 1024 MB (como el Administrador de tareas); "
           "los fabricantes suelen usar 1000 MB."),
     ("b", "El total de una descarga es mayor que el tamaño del archivo: las cabeceras de red suman "
           "un 5–6 %, y algunos gestores repiten partes del archivo."),
     ("b", "Con el proxy activo, lo que hace un navegador aparece con el nombre del navegador."))


class HelpWindow(tk.Toplevel):
    def __init__(self, app, start="Introducción", cfg=None, save_cfg=None, data_dir=""):
        super().__init__(app, bg=BG)
        self.app, self.cfg, self.save_cfg, self.data_dir = app, cfg, save_cfg, data_dir
        self.title("NavTool – Ayuda")
        self.attributes("-topmost", True)
        if hasattr(app, "place_near"):
            app.place_near(self, 700, 560)
        else:
            self.geometry("700x560")
        self.tabs = {}
        bar = tk.Frame(self, bg=BG)
        bar.pack(fill="x", padx=8, pady=(8, 0))
        for name in list(SECCIONES) + ["Acerca de"]:
            b = tk.Button(bar, text=name, relief="flat", bd=0, padx=12, pady=4, cursor="hand2",
                          font=("Segoe UI", 9, "bold"), command=lambda n=name: self.show(n))
            b.pack(side="left", padx=(0, 3))
            self.tabs[name] = b
        body = tk.Frame(self, bg=PANEL)
        body.pack(fill="both", expand=True, padx=8, pady=8)
        sb = tk.Scrollbar(body)
        sb.pack(side="right", fill="y")
        self.txt = tk.Text(body, bg=PANEL, fg=FG, relief="flat", wrap="word", padx=16, pady=12,
                           font=("Segoe UI", 10), yscrollcommand=sb.set, cursor="arrow",
                           spacing1=2, spacing3=4)
        self.txt.pack(fill="both", expand=True)
        sb.config(command=self.txt.yview)
        t = self.txt
        t.tag_config("h", font=("Segoe UI", 13, "bold"), foreground=ACC, spacing1=12, spacing3=6)
        t.tag_config("p", lmargin1=0, lmargin2=0)
        t.tag_config("b", lmargin1=14, lmargin2=28)
        t.tag_config("n", lmargin1=6, lmargin2=30, spacing3=6)
        t.tag_config("note", foreground="#ffd166", spacing1=10)
        t.tag_config("muted", foreground=MUTED)
        t.tag_config("big", font=("Segoe UI", 22, "bold"), foreground=FG)
        foot = tk.Frame(self, bg=BG)
        foot.pack(fill="x", padx=8, pady=(0, 8))
        self.intro_var = tk.BooleanVar(value=bool((cfg or {}).get("intro", True)))
        tk.Checkbutton(foot, text="Mostrar la animación de inicio al abrir NavTool",
                       variable=self.intro_var, command=self._toggle_intro, bg=BG, fg=FG,
                       selectcolor=PANEL, activebackground=BG, activeforeground=FG,
                       font=("Segoe UI", 9)).pack(side="left")
        tk.Button(foot, text="Cerrar", command=self.destroy, bg=ACC, fg="white", relief="flat",
                  padx=14, cursor="hand2").pack(side="right")
        self.show(start if start in self.tabs else "Introducción")
        self.bind("<Escape>", lambda e: self.destroy())

    def _toggle_intro(self):
        if self.cfg is not None:
            self.cfg["intro"] = bool(self.intro_var.get())
            if self.save_cfg:
                self.save_cfg(self.cfg)

    def show(self, name):
        for n, b in self.tabs.items():
            b.config(bg=ACC if n == name else "#27405f", fg="white", activebackground=ACC,
                     activeforeground="white")
        t = self.txt
        t.config(state="normal")
        t.delete("1.0", "end")
        if name == "Acerca de":
            self._about()
        else:
            for style, text in SECCIONES[name]:
                if style == "b":
                    t.insert("end", "•  ", "b")
                    t.insert("end", text + "\n", "b")
                elif style == "n":
                    t.insert("end", text + "\n", "n")
                elif style == "h":
                    t.insert("end", text + "\n", "h")
                else:
                    t.insert("end", text + "\n\n", "p")
        t.config(state="disabled")
        t.yview_moveto(0)

    def _about(self):
        t = self.txt
        t.insert("end", "◉ NavTool\n", "big")
        t.insert("end", f"Versión {VERSION}\n\n", "muted")
        t.insert("end", "Monitor y filtro de navegación y de red para Windows: barra flotante que funciona "
                        "con todos los navegadores, muestra la carga de las páginas, bloquea publicidad y "
                        "rastreadores y explica el tráfico de tu equipo.\n\n")
        t.insert("end", "Créditos\n", "h")
        t.insert("end", f"•  Diseño y desarrollo: {CREDITOS['autor']}\n", "b")
        t.insert("end", "•  Asistencia de programación: Claude (Anthropic)\n", "b")
        if CREDITOS["licencia"]:
            t.insert("end", f"•  Licencia: {CREDITOS['licencia']}\n", "b")
        self._enlaces(t)
        t.insert("end", "Privacidad\n", "h")
        t.insert("end", "•  Todo se procesa y se guarda en tu equipo. Sin cuentas, sin telemetría, sin "
                        "actualizaciones automáticas.\n", "b")
        t.insert("end", f"•  Tus datos: {self.data_dir}\n", "b")
        t.insert("end", "•  Puedes borrar el historial cuando quieras (🕘 Historial).\n", "b")
        t.insert("end", "Seguridad\n", "h")
        t.insert("end", "•  El proxy solo acepta conexiones de este equipo, usa un puerto aleatorio y "
                        "limita tamaños y tiempos. Se comprobó con una batería de pruebas de ataque y "
                        "regresión (ver SEGURIDAD.md).\n", "b")
        t.insert("end", "•  Los ejecutables no están firmados digitalmente: Windows SmartScreen puede "
                        "avisar al instalar.\n", "b")
        t.insert("end", "Componentes de terceros\n", "h")
        t.insert("end", "•  Npcap (captura de paquetes, npcap.com) · psutil · Python y Tkinter. Cada uno pertenece a "
                        "sus autores y se rige por su propia licencia.\n",
                 "b")
        t.insert("end", "\nNavTool es una herramienta informativa: no sustituye a un antivirus ni a un "
                        "cortafuegos.\n", "note")
        if self.data_dir and os.path.isdir(self.data_dir):
            self._boton(t, "Abrir la carpeta de datos", lambda: os.startfile(self.data_dir))  # nosec B606

    def _boton(self, t, texto, cmd):
        row = tk.Frame(t, bg=PANEL)
        tk.Button(row, text=texto, relief="flat", bg="#27405f", fg="white", cursor="hand2",
                  command=cmd, padx=8).pack(side="left", pady=4)
        t.insert("end", "\n")
        t.window_create("end", window=row)
        t.insert("end", "\n")

    def _enlaces(self, t):
        """Código fuente y donaciones OPCIONALES: solo aparecen si están en creditos.json."""
        if CREDITOS["repo"].startswith("https://"):
            self._boton(t, "Código fuente en GitHub", lambda: webbrowser.open(CREDITOS["repo"]))
        dons = [d for d in CREDITOS["donaciones"] if isinstance(d, dict) and d.get("nombre")
                and (str(d.get("url", "")).startswith("https://") or d.get("texto"))]
        if not dons:
            return
        t.insert("end", "Apoyar el proyecto (opcional)\n", "h")
        t.insert("end", "NavTool es gratuito. Si te resulta útil y quieres apoyar su desarrollo, puedes "
                        "hacerlo aquí; no es necesario para usarlo.\n", "p")
        for d in dons[:5]:
            nombre, url, texto = str(d["nombre"])[:30], str(d.get("url", "")), str(d.get("texto", ""))[:120]
            if texto:
                def copiar(x=texto):
                    self.clipboard_clear()
                    self.clipboard_append(x)
                self._boton(t, f"{nombre}: copiar {texto[:14]}…" if len(texto) > 14 else
                            f"{nombre}: copiar {texto}", copiar)
            else:
                self._boton(t, f"Apoyar con {nombre}", lambda u=url: webbrowser.open(u))
        t.insert("end", "Comprueba siempre que la dirección o el enlace coinciden con los de la página "
                        "oficial del proyecto.\n", "muted")
