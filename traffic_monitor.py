"""Monitor de tráfico de red de TrafficBar (Npcap, sin librerías de terceros para los paquetes).

Captura todos los paquetes que entran y salen del equipo, los agrupa en
"conversaciones" (programa ↔ destino ↔ servicio) y los muestra en lenguaje claro.
"""
import collections
import csv
import ipaddress
import os
import queue
import socket
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import psutil

import pcap
from i18n import tr
from netparse import ip_text, parse_dns, parse_frame
from safety import bring_to_front, clean_text, powershell_exe
from tooltip import tip

MAX_FLOWS = 30000        # tope de conexiones seguidas (protege ante inundaciones de paquetes)
MAX_CONVS = 5000
MAX_CACHE = 20000

# --------------------------------------------------------------------- vocabulario
SERVICES = {
    ("TCP", 443): ("Web segura (HTTPS)", "web"),
    ("UDP", 443): ("Web moderna (QUIC / HTTP3)", "web"),
    ("TCP", 80): ("Web sin cifrar (HTTP)", "web"),
    ("TCP", 8080): ("Web (HTTP alterno)", "web"),
    ("TCP", 5228): ("Notificaciones push de Google", "web"),
    ("UDP", 53): ("Consulta de nombres (DNS)", "dns"),
    ("TCP", 53): ("Consulta de nombres (DNS)", "dns"),
    ("TCP", 853): ("DNS cifrado (DoT)", "dns"),
    ("UDP", 123): ("Sincronizar la hora (NTP)", "system"),
    ("UDP", 67): ("Asignación de IP (DHCP)", "system"),
    ("UDP", 68): ("Asignación de IP (DHCP)", "system"),
    ("UDP", 5353): ("Descubrir dispositivos (mDNS)", "local"),
    ("UDP", 5355): ("Descubrir nombres locales (LLMNR)", "local"),
    ("UDP", 1900): ("Descubrir dispositivos (UPnP/SSDP)", "local"),
    ("UDP", 3702): ("Descubrir dispositivos (WS-Discovery)", "local"),
    ("UDP", 137): ("Nombres de Windows (NetBIOS)", "local"),
    ("UDP", 138): ("Nombres de Windows (NetBIOS)", "local"),
    ("TCP", 139): ("Archivos compartidos (SMB)", "local"),
    ("TCP", 445): ("Archivos compartidos (SMB)", "local"),
    ("TCP", 22): ("Acceso remoto seguro (SSH)", "remote"),
    ("TCP", 3389): ("Escritorio remoto (RDP)", "remote"),
    ("TCP", 5900): ("Escritorio remoto (VNC)", "remote"),
    ("TCP", 25): ("Correo: envío (SMTP)", "mail"),
    ("TCP", 465): ("Correo: envío seguro", "mail"),
    ("TCP", 587): ("Correo: envío (SMTP)", "mail"),
    ("TCP", 110): ("Correo: recepción (POP3)", "mail"),
    ("TCP", 995): ("Correo: recepción segura", "mail"),
    ("TCP", 143): ("Correo: recepción (IMAP)", "mail"),
    ("TCP", 993): ("Correo: recepción segura (IMAP)", "mail"),
    ("UDP", 3478): ("Llamadas de voz/video (STUN)", "web"),
    ("UDP", 19302): ("Llamadas de voz/video (Google)", "web"),
    ("TCP", 1935): ("Video en vivo (RTMP)", "web"),
    ("UDP", 51820): ("VPN (WireGuard)", "remote"),
    ("UDP", 1194): ("VPN (OpenVPN)", "remote"),
}

CATEGORY_COLOR = {
    "web": "#6cc0ff", "dns": "#c39bff", "local": "#8fa0b5", "ads": "#ff6b6b",
    "mail": "#ffd166", "remote": "#ff9f43", "system": "#7fd6a6", "other": "#e8eef7",
    "inbound": "#ff9f43", "telemetry": "#c9a227",
}
CATEGORY_NAME = {
    "web": "Navegación / internet", "dns": "Nombres (DNS)", "local": "Red local",
    "ads": "Publicidad / rastreo", "mail": "Correo", "remote": "Acceso remoto / VPN",
    "system": "Sistema", "other": "Otro", "inbound": "Entrante", "telemetry": "Telemetría / diagnóstico",
}

COMPANIES = [
    (("google.com", "googleapis.com", "gstatic.com", "googlevideo.com", "youtube.com",
      "ytimg.com", "ggpht.com", "gvt1.com", "1e100.net", "googleusercontent.com"), "Google"),
    (("microsoft.com", "windows.com", "windowsupdate.com", "live.com", "office.com",
      "office365.com", "msedge.net", "azure.com", "msn.com", "bing.com", "skype.com",
      "microsoftonline.com", "azureedge.net", "trafficmanager.net", "msftconnecttest.com"),
     "Microsoft"),
    (("facebook.com", "fbcdn.net", "instagram.com", "whatsapp.net", "whatsapp.com",
      "facebook.net", "fb.com", "cdninstagram.com"), "Meta"),
    (("amazon.com", "amazonaws.com", "cloudfront.net", "amazon-adsystem.com", "primevideo.com"),
     "Amazon"),
    (("apple.com", "icloud.com", "mzstatic.com", "aaplimg.com"), "Apple"),
    (("netflix.com", "nflxvideo.net", "nflxso.net"), "Netflix"),
    (("spotify.com", "scdn.co"), "Spotify"),
    (("tiktok.com", "tiktokcdn.com", "byteoversea.com"), "TikTok"),
    (("akamai.net", "akamaiedge.net", "akamaitechnologies.com"), "Akamai (CDN)"),
    (("cloudflare.com", "cloudflare-dns.com"), "Cloudflare"),
    (("github.com", "githubusercontent.com"), "GitHub"),
    (("anthropic.com", "claude.ai"), "Anthropic"),
    (("discord.com", "discordapp.com", "discord.gg"), "Discord"),
    (("steampowered.com", "steamcontent.com", "valvesoftware.com"), "Steam"),
]

# Servidores conocidos de telemetría/diagnóstico: un programa que contacta con ellos está enviando
# datos de uso, fallos o rendimiento a su fabricante, no navegando ni sincronizando contenido.
# Lista no exhaustiva, pensada para avisar de lo más común, no para bloquear.
TELEMETRY = (
    "vortex.data.microsoft.com", "vortex-win.data.microsoft.com", "settings-win.data.microsoft.com",
    "watson.telemetry.microsoft.com", "watson.ppe.telemetry.microsoft.com", "telemetry.microsoft.com",
    "telecommand.telemetry.microsoft.com", "oca.telemetry.microsoft.com", "oca.microsoft.com",
    "wes.df.telemetry.microsoft.com", "sqm.telemetry.microsoft.com", "survey.watson.microsoft.com",
    "watson.microsoft.com", "self.events.data.microsoft.com", "browser.events.data.msn.com",
    "eu-mobile.events.data.microsoft.com", "us-mobile.events.data.microsoft.com",
    "diagnostics.support.microsoft.com", "functional.events.data.microsoft.com",
    "metrics.icloud.com", "diagassets.apple.com", "gs-loc.apple.com",
    "sentry.io", "bugsnag.com", "crashlytics.com", "firebase-settings.crashlytics.com",
    "app-measurement.com", "mixpanel.com", "amplitude.com", "segment.io", "segment.com",
    "appsflyer.com", "adjust.com", "branch.io", "fullstory.com", "heap.io",
    "newrelic.com", "nr-data.net", "datadoghq.com", "hockeyapp.net", "appcenter.ms",
    "google-analytics.com", "analytics.google.com", "clarity.ms", "app-analytics-services.com",
)

SPARK = "▁▂▃▄▅▆▇█"


def is_telemetry(host):
    h = (host or "").lower()
    return any(h == s or h.endswith("." + s) for s in TELEMETRY)


