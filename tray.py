"""Icono de NavTool en el área de notificaciones (junto al reloj de Windows), sin librerías de terceros:
usa directamente Shell_NotifyIcon y un menú emergente de Windows mediante ctypes."""
import ctypes
import threading
from ctypes import wintypes

from i18n import tr

WM_APP_TRAY = 0x8000 + 1                       # mensaje de retorno del icono
WM_CLOSE, WM_DESTROY, WM_NULL = 0x0010, 0x0002, 0x0000
WM_LBUTTONUP, WM_RBUTTONUP, WM_CONTEXTMENU = 0x0202, 0x0205, 0x007B
NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
NIF_MESSAGE, NIF_ICON, NIF_TIP, NIF_INFO = 0x1, 0x2, 0x4, 0x10
NIIF_INFO = 0x1
MF_STRING, MF_GRAYED, MF_CHECKED, MF_SEPARATOR = 0x0, 0x1, 0x8, 0x800
TPM_RIGHTBUTTON, TPM_RETURNCMD, TPM_NONOTIFY, TPM_BOTTOMALIGN = 0x2, 0x100, 0x80, 0x20
LR_LOADFROMFILE, IMAGE_ICON, SM_CXSMICON = 0x10, 1, 49
LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
SEP = None                                     # separador en la lista de elementos


class _NOTIFYICONDATA(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND), ("uID", wintypes.UINT),
                ("uFlags", wintypes.UINT), ("uCallbackMessage", wintypes.UINT), ("hIcon", wintypes.HICON),
                ("szTip", wintypes.WCHAR * 128), ("dwState", wintypes.DWORD), ("dwStateMask", wintypes.DWORD),
                ("szInfo", wintypes.WCHAR * 256), ("uTimeout", wintypes.UINT),
                ("szInfoTitle", wintypes.WCHAR * 64), ("dwInfoFlags", wintypes.DWORD),
                ("guidItem", ctypes.c_byte * 16), ("hBalloonIcon", wintypes.HICON)]


class _WNDCLASS(ctypes.Structure):
    _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR)]


_u, _s, _k = ctypes.windll.user32, ctypes.windll.shell32, ctypes.windll.kernel32
_u.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
_u.DefWindowProcW.restype = LRESULT
_u.RegisterClassW.argtypes = [ctypes.POINTER(_WNDCLASS)]
_u.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                               ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND,
                               wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
_u.CreateWindowExW.restype = wintypes.HWND
_u.DestroyWindow.argtypes = [wintypes.HWND]
_u.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
_u.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
_u.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
_u.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
_u.CreatePopupMenu.restype = wintypes.HMENU
_u.AppendMenuW.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR]
_u.SetMenuDefaultItem.argtypes = [wintypes.HMENU, wintypes.UINT, wintypes.UINT]
_u.TrackPopupMenu.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                              wintypes.HWND, wintypes.LPVOID]
_u.DestroyMenu.argtypes = [wintypes.HMENU]
_u.SetForegroundWindow.argtypes = [wintypes.HWND]
_u.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
_u.RegisterWindowMessageW.argtypes = [wintypes.LPCWSTR]
_u.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT, ctypes.c_int, ctypes.c_int,
                          wintypes.UINT]
_u.LoadImageW.restype = wintypes.HANDLE
_u.DestroyIcon.argtypes = [wintypes.HICON]
_s.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(_NOTIFYICONDATA)]
_k.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
_k.GetModuleHandleW.restype = wintypes.HMODULE


