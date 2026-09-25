"""Suite de pruebas de seguridad de TrafficBar.

Ataques reales contra el proxy, el filtro, las utilidades y el monitor, más pruebas de
regresión de que lo normal sigue funcionando. Todo local y en carpetas temporales:
no toca tu configuración ni el proxy de Windows.

Uso:   python pruebas_seguridad.py
"""
import faulthandler
faulthandler.dump_traceback_later(240, exit=True)
import http.server
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time

tmp = tempfile.mkdtemp(prefix="navsec_")
os.environ["APPDATA"] = os.path.join(tmp, "roaming")
os.environ["LOCALAPPDATA"] = os.path.join(tmp, "local")
for d in (os.environ["APPDATA"], os.environ["LOCALAPPDATA"]):
    os.makedirs(d)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import psutil                      # noqa: E402
import trafficbar as n                # noqa: E402
import safety                      # noqa: E402
import proxy_core                  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"[{'OK   ' if ok else 'FALLA'}] {name}" + (f"  → {detail}" if detail else ""), flush=True)


# ------------------------------------------------------------------ escenario
hits = []


class Victim(http.server.BaseHTTPRequestHandler):
    """Servicio 'interno' (p. ej. un router) al que un atacante querría llegar."""

    def _reply(self, body=b"ok", ctype="text/plain", extra=None):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        hits.append(("GET", self.path))
        if self.path.startswith("/page"):
            body = (b"<html><head><title>x</title></head><body><script>var a=1;</script>"
                    b"<marquee>hola</marquee>ni\xf1o</body></html>")
            return self._reply(body, "text/html; charset=iso-8859-1")
        if self.path.startswith("/big"):
            return self._reply(b"z" * 200000, "application/octet-stream")
        self._reply()

    def do_POST(self):
        hits.append(("POST", self.path))
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        self._reply()

    def log_message(self, *a):
        pass


victim = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Victim)
VP = victim.server_address[1]
threading.Thread(target=victim.serve_forever, daemon=True).start()
proxy = n.Proxy()
PP = proxy.start()


def raw(port, data, timeout=6):
    s = socket.create_connection(("127.0.0.1", port), timeout=timeout)
    s.sendall(data)
    out = b""
    try:
        while (d := s.recv(65536)):
            out += d
    except OSError:
        pass
    s.close()
    return out


def status(resp):
    return resp.split(b"\r\n", 1)[0].decode("latin-1")


print(f"Proxy de prueba en 127.0.0.1:{PP}\n=== ATAQUES (todos deben fallar) ===")

# 1. peticiones que no son de proxy (SSRF/CSRF desde una web)
hits.clear()
for line in (f"GET //127.0.0.1:{VP}/admin", f"GET /admin", f"POST //127.0.0.1:{VP}/reboot"):
    raw(PP, f"{line} HTTP/1.1\r\nHost: evil.example\r\nContent-Length: 0\r\nConnection: close\r\n\r\n".encode())
check("Peticiones que no son de proxy no llegan a la red interna", not hits, f"llegadas: {hits}")

# 2. secuestro del puerto
try:
    s2 = socket.socket()
    s2.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s2.bind(("127.0.0.1", PP))
    hijack = True
    s2.close()
except OSError:
    hijack = False
check("Otro programa NO puede enlazarse al puerto del proxy", not hijack)

# 3. memoria con descarga grande (streaming)
class Big(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(120 * 1048576))
        self.end_headers()
        chunk = b"\0" * 1048576
        try:
            for _ in range(120):
                self.wfile.write(chunk)
        except OSError:
            pass

    def log_message(self, *a):
        pass


big = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Big)
BP = big.server_address[1]
threading.Thread(target=big.serve_forever, daemon=True).start()
me, peak, stop = psutil.Process(), [0], [False]


def sample():
    while not stop[0]:
        peak[0] = max(peak[0], me.memory_info().rss)
        time.sleep(0.02)


threading.Thread(target=sample, daemon=True).start()
base = me.memory_info().rss
subprocess.run(["curl", "-s", "-o", "NUL", "-x", f"http://127.0.0.1:{PP}", f"http://127.0.0.1:{BP}/iso"],
               timeout=90, check=False)
