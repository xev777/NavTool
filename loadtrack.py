"""Seguimiento de las conexiones que pasan por el proxy (carga de sitios).

Cada conexión (petición HTTP o túnel HTTPS) es una fila con sitio, bytes y estado:
  active   → descargando ahora
  done     → terminó
  cut      → cortada por el usuario
  blocked  → bloqueada por la lista de dominios
"""
import socket
import threading
import time


class Loader:
    QUIET = 0.8        # un túnel HTTPS sin datos durante este tiempo se considera terminado
    HOLD = 4.0         # tras cortar todo, se rechazan conexiones nuevas durante este tiempo
    IDLE_CLEAR = 6.0   # tras este reposo se limpia la lista de la carga anterior
    NEW_LOAD_GAP = 1.5  # reposo mínimo para que una conexión nueva empiece una carga nueva

    def __init__(self):
        self.lock = threading.Lock()
        self.items = {}       # conexiones vivas: id -> {socks, kind, last, bytes}
        self.info = {}        # filas de la carga actual: id -> {host, kind, start, end, bytes, state}
        self.seq = 0
        self.hold_until = 0.0
        self.idle_since = None
        self.last = (0.0, 0, 0)   # (fracción, activas, total) de la última consulta

    # ---- estado global
    def held(self):
        return time.time() < self.hold_until

    def idle_for(self):
        with self.lock:
            return time.time() - self.idle_since if self.idle_since else 0.0

    def _new_load_if_idle(self, now):
        """Si todo lo anterior terminó hace un rato, esta conexión inicia una carga nueva."""
        if (self.idle_since and now - self.idle_since > self.NEW_LOAD_GAP
                and not any(r["state"] == "active" for r in self.info.values())):
            self.info.clear()

    # ---- alta / baja de conexiones
    def register(self, kind, socks, host=""):
        now = time.time()
        with self.lock:
            self._new_load_if_idle(now)
            self.seq += 1
            i = self.seq
            self.items[i] = {"socks": list(socks), "kind": kind, "last": now, "bytes": 0}
            self.info[i] = {"host": host, "kind": kind, "start": now, "end": None,
                            "bytes": 0, "state": "active"}
            self.idle_since = None
            return i

    def blocked(self, host, why="blocked"):
        """Anota un intento bloqueado (why: 'blocked' por lista, 'cut' por corte manual)."""
        now = time.time()
        with self.lock:
            self._new_load_if_idle(now)
            self.seq += 1
            self.info[self.seq] = {"host": host, "kind": "req", "start": now, "end": now,
                                   "bytes": 0, "state": why}

    def add_sock(self, i, sock):
        with self.lock:
            if i in self.items and sock:
                self.items[i]["socks"].append(sock)

    def bytes_of(self, i):
        with self.lock:
            it = self.items.get(i)
            return it["bytes"] if it else 0

    def touch(self, i, n=0):
        with self.lock:
            it = self.items.get(i)
            if it:
                it["last"] = time.time()
                it["bytes"] += n

    def unregister(self, i):
        with self.lock:
            it = self.items.pop(i, None)
            row = self.info.get(i)
            if it and row:
                row["bytes"] = it["bytes"]
                if row["state"] == "active":
                    row["state"] = "done"
                row["end"] = row["end"] or time.time()

    # ---- consulta para la interfaz
    def poll(self):
        """Actualiza estados y devuelve (fracción 0..1, activas, total)."""
        now = time.time()
        with self.lock:
            active = 0
            for i, row in self.info.items():
                if row["state"] in ("cut", "blocked"):
                    continue
                it = self.items.get(i)
                if it:
                    row["bytes"] = it["bytes"]
                    is_active = it["kind"] == "req" or now - it["last"] < self.QUIET
                    row["state"] = "active" if is_active else "done"
                    if not is_active and row["end"] is None:
                        row["end"] = it["last"]
                    active += is_active
                elif row["state"] == "active":
                    row["state"] = "done"
            total = len(self.info)
            finished = sum(1 for r in self.info.values() if r["state"] != "active")
            if active:
                self.idle_since = None
            elif self.idle_since is None:
                self.idle_since = now
            elif now - self.idle_since > self.IDLE_CLEAR:
                self.info.clear()
                total = finished = 0
            self.last = (finished / total if total else 0.0, active, total)
            return self.last

    def rows(self):
        with self.lock:
            return [dict(r, id=i) for i, r in self.info.items()]

    # ---- cortes
    @staticmethod
    def _close(socks):
        for s in socks:
            for op in (lambda: s.shutdown(socket.SHUT_RDWR), s.close):
                try:
                    op()
                except OSError:
                    pass

    def cut_item(self, i):
        with self.lock:
            it = self.items.pop(i, None)
            row = self.info.get(i)
            if row:
                row["state"] = "cut"
                row["end"] = time.time()
                if it:
                    row["bytes"] = it["bytes"]
            socks = it["socks"] if it else []
        self._close(socks)

    def cut(self):
        """Corta todo lo que se está cargando y rechaza lo nuevo unos segundos."""
        now = time.time()
        with self.lock:
            self.hold_until = now + self.HOLD
            socks = []
            for i, it in self.items.items():
                socks += it["socks"]
                row = self.info.get(i)
                if row and row["state"] == "active":
                    row["state"] = "cut"
                    row["end"] = now
                    row["bytes"] = it["bytes"]
            self.items.clear()
        self._close(socks)
        return len(socks)