class Tray:
    """Las acciones del menú se entregan a `post(nombre)`, que las encola para que las ejecute el hilo
    de la interfaz. `state()` devuelve un dict con proxy_on, unseen, has_report, autostart, can_autostart."""

    def __init__(self, icon_path, post, state):
        self.post, self.state, self.icon_path = post, state, icon_path
        self.hwnd = None
        self.hicon = None
        self.tip = "NavTool"
        self.thread = None
        self.ready = threading.Event()
        self._wndproc = WNDPROC(self._proc)             # se conserva: si se libera, Windows llamaría a la nada
        self._taskbar_msg = _u.RegisterWindowMessageW("TaskbarCreated")

    # ---- elementos del menú (Nombre de acción, texto)
    def _items(self):
        s = self.state()
        n = s["unseen"]
        return [
            (tr("Mostrar / ocultar barra"), "toggle_bar", True, None, True),
            (tr("Restaurar posición de la barra (si no se ve)"), "reset_position", False, None, True),
            (tr("Contraer / expandir barra"), "toggle_collapse", False, None, True),
            (tr("Barra: cambiar tamaño (grande / compacto)"), "toggle_size", False, None, True),
            (tr("Desactivar proxy (⏻ ON)") if s["proxy_on"] else tr("Activar proxy (⏻ OFF)"),
             "toggle_proxy", False, None, True),
            SEP,
            (tr("📡 Tráfico de red"), "traffic", False, None, True),
            (tr("📋 Último informe de privacidad"), "report", False, None, s["has_report"]),
            (tr("🕘 Historial y alertas") + (("  " + tr(f"({n} nuevas)")) if n else ""),
             "history", False, None, True),
            SEP,
            (tr("📅 Cuota mensual de datos"), "quota", False, None, True),
            (tr("🚫 Programas bloqueados"), "blocked", False, None, True),
            (tr("🛍 Compatibilidad con apps de la Tienda"), "store", False, None, True),
            SEP,
            (tr("❓ Ayuda"), "help", False, None, True),
            (tr("Acerca de NavTool"), "about", False, None, True),
            SEP,
            (tr("Iniciar con Windows"), "toggle_autostart", False, bool(s["autostart"]), bool(s["can_autostart"])),
            (tr("Salir de NavTool"), "quit", False, None, True),
        ]

    # ---- hilo del icono
    def start(self):
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        self.ready.wait(3)

    def _run(self):
        hinst = _k.GetModuleHandleW(None)
        wc = _WNDCLASS()
        wc.lpfnWndProc, wc.hInstance, wc.lpszClassName = self._wndproc, hinst, "NavToolTrayWindow"
        _u.RegisterClassW(ctypes.byref(wc))
        self.hwnd = _u.CreateWindowExW(0, "NavToolTrayWindow", "NavTool", 0, 0, 0, 0, 0, None, None, hinst, None)
        cx = _u.GetSystemMetrics(SM_CXSMICON)
        self.hicon = _u.LoadImageW(None, self.icon_path, IMAGE_ICON, cx, cx, LR_LOADFROMFILE)
        self._add()
        self.ready.set()
        msg = wintypes.MSG()
        while _u.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            _u.TranslateMessage(ctypes.byref(msg))
            _u.DispatchMessageW(ctypes.byref(msg))
        if self.hicon:
            _u.DestroyIcon(self.hicon)

    def _data(self, flags):
        d = _NOTIFYICONDATA()
        d.cbSize = ctypes.sizeof(_NOTIFYICONDATA)
        d.hWnd, d.uID, d.uFlags = self.hwnd, 1, flags
        return d

    def _add(self):
        d = self._data(NIF_MESSAGE | NIF_ICON | NIF_TIP)
        d.uCallbackMessage, d.hIcon, d.szTip = WM_APP_TRAY, self.hicon, self.tip[:127]
        _s.Shell_NotifyIconW(NIM_ADD, ctypes.byref(d))

    def _proc(self, hwnd, msg, wp, lp):
        try:
            if msg == WM_APP_TRAY:
                ev = lp & 0xFFFF
                if ev == WM_LBUTTONUP:
                    self.post("toggle_bar")
                elif ev in (WM_RBUTTONUP, WM_CONTEXTMENU):
                    self._menu(hwnd)
                return 0
            if msg == self._taskbar_msg:                # el Explorador se reinició: hay que volver a poner el icono
                self._add()
                return 0
            if msg == WM_DESTROY:
                d = self._data(0)
                _s.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(d))
                _u.PostQuitMessage(0)
                return 0
        except Exception:
            pass                                        # jamás debe caerse el hilo del icono por un error de un menú
        return _u.DefWindowProcW(hwnd, msg, wp, lp)

    def _menu(self, hwnd):
        items = self._items()
        h = _u.CreatePopupMenu()
        acciones, default_id = {}, None
        for i, it in enumerate(items, 1):
            if it is SEP:
                _u.AppendMenuW(h, MF_SEPARATOR, 0, None)
                continue
            texto, accion, default, checked, enabled = it
            flags = MF_STRING | (MF_CHECKED if checked else 0) | (0 if enabled else MF_GRAYED)
            _u.AppendMenuW(h, flags, i, texto)
            acciones[i] = accion
            if default:
                default_id = i
        if default_id:
            _u.SetMenuDefaultItem(h, default_id, 0)
        pt = wintypes.POINT()
        _u.GetCursorPos(ctypes.byref(pt))
        _u.SetForegroundWindow(hwnd)                    # sin esto el menú no se cierra al hacer clic fuera
        cmd = _u.TrackPopupMenu(h, TPM_RIGHTBUTTON | TPM_RETURNCMD | TPM_NONOTIFY | TPM_BOTTOMALIGN,
                                pt.x, pt.y, 0, hwnd, None)
        _u.PostMessageW(hwnd, WM_NULL, 0, 0)
        _u.DestroyMenu(h)
        if cmd in acciones:
            self.post(acciones[cmd])

    # ---- API
    def stop(self):
        try:
            if self.hwnd:
                _u.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)
        except Exception:
            pass

    def notify(self, title, message):
        try:
            d = self._data(NIF_INFO)
            d.szInfoTitle, d.szInfo, d.dwInfoFlags = title[:63], message[:255], NIIF_INFO
            _s.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(d))
        except Exception:
            pass

    def set_tooltip(self, text):
        self.tip = text[:127]
        try:
            d = self._data(NIF_TIP)
            d.szTip = self.tip
            _s.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(d))
        except Exception:
            pass