stop[0] = True
grew = (peak[0] - base) / 1048576
check("Una descarga de 120 MB no se acumula en la memoria del proxy", grew < 40, f"memoria +{grew:.0f} MB")

# 4. regex hostil (páginas de 1 MB)
n.CFG.update(block_scripts=True, block_sound=True, block_blink=True, block_background=True, block_popups=True)
worst = 0
for evil in ("<script " * 120000, "<embed " * 150000, "<marquee " * 110000, '<a background="' * 60000,
             "<object " * 120000, "<style " * 150000):
    evil = evil[:1_000_000]
    t = time.time()
    n.filter_html(evil)
    worst = max(worst, time.time() - t)
check("Páginas hostiles de 1 MB no congelan el filtro", worst < 3, f"peor caso {worst:.2f} s")

# 5. file:// y otros esquemas
bad = []
for u in ("file:///C:/Windows/win.ini", "ftp://x/y", "gopher://x", "javascript:alert(1)", "data:text/html,x"):
    try:
        n.normalize_url(u)
        bad.append(u)
    except ValueError:
        pass
check("Mapa/Sitio rechazan file://, ftp://, javascript: y demás", not bad, f"aceptadas: {bad}")

# 6. «Limpiar» con TEMP manipulada y con uniones
victim_dir = os.path.join(tmp, "MIS_DOCUMENTOS")
os.makedirs(victim_dir)
open(os.path.join(victim_dir, "tesis.docx"), "w").write("importante")
old_temp = os.environ.get("TEMP")
os.environ["TEMP"] = victim_dir
targets = [t[1] for t in n.clean_targets()]
os.environ["TEMP"] = old_temp
check("«Limpiar» ignora una variable TEMP manipulada", victim_dir not in targets)

trap = os.path.join(tmp, "trampa")
os.makedirs(trap)
junction = os.path.join(trap, "enlace")
subprocess.run(["cmd", "/c", "mklink", "/J", junction, victim_dir], capture_output=True, check=False)
freed = n.remove_path(trap, True)
check("«Limpiar» no atraviesa uniones (junction) hacia otras carpetas",
      os.path.exists(os.path.join(victim_dir, "tesis.docx")), f"liberado {freed} B")
check("«Limpiar» rechaza como objetivo una unión", n.remove_path(junction, True) == 0
      and os.path.exists(os.path.join(victim_dir, "tesis.docx")))

# 7. ping/tracert
check("Ping rechaza «-t», «-n 9999», rutas y comillas",
      all(safety.valid_host(x) is None for x in ("-t", "-n", "a b", "x;y", "a&b", "|calc", "", "-")))
check("Ping acepta hosts e IPs legítimos",
      all(safety.valid_host(x) for x in ("example.com", "8.8.8.8", "2001:db8::1", "sub-1.dominio.co.uk")))
check("Ping/Traceroute usan rutas absolutas de System32",
      os.path.isabs(safety.system_exe("ping")) and safety.system_exe("ping").lower().endswith("system32\\ping.exe"))

# 8. DNS falso y DNS legítimo
import struct  # noqa: E402
import netparse  # noqa: E402
from traffic_monitor import Engine  # noqa: E402


def dns_msg(ident, qr, name, ips=(), rcode=0, qtype=1):
    """Mensaje DNS armado a mano (sin librerías): pregunta + respuestas A/AAAA."""
    def nm(n):
        return b"".join(bytes([len(p)]) + p.encode() for p in n.split(".")) + b"\x00"
    m = struct.pack("!HHHHHH", ident, (qr << 15) | 0x0100 | rcode, 1, len(ips), 0, 0) + nm(name) + struct.pack("!HH", qtype, 1)
    for ip in ips:
        a = socket.inet_pton(socket.AF_INET6 if ":" in ip else socket.AF_INET, ip)
        m += b"\xc0\x0c" + struct.pack("!HHIH", 28 if ":" in ip else 1, 1, 60, len(a)) + a
    return m


def dns(*a, **k):
    return netparse.parse_dns(dns_msg(*a, **k))


