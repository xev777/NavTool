"""Captura de paquetes con Npcap mediante ctypes (sin Scapy ni otras librerías).

Solo se carga `wpcap.dll` desde las carpetas de sistema de Npcap (ruta absoluta): nunca desde la carpeta
actual ni del PATH, para que nadie pueda «plantar» una DLL.
"""
import ctypes
import os
import socket
import time

SYS = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")
CANDIDATAS = (os.path.join(SYS, "Npcap"), SYS)                # modo normal / modo compatible con WinPcap
ERRBUF = 256
_lib = {"dll": None, "err": None}


class _timeval(ctypes.Structure):
    _fields_ = [("tv_sec", ctypes.c_long), ("tv_usec", ctypes.c_long)]


class _pkthdr(ctypes.Structure):
    _fields_ = [("ts", _timeval), ("caplen", ctypes.c_uint32), ("len", ctypes.c_uint32)]


class _sockaddr(ctypes.Structure):
    _fields_ = [("family", ctypes.c_ushort), ("data", ctypes.c_ubyte * 14)]


class _addr(ctypes.Structure):
    pass


_addr._fields_ = [("next", ctypes.POINTER(_addr)), ("addr", ctypes.POINTER(_sockaddr)),
                  ("netmask", ctypes.POINTER(_sockaddr)), ("broadaddr", ctypes.POINTER(_sockaddr)),
                  ("dstaddr", ctypes.POINTER(_sockaddr))]


class _if(ctypes.Structure):
    pass


_if._fields_ = [("next", ctypes.POINTER(_if)), ("name", ctypes.c_char_p),
                ("description", ctypes.c_char_p), ("addresses", ctypes.POINTER(_addr)),
                ("flags", ctypes.c_uint32)]


def disponible():
    """Ruta de la carpeta de Npcap si está instalado, o None."""
    for d in CANDIDATAS:
        if os.path.isfile(os.path.join(d, "wpcap.dll")):
            return d
    return None


def _cargar():
    if _lib["dll"] is not None:
        return _lib["dll"]
    d = disponible()
    if not d:
        raise OSError("Npcap no está instalado (npcap.com)")
    if hasattr(os, "add_dll_directory"):
        os.add_dll_directory(d)                               # Packet.dll está junto a wpcap.dll
    w = ctypes.WinDLL(os.path.join(d, "wpcap.dll"))
    P, c = ctypes.POINTER, ctypes
    sig = {
        "pcap_create": (c.c_void_p, [c.c_char_p, c.c_char_p]),
        "pcap_set_snaplen": (c.c_int, [c.c_void_p, c.c_int]),
        "pcap_set_promisc": (c.c_int, [c.c_void_p, c.c_int]),
        "pcap_set_timeout": (c.c_int, [c.c_void_p, c.c_int]),
        "pcap_set_buffer_size": (c.c_int, [c.c_void_p, c.c_int]),
        "pcap_activate": (c.c_int, [c.c_void_p]),
        "pcap_geterr": (c.c_char_p, [c.c_void_p]),
        "pcap_datalink": (c.c_int, [c.c_void_p]),
        "pcap_next_ex": (c.c_int, [c.c_void_p, P(P(_pkthdr)), P(P(c.c_ubyte))]),
        "pcap_stats": (c.c_int, [c.c_void_p, c.c_void_p]),
        "pcap_close": (None, [c.c_void_p]),
        "pcap_findalldevs": (c.c_int, [P(P(_if)), c.c_char_p]),
        "pcap_freealldevs": (None, [P(_if)]),
    }
    for nombre, (res, args) in sig.items():
        f = getattr(w, nombre)
        f.restype, f.argtypes = res, args
    try:                                                      # extensión de Npcap: entrega por lotes
        w.pcap_setmintocopy.restype, w.pcap_setmintocopy.argtypes = c.c_int, [c.c_void_p, c.c_int]
    except AttributeError:
        pass
    _lib["dll"] = w
    return w


def dispositivos():
    """Tarjetas que ve Npcap: [{name, description, ips}] (ips = direcciones IPv4)."""
    w = _cargar()
    err = ctypes.create_string_buffer(ERRBUF)
    head = ctypes.POINTER(_if)()
    if w.pcap_findalldevs(ctypes.byref(head), err) != 0:
        raise OSError(err.value.decode("utf8", "ignore") or "pcap_findalldevs falló")
    out = []
    try:
        d = head
        while d:
            it = d.contents
            ips, a = [], it.addresses
            while a:
                sa = a.contents.addr
                if sa and sa.contents.family == socket.AF_INET:
                    b = bytes(sa.contents.data[2:6])          # sockaddr_in: puerto(2) + dirección(4)
                    ips.append(socket.inet_ntop(socket.AF_INET, b))
                a = a.contents.next
            out.append({"name": (it.name or b"").decode("utf8", "ignore"),
                        "description": (it.description or b"").decode("utf8", "ignore")
                        or (it.name or b"").decode("utf8", "ignore"), "ips": ips})
            d = it.next
    finally:
        w.pcap_freealldevs(head)
    return out


def ip_de_salida():
    """IP local con la que este equipo sale a Internet (no envía nada: solo consulta la ruta)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return ""
    finally:
        s.close()


class Captura:
    """Una tarjeta abierta. Búfer de 16 MB en el kernel, copia directa y contador de descartes."""

    def __init__(self, nombre, buf=16 << 20, snaplen=1600):
        self.w = _cargar()
        err = ctypes.create_string_buffer(ERRBUF)
        self.p = self.w.pcap_create(nombre.encode("utf8"), err)
        if not self.p:
            raise OSError(err.value.decode("utf8", "ignore") or "pcap_create falló")
        self.w.pcap_set_snaplen(self.p, snaplen)
        self.w.pcap_set_promisc(self.p, 0)                    # solo nuestro tráfico
        self.w.pcap_set_timeout(self.p, 50)
        self.w.pcap_set_buffer_size(self.p, buf)
        st = self.w.pcap_activate(self.p)
        if st < 0:
            msg = (self.w.pcap_geterr(self.p) or b"").decode("utf8", "ignore")
            self.w.pcap_close(self.p)
            raise OSError(msg or f"pcap_activate = {st}")
        if hasattr(self.w, "pcap_setmintocopy"):
            self.w.pcap_setmintocopy(self.p, 8192)
        self.dlt = self.w.pcap_datalink(self.p)
        self.hdr = ctypes.POINTER(_pkthdr)()
        self.data = ctypes.POINTER(ctypes.c_ubyte)()
        self.closed = False

    def next(self):
        """(bytes de la trama, longitud real en el cable) o (None, 0) si no hay nada ahora."""
        if self.closed:
            return None, 0
        if self.w.pcap_next_ex(self.p, ctypes.byref(self.hdr), ctypes.byref(self.data)) <= 0:
            return None, 0
        h = self.hdr.contents
        return ctypes.string_at(self.data, h.caplen), h.len

    def stats(self):
        """(recibidos, descartados por el kernel)."""
        buf = (ctypes.c_uint * 8)()                           # holgado: la estructura varía entre versiones
        if self.closed or self.w.pcap_stats(self.p, buf) != 0:
            return 0, 0
        return buf[0], buf[1]

    def close(self):
        if not self.closed:
            self.closed = True
            time.sleep(0.15)                                  # que el lector salga de pcap_next_ex
            self.w.pcap_close(self.p)
