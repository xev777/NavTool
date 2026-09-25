"""Listas de bloqueo de TrafficBar: una incluida, otras descargables y las excepciones del usuario.

Seguridad de la descarga (una lista es una entrada externa que decide qué sitios se bloquean):
- solo HTTPS, con verificación de certificado, y las redirecciones tampoco pueden bajar a HTTP;
- tamaño máximo, tiempo máximo y máximo de dominios;
- cada línea se valida como nombre de dominio (nada de IPs, rutas ni comandos);
- una respuesta casi vacía se rechaza (evita reemplazar una buena lista por una página de error);
- las excepciones del usuario y unos pocos dominios esenciales NUNCA se bloquean.
"""
import ipaddress
import json
import os
import time
import urllib.error
import urllib.request

import privacy
from safety import valid_host

SOURCES = {
    "pgl": {
        "nombre": "Peter Lowe: publicidad y rastreo",
        "url": "https://pgl.yoyo.org/adservers/serverlist.php?hostformat=hosts&showintro=0&mimetype=plaintext",
        "aprox": "≈ 3.500 dominios",
    },
    "stevenblack": {
        "nombre": "StevenBlack: amplia (incluye malware)",
        "url": "https://raw.githubusercontent.com/StevenBlack/hosts/master/hosts",
        "aprox": "≈ 80.000 dominios",
    },
}
MAX_BYTES = 8 * 1024 * 1024
MAX_DOMAINS = 300_000
MIN_DOMAINS = 50            # menos que esto = respuesta basura, no una lista
TIMEOUT = 25
STALE_DAYS = 7
# Nunca se bloquean, aunque una lista (o el usuario, por error) los incluya.
NEVER_BLOCK = {"rdap.org", "pgl.yoyo.org", "raw.githubusercontent.com", "github.com",
               "microsoft.com", "windowsupdate.com", "msftconnecttest.com"}
_JUNK = {"localhost", "localhost.localdomain", "local", "broadcasthost", "ip6-localhost",
         "ip6-loopback", "ip6-localnet", "ip6-mcastprefix", "ip6-allnodes", "ip6-allrouters"}
_HOST_PREFIX = {"0.0.0.0", "127.0.0.1", "::1", "::", "255.255.255.255"}  # nosec B104: prefijo de archivos «hosts», no un enlace de red


def builtin_domains():
    """Lista incluida en TrafficBar: publicidad y analítica conocidas (sin redes sociales, que
    romperían inicios de sesión y botones de «compartir»)."""
    return set(privacy.ADS) | set(privacy.ANALYTICS)


def _is_ip(text):
    try:
        ipaddress.ip_address(text)
        return True
    except ValueError:
        return False


def parse_list(text):
    """Acepta formato «hosts» (0.0.0.0 dominio) o un dominio por línea. Devuelve solo dominios
    válidos, en minúsculas."""
    out = set()
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or len(line) > 300:
            continue
        parts = line.split()
        if len(parts) == 1:
            cand = parts[0]
        elif parts[0] in _HOST_PREFIX and len(parts) == 2:
            cand = parts[1]
        else:
            continue                                   # cualquier otro formato se ignora
        host = valid_host(cand)
        if not host or _is_ip(host):
            continue
        host = host.lower()
        if "." not in host or host in _JUNK:
            continue
        out.add(host)
        if len(out) >= MAX_DOMAINS:
            break
    return out


class _SoloHttps(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not newurl.lower().startswith("https://"):
            raise urllib.error.URLError("redirección a una dirección que no es HTTPS: rechazada")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _abrir(req, timeout):
    return urllib.request.build_opener(_SoloHttps).open(req, timeout=timeout)   # nosec B310: HTTPS


# --------------------------------------------------------------- almacenamiento
def _paths(carpeta, clave):
    return os.path.join(carpeta, f"{clave}.txt")


def meta(carpeta):
    try:
        with open(os.path.join(carpeta, "listas.json"), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _guardar_meta(carpeta, m):
    tmp = os.path.join(carpeta, "listas.json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(m, f, indent=1)
    os.replace(tmp, os.path.join(carpeta, "listas.json"))


def cargar(carpeta, clave):
    try:
        with open(_paths(carpeta, clave), encoding="utf-8") as f:
            return parse_list(f.read(MAX_BYTES))
    except OSError:
        return set()


def descargar(clave, carpeta, abrir=_abrir):
    """Descarga una lista, la valida y la guarda. Devuelve cuántos dominios tiene.
    Lanza ValueError/URLError/OSError con un mensaje legible si algo falla."""
    url = SOURCES[clave]["url"]
    if not url.startswith("https://"):
        raise ValueError("solo se admiten listas por HTTPS")
    os.makedirs(carpeta, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "TrafficBar (lista de bloqueo)"})
    with abrir(req, TIMEOUT) as r:
        data = r.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("la lista es demasiado grande")
    dominios = parse_list(data.decode("utf-8", "ignore"))
    if len(dominios) < MIN_DOMAINS:
        raise ValueError("la respuesta no parece una lista de dominios")
    tmp = _paths(carpeta, clave) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(sorted(dominios)) + "\n")
    os.replace(tmp, _paths(carpeta, clave))
    m = meta(carpeta)
    m[clave] = {"fecha": time.time(), "n": len(dominios)}
    _guardar_meta(carpeta, m)
    return len(dominios)


def desactualizada(carpeta, clave):
    f = meta(carpeta).get(clave, {}).get("fecha")
    return not isinstance(f, (int, float)) or time.time() - f > STALE_DAYS * 86400


# ------------------------------------------------------------------ combinación
def combinar(usuario, incluida, listas, excepciones):
    """Conjunto final de dominios bloqueados (sin las excepciones ni los esenciales)."""
    todo = set(usuario) | (builtin_domains() if incluida else set())
    for s in listas:
        todo |= s
    return todo - set(excepciones) - NEVER_BLOCK


def esta_bloqueado(host, bloqueados, excepciones):
    """Un dominio se bloquea si él o algún dominio padre está en la lista, salvo que él o algún
    padre esté en las excepciones (las excepciones ganan siempre)."""
    partes = (host or "").lower().split(".")
    for i in range(len(partes) - 1):
        d = ".".join(partes[i:])
        if d in excepciones or d in NEVER_BLOCK:
            return False
    return any(".".join(partes[i:]) in bloqueados for i in range(len(partes) - 1))


# --------------------------------------------------------- para medir (medir_ahorro.py)
def medicion_blocker(usar=("pgl",)):
    """Bloqueador con la lista inicial + incluida + listas descargadas (caché en /mediciones)."""
    import trafficbar
    carpeta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mediciones", "cache_listas")
    inicial = {l.strip() for l in trafficbar.DEFAULT_BLOCKLIST.splitlines() if l.strip()}
    sets = []
    for clave in usar:
        if desactualizada(carpeta, clave):
            print(f"  descargando lista «{clave}»…")
            print(f"    {descargar(clave, carpeta)} dominios")
        sets.append(cargar(carpeta, clave))
    total = combinar(inicial, True, sets, set())
    print(f"  bloqueador C: {len(total)} dominios")
    return lambda host: esta_bloqueado(host, total, set())