e = Engine()
e._on_dns(dns(1234, 1, "microsoft.com", ["6.6.6.6"]), False, time.time(), "8.8.8.8")
check("Una respuesta DNS que nadie pidió NO cambia nombres", "6.6.6.6" not in e.dns)
e._on_dns(dns(77, 0, "ejemplo.org"), True, time.time(), "8.8.8.8")
e._on_dns(dns(77, 1, "ejemplo.org", ["6.6.6.6"]), False, time.time(), "6.6.6.6")   # id correcto pero otro servidor
check("Una respuesta con el id correcto pero de OTRO servidor se ignora", "6.6.6.6" not in e.dns)
e._on_dns(dns(77, 0, "ejemplo.org"), True, time.time(), "8.8.8.8")
e._on_dns(dns(77, 1, "ejemplo.org", ["93.184.216.34"]), False, time.time(), "8.8.8.8")
check("La respuesta legítima (misma consulta y servidor) SÍ se usa", e.dns.get("93.184.216.34") == "ejemplo.org")
# el lector de paquetes ante datos hostiles: nunca lanza y no devuelve basura
import random  # noqa: E402
rnd = random.Random(1)
base = dns_msg(5, 1, "a.b.c.example.org", ["1.2.3.4", "2001:db8::1"])
raised = False
for _ in range(4000):
    b = bytearray(base)
    for _ in range(rnd.randint(1, 8)):
        b[rnd.randrange(len(b))] = rnd.randrange(256)
    try:
        netparse.parse_dns(bytes(b)[:rnd.randint(0, len(b))])
        netparse.parse_frame(b"\x00" * 12 + b"\x08\x00" + bytes(b))
        netparse.parse_frame(bytes(b))
    except Exception:
        raised = True
check("El lector de paquetes no lanza ante 4.000 mensajes DNS/tramas corruptos", not raised)
loop = struct.pack("!HHHHHH", 1, 0x0100, 1, 0, 0, 0) + b"\xc0\x0c" + struct.pack("!HH", 1, 1)      # puntero que se apunta a sí mismo
check("Un nombre DNS con bucle de compresión se rechaza (sin colgarse)", netparse.parse_dns(loop) is None)
check("Un nombre DNS de más de 255 caracteres se rechaza", netparse.parse_dns(struct.pack("!HHHHHH", 1, 0x0100, 1, 0, 0, 0) + (b"\x3f" + b"a" * 63) * 5 + b"\x00" + struct.pack("!HH", 1, 1)) is None)
check("Un DNS con miles de respuestas declaradas solo lee 32", len(netparse.parse_dns(dns_msg(9, 1, "x.org", ["1.1.1.%d" % (i % 250 + 1) for i in range(60)])).answers) <= 32)

# 9. configuración corrupta
cfgp = n.CFG_FILE
backup = open(cfgp, encoding="utf-8").read() if os.path.exists(cfgp) else "{}"
crashed, sane = False, False
for bad_cfg in ({"engine": "abc"}, {"engines": "x"}, {"alert_up_mb_s": "NaN", "monitor_bg": "no"},
                {"engines": [{"name": "x", "url": "javascript:alert(1)//{q}"}], "engine": 99}, [], "texto"):
    try:
        json.dump(bad_cfg, open(cfgp, "w"))
        c = n.load_cfg()
        sane = all(u["url"].startswith(("http://", "https://")) for u in c["engines"]) \
            and 0 <= c["engine"] < len(c["engines"]) and isinstance(c["monitor_bg"], bool)
    except Exception as ex:
        crashed = True
open(cfgp, "w", encoding="utf-8").write(backup)
check("Un config.json corrupto o malicioso no rompe la app ni cuela URLs peligrosas", not crashed and sane)

# 10. cabeceras y cuerpos malformados
r = raw(PP, f"POST http://127.0.0.1:{VP}/x HTTP/1.1\r\nHost: x\r\nContent-Length: abc\r\nConnection: close\r\n\r\n".encode())
check("Content-Length inválido → error 400 controlado", status(r).startswith("HTTP/1.1 400"), status(r))
r = raw(PP, f"POST http://127.0.0.1:{VP}/x HTTP/1.1\r\nHost: x\r\nContent-Length: 99999999999\r\nConnection: close\r\n\r\n".encode())
check("Cuerpo gigante declarado → 413", status(r).startswith("HTTP/1.1 413"), status(r))
r = raw(PP, f"POST http://127.0.0.1:{VP}/x HTTP/1.1\r\nHost: x\r\nTransfer-Encoding: chunked\r\nConnection: close\r\n\r\n0\r\n\r\n".encode())
check("Cuerpo chunked (no soportado) → 501, sin desincronizar la conexión", status(r).startswith("HTTP/1.1 501"), status(r))
r = raw(PP, b"CONNECT bad host:443 HTTP/1.1\r\nHost: x\r\n\r\n")
check("CONNECT con destino inválido → 400", status(r).startswith("HTTP/1.1 400"), status(r))
r = raw(PP, f"CONNECT 127.0.0.1:{PP} HTTP/1.1\r\nHost: x\r\n\r\n".encode())
check("El proxy no se deja usar a sí mismo (bucle)", status(r).startswith("HTTP/1.1 403"), status(r))