def company_of(host):
    h = (host or "").lower()
    for suffixes, name in COMPANIES:
        if any(h == s or h.endswith("." + s) for s in suffixes):
            return name
    return ""


def human(n):
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {u}" if u == "B" else f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} TB"


def human_rate(n):
    return "·" if n <= 0 else human(n) + "/s"


def ip_kind(ip):
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return "public"
    if a.is_multicast or (a.is_private and ip.endswith(".255")):
        return "multicast"
    if a.is_private or a.is_link_local or a.is_loopback:
        return "private"
    return "public"


def describe(proto, port, remote_ip, host):
    text, cat = _describe(proto, port, remote_ip, host)
    return tr(text), cat


def _describe(proto, port, remote_ip, host):
    if proto == "ICMP":
        return "Ping / diagnóstico de red (ICMP)", "system"
    svc = SERVICES.get((proto, port))
    if svc:
        text, cat = svc
    elif port == 0:
        text, cat = f"{proto} (varios puertos)", "other"
    else:
        text, cat = f"{proto} puerto {port}", "other"
    kind = ip_kind(remote_ip)
    if kind in ("private", "multicast") and cat in ("other", "web"):
        cat = "local"
        text = tr(text) + " " + tr("· red local" if kind == "private" else "· difusión local")
    return text, cat


# -------------------------------------------------------------- lectores de paquetes
def parse_sni(d):
    """Extrae el nombre del servidor (SNI) de un TLS ClientHello."""
    try:
        if len(d) < 44 or d[0] != 0x16 or d[5] != 1:
            return None
        i = 43
        i += 1 + d[i]
        i += 2 + int.from_bytes(d[i:i + 2], "big")
        i += 1 + d[i]
        if i > len(d):
            return None
        end = min(i + 2 + int.from_bytes(d[i:i + 2], "big"), len(d))
        i += 2
        while i + 4 <= end:
            t = int.from_bytes(d[i:i + 2], "big")
            n = int.from_bytes(d[i + 2:i + 4], "big")
            i += 4
            if t == 0:
                ln = int.from_bytes(d[i + 3:i + 5], "big")
                return d[i + 5:i + 5 + ln].decode("ascii", "ignore") or None
            i += n
    except (IndexError, ValueError):
        pass
    return None


def parse_http_host(d):
    if d[:4] in (b"GET ", b"POST", b"HEAD", b"PUT ", b"DELE", b"OPTI") or d[:5] == b"PATCH":
        k = d.find(b"\r\nHost:")
        if k >= 0:
            e = d.find(b"\r\n", k + 7)
            return d[k + 7:e if e > 0 else None].decode("ascii", "ignore").strip().split(":")[0] or None
    return None


# --------------------------------------------------------------------------- motor
class Flow:
    __slots__ = ("proto", "lip", "lport", "rip", "rport", "down", "up", "pkts", "first", "last",
                 "inbound", "sni", "http", "hello", "conv", "cd", "cu", "proc", "miss")

    def __init__(self, proto, lip, lport, rip, rport, inbound, now):
        self.proto, self.lip, self.lport, self.rip, self.rport = proto, lip, lport, rip, rport
        self.inbound = inbound
        self.down = self.up = self.pkts = self.cd = self.cu = 0
        self.first = self.last = now
        self.sni = self.http = None
        self.hello = b""
        self.conv = None
        self.proc = None
        self.miss = 0


class Conv:
    def __init__(self, cid, key, now):
        self.id, self.key = cid, key
        self.proc, self.host, self.proto, self.svc_port, self.inbound = key
        self.down = self.up = self.pkts = self.nflows = 0
        self.tick_down = self.tick_up = 0
        self.first = self.last = now
        self.ip = ""
        self.hist = collections.deque(maxlen=20)
        self.name_src = "ninguno"
        self.remote_ports = set()


