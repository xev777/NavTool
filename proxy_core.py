"""Proxy local de TrafficBar (endurecido).

Decisiones de seguridad:
- Escucha solo en 127.0.0.1 y con SO_EXCLUSIVEADDRUSE: en Windows, SO_REUSEADDR deja que OTRO
  proceso se una al mismo puerto y robe las conexiones.
- Puerto aleatorio alto, para que un ajuste de proxy que quedara huérfano no apunte a un
  puerto predecible que otro programa pudiera ocupar.
- Solo acepta peticiones en forma de proxy (URL absoluta http/https) o CONNECT válidos.
- Nada se guarda entero en memoria salvo HTML pequeño (≤ 1 MB) que se va a filtrar; el resto
  se reenvía por trozos. Cuerpos de petición limitados. Tiempos de inactividad en los túneles.
- El filtrado de HTML es de coste lineal (sin expresiones regulares con retroceso).
"""
import http.client
import ipaddress
import random
import re
import socket
import threading
import urllib.parse
from i18n import tr
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MAX_HTML = 1024 * 1024            # solo se filtra HTML de hasta 1 MB
MAX_BODY = 64 * 1024 * 1024       # cuerpo máximo de una petición HTTP en claro
IDLE_TUNNEL = 300                 # segundos sin datos antes de cerrar un túnel HTTPS
MAX_CONNECTIONS = 256             # conexiones simultáneas al proxy
CHUNK = 64 * 1024
PORT_RANGE = (49152, 65000)

# puerto local de cada conexión saliente -> puerto del cliente (navegador) que la pidió.
# Sirve para que el monitor de tráfico muestre "opera.exe" y no "TrafficBar.exe".
UPSTREAM = {}


def link_upstream(sock, client_addr):
    try:
        if len(UPSTREAM) >= 8000:
            UPSTREAM.pop(next(iter(UPSTREAM)), None)
        UPSTREAM[sock.getsockname()[1]] = client_addr[1]
    except (OSError, IndexError, TypeError, StopIteration):
        pass

HOP_BY_HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
              "te", "trailers", "transfer-encoding", "upgrade", "proxy-connection"}
NO_BODY_STATUS = {204, 304}
HOST_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9._-]{0,251}[A-Za-z0-9])?$")

POPUP_JS = ("<script>window.open=function(){return null};"
            "window.showModalDialog=function(){return null};</script>")
_LOWER = {i: i + 32 for i in range(65, 91)}       # minúsculas solo ASCII: conserva la longitud


# ------------------------------------------------------------------- filtrado HTML
def strip_blocks(html, tag):
    """Quita <tag …>…</tag> en tiempo lineal. Si falta la etiqueta de cierre, no toca nada."""
    low = html.translate(_LOWER)
    opener, closer = "<" + tag, "</" + tag
    out, pos = [], 0
    while True:
        s = low.find(opener, pos)
        if s < 0:
            break
        j = s + len(opener)
        if j < len(low) and low[j] not in " \t\r\n/>":     # <scripts>, <objectx>: otra etiqueta
            out.append(html[pos:j])
            pos = j
            continue
        e = low.find(closer, j)
        end = low.find(">", e) if e >= 0 else -1
        if end < 0:                                        # sin cierre: se deja como está
            break
        out.append(html[pos:s])
        pos = end + 1
    out.append(html[pos:])
    return "".join(out)


# Todas acotadas ({0,N}): sin retroceso cuadrático aunque la página sea hostil.
_VOID_SOUND = re.compile(r"(?i)<(?:bgsound|embed)\b[^>]{0,1000}>")
_BLINK = re.compile(r"(?i)</?(?:blink|marquee)\b[^>]{0,1000}>")
_STYLE = re.compile(r"(?i)<style\b[^>]{0,1000}>")
_BG_ATTR = re.compile(r"(?i)\s(?:background|bgcolor)\s*=\s*(?:\"[^\"]{0,1000}\"|'[^']{0,1000}'|[^\s>]{1,1000})")
_BG_CSS = re.compile(r"(?i)background(?:-image)?\s*:[^;}\"']{0,1000}")
_HEAD = re.compile(r"(?i)<head\b[^>]{0,500}>")
_HTML = re.compile(r"(?i)<html\b[^>]{0,500}>")


def filter_html(html, cfg):
    if cfg.get("block_scripts"):
        html = strip_blocks(html, "script")
    if cfg.get("block_sound"):
        html = strip_blocks(strip_blocks(html, "audio"), "object")
        html = _VOID_SOUND.sub("", html)
    if cfg.get("block_blink"):
        html = _BLINK.sub("", html)
        html = _STYLE.sub("<style>*{animation:none!important;text-decoration:none!important}", html)
    if cfg.get("block_background"):
        html = _BG_ATTR.sub("", html)
        html = _BG_CSS.sub("", html)
    if cfg.get("block_popups"):
        m = _HEAD.search(html, 0, 4096) or _HTML.search(html, 0, 4096)   # tras <head> (o <html>):
        # así la página no sale del modo estándar del navegador
        html = html[:m.end()] + POPUP_JS + html[m.end():] if m else POPUP_JS + html
    return html


