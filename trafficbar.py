"""TrafficBar – barra flotante de utilidades de navegación para Windows.

Funciona como proxy local: se registra como proxy del sistema, así que
filtra el tráfico de cualquier navegador (Chrome, Edge, Firefox, Opera...).
"""
import atexit
import collections
import ctypes
import copy
import json
import os
import queue
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import tkinter as tk
import urllib.parse
import urllib.request
import webbrowser
import ayuda
import blocklists
import cuota
import i18n
import programas
import tienda
from i18n import tr
from history import History
from safety import (force_paint, paint_soon, clean_text, http_url, in_protected_folder, is_reparse, known_folder,
                    monitor_work_area, system_exe, under, valid_host)
from tooltip import tip
from proxy_core import Proxy as _CoreProxy, filter_html as _filter_html
from loadtrack import Loader
from tkinter import messagebox, scrolledtext

try:
    import winreg
except ImportError:  # pruebas fuera de Windows
    winreg = None

if sys.stdout is None:  # ejecutable sin consola
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

APP = "TrafficBar"
PROXY_PORT = 0            # lo elige el proxy al arrancar (puerto aleatorio alto)
LEGACY_PORT = 8118        # puerto fijo de versiones anteriores (para limpiar ajustes huérfanos)
LOCAL_BASE = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or os.path.expanduser("~")


def _app_dir():
    return os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False)
                                           else __file__))


# Versión portable: si junto al programa existe «portable.flag», todo (configuración, historial,
# estado) se guarda en la carpeta «Datos» de al lado, sin tocar el perfil del usuario ni el registro.
PORTABLE = os.path.exists(os.path.join(_app_dir(), "portable.flag"))
DATA_DIR = os.path.join(_app_dir(), "Datos") if PORTABLE else os.path.join(LOCAL_BASE, APP)
CFG_FILE = os.path.join(DATA_DIR, "config.json")
BLOCK_FILE = os.path.join(DATA_DIR, "blocklist.txt")
ALLOW_FILE = os.path.join(DATA_DIR, "allowlist.txt")     # excepciones: nunca se bloquean
LISTS_DIR = os.path.join(DATA_DIR, "listas")             # listas descargadas
STATE_FILE = os.path.join(DATA_DIR, "proxy_state.json")

DEFAULT_BLOCKLIST = """\
doubleclick.net
googlesyndication.com
googleadservices.com
google-analytics.com
googletagmanager.com
adservice.google.com
adnxs.com
adsrvr.org
advertising.com
taboola.com
outbrain.com
criteo.com
criteo.net
scorecardresearch.com
quantserve.com
popads.net
popcash.net
propellerads.com
exoclick.com
adsterra.com
revcontent.com
mgid.com
pubmatic.com
rubiconproject.com
openx.net
moatads.com
zedo.com
"""

DEFAULT_ENGINES = [
    {"name": "Google", "url": "https://www.google.com/search?q={q}"},
    {"name": "Brave", "url": "https://search.brave.com/search?q={q}"},
    {"name": "DuckDuckGo", "url": "https://duckduckgo.com/?q={q}"},
    {"name": "Bing", "url": "https://www.bing.com/search?q={q}"},
    {"name": "Wikipedia", "url": "https://es.wikipedia.org/w/index.php?search={q}"},
]
MAX_ENGINES = 5

DEFAULT_CFG = {
    "engines": DEFAULT_ENGINES,   # hasta 5 motores de búsqueda ({q} = lo que se busca)
    "engine": 0,                  # índice del motor activo
    "auto_panel": True,           # desplegar el panel de carga al empezar a cargar
    "lists_builtin": True,        # lista de publicidad y analítica incluida en TrafficBar
    "list_pgl": True,             # lista descargable: Peter Lowe (publicidad y rastreo)
    "list_stevenblack": False,    # lista descargable: StevenBlack (amplia, incluye malware)
    "lists_auto": False,          # actualizar las listas solas cada semana
    "measure_only": False,        # «solo medir»: no bloquea, calcula cuántos datos se ahorrarían
    "ad_bytes_per_conn": None,    # peso medio (medido) de una conexión a publicidad/rastreo
    "quota_gb": 0.0,              # cuota mensual de datos de tu plan (0 = sin cuota)
    "quota_day": 1,               # día del mes en que empieza tu ciclo de facturación
    "quota_count": "both",        # qué cuenta tu plan: "both" (bajada + subida) o "down"
    "store_hint": False,          # ya se avisó de las apps de la Tienda al encender el proxy
    "lang": None,                 # idioma de la interfaz (None = el elegido al instalar; «en» por defecto)
    "ui_scale": 0.85,             # tamaño de textos y ventanas (1.0 normal · 0.85 pequeño · 0.75 muy pequeño)
    "intro": True,                # animación de inicio de 3 segundos
    "bar_size": "large",          # tamaño de la barra: "large" (grande) o "compact" (compacta)
    "bar_magnet": True,           # imán: la barra se pega a los bordes de la pantalla
    "bar_dock": None,             # anclada arriba ("top") o abajo ("bottom") del monitor
    "bar_collapsed": False,       # la barra está contraída (píldora)
    "bar_auto": False,            # contraer sola al alejar el ratón; abrir al acercarlo
    "bar_x": None,                # última posición de la barra (None = centrada arriba)
    "bar_y": None,
    "alert_up_mb_s": 3.0,         # alerta: subida sostenida del equipo (MB/s durante 20 s)
    "alert_proc_mb_min": 100.0,   # alerta: un programa que envía más de X MB en un minuto
    "monitor_bg": False,          # captura Npcap continua por programa (requiere administrador)
    "block_domains": True,   # filtro por dominio (HTTP y HTTPS)
    "block_popups": True,    # neutraliza window.open (solo HTTP)
    "block_scripts": False,  # elimina <script> (solo HTTP)
    "block_sound": True,     # bgsound / audio / embed (solo HTTP)
    "block_blink": True,     # <blink>, <marquee>, animaciones (solo HTTP)
    "block_background": False,  # fondos e imágenes de fondo (solo HTTP)
    "block_cookies": False,  # elimina Cookie / Set-Cookie (solo HTTP)
}

# ----------------------------------------------------------------- configuración
def _num(v, default, lo, hi):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    return default if f != f else min(max(f, lo), hi)      # NaN → valor por defecto


def sanitize_cfg(cfg):
    """Un config.json editado a mano o dañado no debe impedir abrir la app ni colar tipos raros."""
    base = DEFAULT_CFG
    out = {}
    for k, default in base.items():
        v = cfg.get(k, default)
        if isinstance(default, bool):
            out[k] = v if isinstance(v, bool) else default
        elif k == "engines":
            out[k] = clean_engines(v)
        elif k == "engine":
            out[k] = int(_num(v, 0, 0, MAX_ENGINES - 1))
        elif k == "bar_size":
            out[k] = v if v in ("large", "compact") else default
        elif k == "bar_dock":
            out[k] = v if v in ("top", "bottom") else None
        elif k in ("bar_x", "bar_y"):
            num = isinstance(v, (int, float)) and not isinstance(v, bool)
            out[k] = int(_num(v, 0, -30000, 30000)) if num else None
        elif k == "quota_gb":
            out[k] = _num(v, 0.0, 0.0, 100000.0)
        elif k == "quota_day":
            out[k] = int(_num(v, 1, 1, 28))
        elif k == "quota_count":
            out[k] = v if v in ("both", "down") else "both"
        elif k == "lang":
            out[k] = v if isinstance(v, str) and (v == "es" or i18n.CODE_RE.match(v)) else None
        elif k == "ui_scale":
            out[k] = _num(v, default, 0.6, 1.0)
        elif k == "alert_up_mb_s":
            out[k] = _num(v, default, 0.5, 10000)
        elif k == "alert_proc_mb_min":
            out[k] = _num(v, default, 10, 1000000)
        else:
            out[k] = v
    out["engine"] = min(out["engine"], len(out["engines"]) - 1)
    return out


def clean_engines(engines):
    """Deja solo motores válidos (nombre, URL http(s) con {q}), máximo 5."""
    out = []
    for e in engines if isinstance(engines, list) else []:
        try:
            name, url = str(e["name"]).strip(), str(e["url"]).strip()
        except (KeyError, TypeError):
            continue
        if name and url.lower().startswith(("http://", "https://")) and "{q}" in url:
            out.append({"name": name[:20], "url": url})
    return out[:MAX_ENGINES] or copy.deepcopy(DEFAULT_ENGINES)


def load_cfg():
    if not PORTABLE and not os.path.exists(DATA_DIR):   # migra datos de versiones anteriores
        roaming = os.environ.get("APPDATA") or ""
        # La app se llamó NavTool (LOCALAPPDATA, luego APPDATA en versiones muy viejas) y antes Naviscope.
        for base, name in ((LOCAL_BASE, "NavTool"), (roaming, "NavTool"), (roaming, "Naviscope")):
            old = os.path.join(base, name) if base else ""
            if old and os.path.isdir(old) and os.path.abspath(old) != os.path.abspath(DATA_DIR):
                try:
                    shutil.copytree(old, DATA_DIR)
                    shutil.rmtree(old, ignore_errors=True)   # no queda una copia duplicada atrás
                except OSError:
                    pass
                break
    os.makedirs(DATA_DIR, exist_ok=True)
    cfg = copy.deepcopy(DEFAULT_CFG)
    try:
        with open(CFG_FILE, encoding="utf-8") as f:
            cfg.update(json.load(f))
    except (OSError, ValueError):
        pass
    cfg = sanitize_cfg(cfg)
    if not os.path.exists(BLOCK_FILE):
        with open(BLOCK_FILE, "w", encoding="utf-8") as f:
            f.write(DEFAULT_BLOCKLIST)
    return cfg


def save_cfg(cfg):
    with open(CFG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def load_blocklist():
    try:
        with open(BLOCK_FILE, encoding="utf-8") as f:
            return {l.strip().lower() for l in f if l.strip() and not l.startswith("#")}
    except OSError:
        return set()


def load_lines(path):
    """Dominios de un archivo de texto (uno por línea); descarta lo que no sea un dominio válido."""
    out = set()
    try:
        with open(path, encoding="utf-8") as f:
            for line in f.read(2_000_000).splitlines():
                line = line.split("#", 1)[0].strip().lower()
                if line and valid_host(line):
                    out.add(line)
    except OSError:
        pass
    return out


# ------------------------------------------------------------------------- estado
class Stats:
    def __init__(self):
        self.lock = threading.Lock()
        self.requests = self.blocked = self.bytes_down = self.bytes_up = 0
        self.filtered = 0
        self.recent_blocked = []
        self.conn_bytes = 0        # bytes de todas las conexiones terminadas
        self.pot_bytes = 0         # de ellos, los que iban a servidores que tus listas bloquean
        self.pot_conns = 0

    def add(self, **kw):
        with self.lock:
            for k, v in kw.items():
                setattr(self, k, getattr(self, k) + v)

    def conn_done(self, host, n):
        """Una conexión terminó. Si va a un servidor de tus listas (y no se bloqueó: modo «solo
        medir» o lista desactivada), cuenta como ahorro POTENCIAL medido."""
        with self.lock:
            self.conn_bytes += n
            if is_blocked_host(host):
                self.pot_bytes += n
                self.pot_conns += 1

    def block(self, host):
        with self.lock:
            self.blocked += 1
            self.recent_blocked = (self.recent_blocked + [host])[-50:]


STATS = Stats()
LOADER = Loader()
CFG = load_cfg()


def _res(name):
    return os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))), name)


def _idiomas_dirs():
    """(carpeta, incluida_con_la_app): los packs incluidos y los que el usuario ha cargado."""
    return [(_res("idiomas"), True), (os.path.join(DATA_DIR, "idiomas"), False)]


def _idioma_inicial():
    """Idioma elegido por el usuario; si no, el que marcó el instalador (idioma.txt); si no, inglés."""
    env = os.environ.get("TRAFFICBAR_LANG")
    if env:
        return env
    if CFG.get("lang"):
        return CFG["lang"]
    try:
        with open(os.path.join(_app_dir(), "idioma.txt"), encoding="utf-8") as f:
            code = f.read().strip()[:8]
        if code == "es" or i18n.CODE_RE.match(code):
            return code
    except OSError:
        pass
    return "en"