class Engine:
    def __init__(self, is_ad=lambda host: False):
        self.lock = threading.Lock()
        self.is_ad = is_ad
        self.flows, self.convs = {}, {}
        self.dns, self.rdns = {}, {}
        self.procmap = {}
        self.pnames = {}
        self.events = collections.deque(maxlen=600)
        self.ev_seq = 0
        self.dns_log = collections.deque(maxlen=800)
        self.dns_pending = {}
        self.hist = collections.deque(maxlen=120)
        self.session_down = self.session_up = 0
        self.total_pkts = 0
        self.cid = 0
        self.paused = False
        self.running = False
        self.sniffer = None
        self.procpath = {}        # nombre de programa -> ruta de su .exe
        self.clientpid = {}       # puerto local del navegador -> pid (para atribuir lo que pasa por el proxy)
        self.socks = []
        self.ipstr = {}
        self.io_base = None
        self.locals = set()
        self.rq = queue.Queue()
        self.oq = queue.Queue()
        self.owner = {}          # ip -> dueño (RDAP), solo si el usuario lo activa
        self.use_rdap = False
        self.error = None
        self.iface_desc = ""

    # ---- ciclo de vida
    def start(self, iface_name=None):
        self.stop()
        self.rq, self.oq = queue.Queue(2000), queue.Queue(2000)  # acotadas; sin señales viejas
        self.error = None
        self.locals = set()
        for addrs in psutil.net_if_addrs().values():
            for a in addrs:
                if a.family in (socket.AF_INET, socket.AF_INET6):
                    self.locals.add(a.address.split("%")[0])
        devs = pcap.dispositivos()
        util = [d for d in devs if any(not ip.startswith(("169.254", "127.", "0.")) for ip in d["ips"])]
        por_desc = {d["description"]: d for d in util}
        if iface_name == "__all__":
            chosen = util
            self.iface_desc = "todas las interfaces activas"
        else:
            if iface_name in por_desc:
                chosen = [por_desc[iface_name]]
            else:
                ip = pcap.ip_de_salida()                    # la tarjeta por la que sale a Internet
                chosen = [d for d in devs if ip and ip in d["ips"]] or util[:1]
            self.iface_desc = chosen[0]["description"] if chosen else ""
        self.running = True
        self.socks = []
        for d in chosen:
            try:
                self.socks.append(pcap.Captura(d["name"]))
            except Exception as e:
                self.error = str(e)
        if not self.socks:
            self.running = False
            raise OSError(self.error or "no se pudo abrir ninguna interfaz")
        self.sniffer = True
        self.io_base = psutil.net_io_counters()
        for s in self.socks:
            threading.Thread(target=self._reader, args=(s,), daemon=True).start()
        for target in (self._tick_loop, self._proc_loop, self._dnscache_loop, *[self._rdns_loop] * 8,
                       *[self._owner_loop] * 3):
            threading.Thread(target=target, daemon=True).start()

    def stop(self):
        self.running = False
        for q, n in ((self.rq, 8), (self.oq, 3)):       # despierta a los hilos para que terminen
            for _ in range(n):
                try:
                    q.put_nowait(None)
                except queue.Full:
                    pass                                # llena: los hilos ya están ocupados y saldrán solos
        for s in self.socks:                            # los lectores salen al ver running=False
            try:
                s.close()
            except Exception:
                pass
        self.socks = []
        self.sniffer = None

    def clear(self):
        with self.lock:
            self.flows.clear()
            self.convs.clear()
            self.events.clear()
            self.dns_log.clear()
            self.hist.clear()
            self.session_down = self.session_up = self.total_pkts = 0
            try:
                self.io_base = psutil.net_io_counters()
            except Exception:
                pass

    # ---- captura
    def _reader(self, sock):
        """Lee paquetes en bruto y solo interpreta las cabeceras necesarias (ver netparse.py)."""
        if sock.dlt != 1:                                   # solo Ethernet / Wi-Fi
            return
        while self.running:
            try:
                raw, n = sock.next()
                if raw is not None:
                    self._fast(raw, n)
            except Exception:
                if not self.running:
                    return
                time.sleep(0.01)

    def _ip(self, b):
        s = self.ipstr.get(b)
        if s is None:
            if len(self.ipstr) > 20000:
                self.ipstr.clear()
            s = self.ipstr[b] = ip_text(b)
        return s

    def _fast(self, raw, n=None):
        """Camino rápido: paquetes de conexiones ya conocidas (casi todo el tráfico de una descarga)."""
        if self.paused:
            return
        n = n or len(raw)
        if len(raw) < 54:
            return self._slow(raw, n)
        et, o = raw[12:14], 14
        if et == b"\x81\x00":
            et, o = raw[16:18], 18
        if et == b"\x08\x00":
            if raw[o + 6] & 0x1f or raw[o + 7]:               # fragmento
                return self._slow(raw, n)
            proto, l4 = raw[o + 9], o + (raw[o] & 15) * 4
            a, b = raw[o + 12:o + 16], raw[o + 16:o + 20]
        elif et == b"\x86\xdd":
            proto, l4 = raw[o + 6], o + 40
            a, b = raw[o + 8:o + 24], raw[o + 24:o + 40]
        else:
            return
        if proto not in (6, 17) or len(raw) < l4 + 8:
            return self._slow(raw, n)                           # ICMP y demás: pocos
        src, dst = self._ip(a), self._ip(b)
        sp, dp = (raw[l4] << 8) | raw[l4 + 1], (raw[l4 + 2] << 8) | raw[l4 + 3]
        out = src in self.locals
        if out:
            key = ("TCP" if proto == 6 else "UDP", src, sp, dst, dp)
        elif dst in self.locals:
            key = ("TCP" if proto == 6 else "UDP", dst, dp, src, sp)
        else:
            return self._slow(raw, n)
        f = self.flows.get(key)
        if f is None or (proto == 17 and (sp == 53 or dp == 53)) or (
                proto == 6 and out and f.sni is None and f.http is None and f.pkts < 12):
            return self._slow(raw, n)                           # flujo nuevo / nombre por descubrir
        with self.lock:
            self.total_pkts += 1
            f.pkts += 1
            f.last = time.time()
            if out:
                f.up += n
            else:
                f.down += n

    def _slow(self, raw, size):
        """Camino completo: conexiones nuevas, primeros paquetes (nombre del sitio) y DNS."""
        if self.paused:
            return
        try:
            fr = parse_frame(raw)
            if fr is None:
                return
            src, dst = ip_text(fr.src), ip_text(fr.dst)
            proto, sp, dp = fr.proto, fr.sport, fr.dport
            out = src in self.locals
            if not out and dst not in self.locals and ip_kind(dst) != "multicast":
                return
            if out:
                lip, lport, rip, rport = src, sp, dst, dp
            else:
                lip, lport, rip, rport = dst, dp, src, sp
            now = time.time()
            key = (proto, lip, lport, rip, rport)
            with self.lock:
                self.total_pkts += 1
                f = self.flows.get(key)
                if f is None:
                    if len(self.flows) >= MAX_FLOWS:      # inundación: se ignora lo nuevo
                        return
                    syn_in = (proto == "TCP" and not out and (fr.flags & 0x12) == 0x02)
                    f = self.flows[key] = Flow(proto, lip, lport, rip, rport,
                                               syn_in or (proto == "UDP" and not out and
                                                          rport > 1023 and lport < 1024), now)
                f.pkts += 1
                f.last = now
                if out:
                    f.up += size
                else:
                    f.down += size
                if proto == "TCP" and out and f.sni is None and f.http is None and f.pkts < 12:
                    payload = bytes(raw[fr.poff:fr.pend])
                    if payload:
                        if payload[:2] == b"\x16\x03" or f.hello:
                            f.hello = (f.hello + payload)[:6000]
                            f.sni = clean_text(parse_sni(f.hello) or "", 253) or None
                        else:
                            f.http = clean_text(parse_http_host(payload) or "", 253) or None
                elif proto == "UDP" and 53 in (sp, dp):
                    msg = parse_dns(raw[fr.poff:fr.pend])
                    if msg:
                        self._on_dns(msg, out, now, rip)
        except Exception:
            pass

    def _on_dns(self, dns, out, now, resolver):
        """Las respuestas solo cuentan si responden a una consulta que hizo ESTE equipo y vienen
        del servidor al que se preguntó: así un paquete DNS falso no puede cambiar el nombre
        con el que ves un destino. `dns` es un netparse.Dns."""
        name = clean_text(dns.qname.rstrip("."), 253)
        qtype = {1: "IPv4", 28: "IPv6", 5: "alias", 15: "correo", 16: "texto", 65: "https"
                 }.get(dns.qtype, str(dns.qtype))
        if dns.qr == 0 and out:
            row = [now, name, qtype, "…"]
            self.dns_log.append(row)
            if len(self.dns_pending) > 2000:
                self.dns_pending.clear()
            self.dns_pending[(dns.id, name)] = (row, resolver)
            self._event("🔎", f"Tu equipo preguntó por «{name}»", "dns")
        elif dns.qr == 1 and not out:
            pending = self.dns_pending.pop((dns.id, name), None)
            if pending is None or pending[1] != resolver:
                self.dns_log.append([now, name, qtype, "⚠ respuesta no solicitada (ignorada)"])
                return
            row = pending[0]
            ips = []
            for ip in dns.answers[:32]:
                try:
                    ipaddress.ip_address(ip)
                except ValueError:
                    continue
                ips.append(ip)
                if len(self.dns) > MAX_CACHE:
                    self.dns.clear()
                self.dns[ip] = name
            row[3] = ", ".join(ips[:3]) if ips else ("no existe" if dns.rcode == 3 else "sin respuesta útil")

    def _event(self, icon, text, cat):
        self.ev_seq += 1
        self.events.append((self.ev_seq, time.time(), icon, tr(text), cat))

    # ---- hilos auxiliares
    def _proc_loop(self):
        while self.running:
            try:
                snap, cl = {}, {}
                me = os.getpid()
                for c in psutil.net_connections(kind="inet"):
                    if c.laddr and c.pid:  # pid 0 = socket ya cerrado (TIME_WAIT)
                        proto = "TCP" if c.type == socket.SOCK_STREAM else "UDP"
                        snap[(proto, c.laddr.port)] = c.pid
                        if proto == "TCP" and c.laddr.ip == "127.0.0.1" and c.pid != me:
                            cl[c.laddr.port] = c.pid
                self.clientpid = cl
                for pid in set(snap.values()) | {me}:
                    self._pname(pid)
                for k, pid in snap.items():
                    self.procmap[k] = (self.pnames[pid], time.time())
                cutoff = time.time() - 90
                for k in [k for k, v in self.procmap.items() if v[1] < cutoff]:
                    self.procmap.pop(k, None)
            except Exception:
                pass
            time.sleep(0.4)

    def _pname(self, pid):
        if pid not in self.pnames:
            try:
                p = psutil.Process(pid)
                self.pnames[pid] = clean_text(p.name(), 60)
                try:
                    if len(self.procpath) < 2000:
                        self.procpath[self.pnames[pid]] = p.exe()
                except psutil.Error:
                    pass
            except psutil.Error:
                self.pnames[pid] = "Sistema" if pid in (0, 4) else f"PID {pid}"
        return self.pnames[pid]

    def _via_proxy(self, f):
        """Si la conexión la abrió el proxy de TrafficBar para un navegador, devuelve ese programa."""
        try:
            import proxy_core
            cport = proxy_core.UPSTREAM.get(f.lport)
        except Exception:
            return None
        pid = self.clientpid.get(cport) if cport else None
        return self._pname(pid) if pid else None

    def _dnscache_loop(self):
        """Nombres resueltos por Windows (sirve aunque el DNS vaya cifrado, p. ej. YogaDNS)."""
        import json
        import subprocess  # nosec B404
        cmd = [powershell_exe(), "-NoProfile", "-NonInteractive", "-Command",
               "Get-DnsClientCache | Select-Object Entry,Data,Type | ConvertTo-Json -Compress"]
        known = set()
        while self.running:
            try:
                out = subprocess.run(cmd, capture_output=True, timeout=20,  # nosec B603
                                     creationflags=0x08000000).stdout.decode("utf-8", "ignore")
                data = json.loads(out) if out.strip() else []
                if isinstance(data, dict):
                    data = [data]
                now = time.time()
                for d in data:
                    if d.get("Type") in (1, 28) and d.get("Data") and d.get("Entry"):
                        ip, name = str(d["Data"]).split("%")[0], clean_text(str(d["Entry"]).rstrip("."), 253)
                        try:
                            ipaddress.ip_address(ip)
                        except ValueError:
                            continue
                        if len(self.dns) > MAX_CACHE:
                            self.dns.clear()
                        self.dns.setdefault(ip, name)
                        if (ip, name) not in known:
                            known.add((ip, name))
                            if len(known) > 60:  # la primera lectura es historial, no se anuncia
                                self.dns_log.append([now, name, "IPv6" if ":" in ip else "IPv4",
                                                     ip + "  (caché de Windows)"])
            except Exception:
                pass
            for _ in range(40):
                if not self.running:
                    return
                time.sleep(0.1)

    def _owner_loop(self):
        """Dueño de la IP vía RDAP (consulta online, solo si el usuario lo activó)."""
        import json
        import urllib.request
        while self.running:
            ip = self.oq.get()
            if ip is None:
                break
            name = ""
            try:
                ipaddress.ip_address(ip)                 # nunca se arma la URL con texto libre
                req = urllib.request.Request(f"https://rdap.org/ip/{ip}",
                                             headers={"Accept": "application/rdap+json"})
                with urllib.request.urlopen(req, timeout=8) as resp:  # nosec B310: https fijo
                    d = json.loads(resp.read(300_000))
                name = d.get("name") or ""
                for ent in d.get("entities", []):
                    vc = ent.get("vcardArray", [None, []])[1]
                    fn = next((x[3] for x in vc if x and x[0] == "fn"), "")
                    if fn and "registrant" in ent.get("roles", []):
                        name = fn
                        break
                if d.get("country"):
                    name += f" ({d['country']})"
            except Exception:
                pass
            self.owner[ip] = clean_text(name, 80)      # lo escribe el dueño de la IP: no es de fiar

    def _rdns_loop(self):
        while self.running:
            ip = self.rq.get()
            if ip is None:
                break
            try:
                if len(self.rdns) > MAX_CACHE:
                    self.rdns.clear()
                self.rdns[ip] = clean_text(socket.gethostbyaddr(ip)[0], 253)
            except OSError:
                self.rdns[ip] = ""

    def _tick_loop(self):
        while self.running:
            time.sleep(1.0)
            try:
                self._tick()
            except Exception:
                pass

    def _host_of(self, f):
        """Nombre + de dónde sale. Ojo: SNI, HTTP e inverso los declara el propio programa o el
        dueño de la IP; no están verificados (la IP sí es real)."""
        if f.sni:
            return f.sni, "SNI: lo declara el programa al conectarse (no verificado)"
        if f.http:
            return f.http, "cabecera HTTP (la declara el programa; no verificada)"
        n = self.dns.get(f.rip)
        if n:
            return n, "consulta DNS de tu equipo"
        n = self.rdns.get(f.rip)
        if n:
            return n, "DNS inverso (lo declara el dueño de la IP; no verificado)"
        # Solo destinos que iniciamos nosotros: preguntar por IPs que nos contactan sin que lo
        # pidamos permitiría a un atacante provocar consultas DNS/RDAP y llenar la memoria.
        if not f.inbound and ip_kind(f.rip) == "public":
            if f.rip not in self.rdns and len(self.rdns) < MAX_CACHE:
                self.rdns[f.rip] = None
                try:
                    self.rq.put_nowait(f.rip)
                except queue.Full:
                    self.rdns.pop(f.rip, None)
            if self.use_rdap and f.rip not in self.owner and len(self.owner) < MAX_CACHE:
                self.owner[f.rip] = None
                try:
                    self.oq.put_nowait(f.rip)
                except queue.Full:
                    self.owner.pop(f.rip, None)
        return f.rip, "ninguno"

    def _tick(self):
        now = time.time()
        with self.lock:
            for c in self.convs.values():
                c.tick_down = c.tick_up = 0
            tot_d = tot_u = 0
            for key, f in list(self.flows.items()):
                if f.proc is None:
                    p = self.procmap.get((f.proto, f.lport))
                    if p and p[0] == self.pnames.get(os.getpid()) and f.proto == "TCP" and f.miss < 4:
                        f.proc = self._via_proxy(f)     # lo pidió un navegador a través de TrafficBar
                        if f.proc is None:
                            f.miss += 1
                            if f.miss >= 4:
                                f.proc = p[0]           # conexión propia de TrafficBar
                    elif p:
                        f.proc = p[0]
                    elif f.proto == "ICMP":
                        f.proc = "Sistema"
                    else:
                        f.miss += 1
                        if f.miss > 6:
                            f.proc = "(no identificado)"
                host, src = self._host_of(f)
                svc_port = f.lport if f.inbound else f.rport
                if svc_port > 10000 and not f.inbound:
                    svc_port = 0
                ckey = (f.proc or "…", host, f.proto, svc_port, f.inbound)
                conv = f.conv
                if conv is None or conv.key != ckey:
                    new = self.convs.get(ckey)
                    if new is None and len(self.convs) >= MAX_CONVS:
                        ckey = (f.proc or "…", "(muchos destinos)", f.proto, 0, f.inbound)
                        new = self.convs.get(ckey)
                    if new is None:
                        self.cid += 1
                        new = self.convs[ckey] = Conv(self.cid, ckey, now)
                        new.ip = f.rip
                        new.name_src = src
                        if ckey[0] != "…":
                            self._announce(new, f)
                    if conv is not None:
                        conv.down -= f.cd
                        conv.up -= f.cu
                        conv.nflows -= 1
                        if conv.nflows <= 0 and conv.down + conv.up <= 0:
                            self.convs.pop(conv.key, None)
                    new.down += f.cd
                    new.up += f.cu
                    new.nflows += 1
                    conv = f.conv = new
                dd, du = f.down - f.cd, f.up - f.cu
                if dd or du:
                    conv.down += dd
                    conv.up += du
                    conv.tick_down += dd
                    conv.tick_up += du
                    conv.last = f.last
                    f.cd, f.cu = f.down, f.up
                    tot_d += dd
                    tot_u += du
                conv.remote_ports.add(f.rport)
                if now - f.last > 120:
                    conv.nflows -= 1
                    del self.flows[key]
            for c in self.convs.values():
                c.hist.append(c.tick_down + c.tick_up)
            self.hist.append((tot_d, tot_u))
            self.session_down += tot_d
            self.session_up += tot_u
            for k in [k for k, c in self.convs.items() if c.nflows <= 0 and now - c.last > 900]:
                del self.convs[k]

    def _announce(self, c, f):
        who = c.proc if not c.proc.startswith("(") else "Un programa"
        svc, _ = describe(c.proto, c.svc_port, f.rip, c.host)
        comp = company_of(c.host)
        dest = c.host + (f" ({comp})" if comp else "")
        if c.inbound:
            self._event("⚠", f"Alguien desde {f.rip} intentó conectarse a tu {who} "
                             f"(puerto {f.lport}) — {svc}", "inbound")
        elif self.is_ad(c.host):
            self._event("🚫", f"{who} contactó con un servidor de publicidad/rastreo: {dest}", "ads")
        elif is_telemetry(c.host):
            self._event("📊", f"{who} envió telemetría/diagnóstico a: {dest}", "telemetry")
        else:
            self._event("↗", f"{who} se conectó con {dest} — {svc}", "web")

    # ---- lectura para la interfaz
    def snapshot(self):
        with self.lock:
            now = time.time()
            rows = []
            for c in self.convs.values():
                host = c.host
                svc, cat = describe(c.proto, c.svc_port, c.ip, host)
                if self.is_ad(host):
                    cat = "ads"
                elif c.inbound:
                    cat = "inbound"
                elif is_telemetry(host):
                    cat = "telemetry"
                rows.append({
                    "id": c.id, "proc": c.proc, "path": self.procpath.get(c.proc, ""), "host": host, "company": company_of(host),
                    "ip": c.ip, "owner": self.owner.get(c.ip) or "", "proto": c.proto, "port": c.svc_port, "service": svc,
                    "cat": cat, "down": c.down, "up": c.up, "rd": c.tick_down, "ru": c.tick_up,
                    "hist": list(c.hist), "first": c.first, "last": c.last, "nflows": c.nflows,
                    "active": now - c.last < 5, "inbound": c.inbound, "src": c.name_src,
                })
            rd = ru = 0
            try:                                     # lo que dice la tarjeta de red (verdad de referencia)
                io, b0 = psutil.net_io_counters(), self.io_base
                if b0 is not None:
                    rd, ru = max(0, io.bytes_recv - b0.bytes_recv), max(0, io.bytes_sent - b0.bytes_sent)
            except Exception:
                pass
            drops = recv = 0
            for c in self.socks:
                try:
                    a, b = c.stats()
                    recv += a
                    drops += b
                except Exception:
                    pass
            return {
                "drops": drops, "recv": recv, "real_down": rd, "real_up": ru,
                "rows": rows, "hist": list(self.hist), "sd": self.session_down,
                "su": self.session_up, "pkts": self.total_pkts,
                "events": list(self.events), "dns": list(self.dns_log),
                "nflows": len(self.flows), "iface": self.iface_desc,
            }