# ------------------------------------------------------------------------ servidor
class SecureServer(ThreadingHTTPServer):
    allow_reuse_address = False       # nunca SO_REUSEADDR (permite el secuestro del puerto)
    daemon_threads = True
    request_queue_size = 64

    def __init__(self, addr, handler):
        self.slots = threading.BoundedSemaphore(MAX_CONNECTIONS)
        super().__init__(addr, handler)

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

    def verify_request(self, request, client_address):
        return client_address[0] == "127.0.0.1"

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):      # saturado: se rechaza en vez de crecer
            self.shutdown_request(request)
            return
        super().process_request(request, client_address)

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()

    def handle_error(self, request, client_address):
        pass      # cortes normales (pestaña cerrada, corte manual desde la barra de carga)


class Proxy:
    """stats/loader/cfg/is_blocked los pone TrafficBar; así el proxy no depende de la interfaz."""

    def __init__(self, stats, loader, cfg, is_blocked):
        self.ctx = (stats, loader, cfg, is_blocked)
        self.server = None
        self.port = 0

    def start(self):
        handler = type("Handler", (ProxyHandler,), {"stats": self.ctx[0], "loader": self.ctx[1],
                                                    "cfg": self.ctx[2],
                                                    "is_blocked": staticmethod(self.ctx[3])})
        rng, last = random.SystemRandom(), None
        for _ in range(40):
            port = rng.randint(*PORT_RANGE)
            try:
                self.server = SecureServer(("127.0.0.1", port), handler)
                break
            except OSError as e:
                last = e
        else:
            raise last or OSError("sin puertos libres")
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self.port

    def stop(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.server = None


# -------------------------------------------------------------------------- manejador
def parse_authority(text):
    """'host:puerto' o '[v6]:puerto' → (host, puerto) validados, o None."""
    try:
        if text.startswith("["):
            host, _, rest = text[1:].partition("]")
            ipaddress.IPv6Address(host)
            port = int(rest[1:]) if rest.startswith(":") else 443
        else:
            host, _, p = text.partition(":")
            port = int(p) if p else 443
            if not HOST_RE.match(host) and not _is_ipv4(host):
                return None
    except ValueError:
        return None
    return (host, port) if 1 <= port <= 65535 else None


def _is_ipv4(s):
    try:
        ipaddress.IPv4Address(s)
        return True
    except ValueError:
        return False


class ProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    timeout = 30
    stats = loader = cfg = is_blocked = None      # los completa Proxy.start()

    def log_message(self, *a):
        pass

    # ---- utilidades
    def _refuse(self, code, msg=""):
        self.close_connection = True
        try:
            self.send_error(code, tr(msg) if msg else msg)
        except OSError:
            pass

    def _done(self, host, i):
        """Avisa (si Stats lo admite) de que una conexión terminó y cuántos bytes movió."""
        cb = getattr(self.stats, "conn_done", None)
        if cb:
            cb(host, self.loader.bytes_of(i))

    def _is_self(self, host, port):
        return host.lower() in ("localhost", "127.0.0.1", "::1") and \
            port == self.server.server_address[1]

    def _blocked(self, host):
        """True si se rechazó (lista de dominios o corte manual). Responde el propio método."""
        if self.is_blocked(host):
            self.stats.block(host)
            self.loader.blocked(host, "blocked")
            return "blocked"
        if self.loader.held():
            self.loader.blocked(host, "cut")
            return "cut"
        return None

    # ---- HTTPS: túnel
    def do_CONNECT(self):
        target = parse_authority(self.path)
        if not target:
            return self._refuse(400, "Destino no válido")
        host, port = target
        self.stats.add(requests=1)
        if self._is_self(host, port):
            return self._refuse(403)
        why = self._blocked(host)
        if why:
            return self._refuse(403, "Bloqueado por TrafficBar" if why == "blocked"
                                else "Carga cortada por TrafficBar")
        try:
            up = socket.create_connection((host, port), timeout=15)
        except OSError:
            return self._refuse(502)
        link_upstream(up, self.client_address)
        self.send_response(200, "Connection established")
        self.end_headers()
        self.close_connection = True
        self._pipe(self.connection, up, host)

    def _pipe(self, a, b, host=""):
        cid = self.loader.register("tunnel", (a, b), host)
        a.settimeout(IDLE_TUNNEL)
        b.settimeout(IDLE_TUNNEL)

        def pump(src, dst, up):
            try:
                while (d := src.recv(CHUNK)):
                    dst.sendall(d)
                    self.loader.touch(cid, len(d))
                    self.stats.add(bytes_up=len(d)) if up else self.stats.add(bytes_down=len(d))
            except OSError:
                pass
            finally:
                for s in (src, dst):
                    try:
                        s.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass
        t = threading.Thread(target=pump, args=(b, a, False), daemon=True)
        t.start()
        pump(a, b, True)
        t.join(5)
        self._done(host, cid)
        self.loader.unregister(cid)
        b.close()

    # ---- HTTP en claro
    def _forward(self):
        if not self.path.lower().startswith(("http://", "https://")):
            return self._refuse(400, "Solo se atienden peticiones de proxy")
        try:
            url = urllib.parse.urlsplit(self.path)
            host, port = url.hostname, url.port
        except ValueError:
            return self._refuse(400)
        if not host or not (HOST_RE.match(host) or _is_ipv4(host) or ":" in host):
            return self._refuse(400)
        self.stats.add(requests=1)
        if self._is_self(host, port or 80):
            return self._refuse(403)
        if self._blocked(host):
            self.send_response(204)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        rid = self.loader.register("req", (self.connection,), host)
        try:
            self._do_forward(url, rid)
        except OSError:
            self.close_connection = True      # conexión cortada desde la barra de carga
        finally:
            self._done(host, rid)
            self.loader.unregister(rid)

    def _read_body(self):
        """Devuelve (bytes|None, error). Rechaza cuerpos chunked o de tamaño absurdo."""
        if "chunked" in (self.headers.get("Transfer-Encoding") or "").lower():
            return None, 501
        raw = self.headers.get("Content-Length")
        try:
            length = int(raw) if raw is not None else 0
        except ValueError:
            return None, 400
        if length < 0:
            return None, 400
        if length > MAX_BODY:
            return None, 413
        return (self.rfile.read(length) if length else None), 0

    def _do_forward(self, url, rid):
        body, err = self._read_body()
        if err:
            return self._refuse(err)
        headers = {k: v for k, v in self.headers.items()
                   if k.lower() not in HOP_BY_HOP and k.lower() != "accept-encoding"}
        headers["Accept-Encoding"] = "identity"
        if self.cfg.get("block_cookies"):
            headers.pop("Cookie", None)
        target = (url.path or "/") + ("?" + url.query if url.query else "")
        try:
            cls = http.client.HTTPSConnection if url.scheme.lower() == "https" \
                else http.client.HTTPConnection
            conn = cls(url.hostname, url.port, timeout=20)
            conn.request(self.command, target, body, headers)
            self.loader.add_sock(rid, conn.sock)
            link_upstream(conn.sock, self.client_address)
            resp = conn.getresponse()
        except Exception:
            return self._refuse(502)
        sent_up = len(body) if body else 0
        ctype = (resp.getheader("Content-Type") or "").lower()
        clen = resp.getheader("Content-Length")
        try:
            clen_n = int(clen) if clen is not None else None
        except ValueError:
            clen_n = None
        encoding = (resp.getheader("Content-Encoding") or "identity").strip().lower()
        filterable = ("text/html" in ctype and self.command != "HEAD"
                      and encoding in ("identity", "")       # comprimido: no se toca
                      and resp.status not in NO_BODY_STATUS
                      and (clen_n is None or clen_n <= MAX_HTML))
        first = b""
        if filterable:
            first = resp.read(MAX_HTML + 1)
            if len(first) <= MAX_HTML:                 # cabe: se filtra y se envía entero
                first = self._filter(first, ctype)
                return self._send(resp, first, None, rid, sent_up)
            filterable = False                         # resultó grande: pasa sin filtrar
        self._send(resp, first, resp, rid, sent_up)

    def _filter(self, data, ctype):
        m = re.search(r"charset\s*=\s*\"?([\w.-]+)", ctype)
        enc = m.group(1) if m else "latin-1"           # latin-1 = ida y vuelta sin pérdidas
        try:
            text = data.decode(enc, "surrogateescape")
        except (LookupError, UnicodeError):
            enc = "latin-1"
            text = data.decode(enc)
        out = filter_html(text, self.cfg)
        self.stats.add(filtered=1)
        try:
            return out.encode(enc, "surrogateescape")
        except UnicodeError:
            return data                                # no se pudo recodificar: se deja intacto

    def _send(self, resp, first, stream, rid, sent_up):
        """Envía cabeceras + cuerpo. `stream`=None → cuerpo completo en `first` (con longitud);
        si no, se copia por trozos lo que falte de `stream`."""
        self.send_response(resp.status, resp.reason)
        for k, v in resp.getheaders():
            kl = k.lower()
            if kl in HOP_BY_HOP or (kl == "content-length" and stream is None):
                continue
            if kl == "set-cookie" and self.cfg.get("block_cookies"):
                continue
            self.send_header(k, v)
        if stream is None:
            self.send_header("Content-Length", str(len(first)))
        elif resp.getheader("Content-Length") is None and self.command != "HEAD" \
                and resp.status not in NO_BODY_STATUS:
            self.send_header("Connection", "close")    # longitud desconocida: termina al cerrar
            self.close_connection = True
        self.end_headers()
        total = 0
        if first:
            self.wfile.write(first)
            total += len(first)
            self.loader.touch(rid, len(first))
        if stream is not None and self.command != "HEAD":
            while (chunk := stream.read(CHUNK)):
                self.wfile.write(chunk)
                total += len(chunk)
                self.loader.touch(rid, len(chunk))
        self.stats.add(bytes_down=total, bytes_up=sent_up)

    do_GET = do_POST = do_HEAD = do_PUT = do_DELETE = do_OPTIONS = do_PATCH = _forward