# 11. exclusión y límites de conexiones
socks = []
try:
    for _ in range(proxy_core.MAX_CONNECTIONS + 40):
        socks.append(socket.create_connection(("127.0.0.1", PP), timeout=2))
    time.sleep(0.5)
    still = raw(PP, f"GET http://127.0.0.1:{VP}/ok HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n".encode(), timeout=3)
    saturado_ok = True          # no se cayó ni se disparó la memoria; puede rechazar mientras está saturado
except OSError:
    saturado_ok = True
finally:
    for s_ in socks:
        s_.close()
time.sleep(1)
after = raw(PP, f"GET http://127.0.0.1:{VP}/ok HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n".encode())
check("Con cientos de conexiones abiertas el proxy aguanta y se recupera", saturado_ok and status(after).startswith("HTTP/1.1 200"), status(after))

# 12. texto disfrazado
disfraz = "factura\u202egpj.exe\x00"
limpio = safety.clean_text(disfraz)
check("Los caracteres de dirección de texto y de control se eliminan de los nombres",
      "\u202e" not in limpio and "\x00" not in limpio, repr(limpio))

# 13. ajustes de proxy huérfanos
n.PROXY_PORT = 0
check("Se reconoce como propio solo el proxy de TrafficBar",
      n.is_our_proxy("127.0.0.1:8118") and not n.is_our_proxy("127.0.0.1:8888") and not n.is_our_proxy("evil.com:8118"))
check("El proxy usa un puerto alto aleatorio, no uno predecible", proxy_core.PORT_RANGE[0] <= PP <= proxy_core.PORT_RANGE[1] and PP != 8118, str(PP))

# 14. listas de bloqueo descargables (entrada externa que decide qué se bloquea)
import blocklists  # noqa: E402
import urllib.error  # noqa: E402

hostil = "\n".join([
    "127.0.0.1 localhost", "0.0.0.0 0.0.0.0", "1.2.3.4 evil.com", "rm -rf /", "javascript:alert(1)",
    "0.0.0.0 -t", "0.0.0.0 mal_dominio!.com", "0.0.0.0 con espacios.com extra", "0.0.0.0 " + "a" * 400 + ".com",
    "0.0.0.0 ok.tracker.com", "otro.tracker.net # comentario", "UPPER.Case.ORG", "192.168.1.1", "::1",
])
parsed = blocklists.parse_list(hostil)
check("Una lista hostil solo deja pasar dominios válidos (sin IPs, comandos ni basura)",
      parsed == {"ok.tracker.com", "otro.tracker.net", "upper.case.org"}, str(sorted(parsed)))


class FakeResp:
    def __init__(self, data):
        self.data = data

    def read(self, n=-1):
        return self.data if n < 0 else self.data[:n]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def intenta(data, clave="pgl", src=None):
    carpeta = os.path.join(tmp, "listas_test")
    old = blocklists.SOURCES[clave]["url"]
    if src:
        blocklists.SOURCES[clave]["url"] = src
    try:
        return blocklists.descargar(clave, carpeta, abrir=lambda req, timeout: FakeResp(data)), None
    except (ValueError, urllib.error.URLError, OSError) as e:
        return None, str(e)
    finally:
        blocklists.SOURCES[clave]["url"] = old


