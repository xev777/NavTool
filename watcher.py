"""Vigilante en segundo plano de NavTool.

- Detecta programas que salen a Internet por primera vez (o desde otra ruta) y avisa.
- Guarda el tráfico total por minuto (siempre) y por programa (si hay captura Npcap).
- Avisa de subidas de datos sostenidas o de un programa que envía mucho en un minuto.
"""
import collections
import ipaddress
import threading
import time

import psutil

import cuota
import programas
from i18n import tr
from safety import clean_text

MB = 1024 * 1024
COOLDOWN = 600          # no repetir la misma alerta durante 10 minutos
MAX_ALERTS = 12         # tope de alertas por cada 10 minutos (contra avalanchas de programas falsos)
UP_WINDOW = 20          # segundos de subida sostenida que disparan el aviso
SCAN_EVERY = 3          # segundos entre lecturas de la tabla de conexiones
TOUCH_EVERY = 30        # segundos entre actualizaciones de "último uso" en la base


def is_public(ip):
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return not (a.is_private or a.is_loopback or a.is_link_local or a.is_multicast
                or a.is_unspecified or a.is_reserved)


class Watcher(threading.Thread):
    def __init__(self, hist, get_cfg, notify, get_engine=lambda: None):
        super().__init__(daemon=True, name="NavTool-watcher")
        self.hist, self.get_cfg, self.notify, self.get_engine = hist, get_cfg, notify, get_engine
        self.stop_evt = threading.Event()
        self.baseline_pending = hist.program_count() == 0   # primera vez: aprender sin avisar
        self.known = set()
        self.by_name = collections.defaultdict(set)          # nombre -> rutas conocidas
        for p in hist.programs():
            self.known.add(p["key"])
            self.by_name[p["name"].lower()].add((p["path"] or "").lower())
        self.pinfo = {}                                      # pid -> (name, path)
        self.seen_pairs = {}                                 # (nombre, ip) -> ts del último registro
        self.touch_acc = collections.Counter()
        self.cool = {}
        self.alert_times = collections.deque(maxlen=MAX_ALERTS)
        self.up_win = collections.deque(maxlen=UP_WINDOW)
        self.minute = None
        self.acc_d = self.acc_u = 0
        self.eng_last = {}
        self.next_scan = self.next_touch = self.next_quota = self.next_expire = 0.0

    # ---- ciclo principal
    def run(self):
        last = psutil.net_io_counters()
        while not self.stop_evt.wait(1.0):
            try:
                now = time.time()
                io = psutil.net_io_counters()
                dd, du = max(0, io.bytes_recv - last.bytes_recv), max(0, io.bytes_sent - last.bytes_sent)
                last = io
                self.acc_d += dd
                self.acc_u += du
                self.check_upload(du)
                if now >= self.next_scan:
                    self.next_scan = now + SCAN_EVERY
                    self.scan()
                if now >= self.next_touch:
                    self.next_touch = now + TOUCH_EVERY
                    self.flush_touch()
                if now >= self.next_quota:                    # cuota mensual: avisa al 80 % y al 100 %
                    self.next_quota = now + 300
                    cuota.comprobar_alertas(self.hist, self.get_cfg(), self.alert)
                if now >= self.next_expire:                   # bloqueos temporales vencidos
                    self.next_expire = now + 60
                    for nombre in programas.caducados():
                        self.alert("unblocked", f"{nombre} volvió a tener acceso a Internet",
                                   "Terminó el tiempo del bloqueo temporal.", nombre)
                m = int(now // 60) * 60
                if self.minute is None:
                    self.minute = m
                elif m != self.minute:
                    self.flush_minute()
                    self.minute = m
            except Exception:
                pass
        try:
            self.flush_minute()
        except Exception:
            pass

    def stop(self):
        self.stop_evt.set()

    # ---- programas nuevos
    def _proc_info(self, pid):
        if pid not in self.pinfo:
            try:
                p = psutil.Process(pid)
                name = p.name()
                try:
                    path = p.exe()
                except psutil.Error:
                    path = ""
            except psutil.Error:
                name, path = f"PID {pid}", ""
            self.pinfo[pid] = (clean_text(name, 60), clean_text(path, 300))
            if len(self.pinfo) > 2000:
                self.pinfo.clear()
        return self.pinfo[pid]

    @staticmethod
    def key_of(name, path):
        return f"{name.lower()}|{(path or '').lower()}"

    def scan(self):
        conns = []
        for c in psutil.net_connections(kind="inet"):
            if c.raddr and c.pid and c.status in ("ESTABLISHED", "SYN_SENT") \
                    and is_public(c.raddr.ip):
                conns.append((c.pid, c.raddr.ip, c.raddr.port))
        self.process_connections(conns, self._proc_info)

    def process_connections(self, conns, info):
        """conns: [(pid, ip_remota, puerto)]; info(pid) -> (nombre, ruta)."""
        first, now = self.baseline_pending, time.time()
        for pid, ip, port in conns:
            name, path = info(pid)
            key = self.key_of(name, path)
            if key not in self.known and self.hist.program(key) is None:
                others = {p for p in self.by_name[name.lower()] if p != (path or "").lower()}
                self.hist.add_program(key, name, path, baseline=first)
                if not first:
                    self._alert_new(name, path, ip, port, others)
            self.known.add(key)
            self.by_name[name.lower()].add((path or "").lower())
            self.touch_acc[key] += 1
            pair = (name.lower(), ip)
            if now - self.seen_pairs.get(pair, 0) > 3600:
                if len(self.seen_pairs) > 50000:
                    self.seen_pairs.clear()
                self.seen_pairs[pair] = now
                self.hist.add_conn(now, name, ip, port, self._host(ip))
        self.baseline_pending = False

    def flush_touch(self):
        for key, n in self.touch_acc.items():
            self.hist.touch_program(key, n)
        self.touch_acc.clear()

    def _host(self, ip):
        eng = self.get_engine()
        if eng:
            return eng.dns.get(ip) or eng.rdns.get(ip) or ""
        return ""

    def _alert_new(self, name, path, ip, port, others):
        where = path or "ruta desconocida"
        if others:
            self.alert("path", "Un programa conocido se ejecuta desde otra ubicación",
                       f"{name} ya se había visto en {', '.join(sorted(o for o in others if o)) or 'otra ruta'}; "
                       f"ahora corre desde {where} y se conecta a {ip}:{port}. Si no lo esperabas, "
                       "puede ser un programa que se hace pasar por otro.", name)
        else:
            self.alert("new", "Nuevo programa con acceso a Internet",
                       f"{name} se conectó por primera vez a {ip}:{port}. Ruta: {where}.", name)

    # ---- alertas
    def alert(self, kind, title, detail, proc=""):
        now = time.time()
        if now - self.cool.get((kind, proc), 0) < COOLDOWN:
            return False
        if len(self.alert_times) == MAX_ALERTS and now - self.alert_times[0] < COOLDOWN:
            return False                       # demasiadas seguidas: se descarta el exceso
        self.alert_times.append(now)
        self.cool[(kind, proc)] = now
        if len(self.cool) > 5000:
            self.cool.clear()
        title, detail = tr(title), tr(detail)          # se guarda en el idioma activo
        self.hist.add_alert(kind, title, detail, proc)
        try:
            self.notify(title, detail if len(detail) < 200 else detail[:197] + "…")
        except Exception:
            pass
        return True

    def check_upload(self, up_bytes):
        self.up_win.append(up_bytes)
        if len(self.up_win) < UP_WINDOW:
            return
        avg = sum(self.up_win) / len(self.up_win)
        if avg < float(self.get_cfg().get("alert_up_mb_s", 3.0)) * MB:
            return
        who = "No se pudo saber qué programa la causa: activa el monitoreo por programa (Historial → Alertas)."
        top = ""
        eng = self.get_engine()
        if eng:
            per = collections.Counter()
            for r in eng.snapshot()["rows"]:
                per[r["proc"]] += r["ru"]
            if per:
                top, up = per.most_common(1)[0]
                who = f"El programa que más envía ahora es {top} ({up / MB:.1f} MB/s)."
        self.alert("upload", "Subida de datos sostenida",
                   f"Tu equipo envía {avg / MB:.1f} MB/s desde hace {UP_WINDOW} s. {who}", top)

    # ---- tráfico por minuto
    def flush_minute(self):
        if self.minute is None:
            return
        if self.acc_d or self.acc_u:
            self.hist.add_minute(self.minute, self.acc_d, self.acc_u)
        self.acc_d = self.acc_u = 0
        eng = self.get_engine()
        if not eng:
            return
        per = collections.defaultdict(lambda: [0, 0])
        for r in eng.snapshot()["rows"]:
            prev = self.eng_last.get(r["id"], (0, 0))
            if r["down"] < prev[0] or r["up"] < prev[1]:
                prev = (0, 0)
            per[r["proc"]][0] += r["down"] - prev[0]
            per[r["proc"]][1] += r["up"] - prev[1]
            self.eng_last[r["id"]] = (r["down"], r["up"])
        limit = float(self.get_cfg().get("alert_proc_mb_min", 100.0)) * MB
        for proc, (d, u) in per.items():
            if d or u:
                self.hist.add_proc_minute(self.minute, proc, d, u)
            if u > limit:
                self.alert("proc_upload", f"{proc} envió mucho en un minuto",
                           f"{proc} subió {u / MB:.0f} MB en el último minuto.", proc)
