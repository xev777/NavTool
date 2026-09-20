"""Utilidades de seguridad compartidas por NavTool."""
import ctypes
import ipaddress
import os
import re
import unicodedata
import urllib.parse

_HOSTNAME = re.compile(r"^(?=.{1,253}$)[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
                       r"(\.[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*\.?$")


# ------------------------------------------------------------ rutas autoritativas
def system_dir():
    """C:\\Windows\\System32 según Windows (no según variables de entorno modificables)."""
    buf = ctypes.create_unicode_buffer(260)
    n = ctypes.windll.kernel32.GetSystemDirectoryW(buf, 260)
    return buf.value if n else r"C:\Windows\System32"


def system_exe(name):
    """Ruta absoluta de un programa de Windows (ping, tracert…): evita ejecutar uno plantado
    en la carpeta de la app o en la carpeta actual."""
    return os.path.join(system_dir(), name + ".exe")


def powershell_exe():
    return os.path.join(system_dir(), "WindowsPowerShell", "v1.0", "powershell.exe")


def known_folder(csidl):
    """0x1C = Local AppData, 0x1A = AppData (itinerante), 0x28 = perfil del usuario."""
    buf = ctypes.create_unicode_buffer(260)
    ok = ctypes.windll.shell32.SHGetFolderPathW(None, csidl, None, 0, buf) == 0
    return buf.value if ok else ""


def in_protected_folder(path):
    """¿`path` está en Archivos de programa (donde solo un administrador puede escribir)?"""
    for csidl in (0x26, 0x2A):          # Program Files, Program Files (x86)
        base = known_folder(csidl)
        if base and under(path, base):
            return True
    return False


def is_reparse(path):
    """Enlace simbólico o unión (junction): borrar «a través» de ellos afecta a otra carpeta."""
    try:
        return os.path.islink(path) or os.path.isjunction(path)
    except OSError:
        return True


def under(path, root):
    """¿`path` está dentro de `root` (o es `root`), tras resolver enlaces?"""
    try:
        p, r = os.path.realpath(path), os.path.realpath(root)
        return os.path.commonpath([p, r]) == r
    except ValueError:
        return False


# ------------------------------------------------------------------ validaciones
def valid_host(text):
    """Nombre de host o IP válidos. No puede empezar por «-» (no puede colarse como opción)."""
    text = (text or "").strip()
    if not text or text.startswith("-"):
        return None
    try:
        return str(ipaddress.ip_address(text))
    except ValueError:
        pass
    return text.rstrip(".") if _HOSTNAME.match(text) else None


def http_url(text):
    """URL http(s) válida o ValueError. Sin esquema se asume http://. Rechaza file://, ftp://…"""
    text = (text or "").strip()
    if "://" not in text:
        text = "http://" + text
    p = urllib.parse.urlsplit(text)
    try:
        p.port                          # un puerto no numérico (p. ej. «data:text/html») es inválido
    except ValueError:
        raise ValueError("Solo se admiten direcciones http:// o https://") from None
    if p.scheme.lower() not in ("http", "https") or not p.hostname:
        raise ValueError("Solo se admiten direcciones http:// o https://")
    return text


def clean_text(text, limit=255):
    """Quita caracteres de control y de dirección de texto (RTL/LRO…) que permiten disfrazar
    nombres de programas o sitios en las pantallas y avisos."""
    text = "".join(c for c in str(text or "") if unicodedata.category(c) not in ("Cc", "Cf"))
    return text[:limit]


# ------------------------------------------------------------------ monitores
class _RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class _MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_ulong), ("rcMonitor", _RECT), ("rcWork", _RECT),
                ("dwFlags", ctypes.c_ulong)]


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def monitor_work_area(x, y):
    """(izq, arriba, der, abajo) del área útil (sin la barra de tareas) del monitor que contiene
    el punto (x, y) o, si no hay ninguno, el más cercano. Coordenadas del escritorio virtual:
    un monitor a la izquierda del principal tiene x negativas."""
    try:
        u = ctypes.windll.user32
        u.MonitorFromPoint.argtypes = [_POINT, ctypes.c_ulong]
        u.MonitorFromPoint.restype = ctypes.c_void_p
        u.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.POINTER(_MONITORINFO)]
        hmon = u.MonitorFromPoint(_POINT(int(x), int(y)), 2)      # 2 = el más cercano
        info = _MONITORINFO()
        info.cbSize = ctypes.sizeof(_MONITORINFO)
        if hmon and u.GetMonitorInfoW(hmon, ctypes.byref(info)):
            w = info.rcWork
            return w.left, w.top, w.right, w.bottom
    except Exception:
        pass
    gm = ctypes.windll.user32.GetSystemMetrics                    # respaldo: todo el escritorio
    left, top = gm(76), gm(77)
    return left, top, left + gm(78), top + gm(79)


def force_paint(win):
    """Obliga a Windows a repintar una ventana. Tras pasar a administrador (UAC) una ventana de
    Tk puede quedar en blanco hasta que se le hace clic: nunca recibe su primer «pintar»."""
    try:
        if not win.winfo_exists():
            return
        win.update_idletasks()
        u = ctypes.windll.user32
        u.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        u.GetAncestor.restype = ctypes.c_void_p
        u.RedrawWindow.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint]
        hwnd = u.GetAncestor(win.winfo_id(), 2) or win.winfo_id()      # 2 = GA_ROOT
        u.RedrawWindow(hwnd, None, None, 0x0001 | 0x0004 | 0x0080 | 0x0100)   # invalidar+borrar+hijos+ya
    except Exception:
        pass


def paint_soon(win, delays=(30, 250, 700, 1600)):
    """Repinta varias veces mientras la ventana termina de abrirse."""
    for ms in delays:
        try:
            win.after(ms, lambda: force_paint(win))
        except Exception:
            return


def bring_to_front(win):
    """Trae una ventana al frente aunque otra aplicación tenga el foco (p. ej. tras el aviso de UAC).
    OJO: NO simular la tecla Alt para esto: Windows lo toma como «entrar en el menú de la ventana» y se
    queda esperando (la ventana no se pinta hasta que haces clic)."""
    try:
        u, k = ctypes.windll.user32, ctypes.windll.kernel32
        u.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        u.GetAncestor.restype = ctypes.c_void_p
        u.GetForegroundWindow.restype = ctypes.c_void_p
        u.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        u.SetForegroundWindow.argtypes = [ctypes.c_void_p]
        u.BringWindowToTop.argtypes = [ctypes.c_void_p]
        hwnd = u.GetAncestor(win.winfo_id(), 2) or win.winfo_id()
        fg = u.GetForegroundWindow()
        me, other = k.GetCurrentThreadId(), (u.GetWindowThreadProcessId(fg, None) if fg else 0)
        attached = bool(other and other != me and u.AttachThreadInput(me, other, True))
        try:
            u.BringWindowToTop(hwnd)
            u.SetForegroundWindow(hwnd)
        finally:
            if attached:
                u.AttachThreadInput(me, other, False)
    except Exception:
        pass