i18n.instalar_hooks()
if not i18n.activar(_idioma_inicial(), _idiomas_dirs()):
    i18n.activar("es", _idiomas_dirs())          # sin pack disponible: texto original
BLOCKLIST = load_blocklist()              # tu lista personal
ALLOWLIST = load_lines(ALLOW_FILE)        # tus excepciones: siempre ganan
LIST_DOMAINS = set()                      # listas descargadas activas
ALL_BLOCK = set()                         # todo junto: lo que realmente se consulta


def rebuild_blocklists():
    global ALL_BLOCK
    ALL_BLOCK = blocklists.combinar(BLOCKLIST, CFG.get("lists_builtin", True), [LIST_DOMAINS], ALLOWLIST)


def reload_lists():
    """Vuelve a leer del disco las listas descargadas que estén activadas."""
    global LIST_DOMAINS
    sets = [blocklists.cargar(LISTS_DIR, k) for k in blocklists.SOURCES if CFG.get("list_" + k)]
    LIST_DOMAINS = set().union(*sets) if sets else set()
    rebuild_blocklists()


reload_lists()
HIST = History(os.path.join(DATA_DIR, "history.db"))
programas.configurar(os.path.join(DATA_DIR, "programas_bloqueados.json"))
tienda.configurar(DATA_DIR)


# ---------------------------------------------------------------- instancia única
_mutex = None


def acquire_single_instance():
    """True si somos la única copia. Si ya hay otra, le pide que se muestre y devuelve False."""
    global _mutex
    k32 = ctypes.windll.kernel32
    _mutex = k32.CreateMutexW(None, False, "Local\\TrafficBar_single_instance")
    if k32.GetLastError() == 183:                      # ERROR_ALREADY_EXISTS
        ev = k32.OpenEventW(0x0002, False, "Local\\TrafficBar_show")
        if ev:
            k32.SetEvent(ev)
            k32.CloseHandle(ev)
        return False
    return True


def release_single_instance():
    global _mutex
    if _mutex:
        ctypes.windll.kernel32.CloseHandle(_mutex)
        _mutex = None


def is_blocked_host(host):
    """¿El dominio (o uno padre) está bloqueado por tus listas? Ignora si el filtro está activo.
    Tus excepciones ganan siempre."""
    return blocklists.esta_bloqueado(host, ALL_BLOCK, ALLOWLIST)


def saved_estimate():
    """Datos que TrafficBar se ahorró, ESTIMADOS: conexiones bloqueadas × peso medio que TÚ mediste
    con «Solo medir». Sin esa medición devuelve None (no se inventa una cifra)."""
    per = CFG.get("ad_bytes_per_conn")
    return int(STATS.blocked * per) if per else None


def saved_text():
    est = saved_estimate()
    return f"≈ {human(est)}" if est is not None else "sin medir (activa «Solo medir» en Filtros)"


def is_blocked(host):
    return CFG["block_domains"] and not CFG.get("measure_only") and is_blocked_host(host)


# ------------------------------------------------------------ proxy (ver proxy_core.py)
def filter_html(html):
    return _filter_html(html, CFG)


class Proxy(_CoreProxy):
    def __init__(self):
        super().__init__(STATS, LOADER, CFG, is_blocked)


# -------------------------------------------------------- proxy del sistema (Win)
INET_KEY = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"


def _refresh_inet():
    w = ctypes.windll.wininet
    w.InternetSetOptionW(0, 39, 0, 0)  # SETTINGS_CHANGED
    w.InternetSetOptionW(0, 37, 0, 0)  # REFRESH


def set_system_proxy(enable):
    if not winreg:
        return
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, INET_KEY, 0, winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, "ProxyEnable", 0, winreg.REG_DWORD, int(enable))
        if enable:
            winreg.SetValueEx(k, "ProxyServer", 0, winreg.REG_SZ, f"127.0.0.1:{PROXY_PORT}")
            winreg.SetValueEx(k, "ProxyOverride", 0, winreg.REG_SZ, "<local>")
    _refresh_inet()


def _state_port():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return int(json.load(f)["port"])
    except (OSError, ValueError, KeyError, TypeError):
        return 0


def _write_state(port):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump({"port": port, "pid": os.getpid()}, f)
    except OSError:
        pass


def _clear_state():
    try:
        os.remove(STATE_FILE)
    except OSError:
        pass


def _listening(port):
    try:
        socket.create_connection(("127.0.0.1", port), timeout=0.4).close()
        return True
    except OSError:
        return False


def is_our_proxy(server):
    """¿Ese ajuste de proxy de Windows lo puso TrafficBar (esta versión o una anterior)?"""
    ports = {p for p in (PROXY_PORT, _state_port(), LEGACY_PORT) if p}
    return bool(server) and any(server == f"127.0.0.1:{p}" for p in ports)


# ------------------------------------------------------ inicio con Windows (solo tu usuario)
AUTOSTART_NAME = "TrafficBar"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def autostart_command():
    """Orden de arranque. Solo existe en la versión compilada: en desarrollo no se registra
    nada, para no dejar apuntando al intérprete de Python."""
    if not getattr(sys, "frozen", False) or PORTABLE:   # la portable no deja rastro en el registro
        return None
    return f'"{sys.executable}" --segundo-plano'


def autostart_enabled():
    if not winreg:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            return winreg.QueryValueEx(k, AUTOSTART_NAME)[0] == autostart_command()
    except OSError:
        return False


def set_autostart(on):
    """Activa/desactiva el inicio con tu sesión (HKCU, sin permisos de administrador).
    Devuelve False si no se pudo (p. ej. no es la versión compilada)."""
    cmd = autostart_command()
    if not winreg or (on and not cmd):
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            if on:
                winreg.SetValueEx(k, AUTOSTART_NAME, 0, winreg.REG_SZ, cmd)
            else:
                try:
                    winreg.DeleteValue(k, AUTOSTART_NAME)
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        return False


def get_system_proxy():
    if not winreg:
        return None
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, INET_KEY) as k:
        def val(n):
            try:
                return winreg.QueryValueEx(k, n)[0]
            except OSError:
                return None
        return val("ProxyEnable"), val("ProxyServer")


# ------------------------------------------------------------------ utilidades
def clean_targets():
    """Devuelve [(descripción, ruta, es_carpeta)] de lo que se puede limpiar.
    Las carpetas base salen de Windows (no de variables de entorno, que otro programa podría
    haber cambiado) y solo se aceptan rutas que sigan dentro de ellas."""
    local, roam = known_folder(0x1C), known_folder(0x1A)
    t = []
    if local:
        t.append(("Archivos temporales de Windows", os.path.join(local, "Temp"), True))
        for name, base in (("Chrome", r"Google\Chrome"), ("Edge", r"Microsoft\Edge"),
                           ("Brave", r"BraveSoftware\Brave-Browser")):
            d = os.path.join(local, base, "User Data", "Default")
            t += [(f"{name}: caché", os.path.join(d, "Cache"), True),
                  (f"{name}: historial", os.path.join(d, "History"), False)]
    ff = os.path.join(roam, "Mozilla", "Firefox", "Profiles") if roam else ""
    if ff and os.path.isdir(ff):
        for prof in os.listdir(ff):
            t.append((f"Firefox ({prof}): historial",
                      os.path.join(ff, prof, "places.sqlite"), False))
    ok = []
    for desc, path, isdir in t:
        base = local if local and path.startswith(local) else roam
        if os.path.exists(path) and not is_reparse(path) and base and under(path, base):
            ok.append((desc, path, isdir))
    return ok


def remove_path(path, is_dir):
    """Borra el contenido de una carpeta (o un archivo) sin atravesar enlaces ni uniones."""
    if is_reparse(path):
        return 0
    freed = 0

    def clean(folder):
        nonlocal freed
        try:
            with os.scandir(folder) as it:
                entries = list(it)
        except OSError:
            return
        for e in entries:
            try:
                if is_reparse(e.path):
                    continue                       # se ignora: apunta fuera de esta carpeta
                if e.is_dir(follow_symlinks=False):
                    clean(e.path)
                    os.rmdir(e.path)
                else:
                    size = e.stat(follow_symlinks=False).st_size
                    os.remove(e.path)
                    freed += size
            except OSError:
                pass
    if is_dir:
        clean(path)
    else:
        try:
            freed = os.path.getsize(path)
            os.remove(path)
        except OSError:
            freed = 0
    return freed


def human(n):
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {u}" if u == "B" else f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} TB"


normalize_url = http_url      # solo http/https (ver safety.py)


# --------------------------------------------------------------------------- GUI
BG, FG, ACC, BTN = "#1b2a41", "#e8eef7", "#3fa9f5", "#27405f"
LOAD_W = 210   # ancho de la barra de carga en la barra flotante
MINI_W = 70    # ancho del mini progreso en la barra contraída
COMPACT_LOAD_W = 120   # ancho de la barra de carga en el tamaño compacto
MAGNET_PX = 22  # distancia a un borde de pantalla a la que la barra se pega