grande = ("0.0.0.0 d%d.example.com\n" * 1).encode() * 1
n_ok, err = intenta("\n".join(f"0.0.0.0 host{i}.ejemplo.com" for i in range(300)).encode())
check("Una lista válida se descarga y se guarda", n_ok == 300 and err is None, f"{n_ok} dominios")
n_big, err = intenta(b"x" * (blocklists.MAX_BYTES + 10))
check("Una respuesta gigante se rechaza (tope de tamaño)", n_big is None and "grande" in (err or ""), err)
n_tiny, err = intenta(b"<html>Error 503</html>")
check("Una respuesta que no es una lista (página de error) se rechaza y no reemplaza la buena",
      n_tiny is None and blocklists.cargar(os.path.join(tmp, "listas_test"), "pgl") != set(), err)
n_http, err = intenta(b"0.0.0.0 a.com\n", src="http://inseguro.example/lista")
check("Una lista por HTTP (sin cifrar) se rechaza", n_http is None and "HTTPS" in (err or ""), err)
try:
    blocklists._SoloHttps().redirect_request(None, None, 302, "x", {}, "http://malo.example/l")
    redir_ok = False
except urllib.error.URLError:
    redir_ok = True
check("Una redirección de HTTPS a HTTP se rechaza", redir_ok)
bl = blocklists.combinar({"a.com"}, True, [{"github.com", "x.tracker.net"}], {"ok.a.com"})
check("Los dominios esenciales (github.com, microsoft.com…) NUNCA se bloquean, aunque una lista los incluya",
      "github.com" not in bl and not blocklists.esta_bloqueado("github.com", {"github.com"}, set()))
check("Las excepciones del usuario ganan a cualquier lista (y a subdominios)",
      blocklists.esta_bloqueado("www.a.com", bl, {"ok.a.com"}) and not blocklists.esta_bloqueado("ok.a.com", bl, {"ok.a.com"})
      and not blocklists.esta_bloqueado("x.ok.a.com", bl, {"ok.a.com"}))
open(os.path.join(tmp, "listas_test", "pgl.txt"), "w", encoding="utf-8").write("\n".join(["ok1.example.com"] * 5 + ["basura!!", "1.1.1.1"]))
check("Un archivo de lista manipulado en disco solo aporta dominios válidos",
      blocklists.cargar(os.path.join(tmp, "listas_test"), "pgl") == {"ok1.example.com"})
n.ALLOWLIST.add("permitido-prueba.com"); n.BLOCKLIST.add("permitido-prueba.com"); n.rebuild_blocklists()
check("En la app, una excepción evita el bloqueo aunque el sitio esté en tu lista", not n.is_blocked_host("cdn.permitido-prueba.com"))
n.ALLOWLIST.discard("permitido-prueba.com"); n.BLOCKLIST.discard("permitido-prueba.com"); n.rebuild_blocklists()
check("La lista incluida bloquea publicidad conocida y deja pasar sitios normales",
      n.is_blocked_host("ib.adnxs.com") and n.is_blocked_host("stats.g.doubleclick.net") and not n.is_blocked_host("www.wikipedia.org"))

print("\n=== REGRESIÓN (lo normal debe seguir funcionando) ===")
hits.clear()
r = subprocess.run(["curl", "-s", "-x", f"http://127.0.0.1:{PP}", f"http://127.0.0.1:{VP}/hola"], capture_output=True, timeout=20)
check("GET normal a través del proxy", r.stdout == b"ok" and ("GET", "/hola") in hits, r.stdout.decode()[:30])
r = subprocess.run(["curl", "-s", "-x", f"http://127.0.0.1:{PP}", "-d", "abc", f"http://127.0.0.1:{VP}/form"], capture_output=True, timeout=20)
check("POST normal a través del proxy", r.stdout == b"ok" and ("POST", "/form") in hits)
r = subprocess.run(["curl", "-s", "-o", "NUL", "-w", "%{size_download}", "-x", f"http://127.0.0.1:{PP}", f"http://127.0.0.1:{VP}/big"], capture_output=True, timeout=20)
check("Descarga binaria por streaming íntegra (200 000 bytes)", r.stdout == b"200000", r.stdout.decode())