# ---------------------------------------------------------------------------- GUI
BG, PANEL, FG, MUTED = "#14202f", "#1b2a41", "#e8eef7", "#8ea3bd"
DOWN_C, UP_C = "#3fa9f5", "#ffa94d"


class TrafficWindow(tk.Toplevel):
    def __init__(self, master, is_ad, engine=None):
        super().__init__(master, bg=BG)
        self.title("TrafficBar – Tráfico de red")
        self.geometry("1120x720")
        if hasattr(master, "place_near"):
            master.place_near(self, 1120, 720)
        self.attributes("-topmost", False)
        self.shared = engine is not None          # captura de segundo plano de TrafficBar
        self.engine = engine or Engine(is_ad)
        self.seen_events = 0
        self.iface_choice = None
        self._style()
        self._build()
        self.protocol("WM_DELETE_WINDOW", self._close)
        if not self.shared:
            self._start_capture(None)
        else:
            self.pause_btn.config(state="disabled", text="En segundo plano")
        self.after(500, self.refresh)
        self.lift()
        self.attributes("-topmost", True)  # al frente al abrir; luego vuelve a ser normal
        self.after(400, lambda: self.attributes("-topmost", False))
        bring_to_front(self)      # sin simular Alt: eso dejaba la ventana en blanco hasta hacer clic
        self.focus_force()

    def _style(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure("Treeview", background="#0f1a2b", fieldbackground="#0f1a2b",
                    foreground=FG, rowheight=int(26 * getattr(self.master, 'ui_scale', 1.0)), borderwidth=0, font=("Segoe UI", 9))
        s.configure("Treeview.Heading", background=PANEL, foreground=MUTED, relief="flat",
                    font=("Segoe UI", 9, "bold"))
        s.map("Treeview", background=[("selected", "#27405f")])
        s.configure("TNotebook", background=BG, borderwidth=0)
        s.configure("TNotebook.Tab", background=PANEL, foreground=MUTED, padding=(14, 6),
                    font=("Segoe UI", 10))
        s.map("TNotebook.Tab", background=[("selected", "#27405f")],
              foreground=[("selected", "white")])
        s.configure("TCombobox", fieldbackground="#0f1a2b", background=PANEL, foreground=FG,
                    arrowcolor=FG, bordercolor=PANEL, lightcolor=PANEL, darkcolor=PANEL)
        s.map("TCombobox", fieldbackground=[("readonly", "#0f1a2b")],
              foreground=[("readonly", FG)], selectbackground=[("readonly", "#0f1a2b")],
              selectforeground=[("readonly", FG)])
        self.option_add("*TCombobox*Listbox.background", "#0f1a2b")
        self.option_add("*TCombobox*Listbox.foreground", FG)
        self.option_add("*TCombobox*Listbox.selectBackground", "#27405f")
        s.configure("Vertical.TScrollbar", background="#27405f", troughcolor="#0f1a2b",
                    bordercolor="#0f1a2b", arrowcolor=FG, lightcolor="#27405f",
                    darkcolor="#27405f")

    def _card(self, parent, title, color):
        f = tk.Frame(parent, bg=PANEL, padx=14, pady=8)
        tk.Label(f, text=title, bg=PANEL, fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w")
        big = tk.Label(f, text="–", bg=PANEL, fg=color, font=("Segoe UI", 20, "bold"))
        big.pack(anchor="w")
        small = tk.Label(f, text="", bg=PANEL, fg=MUTED, font=("Segoe UI", 9))
        small.pack(anchor="w")
        f.pack(side="left", fill="x", expand=True, padx=4)
        return big, small

    def _button(self, parent, text, cmd, accent=False):
        b = tk.Button(parent, text=text, command=cmd, relief="flat", bd=0, padx=12, pady=4,
                      bg="#3fa9f5" if accent else "#27405f", fg="white", cursor="hand2",
                      activebackground="#5cb8ff", font=("Segoe UI", 9))
        b.pack(side="left", padx=3)
        return b

    def _build(self):
        cards = tk.Frame(self, bg=BG)
        cards.pack(fill="x", padx=10, pady=(10, 4))
        self.c_down = self._card(cards, "↓ BAJADA (lo que recibes)", DOWN_C)
        self.c_up = self._card(cards, "↑ SUBIDA (lo que envías)", UP_C)
        self.c_conn = self._card(cards, "CONVERSACIONES ACTIVAS", "#7fd6a6")
        self.c_tot = self._card(cards, "TOTAL DESDE QUE ABRISTE", FG)
        tip(self.c_down[0].master, "Velocidad a la que llegan datos a tu equipo ahora mismo, sumando "
                                   "todos los programas.")
        tip(self.c_up[0].master, "Velocidad a la que tu equipo envía datos ahora mismo. Si es alta "
                                 "sin que estés subiendo nada, revisa qué programa la causa.")
        tip(self.c_conn[0].master, "Conversaciones = un programa hablando con un destino por un "
                                   "servicio. Cuenta las que han movido datos en los últimos 5 s.")
        tip(self.c_tot[0].master, "Datos bajados (↓) y subidos (↑) desde que abriste este monitor.")

        self.summary = tk.Label(self, text="Esperando tráfico…", bg=BG, fg=FG, anchor="w",
                                font=("Segoe UI", 11), wraplength=1080, justify="left")
        self.summary.pack(fill="x", padx=14, pady=(2, 2))
        self.alert = tk.Label(self, text="", bg=BG, fg="#ff9f43", anchor="w",
                              font=("Segoe UI", 9))
        self.alert.pack(fill="x", padx=14)

        self.graph = tk.Canvas(self, height=120, bg="#0f1a2b", highlightthickness=0)
        self.graph.pack(fill="x", padx=14, pady=4)
        tip(self.graph, "Tráfico del último minuto. Azul = bajada, naranja = subida. La escala se "
                        "ajusta al pico.")

        ctl = tk.Frame(self, bg=BG)
        ctl.pack(fill="x", padx=10, pady=4)
        self.pause_btn = self._button(ctl, "⏸ Pausar", self.toggle_pause)
        tip(self.pause_btn, "Congela la captura para poder leer con calma. No pierde lo ya visto.")
        tip(self._button(ctl, "🗑 Limpiar", self.engine_clear),
            "Vacía las listas y los totales de esta sesión (no borra el historial guardado).")
        tip(self._button(ctl, "💾 Exportar CSV", self.export_csv),
            "Guarda la lista de conversaciones en un archivo CSV para abrirla en Excel.")
        tip(self._button(ctl, "🚫 Bloqueados", lambda: self.master.win_blocked()),
            "Programas a los que TrafficBar quitó el acceso a Internet. Para bloquear uno: clic derecho "
            "sobre su fila.")
        tk.Label(ctl, text="  Buscar:", bg=BG, fg=MUTED).pack(side="left")
        self.q = tk.StringVar()
        search = tk.Entry(ctl, textvariable=self.q, width=22, bg="#0f1a2b", fg=FG,
                          insertbackground=FG, relief="flat")
        search.pack(side="left", padx=4, ipady=3)
        tip(search, "Filtra por programa, sitio, empresa, servicio o IP.")
        self.only_active = tk.BooleanVar(value=True)
        cb1 = tk.Checkbutton(ctl, text="Solo activas", variable=self.only_active, bg=BG, fg=FG,
                             selectcolor=PANEL, activebackground=BG, activeforeground=FG)
        cb1.pack(side="left", padx=6)
        tip(cb1, "Muestra solo lo que ha movido datos en los últimos 5 segundos. Sin marcar, "
                 "también las conversaciones ya terminadas.")
        self.hide_local = tk.BooleanVar(value=False)
        cb2 = tk.Checkbutton(ctl, text="Ocultar red local", variable=self.hide_local, bg=BG,
                             fg=FG, selectcolor=PANEL, activebackground=BG, activeforeground=FG)
        cb2.pack(side="left", padx=6)
        tip(cb2, "Oculta el ruido de tu red doméstica: descubrimiento de dispositivos, archivos "
                 "compartidos, router...")
        self.rdap = tk.BooleanVar(value=False)
        cb3 = tk.Checkbutton(ctl, text="Identificar dueño de IPs (consulta online)", variable=self.rdap,
                             command=self._toggle_rdap, bg=BG, fg=FG, selectcolor=PANEL,
                             activebackground=BG, activeforeground=FG)
        cb3.pack(side="left", padx=6)
        tip(cb3, "Para IPs sin nombre, pregunta a un servicio público (rdap.org) de quién son "
                 "(Amazon, Google...).\nEnvía esas IPs fuera de tu equipo: por eso está apagado y "
                 "pide confirmación.")
        self.iface_cb = ttk.Combobox(ctl, state="readonly", width=40)
        self.iface_cb.pack(side="right")
        tip(self.iface_cb, "Tarjeta de red que se vigila. «Automática» = la que sale a Internet.")
        self.iface_cb.bind("<<ComboboxSelected>>", self._change_iface)
        self._fill_ifaces()

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=10, pady=(4, 10))
        self.nb = nb
        nb.bind("<<NotebookTabChanged>>", lambda e: self.after(20, self.redraw_tabs))

        t1 = tk.Frame(nb, bg=BG)
        nb.add(t1, text="  Conversaciones  ")
        cols = ("proc", "dest", "svc", "rd", "ru", "tot", "spark")
        self.tree = ttk.Treeview(t1, columns=cols, show="headings", selectmode="browse")
        for c, txt, w, anc in (("proc", "Programa", 130, "w"), ("dest", "Con quién habla", 300, "w"),
                               ("svc", "Qué está haciendo", 230, "w"), ("rd", "↓ ahora", 80, "e"),
                               ("ru", "↑ ahora", 80, "e"), ("tot", "Total ↓ / ↑", 130, "e"),
                               ("spark", "Actividad (20 s)", 140, "w")):
            self.tree.heading(c, text=txt)
            self.tree.column(c, width=w, anchor=anc)
        for cat, color in CATEGORY_COLOR.items():
            self.tree.tag_configure(cat, foreground=color)
        self.tree.tag_configure("idle", foreground="#5f7390")
        sb = ttk.Scrollbar(t1, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<Double-1>", self.show_detail)
        self.tree.bind("<Button-3>", self._row_menu)
        self.row_data = {}
        tip(self.tree, area=self._tree_tip)

        t2 = tk.Frame(nb, bg=BG)
        nb.add(t2, text="  Por programa  ")
        self.prog = tk.Canvas(t2, bg="#0f1a2b", highlightthickness=0)
        self.prog.pack(fill="both", expand=True)

        t3 = tk.Frame(nb, bg=BG)
        nb.add(t3, text="  Qué está pasando  ")
        self.feed = tk.Text(t3, bg="#0f1a2b", fg=FG, relief="flat", font=("Segoe UI", 10),
                            wrap="word", state="disabled", padx=10, pady=8, spacing1=3)
        for cat, color in CATEGORY_COLOR.items():
            self.feed.tag_configure(cat, foreground=color)
        self.feed.tag_configure("time", foreground="#5f7390")
        self.feed.pack(fill="both", expand=True)

        t4 = tk.Frame(nb, bg=BG)
        nb.add(t4, text="  Nombres consultados (DNS)  ")
        self.dns_tree = ttk.Treeview(t4, columns=("t", "n", "k", "a"), show="headings")
        for c, txt, w in (("t", "Hora", 80), ("n", "Nombre por el que preguntó tu equipo", 380),
                          ("k", "Tipo", 80), ("a", "Respuesta (IP)", 360)):
            self.dns_tree.heading(c, text=txt)
            self.dns_tree.column(c, width=w, anchor="w")
        self.dns_tree.pack(fill="both", expand=True)

    # ---- captura
    def _fill_ifaces(self):
        try:
            names = [d["description"] for d in pcap.dispositivos()
                     if any(not ip.startswith(("169.254", "127.", "0.")) for ip in d["ips"])]
        except Exception:
            names = []
        self.iface_cb["values"] = ["Automática (la que sale a internet)",
                                   "Todas las interfaces activas"] + names
        self.iface_cb.current(0)

    def _change_iface(self, _e=None):
        i = self.iface_cb.current()
        self._start_capture(None if i == 0 else "__all__" if i == 1 else self.iface_cb.get())

    def _start_capture(self, choice):
        try:
            self.engine.start(choice)
        except Exception as e:
            messagebox.showerror("TrafficBar", f"No se pudo iniciar la captura:\n{e}\n\n"
                                 "Comprueba que Npcap está instalado y que TrafficBar se "
                                 "ejecuta como administrador.", parent=self)

    def _toggle_rdap(self):
        if self.rdap.get() and not messagebox.askyesno(
                "TrafficBar", "Para saber de quién es una IP desconocida, TrafficBar enviará esa "
                "IP (no tu contenido ni tu nombre) a un servicio público de registros de "
                "Internet (rdap.org).\n\n¿Activar?", parent=self):
            self.rdap.set(False)
        self.engine.use_rdap = self.rdap.get()
        if self.engine.use_rdap:  # reintenta las que ya quedaron sin nombre
            self.engine.owner = {k: v for k, v in self.engine.owner.items() if v}

    def toggle_pause(self):
        self.engine.paused = not self.engine.paused
        self.pause_btn.config(text="▶ Reanudar" if self.engine.paused else "⏸ Pausar")

    def engine_clear(self):
        self.engine.clear()
        self.tree.delete(*self.tree.get_children())
        self.feed.config(state="normal")
        self.feed.delete("1.0", "end")
        self.feed.config(state="disabled")
        self.dns_tree.delete(*self.dns_tree.get_children())
        self.seen_events = 0

    def _close(self):
        if not self.shared:                       # la captura compartida sigue en segundo plano
            self.engine.stop()
        self.destroy()

    # ---- refresco
    def refresh(self):
        if not self.winfo_exists():
            return
        snap = self.engine.snapshot()
        self._draw_cards(snap)
        self._draw_graph(snap["hist"])
        rows = self._filtered(snap["rows"])
        self._fill_tree(rows)
        if self.nb.index("current") == 1:
            self._draw_programs(snap["rows"])
        self._fill_feed(snap["events"])
        if self.nb.index("current") == 3:
            self._fill_dns(snap["dns"])
        self.title(f"TrafficBar – Tráfico de red · capturando: {snap['iface']}")
        self.after(1000, self.refresh)

    def redraw_tabs(self):
        snap = self.engine.snapshot()
        i = self.nb.index("current")
        if i == 1:
            self._draw_programs(snap["rows"])
        elif i == 3:
            self._fill_dns(snap["dns"])

    def _filtered(self, rows):
        q = self.q.get().strip().lower()
        out = []
        for r in rows:
            if self.only_active.get() and not r["active"]:
                continue
            if self.hide_local.get() and r["cat"] == "local":
                continue
            if q and q not in f"{r['proc']} {r['host']} {r['service']} {r['company']} {r['ip']}".lower():
                continue
            out.append(r)
        out.sort(key=lambda r: (r["rd"] + r["ru"], r["last"]), reverse=True)
        return out[:400]

    def _draw_cards(self, s):
        d, u = (s["hist"][-1] if s["hist"] else (0, 0))
        self.c_down[0].config(text=human_rate(d) if d else "0 B/s")
        self.c_down[1].config(text=f"máx 1 min: {human_rate(max([x[0] for x in s['hist'][-60:]] or [0]))}")
        self.c_up[0].config(text=human_rate(u) if u else "0 B/s")
        self.c_up[1].config(text=f"máx 1 min: {human_rate(max([x[1] for x in s['hist'][-60:]] or [0]))}")
        act = [r for r in s["rows"] if r["active"]]
        self.c_conn[0].config(text=str(len(act)))
        cov = ""
        if s["real_down"] > 50e6:                       # comparar con la tarjeta de red, para no engañar
            pct = s["sd"] * 100 / s["real_down"]
            cov = f" · ve {pct:.0f} % de la tarjeta" if pct < 85 else ""
        if s.get("drops"):
            cov += f" · Npcap descartó {s['drops']:,} paquetes"
        self.c_conn[1].config(text=f"{s['nflows']} conexiones · {s['pkts']:,} paquetes{cov}")
        self.c_tot[0].config(text=f"↓ {human(s['sd'])}")
        self.c_tot[1].config(text=f"↑ {human(s['su'])}")
        if act:
            top = max(act, key=lambda r: r["rd"] + r["ru"])
            if top["rd"] + top["ru"] > 0:
                who = top["host"] + (f" ({top['company']})" if top["company"] else "")
                verb = tr("descarga de" if top["rd"] >= top["ru"] else "envía datos a")
                self.summary.config(
                    text=f"Ahora mismo lo que más tráfico mueve: {top['proc']} {verb} {who} "
                         f"— {top['service']} ({human_rate(top['rd'] + top['ru'])}).")
            else:
                self.summary.config(text="Hay conexiones abiertas pero casi sin movimiento.")
        else:
            self.summary.config(text="Red tranquila: no hay actividad ahora mismo.")
        inbound = [r for r in s["rows"] if r["inbound"] and r["active"]]
        ads = [r for r in s["rows"] if r["cat"] == "ads" and r["active"]]
        msg = []
        if inbound:
            msg.append(f"⚠ {len(inbound)} intento(s) de conexión ENTRANTE activos")
        if ads:
            msg.append(f"🚫 {len(ads)} conversación(es) con publicidad/rastreo")
        self.alert.config(text="   ".join(msg))

    def _draw_graph(self, hist):
        c = self.graph
        c.delete("all")
        w, h = max(c.winfo_width(), 200), 120
        data = hist[-60:]
        peak = max([max(a, b) for a, b in data] or [0]) or 1
        peak = max(peak, 1024)
        for i in range(1, 4):
            y = h - 16 - (h - 26) * i / 3
            c.create_line(0, y, w, y, fill="#1d2c42")
        c.create_text(6, 6, anchor="nw", fill=MUTED, font=("Segoe UI", 8),
                      text=f"máx {human_rate(peak)}")
        c.create_text(w - 6, h - 4, anchor="se", fill=MUTED, font=("Segoe UI", 8),
                      text="ahora")
        c.create_text(6, h - 4, anchor="sw", fill=MUTED, font=("Segoe UI", 8), text="hace 60 s")
        if len(data) < 2:
            return
        step = (w - 12) / 59
        x0 = w - 6 - step * (len(data) - 1)
        for idx, color in ((0, DOWN_C), (1, UP_C)):
            pts = [(x0 + i * step, h - 16 - (h - 26) * v[idx] / peak) for i, v in enumerate(data)]
            poly = [x0, h - 16] + [p for xy in pts for p in xy] + [pts[-1][0], h - 16]
            c.create_polygon(poly, fill=color, stipple="gray50" if idx else "", outline="")
            c.create_line([p for xy in pts for p in xy], fill=color, width=2)

    HEAD_TIPS = {
        "proc": "Programa de tu equipo que abrió la conexión.",
        "dest": "Con quién habla. La IP es real; el nombre lo declara el programa o el dueño de la "
                "IP y no está verificado.",
        "svc": "Qué servicio parece ser, según el puerto (443 = web segura, 53 = DNS...).",
        "rd": "Velocidad de bajada de esta conversación ahora mismo.",
        "ru": "Velocidad de subida de esta conversación ahora mismo.",
        "tot": "Total desde que abriste el monitor: bajado / subido.",
        "spark": "Actividad de los últimos 20 segundos (más alto = más tráfico).",
    }

    def _tree_tip(self, x, y):
        cols = self.tree["columns"]
        if self.tree.identify_region(x, y) == "heading":
            try:
                return self.HEAD_TIPS.get(cols[int(self.tree.identify_column(x)[1:]) - 1])
            except (ValueError, IndexError):
                return None
        r = self.row_data.get(self.tree.identify_row(y))
        if not r:
            return None
        text = (f"{r['proc']} ↔ {r['host']}\n{r['service']}\nIP {r['ip']} · {r['nflows']} "
                f"conexión(es)\nNombre: {r['src']}")
        if r["inbound"]:
            text += "\n⚠ ENTRANTE: alguien de fuera contactó con este programa."
        if r["cat"] == "ads":
            text += "\nEstá en tu lista de publicidad / rastreo."
        if r["cat"] == "telemetry":
            text += "\nEs un servidor de telemetría/diagnóstico conocido: TrafficBar lo registra, no lo bloquea."
        return text + "\n(Doble clic: detalle completo)"

    def _fill_tree(self, rows):
        self.row_data = {str(r["id"]): r for r in rows}
        existing = set(self.tree.get_children())
        wanted = []
        for r in rows:
            iid = str(r["id"])
            wanted.append(iid)
            hist = r["hist"] or [0]
            m = max(hist) or 1
            spark = "".join(SPARK[min(7, int(v / m * 7.999))] if v else "▁" for v in hist)
            dest = r["host"]
            if r["company"]:
                dest += f"  ·  {r['company']}"
            elif dest == r["ip"] and r["cat"] != "local":
                dest += f"  ·  {r['owner']}" if r["owner"] else "  " + tr("(sin nombre)")
            svc = ("↙ ENTRANTE: " if r["inbound"] else "") + r["service"]
            vals = (r["proc"], dest, svc, human_rate(r["rd"]), human_rate(r["ru"]),
                    f"{human(r['down'])} / {human(r['up'])}", spark)
            tags = (r["cat"] if r["active"] else "idle",)
            if iid in existing:
                self.tree.item(iid, values=vals, tags=tags)
            else:
                self.tree.insert("", "end", iid=iid, values=vals, tags=tags)
        for iid in existing - set(wanted):
            self.tree.delete(iid)
        if list(self.tree.get_children()) != wanted:
            for i, iid in enumerate(wanted):
                self.tree.move(iid, "", i)

    def _draw_programs(self, rows):
        c = self.prog
        c.delete("all")
        agg = collections.defaultdict(lambda: [0, 0, 0, 0])
        for r in rows:
            a = agg[r["proc"]]
            a[0] += r["down"]
            a[1] += r["up"]
            a[2] += r["rd"] + r["ru"]
            a[3] += 1
        items = sorted(agg.items(), key=lambda kv: kv[1][0] + kv[1][1], reverse=True)[:14]
        w = max(c.winfo_width(), 500)
        top = max([a[0] + a[1] for _, a in items] or [1]) or 1
        c.create_text(14, 12, anchor="nw", fill=MUTED, font=("Segoe UI", 9),
                      text="Quién usa tu conexión (total desde que abriste el monitor). "
                           "Azul = bajada, naranja = subida.")
        y = 44
        for name, (d, u, rate, n) in items:
            c.create_text(14, y, anchor="nw", fill=FG, font=("Segoe UI", 10, "bold"), text=name)
            c.create_text(w - 14, y, anchor="ne", fill=MUTED, font=("Segoe UI", 9),
                          text=f"↓ {human(d)}   ↑ {human(u)}   · ahora {human_rate(rate)} · {n} conv.")
            bw = w - 28
            c.create_rectangle(14, y + 20, 14 + bw, y + 30, fill="#1d2c42", width=0)
            dw = bw * d / top
            uw = bw * u / top
            c.create_rectangle(14, y + 20, 14 + dw, y + 30, fill=DOWN_C, width=0)
            c.create_rectangle(14 + dw, y + 20, 14 + dw + uw, y + 30, fill=UP_C, width=0)
            y += 46

    def _fill_feed(self, events):
        new = [e for e in events if e[0] > self.seen_events]
        if not new:
            return
        self.seen_events = new[-1][0]
        atbottom = self.feed.yview()[1] > 0.97
        self.feed.config(state="normal")
        for _, ts, icon, text, cat in new:
            self.feed.insert("end", time.strftime("%H:%M:%S  ", time.localtime(ts)), "time")
            self.feed.insert("end", f"{icon} {text}\n", cat)
        lines = int(self.feed.index("end-1c").split(".")[0])
        if lines > 700:
            self.feed.delete("1.0", f"{lines - 600}.0")
        self.feed.config(state="disabled")
        if atbottom:
            self.feed.see("end")

    def _fill_dns(self, dns):
        self.dns_tree.delete(*self.dns_tree.get_children())
        for ts, name, kind, ans in reversed(dns[-300:]):
            self.dns_tree.insert("", "end", values=(time.strftime("%H:%M:%S", time.localtime(ts)),
                                                    name, kind, ans))

    def _row_menu(self, e):
        iid = self.tree.identify_row(e.y)
        r = self.row_data.get(iid)
        if not r:
            return
        self.tree.selection_set(iid)
        m = tk.Menu(self, tearoff=0, bg=BG, fg=FG, activebackground="#3fa9f5", activeforeground="white",
                    font=("Segoe UI", 10))
        m.add_command(label=f"🚫 Bloquear el acceso a Internet de «{r['proc']}»…",
                      command=lambda: self.block_program(r))
        m.add_command(label="Detalle de la conversación", command=self.show_detail)
        try:
            m.tk_popup(e.x_root, e.y_root)
        finally:
            m.grab_release()

    def block_program(self, r):
        import programas
        path = r.get("path") or ""
        if not path:
            messagebox.showinfo("TrafficBar", "No se pudo saber dónde está el programa (quizá ya se cerró).",
                                parent=self)
            return
        if not programas.es_admin():
            messagebox.showinfo("TrafficBar", "Bloquear requiere permisos de administrador.", parent=self)
            return
        mins = programas.preguntar(self, r["proc"], path)
        if mins is None:
            return
        ok, why = programas.bloquear(path, mins)
        if ok:
            messagebox.showinfo("TrafficBar", f"«{r['proc']}» ya no tiene acceso a Internet. "
                                "Puedes deshacerlo en 🚫 Bloqueados.", parent=self)
        else:
            messagebox.showerror("TrafficBar", why, parent=self)

    def show_detail(self, _e=None):
        sel = self.tree.selection()
        if not sel:
            return
        snap = self.engine.snapshot()
        r = next((x for x in snap["rows"] if str(x["id"]) == sel[0]), None)
        if not r:
            return
        t = tk.Toplevel(self, bg=BG)
        t.title("Detalle de la conversación")
        t.geometry("560x420")
        who = r["host"] + (f" ({r['company']})" if r["company"] else
                           f" ({r['owner']})" if r["owner"] else "")
        lines = [
            (f"{r['proc']}  ↔  {who}", "h"),
            ("", ""),
            (f"En palabras simples: el programa «{r['proc']}» "
             + ("recibió un intento de conexión desde " if r["inbound"] else "se comunica con ")
             + f"{who}, usando {r['service']}.", ""),
            ("", ""),
            (f"Categoría:        {CATEGORY_NAME.get(r['cat'], r['cat'])}", ""),
            (f"IP:               {r['ip']}", ""),
            (f"Protocolo/puerto: {r['proto']} / {r['port'] or 'varios'}", ""),
            (f"Nombre obtenido:  {r['src']}", ""),
            (f"Conexiones:      {r['nflows']} abiertas", ""),
            (f"Bajado:          {human(r['down'])}", ""),
            (f"Subido:          {human(r['up'])}", ""),
            (f"Primera vez:     {time.strftime('%H:%M:%S', time.localtime(r['first']))}", ""),
            (f"Última actividad: {time.strftime('%H:%M:%S', time.localtime(r['last']))}", ""),
        ]
        if r["proto"] == "TCP" and r["port"] in (443, 5228):
            lines += [("", ""), ("El contenido va cifrado: solo se ve a dónde va y cuánto "
                                 "tráfico mueve, no lo que dice.", "m")]
        if r["cat"] == "ads":
            lines += [("", ""), ("Este dominio está en tu lista de publicidad/rastreo. Puedes "
                                 "bloquearlo desde TrafficBar > Filtros.", "m")]
        if r["cat"] == "telemetry":
            lines += [("", ""), ("Este es un servidor de telemetría/diagnóstico conocido: el programa "
                                 "envía datos de uso o de fallos a su fabricante. TrafficBar solo lo "
                                 "registra en 📊 Telemetría detectada; no corta la conexión.", "m")]
        if r["inbound"]:
            lines += [("", ""), ("Una conexión ENTRANTE es alguien de fuera hablando con tu "
                                 "equipo. Es normal en juegos, torrents o compartir archivos; "
                                 "si no esperabas nada de eso, investígalo.", "m")]
        box = tk.Text(t, bg="#0f1a2b", fg=FG, relief="flat", font=("Consolas", 10), wrap="word",
                      padx=12, pady=10)
        box.tag_configure("h", font=("Segoe UI", 13, "bold"), foreground="#6cc0ff")
        box.tag_configure("m", foreground="#ffd166")
        for text, tag in lines:
            box.insert("end", text + "\n", tag)
        box.config(state="disabled")
        box.pack(fill="both", expand=True, padx=8, pady=8)

    def export_csv(self):
        path = filedialog.asksaveasfilename(parent=self, defaultextension=".csv",
                                            filetypes=[("CSV", "*.csv")],
                                            initialfile="trafico_naviscope.csv")
        if not path:
            return
        snap = self.engine.snapshot()
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["Programa", "Destino", "Empresa", "IP", "Protocolo", "Puerto",
                        "Servicio", "Categoría", "Bajado (bytes)", "Subido (bytes)",
                        "Entrante", "Primera vez", "Última vez"])
            for r in sorted(snap["rows"], key=lambda r: r["down"] + r["up"], reverse=True):
                w.writerow([r["proc"], r["host"], r["company"], r["ip"], r["proto"], r["port"],
                            r["service"], CATEGORY_NAME.get(r["cat"], r["cat"]), r["down"],
                            r["up"], "sí" if r["inbound"] else "no",
                            time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(r["first"])),
                            time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(r["last"]))])
        messagebox.showinfo("TrafficBar", f"Exportado en:\n{path}", parent=self)