class Floating(tk.Tk):
    def report_callback_exception(self, exc, val, tb):
        import traceback
        try:
            log = os.path.join(DATA_DIR, "errores.log")
            if os.path.exists(log) and os.path.getsize(log) > 512 * 1024:
                os.remove(log)                # tamaño máximo: no crece sin límite
            with open(log, "a", encoding="utf-8") as f:
                f.write(time.strftime("%Y-%m-%d %H:%M:%S\n") + "".join(
                    traceback.format_exception(exc, val, tb)) + "\n")
        except OSError:
            pass

    def __init__(self):
        super().__init__()
        self.base_scaling = float(self.tk.call("tk", "scaling"))
        self.ui_scale = CFG.get("ui_scale", 0.85)
        self.tk.call("tk", "scaling", self.base_scaling * self.ui_scale)   # textos de todas las ventanas
        self.title(APP)
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(bg=BG)
        self.proxy = Proxy()
        self.prev_proxy = get_system_proxy()
        if self.prev_proxy and self.prev_proxy[0] and is_our_proxy(self.prev_proxy[1]):
            # un cierre brusco anterior dejó el proxy de Windows apuntando a un puerto que ya
            # nadie atiende (y que otro programa podría ocupar). El puerto antiguo fijo solo se
            # limpia si nada escucha en él, por si aún corre una versión vieja.
            port = int(self.prev_proxy[1].rsplit(":", 1)[1])
            if port != LEGACY_PORT or not _listening(port):
                set_system_proxy(False)
                self.prev_proxy = (0, None)
                _clear_state()
        self._drag = (0, 0)
        self.reports = collections.deque(maxlen=50)   # informes de privacidad de la sesión
        self.last_report = None
        self._was_loading = False

        outer = tk.Frame(self, bg=BG, highlightbackground=ACC, highlightthickness=1)
        outer.pack()
        self.grip = tk.Label(outer, text="◉ TrafficBar", bg=BG, fg=ACC, font=("Segoe UI", 9, "bold"),
                             cursor="fleur")
        self.grip.pack(side="left", padx=6)
        self._bind_drag(self.grip)

        # la barra completa y la «píldora» contraída comparten el mismo marco exterior
        self.full = tk.Frame(outer, bg=BG)
        self.mini = tk.Frame(outer, bg=BG)
        self.collapsed = False
        self._auto_collapsed = False       # contraída sola por el modo automático (se abre al pasar)
        self._last_inside = time.time()
        self._menu_until = 0.0             # mientras hay un menú abierto no se contrae sola
        bar = self.full
        self.full.pack(side="left")

        self.cut_msg_until = 0.0
        self.panel = None
        self.panel_block_until = 0.0
        self._btns = {}
        self._dock_pending = CFG.get("bar_dock")
        self._build_full()
        # sin ✕: cerrar la ventana solo oculta la barra; se sale desde el icono de la bandeja
        self._build_mini()
        self._add_static_tips()

        self.update_idletasks()
        w = self.winfo_reqwidth()
        x, y = CFG.get("bar_x"), CFG.get("bar_y")
        if x is None or y is None:
            x, y = (self.winfo_screenwidth() - w) // 2, 8
        self.geometry(f"+{int(x)}+{int(y)}")
        self.set_collapsed(bool(CFG.get("bar_collapsed")), persist=False)   # también ajusta a la pantalla
        self.protocol("WM_DELETE_WINDOW", self.hide_bar)
        self.after(250, self._autohide_tick)
        if "--segundo-plano" in sys.argv:      # arranque con Windows: solo el icono de la bandeja
            self.withdraw()
        self._set_icon()
        atexit.register(self._emergency_restore)

        # segundo plano: icono junto al reloj, vigilante de alertas y captura opcional por programa
        self._acts = queue.Queue()      # acciones que llegan desde otros hilos (bandeja, alertas)
        self._unseen = HIST.unseen_alerts()
        self._tel_unseen = HIST.unseen_alerts("telemetry")
        self.bg_engine = None
        self.history_win = None
        self.telemetry_win = None
        self.tray = None
        try:
            from tray import Tray
            self.tray = Tray(self._resource("trafficbar.ico"), self._acts.put, lambda: {
                "proxy_on": bool(self.proxy.server), "unseen": self._unseen,
                "tel_unseen": self._tel_unseen,
                "has_report": bool(self.last_report), "autostart": autostart_enabled(),
                "can_autostart": bool(autostart_command())})
            self.tray.start()
        except Exception:
            self.tray = None            # sin bandeja la app sigue funcionando con la barra
        from watcher import Watcher
        self.watcher = Watcher(HIST, lambda: CFG, self._notify, self._get_engine)
        self.watcher.start()
        threading.Thread(target=HIST.purge, args=(30,), daemon=True).start()
        if CFG.get("lists_auto"):
            threading.Thread(target=self._auto_lists, daemon=True).start()
        self._start_bg_engine()
        self._show_evt_stop = False
        threading.Thread(target=self._wait_show_event, daemon=True).start()
        self.refresh_alert_badge()
        self.after(150, self._poll_acts)
        self.after(1000, self.tick)
        self.after(100, self.draw_progress)
        if "--traffic" in sys.argv:
            self.after(600, self.win_traffic)
        paint_soon(self, (100, 600, 1500, 3200))

    # ---- segundo plano: bandeja, alertas, instancia única
    def _poll_acts(self):
        try:
            while True:
                act = self._acts.get_nowait()
                if callable(act):              # un hilo de fondo pide ejecutar algo en la interfaz
                    act()
                    continue
                {"toggle_bar": self.toggle_bar, "show_bar": self.show_bar,
                 "reset_position": self.reset_bar_position,
                 "toggle_collapse": self.toggle_collapse, "toggle_size": self.toggle_size,
                 "toggle_autostart": self.toggle_autostart,
                 "toggle_proxy": self.toggle_proxy, "traffic": self.win_traffic,
                 "report": self.win_report, "history": self.win_history,
                 "help": self.win_help, "about": lambda: self.win_help("Acerca de"),
                 "quota": self.win_quota, "blocked": self.win_blocked, "store": self.win_tienda,
                 "telemetria": self.win_telemetria,
                 "badge": self.refresh_alert_badge, "quit": self.quit_app}.get(act, lambda: None)()
        except queue.Empty:
            pass
        except tk.TclError:
            return
        self.after(150, self._poll_acts)

    def _wait_show_event(self):
        """Otra copia de TrafficBar que se abre avisa aquí para que mostremos la barra."""
        k32 = ctypes.windll.kernel32
        ev = k32.CreateEventW(None, False, False, "Local\\TrafficBar_show")
        while not self._show_evt_stop:
            if k32.WaitForSingleObject(ev, 500) == 0:
                self._acts.put("show_bar")
        k32.CloseHandle(ev)

    def show_bar(self):
        self.deiconify()
        self.attributes("-topmost", True)
        self.lift()
        self._clamp_on_screen()        # por si el monitor donde estaba ya no está conectado

    def hide_bar(self):
        if self.panel is not None and self.panel.winfo_exists():
            self.panel.destroy()
            self.panel = None
        self.withdraw()

    def toggle_bar(self):
        self.show_bar() if self.state() == "withdrawn" else self.hide_bar()

    def reset_bar_position(self):
        """Trae la barra a una posición visible del monitor principal. Recupera la barra si quedó
        fuera de la pantalla, por ejemplo tras desconectar el monitor donde estaba."""
        CFG["bar_dock"] = None
        self._dock_pending = None
        self.update_idletasks()
        w = self.winfo_reqwidth()
        left, top, right, _bottom = monitor_work_area(0, 0)     # (0, 0) siempre está en el monitor principal
        x, y = left + max(0, (right - left - w) // 2), top + 8
        self.geometry(f"+{x}+{y}")
        CFG["bar_x"], CFG["bar_y"] = x, y
        save_cfg(CFG)
        self.show_bar()

    def _notify(self, title, message):
        """Llamado desde el vigilante (otro hilo): aviso junto al reloj y actualiza el contador."""
        if self.tray:
            self.tray.notify(tr(title), tr(message))
        self._acts.put("badge")

    def refresh_alert_badge(self):
        self._unseen = HIST.unseen_alerts()
        self._tel_unseen = HIST.unseen_alerts("telemetry")
        n = self._unseen
        self.hist_btn.config(text=self._hist_text(n), bg="#c9772b" if n else BTN)

    def _get_engine(self):
        if self.bg_engine and self.bg_engine.running:
            return self.bg_engine
        t = getattr(self, "traffic", None)
        if t is not None and t.winfo_exists() and t.engine.running:
            return t.engine
        return None

    def _start_bg_engine(self):
        """Captura Npcap continua por programa (solo con administrador y Npcap instalado)."""
        if not CFG.get("monitor_bg") or self.bg_engine:
            return
        if not ctypes.windll.shell32.IsUserAnAdmin() or not os.path.isdir(r"C:\Windows\System32\Npcap"):
            return
        try:
            from traffic_monitor import Engine
            eng = Engine(is_blocked_host)
            eng.start(None)
            self.bg_engine = eng
        except Exception:
            self.bg_engine = None

    def monitor_state(self):
        on = bool(CFG.get("monitor_bg"))
        if not on:
            return False, "Desactivado. Sin él se guarda el tráfico total, no el de cada programa."
        if self.bg_engine and self.bg_engine.running:
            return True, "Activo: capturando por programa en segundo plano."
        if not os.path.isdir(r"C:\Windows\System32\Npcap"):
            return True, "Pendiente: falta instalar Npcap (npcap.com)."
        if not ctypes.windll.shell32.IsUserAnAdmin():
            return True, ("Pendiente: TrafficBar no está como administrador. Abre «📡 Tráfico» y "
                          "acepta reiniciar como administrador.")
        return True, "Pendiente: se activará en unos segundos."

    def set_monitor(self, on):
        CFG["monitor_bg"] = bool(on)
        save_cfg(CFG)
        if on:
            self._start_bg_engine()
        elif self.bg_engine:
            self.bg_engine.stop()
            self.bg_engine = None
        self._update_traffic_led()
        return self.monitor_state()[1]

    def _update_traffic_led(self):
        """Punto junto a «📡 Tráfico»: verde solo cuando la captura por programa está realmente
        activa en segundo plano (Npcap + administrador). No cambia el color del botón."""
        if not hasattr(self, "traffic_led") or not self.traffic_led.winfo_exists():
            return
        eng = getattr(self, "bg_engine", None)
        on = bool(eng and eng.running)
        self.traffic_led.itemconfig(self._traffic_led_dot, fill="#3fb97f" if on else BG)

    def win_history(self):
        if self.history_win is not None and self.history_win.winfo_exists():
            self.history_win.deiconify()
            self.history_win.lift()
            return
        from history_view import HistoryWindow
        self.history_win = HistoryWindow(self, HIST, CFG, save_cfg, self._open_report_dict,
                                         self.set_monitor, self.monitor_state)

    def _open_report_dict(self, rep):
        from report_view import ReportWindow
        ReportWindow(self, rep, self.add_block, is_blocked_host, self.add_allow)

    def win_telemetria(self):
        if self.telemetry_win is not None and self.telemetry_win.winfo_exists():
            self.telemetry_win.deiconify()
            self.telemetry_win.lift()
            return
        from telemetria import TelemetryWindow
        self.telemetry_win = TelemetryWindow(self, HIST, self.refresh_alert_badge)

    @property
    def compact(self):
        return CFG.get("bar_size") == "compact"

    def _btn(self, parent, text, cmd, accent=False, key=None):
        cp = self.compact
        b = tk.Button(parent, text=text, command=cmd, bg="#1f6fa8" if accent else BTN, fg=FG,
                      relief="flat", bd=0, font=("Segoe UI", 8 if cp else 9),
                      activebackground=ACC, activeforeground="white",
                      padx=5 if cp else 8, pady=1 if cp else 2, cursor="hand2")
        b.pack(side="left", padx=1 if cp else 2, pady=2 if cp else 4)
        self._btns[key or text] = b
        return b

    # etiquetas que cambian según el tamaño
    def _power_text(self, on):
        return "⏻" if self.compact else ("⏻ ON" if on else "⏻ OFF")

    def _stats_text(self):
        return f"🚫{STATS.blocked}" if self.compact else f"{STATS.blocked} bloq."

    def _hist_text(self, n):
        base = "🕘" if self.compact else "🕘 Historial"
        return f"{base} {n}" if n and self.compact else (f"{base} · {n}" if n else base)

    def _refresh_report_btn(self):
        from privacy import GRADE_COLOR
        r = self.last_report
        if r:
            text = f"📋 {r['grade']}" if self.compact else f"📋 Informe · {r['grade']}"
            self.report_btn.config(text=text, bg=GRADE_COLOR[r["grade"]], fg="#0b1220")
        else:
            self.report_btn.config(text="📋" if self.compact else "📋 Informe", bg=BTN, fg=FG)

    def _build_full(self):
        """Construye la barra completa según el tamaño elegido (grande o compacto)."""
        for c in self.full.winfo_children():
            c.destroy()
        self._btns = {}
        bar, cp = self.full, self.compact
        fs = 8 if cp else 9
        self.load_w, self.load_h = (COMPACT_LOAD_W, 20) if cp else (LOAD_W, 24)
        self.grip.config(font=("Segoe UI", fs, "bold"))

        self._btn(bar, "◂◂" if cp else "◂", self.step_down, key="collapse")
        self.power = self._btn(bar, self._power_text(bool(self.proxy.server)), self.toggle_proxy,
                               key="power")
        if self.proxy.server:
            self.power.config(bg="#2e8b57")
        # barra de carga: clic = desplegar/plegar el panel; ✂ = cortar todo al instante
        self.load_bar = tk.Canvas(bar, width=self.load_w, height=self.load_h, bg="#0f1a2b",
                                  highlightthickness=1, highlightbackground=BTN, cursor="hand2")
        self.load_bar.pack(side="left", padx=(3 if cp else 4, 0), pady=2 if cp else 4)
        self.load_bar.bind("<Button-1>", lambda e: self.toggle_panel())
        self.cut_btn = tk.Button(bar, text="✂", command=self.cut_loading, bg="#7a2a2a", fg="white",
                                 relief="flat", bd=0, font=("Segoe UI", 9 if cp else 10, "bold"),
                                 padx=5 if cp else 7, activebackground="#ff6b6b", cursor="hand2")
        self.cut_btn.pack(side="left", padx=(2, 3 if cp else 4), pady=2 if cp else 4)
        self.stats_lbl = tk.Label(bar, text=self._stats_text(), bg=BG, fg=FG, font=("Segoe UI", fs),
                                  width=5 if cp else 8)
        self.stats_lbl.pack(side="left")
        self._btn(bar, "📡" if cp else "📡 Tráfico", self.win_traffic, accent=True, key="traffic")
        self.traffic_led = tk.Canvas(bar, width=8, height=8, bg=BG, highlightthickness=0)
        self.traffic_led.pack(side="left", padx=(0, 3 if cp else 5))
        self._traffic_led_dot = self.traffic_led.create_oval(0, 0, 8, 8, fill=BG, outline="")
        tip(self.traffic_led, lambda: self.monitor_state()[1])
        self._update_traffic_led()
        self.report_btn = self._btn(bar, "📋" if cp else "📋 Informe", self.win_report, key="report")
        self.hist_btn = self._btn(bar, "🕘" if cp else "🕘 Historial", self.win_history, key="hist")
        tools = (("Estadísticas", "📊 Estadísticas", self.win_stats),
                 ("Filtros", "🛡 Filtros", self.win_filters),
                 ("Limpiar", "🧹 Limpiar", self.win_clean),
                 ("Mapa", "🗺 Mapa del sitio", self.win_sitemap),
                 ("Red", "📶 Ping / Traceroute", self.win_net),
                 ("Sitio", "ℹ Información del sitio", self.win_siteinfo))
        if cp:      # compacto: las seis herramientas caben en un solo menú
            self.tools_btn = tk.Menubutton(bar, text="🧰▾", bg=BTN, fg=FG, relief="flat", bd=0,
                                           font=("Segoe UI", fs), padx=6, cursor="hand2",
                                           activebackground=ACC, activeforeground="white")
            self.tools_btn.pack(side="left", padx=1, pady=2)
            m = tk.Menu(self.tools_btn, tearoff=0, bg=BG, fg=FG, activebackground=ACC,
                        activeforeground="white", font=("Segoe UI", 10),
                        postcommand=lambda: setattr(self, "_menu_until", time.time() + 8))
            for _short, label, cmd in tools:
                m.add_command(label=label, command=cmd)
            self.tools_btn.config(menu=m)
        else:
            for short, _label, cmd in tools:
                self._btn(bar, short, cmd)
        self._btn(bar, "❓" if cp else "❓ Ayuda", self.win_help, key="help")
        self._build_search(bar)
        self._refresh_report_btn()
        n = getattr(self, "_unseen", 0)
        self.hist_btn.config(text=self._hist_text(n), bg="#c9772b" if n else BTN)
        self._add_tips()

    # ---- tooltips
    def _add_static_tips(self):
        """Partes que no se reconstruyen al cambiar de tamaño: el asa y la píldora contraída."""
        tip(self.grip, "TrafficBar\nArrastra para mover la barra: se pega a los bordes de la pantalla.\n"
                       "Clic derecho: tamaño, anclar, contraer, ocultar.")
        tip(self.mini_dot, lambda: "Proxy ENCENDIDO" if self.proxy.server else "Proxy APAGADO")
        tip(self.mini_bar, "Estado de la carga de páginas.\nClic: expandir la barra.")
        tip(self.mini_badge, lambda: f"{self._unseen} alerta(s) nueva(s). Expande la barra y abre "
                                     "🕘 Historial.")
        tip(self.mini_exp, "Expandir la barra (tamaño grande)")

    def _add_tips(self):
        b = self._btns
        tip(b["collapse"], lambda: (
            "Paso 2 de 3: contraer del todo (píldora pequeña).\nUn clic en la píldora la vuelve a abrir "
            "en tamaño grande." if self.compact else
            "Paso 1 de 3: reducir la barra a tamaño mediano.\nOtro clic la contrae del todo; "
            "un tercero la abre de nuevo en grande."))
        tip(self.power, lambda: (
            "Proxy ENCENDIDO: TrafficBar filtra y analiza lo que cargan tus navegadores.\n"
            "Clic para apagarlo (Windows vuelve a su configuración anterior)."
            if self.proxy.server else
            "Proxy APAGADO.\nClic para encenderlo: TrafficBar se pone entre tus navegadores e Internet "
            "para bloquear anuncios, medir la carga de las páginas y generar informes.\n"
            "Cambia el proxy de Windows y lo restaura al apagar."))

        def load_tip():
            frac, active, total = LOADER.last
            if active:
                return (f"Cargando: {total - active} de {total} conexiones listas ({int(frac * 100)} %).\n"
                        "Clic: ver cada conexión en el panel.")
            if total:
                return f"Última carga: {total} conexiones completadas.\nClic: ver el detalle."
            return ("Aquí verás cómo cargan las páginas (necesita el ⏻ encendido).\n"
                    "Clic: abrir el panel de carga.")
        tip(self.load_bar, load_tip)
        tip(self.cut_btn, "Corta AHORA todas las conexiones en curso y rechaza las nuevas durante "
                          "4 s.\nSirve para frenar pop-ups o cargas en cadena.")
        tip(self.stats_lbl, lambda: f"{STATS.blocked} peticiones bloqueadas desde que abriste TrafficBar "
                                    f"(ahorro estimado: {saved_text()})." + (
            "\nÚltimos: " + ", ".join(STATS.recent_blocked[-3:]) if STATS.recent_blocked else ""))
        tip(b["help"], "Ayuda: qué es TrafficBar, cómo funciona, paso a paso y Acerca de.")
        tip(b["traffic"], "Monitor de red en vivo: quién habla con quién, cuánto y con qué "
                          "programa.\nRequiere Npcap y permisos de administrador.")

        def report_tip():
            r = self.last_report
            if not r:
                return ("Informe de privacidad de la última página cargada.\n"
                        "Aún no hay ninguno: enciende el ⏻ y navega.")
            return (f"Informe de la última página:\n{r['main']} · nota {r['grade']} ({r['score']}/100)\n"
                    f"{r['verdict']}\nClic para abrirlo.")
        tip(self.report_btn, report_tip)
        tip(self.hist_btn, lambda: (
            f"Historial y alertas: {self._unseen} nueva(s).\nClic para verlas." if self._unseen else
            "Historial y alertas.\nLínea de tiempo del tráfico, conexiones (¿qué se conectó "
            "anoche?), programas y páginas visitadas."))
        if self.compact:
            tip(self.tools_btn, "Herramientas: estadísticas, filtros, limpiar, mapa del sitio, "
                                "ping / traceroute e información de un sitio.")
        else:
            for txt, text in (
                    ("Estadísticas", "Contadores de la sesión: peticiones, bloqueos, datos descargados "
                                     "y últimos dominios bloqueados."),
                    ("Filtros", "Qué se bloquea: pop-ups, scripts, sonidos, parpadeo, fondos, cookies "
                                "y tu lista de dominios de publicidad."),
                    ("Limpiar", "Borra temporales y cachés del navegador (el historial es opcional).\n"
                                "Te pide confirmar antes."),
                    ("Mapa", "Lista los enlaces de una página web, separados en internos y externos."),
                    ("Red", "Ping y traceroute: comprueba si un sitio responde y por dónde pasa la "
                            "conexión."),
                    ("Sitio", "Información de un sitio: IP, DNS, título y cabeceras del servidor.")):
                tip(b[txt], text)
        tip(self.search_entry, "Escribe el tema y pulsa Enter: se abre en tu navegador con el "
                               "motor elegido.\nMayús+Enter: lo busca en todos los motores a la vez.")
        tip(self.eng_btn, lambda: f"Motor de búsqueda: {CFG['engines'][CFG['engine']]['name']}.\n"
                                  "Clic: cambiar de motor, buscar en todos o editar la lista (hasta 5).")
        tip(self.search_btn, "Buscar")

    # ---- barra contraíble: completa ⇄ «píldora»
    def _bind_drag(self, widget):
        def press(e):
            self._drag = (e.x_root - self.winfo_x(), e.y_root - self.winfo_y())
            self._moved = False

        def move(e):
            self._moved = True
            x, y = e.x_root - self._drag[0], e.y_root - self._drag[1]
            x, y, self._dock_pending = self._magnet(x, y)
            self.geometry(f"+{x}+{y}")

        def release(_e):
            if self._moved:
                CFG["bar_dock"] = self._dock_pending
                self._save_pos()
        widget.bind("<Button-1>", press)
        widget.bind("<B1-Motion>", move)
        widget.bind("<ButtonRelease-1>", release)
        widget.bind("<Button-3>", self._bar_menu)

    def _magnet(self, x, y):
        """Imán: si la barra queda a menos de MAGNET_PX de un borde del monitor donde está, se
        pega. Devuelve (x, y, ancla) con ancla "top", "bottom" o None."""
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        left, top, right, bottom = monitor_work_area(x + w // 2, y + h // 2)
        dock = None
        if CFG.get("bar_magnet", True):
            if abs(y - top) <= MAGNET_PX:
                y, dock = top, "top"
            elif abs(y + h - bottom) <= MAGNET_PX:
                y, dock = bottom - h, "bottom"
            if abs(x - left) <= MAGNET_PX:
                x = left
            elif abs(x + w - right) <= MAGNET_PX:
                x = right - w
            elif abs(x + w / 2 - (left + right) / 2) <= MAGNET_PX:
                x = int((left + right - w) // 2)
        return int(x), int(y), dock

    def dock_to(self, side):
        """Ancla la barra arriba/abajo del monitor donde está (o la suelta con None)."""
        CFG["bar_dock"] = side
        self._dock_pending = side
        self._clamp_on_screen()
        self._save_pos()

    def set_magnet(self):
        CFG["bar_magnet"] = bool(self.magnet_var.get())
        save_cfg(CFG)

    def toggle_size(self):
        self.set_bar_size("large" if self.compact else "compact")

    def _rebuild_ui(self):
        for c in self.mini.winfo_children():
            c.destroy()
        self._build_mini()
        self._build_full()
        self._add_static_tips()
        self.set_collapsed(self.collapsed, persist=False)

    def set_language(self, code):
        if not i18n.activar(code, _idiomas_dirs()):
            messagebox.showerror(APP, tr("No se pudo cargar ese idioma."), parent=self)
            i18n.activar("es", _idiomas_dirs())
            return
        CFG["lang"] = code
        save_cfg(CFG)
        self._rebuild_ui()
        messagebox.showinfo(APP, tr("Idioma cambiado. Las ventanas que ya están abiertas se "
                                    "actualizan al volver a abrirlas."), parent=self)

    def load_lang_pack(self):
        from tkinter import filedialog
        ruta = filedialog.askopenfilename(parent=self, title=tr("Elige un pack de idioma (.json)"),
                                          filetypes=[("Language pack", "*.json")])
        if not ruta:
            return
        pack, err = i18n.importar(ruta, os.path.join(DATA_DIR, "idiomas"))
        if not pack:
            messagebox.showerror(APP, err, parent=self)
            return
        if messagebox.askyesno(APP, f"Pack de idioma «{pack['name']}» instalado "
                                    f"({len(pack['strings'])} textos).\n\n¿Activarlo ahora?", parent=self):
            self.set_language(pack["code"])

    def export_lang_template(self):
        from tkinter import filedialog
        destino = filedialog.asksaveasfilename(parent=self, defaultextension=".json",
                                               initialfile="plantilla-idioma.json",
                                               title=tr("Guardar la plantilla de traducción"),
                                               filetypes=[("JSON", "*.json")])
        if destino:
            i18n.exportar_plantilla(_res(os.path.join("idiomas", "plantilla.json")), destino)
            messagebox.showinfo(APP, tr("Plantilla guardada. Traduce los textos de la derecha, cambia "
                                        "«code» y «name» en «meta» y cárgala con «Cargar un pack de idioma…»."),
                                parent=self)

    def set_ui_scale(self, s):
        """Cambia el tamaño de textos y ventanas. Las ventanas nuevas lo usan al abrirse."""
        self.ui_scale = s
        CFG["ui_scale"] = s
        save_cfg(CFG)
        self.tk.call("tk", "scaling", self.base_scaling * s)
        for c in self.mini.winfo_children():
            c.destroy()
        self._build_mini()
        self._build_full()
        self._add_static_tips()
        self.set_collapsed(self.collapsed, persist=False)

    def set_bar_size(self, size):
        """Cambia entre el tamaño grande y el compacto reconstruyendo la barra en caliente."""
        if size not in ("large", "compact"):
            return
        CFG["bar_size"] = size
        save_cfg(CFG)
        self._build_full()
        self.set_collapsed(self.collapsed, persist=False)   # recoloca, respeta el ancla y la pantalla

    # ---- ventanas junto a la barra
    def anchor_for(self, w, h, gap=4):
        """Posición (x, y) para una ventana de w×h pegada a la barra: debajo si la barra está en
        la mitad superior de su monitor, encima si está en la inferior. Siempre dentro del
        monitor de la barra (por eso sigue a la barra al cambiar de pantalla)."""
        bx, by = self.winfo_x(), self.winfo_y()
        bw, bh = self.winfo_reqwidth(), self.winfo_reqheight()
        left, top, right, bottom = monitor_work_area(bx + bw // 2, by + bh // 2)
        below, above = by + bh + gap, by - h - gap
        prefer_below = by + bh // 2 < (top + bottom) // 2
        options = [(below, below + h <= bottom), (above, above >= top)]
        if not prefer_below:
            options.reverse()
        y = next((yy for yy, fits in options if fits), below)
        y = max(top, min(y, bottom - h))
        x = max(left, min(bx + (bw - w) // 2, right - w))
        return int(x), int(y)

    def place_near(self, win, w, h):
        """Coloca una ventana normal (Tráfico, Historial, Informe...) junto a la barra."""
        left, top, right, bottom = monitor_work_area(self.winfo_x() + self.winfo_reqwidth() // 2,
                                                     self.winfo_y() + self.winfo_reqheight() // 2)
        s = self.ui_scale
        w, h = min(int(w * s), right - left - 20), min(int(h * s), bottom - top - 20)
        x, y = self.anchor_for(w, h)
        win.geometry(f"{w}x{h}+{x}+{y}")
        paint_soon(win)

    def _save_pos(self):
        m = re.match(r"\d+x\d+([+-]\d+)([+-]\d+)", self.geometry())
        CFG["bar_x"], CFG["bar_y"] = (int(m.group(1)), int(m.group(2))) if m else (
            self.winfo_x(), self.winfo_y())
        save_cfg(CFG)

    def _build_mini(self):
        m = self.mini
        self.mini_dot = tk.Label(m, text="⏻", bg=BG, fg="#6d84a3", font=("Segoe UI", 10, "bold"),
                                 cursor="hand2")
        self.mini_dot.pack(side="left", padx=(0, 4))
        self.mini_bar = tk.Canvas(m, width=MINI_W, height=12, bg="#0f1a2b", highlightthickness=0,
                                  cursor="hand2")
        self.mini_bar.pack(side="left", pady=6)
        self.mini_badge = tk.Label(m, text="", bg=BG, fg="#ffa94d", font=("Segoe UI", 9, "bold"),
                                   cursor="hand2")
        self.mini_badge.pack(side="left", padx=(4, 0))
        exp = self.mini_exp = tk.Label(m, text="▸", bg=BG, fg=ACC, font=("Segoe UI", 11, "bold"),
                                       cursor="hand2")
        exp.pack(side="left", padx=(6, 4))
        for w in (m, self.mini_dot, self.mini_bar, self.mini_badge, exp):
            w.bind("<Button-1>", lambda e: self.expand_full())
            w.bind("<Button-3>", self._bar_menu)

    def set_collapsed(self, flag, persist=True):
        self.collapsed = bool(flag)
        (self.full if self.collapsed else self.mini).pack_forget()
        (self.mini if self.collapsed else self.full).pack(side="left")
        self.grip.config(text="◉" if self.collapsed else "◉ TrafficBar")
        if persist:
            CFG["bar_collapsed"] = self.collapsed
            save_cfg(CFG)
        self._clamp_on_screen()

    def collapse(self):
        self.set_collapsed(True)

    def step_down(self):
        """Los tres estados de la barra: grande → mediano (compacto) → contraída → grande."""
        if self.collapsed:
            self.expand_full()
        elif not self.compact:
            self.set_bar_size("compact")
        else:
            self.collapse()

    def expand_full(self):
        self.set_bar_size("large")
        self.expand()

    def expand(self):
        self.set_collapsed(False)
        self._last_inside = time.time()

    def toggle_collapse(self):
        self.expand() if self.collapsed else self.collapse()

    def _clamp_on_screen(self):
        """Tras cambiar de tamaño: mantiene el ancla (arriba/abajo) y evita que la barra quede
        fuera del área útil del monitor donde está (multipantalla, sin invadir la barra de tareas)."""
        self.update_idletasks()
        m = re.match(r"\d+x\d+([+-]\d+)([+-]\d+)", self.geometry())
        if not m:
            return
        x, y = int(m.group(1)), int(m.group(2))
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        left, top, right, bottom = monitor_work_area(x + w // 2, y + h // 2)
        nx = min(max(x, left), max(left, right - w))
        ny = min(max(y, top), max(top, bottom - h))
        dock = CFG.get("bar_dock") if CFG.get("bar_magnet", True) else None
        if dock == "top":
            ny = top
        elif dock == "bottom":
            ny = bottom - h
        if (nx, ny) != (x, y):
            self.geometry(f"+{nx}+{ny}")

    def _pointer_inside(self):
        px, py = self.winfo_pointerxy()
        x, y = self.winfo_rootx(), self.winfo_rooty()
        return x - 6 <= px <= x + self.winfo_width() + 6 and y - 6 <= py <= y + self.winfo_height() + 6

    def _busy(self, now):
        """Cosas que impiden contraer sola la barra: un menú abierto, el panel de carga o estar
        escribiendo en el buscador."""
        if now < self._menu_until:
            return True
        if self.panel is not None and self.panel.winfo_exists():
            return True
        try:
            return self.focus_get() is self.search_entry and \
                self.search_var.get() not in ("", self.search_hint)
        except (KeyError, tk.TclError):
            return False

    def _autohide_tick(self):
        try:
            if CFG.get("bar_auto") and self.state() != "withdrawn":
                now = time.time()
                if self._pointer_inside():
                    self._last_inside = now
                    if self.collapsed:                      # el ratón llega: se abre
                        self.set_collapsed(False, persist=False)
                elif not self.collapsed and now - self._last_inside > 2.5 and not self._busy(now):
                    self.set_collapsed(True, persist=False)  # el ratón se va: se contrae
        except tk.TclError:
            return
        self.after(250, self._autohide_tick)

    def _update_mini(self, frac, active, total):
        if not self.collapsed:
            return
        c, w = self.mini_bar, MINI_W
        c.delete("all")
        if total:
            c.create_rectangle(0, 0, max(3, w * frac), 12, width=0,
                               fill=ACC if active else "#3fb97f")
        else:
            c.create_line(0, 6, w, 6, fill="#27405f")
        self.mini_dot.config(fg="#3fb97f" if self.proxy.server else "#6d84a3")
        self.mini_badge.config(text=f"🔔{self._unseen}" if self._unseen else "")

    def _bar_menu(self, event):
        m = tk.Menu(self, tearoff=0, bg=BG, fg=FG, activebackground=ACC, activeforeground="white",
                    font=("Segoe UI", 10))
        m.add_command(label="Expandir barra" if self.collapsed else "Contraer barra",
                      command=self.toggle_collapse)
        m.add_command(label="Tamaño: cambiar a " + ("grande" if self.compact else "compacto"),
                      command=self.toggle_size)
        self.magnet_var = tk.BooleanVar(value=bool(CFG.get("bar_magnet", True)))
        m.add_checkbutton(label="Imán en los bordes de la pantalla", variable=self.magnet_var,
                          command=self.set_magnet)
        m.add_command(label="Anclar arriba", command=lambda: self.dock_to("top"))
        m.add_command(label="Anclar abajo", command=lambda: self.dock_to("bottom"))
        if CFG.get("bar_dock"):
            m.add_command(label="Soltar (quitar el ancla)", command=lambda: self.dock_to(None))
        self.auto_var = tk.BooleanVar(value=bool(CFG.get("bar_auto")))
        m.add_checkbutton(label="Contraer sola al alejar el ratón", variable=self.auto_var,
                          command=self._set_auto)
        self.start_var = tk.BooleanVar(value=autostart_enabled())
        m.add_checkbutton(label="Iniciar con Windows (en la bandeja)", variable=self.start_var,
                          command=self.toggle_autostart,
                          state="normal" if autostart_command() else "disabled")
        sm = tk.Menu(m, tearoff=0, bg=BG, fg=FG, activebackground=ACC, activeforeground="white",
                     font=("Segoe UI", 10))
        self.scale_var = tk.DoubleVar(value=self.ui_scale)
        for label, val in (("Normal (100 %)", 1.0), ("Pequeño (85 %)", 0.85),
                           ("Muy pequeño (75 %)", 0.75)):
            sm.add_radiobutton(label=label, variable=self.scale_var, value=val,
                               command=lambda v=val: self.set_ui_scale(v))
        m.add_cascade(label="Tamaño de textos y ventanas", menu=sm)
        lm = tk.Menu(m, tearoff=0, bg=BG, fg=FG, activebackground=ACC, activeforeground="white",
                     font=("Segoe UI", 10))
        self.lang_var = tk.StringVar(value=i18n.idioma())
        lm.add_radiobutton(label="Español (original)", variable=self.lang_var, value="es",
                           command=lambda: self.set_language("es"))
        for code, info in sorted(i18n.paquetes(_idiomas_dirs()).items()):
            lm.add_radiobutton(label=f"{info['name']} ({code})", variable=self.lang_var, value=code,
                               command=lambda c=code: self.set_language(c))
        lm.add_separator()
        lm.add_command(label="Cargar un pack de idioma…", command=self.load_lang_pack)
        lm.add_command(label="Exportar la plantilla para traducir…", command=self.export_lang_template)
        m.add_cascade(label="🌐 Idioma / Language", menu=lm)
        m.add_separator()
        m.add_command(label="📅 Cuota mensual de datos…", command=self.win_quota)
        m.add_command(label="🚫 Programas bloqueados…", command=self.win_blocked)
        m.add_command(label="🛍 Compatibilidad con apps de la Tienda…", command=self.win_tienda)
        m.add_separator()
        m.add_command(label="❓ Ayuda", command=self.win_help)
        m.add_command(label="Acerca de TrafficBar", command=lambda: self.win_help("Acerca de"))
        m.add_separator()
        m.add_command(label="Ocultar en la bandeja del sistema", command=self.hide_bar)
        self._menu_until = time.time() + 8
        try:
            m.tk_popup(event.x_root, event.y_root)
        finally:
            m.grab_release()

    def toggle_autostart(self):
        want = not autostart_enabled()
        if not set_autostart(want):
            messagebox.showinfo(APP, "El inicio con Windows solo está disponible en la versión "
                                "instalada (no en la portable, que no deja rastro en el PC).",
                                parent=self)

    def _set_auto(self):
        CFG["bar_auto"] = bool(self.auto_var.get())
        save_cfg(CFG)

    def tick(self):
        self.stats_lbl.config(text=self._stats_text())
        self._update_traffic_led()
        self._tick_n = getattr(self, "_tick_n", 0) + 1
        if self._tick_n % 60 == 0 and STATS.pot_conns >= 20:     # aprende el peso medio MEDIDO
            avg = STATS.pot_bytes / STATS.pot_conns
            old = CFG.get("ad_bytes_per_conn")
            new = round(avg if not old else (old + avg) / 2)
            if new != old:
                CFG["ad_bytes_per_conn"] = new
                save_cfg(CFG)
        if self.tray:
            self.tray.set_tooltip(f"TrafficBar · proxy {'ON' if self.proxy.server else 'OFF'} · "
                                  f"{STATS.blocked} bloqueados"
                                  + (f" · {self._unseen} alertas nuevas" if self._unseen else ""))
        self.after(1000, self.tick)

    def draw_progress(self):
        c, now = self.load_bar, time.time()
        c.delete("all")
        w, h = self.load_w, self.load_h
        frac, active, total = LOADER.poll()
        if now < self.cut_msg_until:
            c.create_rectangle(0, 0, w, h, fill="#7a2a2a", width=0)
            c.create_text(w / 2, h / 2, text="✂ carga cortada", fill="white",
                          font=("Segoe UI", 9, "bold"))
        elif total:
            c.create_rectangle(0, 0, max(6, w * frac), h, fill=ACC if active else "#3fb97f", width=0)
            if active:  # franja que recorre la barra: la carga sigue viva
                seg = 36
                pos = ((now * 1.3) % 1.0) * (w + seg) - seg
                c.create_rectangle(max(0, pos), 0, min(w * max(frac, 0.05), pos + seg), h,
                                   fill="#8fd0ff", width=0)
            if self.compact:
                label = f"{int(frac * 100)} % · {total - active}/{total}" if active else f"listo · {total}"
            else:
                label = (f"cargando {total - active}/{total} · {int(frac * 100)} %" if active
                         else f"listo · {total} recursos")
            c.create_text(w / 2, h / 2, text=label, fill="white",
                          font=("Segoe UI", 8 if self.compact else 9, "bold"))
        else:
            c.create_text(w / 2, h / 2, fill="#6d84a3", font=("Segoe UI", 8),
                          text="▾ carga: reposo" if self.compact else "▾ carga de sitios: en reposo")

        self._update_mini(frac, active, total)

        # al terminar una carga de cierto tamaño se genera su informe de privacidad
        if self._was_loading and not active and total >= 4:
            self.after(1500, self._make_report)
        self._was_loading = bool(active)

        # panel: se despliega solo al empezar una carga grande y se pliega al terminar
        open_ = self.panel is not None and self.panel.winfo_exists()
        if not open_ and self.panel is not None:      # lo cerró el usuario desde el panel
            self.panel_block_until = now + 20
            self.panel = None
        if CFG.get("auto_panel", True):
            if not open_ and (active >= 3 or total >= 5) and active and \
                    now > self.panel_block_until and self.winfo_viewable():
                self.open_panel(auto=True)
            elif open_ and self.panel.auto and not self.panel.pinned and not active \
                    and LOADER.idle_for() > 4:
                self.panel.destroy()
                self.panel = None
        self.after(100, self.draw_progress)

    def open_panel(self, auto=False):
        from load_panel import LoadPanel
        self.panel = LoadPanel(self, LOADER, is_blocked_host, self.cut_loading, self._panel_setting,
                               lambda: self.last_report, self.win_report)
        self.panel.auto = auto

    # ---- informe de privacidad
    def _make_report(self):
        if LOADER.last[1]:            # volvió a haber actividad: la carga no había terminado
            return
        from privacy import build_report, GRADE_COLOR
        rep = build_report(LOADER.rows(), is_blocked_host)
        if not rep or rep["n_hosts"] < 3:
            return
        self.last_report = rep
        self.reports.append(rep)
        try:
            HIST.add_report(rep)
        except Exception:
            pass                        # el historial nunca debe romper la carga
        self._refresh_report_btn()

    def win_report(self):
        if not self.last_report:
            messagebox.showinfo(APP, "Aún no hay informe.\n\nEnciende el ⏻ y abre una página: "
                                "al terminar de cargar aparecerá aquí su informe de privacidad.",
                                parent=self)
            return
        from report_view import ReportWindow
        ReportWindow(self, self.last_report, self.add_block, is_blocked_host, self.add_allow)

    def add_block(self, host):
        """Añade el dominio (registrable) a tu lista de bloqueo. True si era nuevo."""
        from privacy import base_domain
        dom = base_domain(host).lower()
        if not dom or dom in BLOCKLIST:
            return False
        BLOCKLIST.add(dom)
        ALLOWLIST.discard(dom)
        with open(BLOCK_FILE, "a", encoding="utf-8") as f:
            f.write(dom + "\n")
        rebuild_blocklists()
        return True

    def add_allow(self, host):
        """Añade el sitio a tus excepciones (nunca se bloquea). True si era nuevo."""
        from privacy import base_domain
        dom = base_domain(host).lower()
        if not dom or dom in ALLOWLIST or not valid_host(dom):
            return False
        ALLOWLIST.add(dom)
        with open(ALLOW_FILE, "a", encoding="utf-8") as f:
            f.write(dom + "\n")
        rebuild_blocklists()
        return True

    # ---- integración con Windows: botón en la barra de tareas e icono
    def _resource(self, name):
        base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base, name)

    def _set_icon(self):
        try:
            self.iconbitmap(default=self._resource("trafficbar.ico"))
        except tk.TclError:
            pass

    def _emergency_restore(self):
        """Si el proceso termina sin pasar por quit_app, no dejar el proxy del sistema roto."""
        try:
            if self.proxy.server:
                self._restore_proxy()
        except Exception:
            pass

    def toggle_panel(self):
        if self.panel is not None and self.panel.winfo_exists():
            self.panel.destroy()
            self.panel = None
            self.panel_block_until = time.time() + 20
        else:
            self.open_panel(auto=False)

    def _panel_setting(self, what):
        if what == "toggle":
            CFG["auto_panel"] = not CFG.get("auto_panel", True)
            save_cfg(CFG)
        return CFG.get("auto_panel", True)

    def cut_loading(self):
        LOADER.cut()
        self.cut_msg_until = time.time() + 1.5

    # ---- buscador con hasta 5 motores
    def _build_search(self, bar):
        box = tk.Frame(bar, bg="#0f1a2b", highlightbackground=BTN, highlightthickness=1)
        box.pack(side="left", padx=(6 if self.compact else 8, 2), pady=2 if self.compact else 4)
        cp = self.compact
        self.search_hint = tr("Buscar…" if cp else "Buscar en la web…")
        if not hasattr(self, "search_var"):          # se conserva lo escrito al cambiar de tamaño
            self.search_var = tk.StringVar(value=self.search_hint)
        elif self.search_var.get() in ("Buscar…", "Buscar en la web…"):
            self.search_var.set(self.search_hint)    # solo el texto de ayuda cambia de un tamaño a otro
        self.search_entry = tk.Entry(box, textvariable=self.search_var, width=14 if cp else 22,
                                     bg="#0f1a2b", insertbackground=FG, relief="flat",
                                     fg="#6d84a3" if self.search_var.get() == self.search_hint else FG,
                                     font=("Segoe UI", 9 if cp else 10))
        self.search_entry.pack(side="left", padx=(6, 0), ipady=2)
        self.search_entry.bind("<Button-1>", lambda e: (self.focus_force(), self.search_entry.focus_set()))
        self.search_entry.bind("<FocusIn>", self._search_focus_in)
        self.search_entry.bind("<FocusOut>", self._search_focus_out)
        self.search_entry.bind("<Return>", lambda e: self.do_search())
        self.search_entry.bind("<Shift-Return>", lambda e: self.do_search(all_engines=True))
        self.eng_var = tk.IntVar(value=CFG["engine"])
        self.eng_btn = tk.Menubutton(box, text="", bg=BTN, fg=FG, relief="flat", bd=0,
                                     font=("Segoe UI", 8 if cp else 9, "bold"), padx=5 if cp else 8,
                                     cursor="hand2", activebackground=ACC, activeforeground="white")
        self.eng_btn.pack(side="left", fill="y")
        self.search_btn = tk.Button(box, text="🔎", command=self.do_search, bg=ACC, fg="white",
                                    relief="flat", bd=0, padx=8, cursor="hand2",
                                    activebackground="#5cb8ff")
        self.search_btn.pack(side="left", fill="y")
        self._build_engine_menu()

    def _search_focus_in(self, _e=None):
        if self.search_var.get() == self.search_hint:
            self.search_var.set("")
            self.search_entry.config(fg=FG)

    def _search_focus_out(self, _e=None):
        if not self.search_var.get().strip():
            self.search_var.set(self.search_hint)
            self.search_entry.config(fg="#6d84a3")

    def _build_engine_menu(self):
        engines = CFG["engines"]
        self.eng_btn.config(text=engines[CFG["engine"]]["name"] + " ▾")
        m = tk.Menu(self.eng_btn, tearoff=0, bg=BG, fg=FG, activebackground=ACC,
                    activeforeground="white", font=("Segoe UI", 10),
                    postcommand=lambda: setattr(self, "_menu_until", time.time() + 8))
        self.eng_var.set(CFG["engine"])
        for i, e in enumerate(engines):
            m.add_radiobutton(label=e["name"], variable=self.eng_var, value=i,
                              command=self._pick_engine)
        m.add_separator()
        if len(engines) > 1:
            m.add_command(label="🔍  Buscar en todos a la vez  (Mayús+Enter)",
                          command=lambda: self.do_search(all_engines=True))
        m.add_command(label="✏  Editar motores…", command=self.win_engines)
        self.eng_btn.config(menu=m)

    def _pick_engine(self):
        CFG["engine"] = self.eng_var.get()
        save_cfg(CFG)
        self._build_engine_menu()
        self.search_entry.focus_set()

    def do_search(self, all_engines=False):
        q = self.search_var.get().strip()
        if not q or q == self.search_hint:
            self.search_entry.focus_set()
            return
        engines = CFG["engines"] if all_engines else [CFG["engines"][CFG["engine"]]]
        for e in engines:
            webbrowser.open_new_tab(e["url"].replace("{q}", urllib.parse.quote_plus(q)))

    def win_engines(self):
        t = self._win("Motores de búsqueda", 700, 330)
        tk.Label(t, text=f"Hasta {MAX_ENGINES} motores. Usa {{q}} donde va lo que buscas. "
                         "Deja una fila vacía para quitarla.", bg=BG, fg=FG, anchor="w",
                 wraplength=660, justify="left").pack(fill="x", padx=12, pady=(12, 6))
        grid = tk.Frame(t, bg=BG)
        grid.pack(fill="x", padx=12)
        rows = []
        engines = CFG["engines"] + [{"name": "", "url": ""}] * (MAX_ENGINES - len(CFG["engines"]))
        for i, e in enumerate(engines[:MAX_ENGINES]):
            n = tk.Entry(grid, width=14, bg="#0f1a2b", fg=FG, insertbackground=FG, relief="flat")
            u = tk.Entry(grid, width=64, bg="#0f1a2b", fg=FG, insertbackground=FG, relief="flat")
            n.insert(0, e["name"])
            u.insert(0, e["url"])
            n.grid(row=i, column=0, padx=(0, 8), pady=4, ipady=3)
            u.grid(row=i, column=1, pady=4, ipady=3)
            rows.append((n, u))
        msg = tk.Label(t, text="", bg=BG, fg="#ff9f43", anchor="w")
        msg.pack(fill="x", padx=12, pady=4)

        def save():
            found = [{"name": n.get().strip(), "url": u.get().strip()} for n, u in rows
                     if n.get().strip() or u.get().strip()]
            for e in found:
                if not e["name"] or not e["url"].lower().startswith(("http://", "https://")) \
                        or "{q}" not in e["url"]:
                    msg.config(text=f"«{e['name'] or '?'}»: necesita nombre y una URL http(s) "
                                    "que contenga {q}")
                    return
            if not found:
                msg.config(text="Debe quedar al menos un motor.")
                return
            CFG["engines"] = clean_engines(found)
            CFG["engine"] = min(CFG["engine"], len(CFG["engines"]) - 1)
            save_cfg(CFG)
            self._build_engine_menu()
            t.destroy()

        def restore():
            CFG["engines"] = copy.deepcopy(DEFAULT_ENGINES)
            CFG["engine"] = 0
            save_cfg(CFG)
            self._build_engine_menu()
            t.destroy()
        row = tk.Frame(t, bg=BG)
        row.pack(pady=6)
        tk.Button(row, text="Guardar", command=save, bg=ACC, fg="white", relief="flat",
                  padx=16).pack(side="left", padx=4)
        tk.Button(row, text="Restaurar por defecto", command=restore, bg=BTN, fg=FG,
                  relief="flat", padx=12).pack(side="left", padx=4)

    def toggle_proxy(self):
        global PROXY_PORT
        if self.proxy.server:
            self.proxy.stop()
            self._restore_proxy()
            _clear_state()
            self.power.config(text=self._power_text(False), bg=BTN)
            return
        try:
            PROXY_PORT = self.proxy.start()
        except OSError as e:
            messagebox.showerror(APP, f"No se pudo iniciar el proxy local:\n{e}")
            return
        cur = get_system_proxy()
        if cur and not is_our_proxy(cur[1]):
            self.prev_proxy = cur         # lo que había antes: es lo que se restaura al apagar
        _write_state(PROXY_PORT)
        set_system_proxy(True)
        self.power.config(text=self._power_text(True), bg="#2e8b57")
        self.after(1500, self._store_hint)

    def _restore_proxy(self):
        if not winreg:
            return
        enable, server = self.prev_proxy or (0, None)
        if enable and server and not is_our_proxy(server):
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, INET_KEY, 0,
                                winreg.KEY_SET_VALUE) as k:
                winreg.SetValueEx(k, "ProxyEnable", 0, winreg.REG_DWORD, 1)
                winreg.SetValueEx(k, "ProxyServer", 0, winreg.REG_SZ, server)
            _refresh_inet()
        else:
            set_system_proxy(False)

    def quit_app(self):
        """Salida real (solo desde el menú del icono): apaga todo y restaura el proxy de Windows."""
        self._show_evt_stop = True
        try:
            self.watcher.stop()
            if self.bg_engine:
                self.bg_engine.stop()
            if self.tray:
                self.tray.stop()
        except Exception:
            pass
        if self.proxy.server:
            self.proxy.stop()
            self._restore_proxy()
            _clear_state()
        release_single_instance()
        self.destroy()

    # ---- monitor de tráfico
    def win_traffic(self):
        if getattr(self, "traffic", None) and self.traffic.winfo_exists():
            self.traffic.lift()
            return
        if not os.path.isdir(r"C:\Windows\System32\Npcap"):
            if messagebox.askyesno(APP, "El monitor de tráfico necesita Npcap (el mismo "
                                   "motor de captura que usa Wireshark).\n\n¿Abrir la página "
                                   "de descarga (npcap.com)?", parent=self):
                webbrowser.open("https://npcap.com/#download")
            return
        if not ctypes.windll.shell32.IsUserAnAdmin():
            exe_dir = os.path.dirname(os.path.abspath(
                sys.executable if getattr(sys, "frozen", False) else __file__))
            warn = "" if in_protected_folder(exe_dir) else (
                "\n\n⚠ TrafficBar está en una carpeta que cualquier programa de tu usuario puede "
                "modificar. Como administrador eso es un riesgo: si algo cambiara estos archivos, "
                "se ejecutarían con permisos elevados. Lo seguro es instalarlo en «Archivos de "
                "programa» (ejecuta Instalar-TrafficBar.ps1).")
            if not messagebox.askyesno(APP, "Capturar todo el tráfico requiere permisos de "
                                       "administrador.\n\n¿Reiniciar TrafficBar como "
                                       "administrador?" + warn, parent=self):
                return
            if getattr(sys, "frozen", False):
                exe, args = sys.executable, "--traffic"
            else:
                exe, args = sys.executable, f'"{os.path.abspath(__file__)}" --traffic'
            release_single_instance()     # la copia nueva (administrador) debe poder arrancar
            if ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, args, None, 1) > 32:
                self.quit_app()
            else:
                acquire_single_instance()
            return
        try:
            from traffic_monitor import TrafficWindow
        except ImportError as e:
            messagebox.showerror(APP, f"Falta un componente: {e}\n\nInstala psutil.",
                                 parent=self)
            return
        self.traffic = TrafficWindow(self, is_blocked_host, engine=self.bg_engine)

    # ---- ventanas
    def _win(self, title, w=520, h=380):
        t = tk.Toplevel(self, bg=BG)
        t.title(f"{APP} – {tr(title)}")
        t.attributes("-topmost", True)
        self.place_near(t, w, h)
        return t

    def _text(self, parent, **kw):
        s = scrolledtext.ScrolledText(parent, bg="#0f1a2b", fg=FG, insertbackground=FG,
                                      font=("Consolas", 9), relief="flat", **kw)
        s.pack(fill="both", expand=True, padx=8, pady=8)
        return s

    def win_quota(self):
        w = getattr(self, "_quota", None)
        if w is not None and w.winfo_exists():
            w.lift()
            return
        self._quota = cuota.QuotaWindow(self, HIST, CFG, save_cfg)

    def win_tienda(self):
        w = getattr(self, "_tienda", None)
        if w is not None and w.winfo_exists():
            w.lift()
            return
        self._tienda = tienda.VentanaTienda(self)

    def _store_hint(self):
        """Una sola vez, sin ventana emergente: avisa de que las apps de la Tienda no pasan por el proxy."""
        if CFG.get("store_hint"):
            return
        CFG["store_hint"] = True
        save_cfg(CFG)
        self._notify("Apps de la Tienda de Windows",
                     "Con el proxy encendido, WhatsApp o la Microsoft Store pueden no conectarse. Solución: clic "
                     "derecho en la barra → «Compatibilidad con apps de la Tienda…».")

    def win_blocked(self):
        w = getattr(self, "_blocked", None)
        if w is not None and w.winfo_exists():
            w.refresh()
            w.lift()
            return
        self._blocked = programas.VentanaBloqueados(self)

    def win_help(self, tab="Introducción"):
        w = getattr(self, "_help", None)
        if w is not None and w.winfo_exists():
            w.show(tab if isinstance(tab, str) else "Introducción")
            w.deiconify()
            w.lift()
            return
        self._help = ayuda.HelpWindow(self, tab if isinstance(tab, str) else "Introducción",
                                      CFG, save_cfg, DATA_DIR)

    def show_intro(self):
        """Animación de 3 s al abrir TrafficBar (no en el arranque silencioso con Windows)."""
        if CFG.get("intro", True) and "--segundo-plano" not in sys.argv \
                and "--traffic" not in sys.argv and self.state() != "withdrawn":
            try:
                ayuda.Splash(self)
            except tk.TclError:
                pass

    def win_stats(self):
        t = self._win("Estadísticas", 420, 360)
        tk.Button(t, text="📅 Cuota mensual de datos…", command=self.win_quota, bg=BTN, fg=FG,
                  relief="flat", cursor="hand2", padx=10).pack(anchor="w", padx=8, pady=(8, 0))
        box = self._text(t)

        def refresh():
            if not t.winfo_exists():
                return
            box.delete("1.0", "end")
            medido = ""
            if STATS.pot_conns:
                medido = (f"Medido (solo medir / listas apagadas):\n  {STATS.pot_conns} conexiones a "
                          f"publicidad y rastreo = {human(STATS.pot_bytes)} de {human(STATS.conn_bytes)} "
                          f"({100 * STATS.pot_bytes / max(STATS.conn_bytes, 1):.1f} %)\n")
            box.insert("end", (
                f"Proxy:            {'ACTIVO' if self.proxy.server else 'apagado'}\n"
                f"Peticiones:       {STATS.requests}\n"
                f"Bloqueadas:       {STATS.blocked}\n"
                f"Ahorro estimado:  {saved_text()}\n"
                f"{medido}"
                f"Páginas filtradas:{STATS.filtered}\n"
                f"Descargado:       {human(STATS.bytes_down)}\n"
                f"Enviado:          {human(STATS.bytes_up)}\n\n"
                "Últimos dominios bloqueados:\n  " + "\n  ".join(STATS.recent_blocked[-15:][::-1])))
            t.after(1000, refresh)
        refresh()

    def _lists_status(self, key):
        m = blocklists.meta(LISTS_DIR).get(key)
        if not m:
            return "sin descargar"
        return f"{m['n']:,} dominios · {time.strftime('%d/%m/%Y', time.localtime(m['fecha']))}".replace(",", ".")

    def update_lists(self, on_done=None):
        """Descarga las listas activadas (en segundo plano) y las aplica."""
        keys = [k for k in blocklists.SOURCES if CFG.get("list_" + k)]

        def work():
            res = []
            for k in keys:
                try:
                    res.append((k, blocklists.descargar(k, LISTS_DIR), None))
                except Exception as e:                      # red, tamaño, formato...
                    res.append((k, 0, str(e)[:160]))
            reload_lists()
            if on_done:
                self._acts.put(lambda: on_done(res))     # la interfaz lo ejecuta en su hilo
        threading.Thread(target=work, daemon=True).start()

    def _auto_lists(self):
        for k in blocklists.SOURCES:
            if CFG.get("list_" + k) and blocklists.desactualizada(LISTS_DIR, k):
                try:
                    blocklists.descargar(k, LISTS_DIR)
                except Exception:
                    pass
        reload_lists()

    def win_filters(self):
        global BLOCKLIST, ALLOWLIST
        t = self._win("Filtros", 600, 800)
        labels = [("block_domains", "Bloquear dominios de publicidad/rastreo (HTTP+HTTPS)"),
                  ("block_popups", "Bloquear pop-ups (window.open)*"),
                  ("block_scripts", "Eliminar scripts*"),
                  ("block_sound", "Bloquear sonidos y objetos incrustados*"),
                  ("block_blink", "Quitar texto parpadeante/animaciones*"),
                  ("block_background", "Quitar fondos*"),
                  ("block_cookies", "Bloquear cookies*"),
                  ("measure_only", "Solo medir (NO bloquea): calcula cuántos datos ahorrarías con las listas")]
        vars_ = {}
        for key, text in labels:
            v = tk.BooleanVar(value=CFG[key])
            vars_[key] = v
            tk.Checkbutton(t, text=text, variable=v, bg=BG, fg=FG, selectcolor=BTN,
                           activebackground=BG, activeforeground=FG,
                           anchor="w").pack(fill="x", padx=10)
        tk.Label(t, text="* Solo en páginas HTTP. El contenido HTTPS va cifrado: ahí se "
                 "filtra únicamente por dominio.", bg=BG, fg="#9fb3cc", wraplength=560,
                 justify="left").pack(padx=10, pady=4)

        # ---- listas de bloqueo
        lf = tk.LabelFrame(t, text=" Listas de bloqueo ",
                           bg=BG, fg=FG, padx=8, pady=6)
        lf.pack(fill="x", padx=10, pady=4)
        lvars, status = {}, {}
        rows = [("lists_builtin", f"Incluida en TrafficBar: publicidad y analítica ({len(blocklists.builtin_domains())} dominios)", None)]
        rows += [("list_" + k, f"{tr(v['nombre'])}  ({tr(v['aprox'])})", k) for k, v in blocklists.SOURCES.items()]
        for cfgkey, text, src in rows:
            r = tk.Frame(lf, bg=BG)
            r.pack(fill="x")
            lvars[cfgkey] = tk.BooleanVar(value=CFG.get(cfgkey, False))
            tk.Checkbutton(r, text=text, variable=lvars[cfgkey], bg=BG, fg=FG, selectcolor=BTN,
                           activebackground=BG, activeforeground=FG, anchor="w").pack(side="left")
            if src:
                status[src] = tk.Label(r, text=self._lists_status(src), bg=BG, fg="#8ea3bd",
                                       font=("Segoe UI", 8))
                status[src].pack(side="right")
        auto_var = tk.BooleanVar(value=CFG.get("lists_auto", False))
        tk.Checkbutton(lf, text="Actualizar solas cada semana (se conecta a los sitios de las listas)",
                       variable=auto_var, bg=BG, fg=FG, selectcolor=BTN, activebackground=BG,
                       activeforeground=FG, anchor="w").pack(fill="x")
        tk.Label(lf, text="Bloquear publicidad mejora la privacidad y reduce conexiones, pero el ahorro "
                 "de datos suele ser pequeño (el peso está sobre todo en imágenes y vídeo de la "
                 "propia página). Activa «Solo medir» unos días para ver cuánto ahorrarías TÚ.",
                 bg=BG, fg="#8ea3bd", anchor="w", wraplength=540, justify="left",
                 font=("Segoe UI", 8)).pack(fill="x", pady=(4, 0))
        msg = tk.Label(lf, text="", bg=BG, fg="#ffd166", anchor="w", wraplength=540, justify="left")

        def apply_cfg():
            for k, v in vars_.items():
                CFG[k] = v.get()
            for k, v in lvars.items():
                CFG[k] = v.get()
            CFG["lists_auto"] = auto_var.get()
            save_cfg(CFG)

        def done(res):
            for k, n_, err in res:
                if k in status and status[k].winfo_exists():
                    status[k].config(text=(f"⚠ {err}" if err else self._lists_status(k)),
                                     fg="#ff9f43" if err else "#7fd6a6")
            if btn.winfo_exists():
                btn.config(state="normal", text="⟳ Actualizar listas ahora")
                msg.config(text="Listas aplicadas. Surten efecto en las próximas cargas.")

        def update():
            apply_cfg()
            btn.config(state="disabled", text="Descargando…")
            msg.config(text="")
            self.update_lists(done)
        btn = tk.Button(lf, text="⟳ Actualizar listas ahora", command=update, bg=ACC, fg="white",
                        relief="flat", padx=12)
        btn.pack(anchor="w", pady=(4, 2))
        msg.pack(fill="x")
        tip(btn, "Descarga las listas marcadas de sus sitios oficiales por HTTPS. Solo se guardan "
                 "nombres de dominio validados; una respuesta rara se descarta.")
        if not any(blocklists.meta(LISTS_DIR).get(k) for k in blocklists.SOURCES):
            msg.config(text="Aún no has descargado ninguna lista: pulsa «Actualizar» para bloquear "
                            "muchos más anuncios y rastreadores.")

        # ---- lista personal y excepciones
        tk.Label(t, text="Tu lista personal (un dominio por línea):", bg=BG, fg=FG).pack(anchor="w", padx=10)
        box = self._text(t, height=6)
        box.insert("end", "\n".join(sorted(BLOCKLIST)))
        tk.Label(t, text="Excepciones: estos sitios NUNCA se bloquean (útil si una página se rompe):",
                 bg=BG, fg=FG).pack(anchor="w", padx=10)
        abox = self._text(t, height=4)
        abox.insert("end", "\n".join(sorted(ALLOWLIST)))

        def save():
            global BLOCKLIST, ALLOWLIST
            apply_cfg()
            lines = [l.strip().lower() for l in box.get("1.0", "end").splitlines() if l.strip()]
            allow = [l.strip().lower() for l in abox.get("1.0", "end").splitlines() if l.strip()]
            with open(BLOCK_FILE, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
            with open(ALLOW_FILE, "w", encoding="utf-8") as f:
                f.write("\n".join(allow) + "\n")
            BLOCKLIST = set(lines)
            ALLOWLIST = {a for a in allow if valid_host(a)}
            reload_lists()
            t.destroy()
        tk.Button(t, text="Guardar", command=save, bg=ACC, fg="white", relief="flat",
                  padx=14).pack(pady=(0, 8))

    def win_clean(self):
        targets = clean_targets()
        if not targets:
            messagebox.showinfo(APP, "No hay nada que limpiar.", parent=self)
            return
        t = self._win("Limpiar", 460, 420)
        tk.Label(t, text="Marca lo que quieres borrar (cierra antes el navegador):",
                 bg=BG, fg=FG).pack(anchor="w", padx=10, pady=6)
        checks = []
        for desc, path, isdir in targets:
            v = tk.BooleanVar(value="historial" not in desc)  # el historial, opt-in
            checks.append((v, path, isdir))
            tk.Checkbutton(t, text=desc, variable=v, bg=BG, fg=FG, selectcolor=BTN,
                           activebackground=BG, activeforeground=FG,
                           anchor="w").pack(fill="x", padx=10)

        def go():
            sel = [(p, d) for v, p, d in checks if v.get()]
            if not sel or not messagebox.askyesno(APP, "¿Borrar lo seleccionado? "
                                                  "No se puede deshacer.", parent=t):
                return
            freed = sum(remove_path(p, d) for p, d in sel)
            messagebox.showinfo(APP, f"Liberado: {human(freed)}", parent=t)
            t.destroy()
        tk.Button(t, text="Limpiar", command=go, bg=ACC, fg="white", relief="flat",
                  padx=14).pack(pady=10)

    def win_sitemap(self):
        t = self._win("Mapa del sitio", 620, 460)
        row = tk.Frame(t, bg=BG)
        row.pack(fill="x", padx=8, pady=6)
        ent = tk.Entry(row)
        ent.pack(side="left", fill="x", expand=True)
        box = self._text(t)

        def work(url):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=15) as resp:    # nosec B310: solo http(s)
                    html = resp.read(3_000_000).decode("utf-8", "replace")
                links = re.findall(r'(?i)<a\b[^>]{0,500}?href\s*=\s*["\']([^"\'#][^"\']{0,2000})["\']', html)
                seen, out = set(), []
                for l in links:
                    full = urllib.parse.urljoin(url, l.strip())
                    if full.startswith("http") and full not in seen:
                        seen.add(full)
                        out.append(full)
                own = urllib.parse.urlsplit(url).netloc
                internal = [l for l in out if urllib.parse.urlsplit(l).netloc == own]
                external = [l for l in out if l not in internal]
                text = (f"{len(out)} enlaces\n\n── Internos ({len(internal)}) ──\n"
                        + "\n".join(internal) + f"\n\n── Externos ({len(external)}) ──\n"
                        + "\n".join(external))
            except Exception as e:
                text = f"Error: {e}"
            self.after(0, lambda: (box.delete("1.0", "end"), box.insert("end", text)))

        def go():
            box.delete("1.0", "end")
            try:
                url = normalize_url(ent.get())
            except ValueError as e:
                box.insert("end", str(e))
                return
            box.insert("end", "Cargando…")
            threading.Thread(target=work, args=(url,), daemon=True).start()
        ent.bind("<Return>", lambda e: go())
        tk.Button(row, text="Mapear", command=go, bg=ACC, fg="white", relief="flat").pack(
            side="left", padx=6)

    def _run_stream(self, box, cmd):
        def work():
            try:
                p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,   # nosec B603
                                     creationflags=0x08000000)
                for line in iter(p.stdout.readline, b""):
                    txt = line.decode("cp850", "replace")
                    self.after(0, lambda t=txt: (box.insert("end", t), box.see("end")))
            except OSError as e:
                self.after(0, lambda: box.insert("end", f"Error: {e}"))
        box.delete("1.0", "end")
        threading.Thread(target=work, daemon=True).start()

    def win_net(self):
        t = self._win("Ping / Traceroute", 620, 460)
        row = tk.Frame(t, bg=BG)
        row.pack(fill="x", padx=8, pady=6)
        ent = tk.Entry(row)
        ent.pack(side="left", fill="x", expand=True)
        box = self._text(t)

        def host():
            h = ent.get().strip()
            h = urllib.parse.urlsplit(h).hostname if "://" in h else h
            return valid_host(h)          # sin «-» inicial: no puede colarse como opción

        def run(cmd):
            h = host()
            if h:
                self._run_stream(box, cmd + [h])
            else:
                box.delete("1.0", "end")
                box.insert("end", "Escribe un nombre de sitio o una IP válidos.")
        tk.Button(row, text="Ping", bg=ACC, fg="white", relief="flat",
                  command=lambda: run([system_exe("ping"), "-n", "4"])).pack(side="left", padx=4)
        tk.Button(row, text="Traceroute", bg=ACC, fg="white", relief="flat",
                  command=lambda: run([system_exe("tracert"), "-d"])).pack(side="left")

    def win_siteinfo(self):
        t = self._win("Información del sitio", 620, 460)
        row = tk.Frame(t, bg=BG)
        row.pack(fill="x", padx=8, pady=6)
        ent = tk.Entry(row)
        ent.pack(side="left", fill="x", expand=True)
        box = self._text(t)

        def work(url):
            out = []
            host = urllib.parse.urlsplit(url).hostname
            try:
                out.append(f"Host: {host}")
                for info in socket.getaddrinfo(host, None):
                    out.append(f"IP:   {info[4][0]}")
                try:
                    out.append(f"DNS inverso: {socket.gethostbyaddr(socket.gethostbyname(host))[0]}")
                except OSError:
                    pass
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                r = urllib.request.urlopen(req, timeout=15)  # nosec B310: solo http(s)
                out.append(f"\nURL final: {r.geturl()}\nEstado: {r.status} {r.reason}\n\nCabeceras:")
                out += [f"  {k}: {v}" for k, v in r.getheaders()]
                title = re.search(r"(?is)<title[^>]{0,300}>(.{0,500}?)</title>", r.read(200000).decode("utf-8", "replace"))
                if title:
                    out.insert(0, f"Título: {clean_text(title.group(1).strip(), 300)}")
            except Exception as e:
                out.append(f"Error: {e}")
            self.after(0, lambda: (box.delete("1.0", "end"), box.insert("end", "\n".join(out))))

        def go():
            box.delete("1.0", "end")
            try:
                url = normalize_url(ent.get())
            except ValueError as e:
                box.insert("end", str(e))
                return
            box.insert("end", "Consultando…")
            threading.Thread(target=work, args=(url,), daemon=True).start()
        ent.bind("<Return>", lambda e: go())
        tk.Button(row, text="Consultar", command=go, bg=ACC, fg="white", relief="flat").pack(
            side="left", padx=6)


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        p = Proxy()
        p.start()
        print("proxy up on", PROXY_PORT)
        threading.Event().wait(float(sys.argv[-1]) if sys.argv[-1].replace(".", "").isdigit() else 10)
        print("stats", STATS.requests, STATS.blocked)
        sys.exit()
    if "--activar-inicio" in sys.argv or "--desactivar-inicio" in sys.argv:   # los usa el instalador
        sys.exit(0 if set_autostart("--activar-inicio" in sys.argv) else 1)
    if "--diagnostico" in sys.argv:        # comprueba Npcap, la captura y el icono de la bandeja; escribe diagnostico.txt
        import pcap
        import tray as _tray
        lineas = [f"TrafficBar {ayuda.VERSION}", f"Python {sys.version.split()[0]} · frozen={getattr(sys, 'frozen', False)}"]
        try:
            lineas.append(f"Npcap: {pcap.disponible()}")
            devs = pcap.dispositivos()
            ip = pcap.ip_de_salida()
            lineas.append(f"Tarjetas: {len(devs)} · IP de salida: {ip}")
            dev = next((d for d in devs if ip in d["ips"]), None)
            if dev:
                cap = pcap.Captura(dev["name"])
                t0, npk = time.time(), 0
                while time.time() - t0 < 2.5:
                    raw, _n = cap.next()
                    npk += raw is not None
                lineas.append(f"Captura en «{dev['description']}»: {npk} paquetes en 2,5 s · descartes {cap.stats()[1]}")
                cap.close()
        except Exception as e:
            lineas.append(f"ERROR de captura: {e}")
        try:
            tr_ = _tray.Tray(_res("trafficbar.ico"), lambda a: None, lambda: {"proxy_on": False, "unseen": 0, "has_report": False,
                                                                        "autostart": False, "can_autostart": False})
            tr_.start()
            lineas.append(f"Icono de la bandeja: {'OK' if tr_.hwnd and tr_.hicon else 'FALLO'} · menú de {sum(1 for i in tr_._items() if i)} elementos")
            time.sleep(0.5)
            tr_.stop()
        except Exception as e:
            lineas.append(f"ERROR de bandeja: {e}")
        lineas.append(f"Idioma: {i18n.idioma()} · packs: {sorted(i18n.paquetes(_idiomas_dirs()))}")
        open(os.path.join(DATA_DIR, "diagnostico.txt"), "w", encoding="utf-8").write(chr(10).join(tr(l) for l in lineas) + chr(10))
        sys.exit(0)
    if "--tienda-aplicar" in sys.argv:     # copia elevada (UAC): aplica el pedido del asistente de la Tienda
        tienda.ejecutar_pedido()
        sys.exit(0)
    if "--quitar-exenciones" in sys.argv:  # lo usa el desinstalador
        tienda.quitar_todas()
        sys.exit(0)
    if "--quitar-bloqueos" in sys.argv:    # lo usa el desinstalador: quita las reglas del cortafuegos
        programas.quitar_todos()
        sys.exit(0)
    if "--restaurar-proxy" in sys.argv:   # lo usa el instalador/desinstalador antes de cerrar TrafficBar
        cur = get_system_proxy()
        if cur and cur[0] and is_our_proxy(cur[1]):
            set_system_proxy(False)
        _clear_state()
        sys.exit(0)
    if not acquire_single_instance():   # ya hay una copia en la bandeja: solo la mostramos
        sys.exit(0)
    app = Floating()
    app.after(120, app.show_intro)
    app.mainloop()