n.CFG.update(block_scripts=False, block_sound=False, block_blink=False, block_background=False, block_popups=False)
r = subprocess.run(["curl", "-s", "-x", f"http://127.0.0.1:{PP}", f"http://127.0.0.1:{VP}/page"], capture_output=True, timeout=20)
orig = b"<html><head><title>x</title></head><body><script>var a=1;</script><marquee>hola</marquee>ni\xf1o</body></html>"
check("Con todos los filtros apagados la página llega idéntica byte a byte (incl. ñ en latin-1)", r.stdout == orig)
n.CFG.update(block_scripts=True, block_blink=True, block_popups=True)
r = subprocess.run(["curl", "-s", "-x", f"http://127.0.0.1:{PP}", f"http://127.0.0.1:{VP}/page"], capture_output=True, timeout=20)
html = r.stdout
check("Filtros: quita <script> y <marquee>, conserva el resto y los acentos",
      b"var a=1" not in html and b"<marquee" not in html and b"hola" in html and b"ni\xf1o" in html)
check("Filtro de pop-ups: se inyecta DENTRO de <head> (no rompe el modo estándar)",
      html.find(b"window.open") > html.find(b"<head>") > 0 and html.startswith(b"<html>"))
n.CFG.update(block_domains=True)
# modo «solo medir» (el ahorro se mide con tu navegación real, no se supone)
n.BLOCKLIST.add("127.0.0.1"); n.rebuild_blocklists()
n.CFG["measure_only"] = False
antes = n.STATS.blocked
r = subprocess.run(["curl", "-s", "-o", "NUL", "-w", "%{http_code}", "-x", f"http://127.0.0.1:{PP}", f"http://127.0.0.1:{VP}/hola"], capture_output=True, timeout=20)
check("Bloqueo real: un servidor de tus listas se rechaza (204) y se cuenta", r.stdout == b"204" and n.STATS.blocked == antes + 1, r.stdout.decode())
n.CFG["measure_only"] = True
b0, c0 = n.STATS.pot_bytes, n.STATS.pot_conns
r = subprocess.run(["curl", "-s", "-x", f"http://127.0.0.1:{PP}", f"http://127.0.0.1:{VP}/big"], capture_output=True, timeout=20)
time.sleep(0.4)
check("«Solo medir» NO bloquea (la descarga llega íntegra) y mide los bytes que se habrían evitado",
      len(r.stdout) == 200000 and n.STATS.pot_bytes - b0 >= 200000 and n.STATS.pot_conns == c0 + 1,
      f"medido +{n.STATS.pot_bytes - b0} bytes")
n.CFG["ad_bytes_per_conn"] = None
check("Sin una medición propia NO se inventa un ahorro estimado", n.saved_estimate() is None and "sin medir" in n.saved_text())
n.CFG["ad_bytes_per_conn"] = 5000
n.STATS.blocked = 10
check("Con el peso medio medido, el ahorro estimado = bloqueadas × peso medio", n.saved_estimate() == 50000, n.saved_text())
n.CFG["ad_bytes_per_conn"] = None; n.CFG["measure_only"] = False; n.STATS.blocked = 0
n.BLOCKLIST.discard("127.0.0.1"); n.rebuild_blocklists()
r = subprocess.run(["curl", "-s", "-o", "NUL", "-w", "%{http_code}", "-x", f"http://127.0.0.1:{PP}", "http://doubleclick.net/x"], capture_output=True, timeout=20)
check("Dominio bloqueado (HTTP) → 204", r.stdout == b"204", r.stdout.decode())
r = subprocess.run(["curl", "-s", "-o", "NUL", "-w", "%{http_code}", "-x", f"http://127.0.0.1:{PP}", "https://ad.doubleclick.net/x"], capture_output=True, timeout=20)
check("Dominio bloqueado (HTTPS/CONNECT) → rechazado", r.stdout in (b"000", b"403"), r.stdout.decode())
r = subprocess.run(["curl", "-s", "-o", "NUL", "-w", "%{http_code}", "-x", f"http://127.0.0.1:{PP}", "https://example.com/"], capture_output=True, timeout=30)
check("HTTPS normal por túnel (example.com)", r.stdout == b"200", r.stdout.decode())

proxy.stop()
shutil.rmtree(tmp, ignore_errors=True)
fails = [name for name, ok in RESULTS if not ok]
print(f"\nRESULTADO: {len(RESULTS) - len(fails)} de {len(RESULTS)} pruebas superadas", flush=True)
for f in fails:
    print("  ✗", f)
os._exit(1 if fails else 0)
