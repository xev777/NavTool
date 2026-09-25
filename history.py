"""Historial local de TrafficBar (SQLite): informes de páginas, programas, tráfico y alertas."""
import contextlib
import json
import sqlite3
import threading
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY, ts REAL, main TEXT, grade TEXT, score INTEGER, n_hosts INTEGER,
    trackers INTEGER, active_trackers INTEGER, protected INTEGER, bytes INTEGER, body TEXT);
CREATE TABLE IF NOT EXISTS programs (
    key TEXT PRIMARY KEY, name TEXT, path TEXT, first_seen REAL, last_seen REAL,
    baseline INTEGER DEFAULT 0, conns INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS minute (ts INTEGER PRIMARY KEY, down INTEGER, up INTEGER);
CREATE TABLE IF NOT EXISTS proc_minute (
    ts INTEGER, proc TEXT, down INTEGER, up INTEGER, PRIMARY KEY (ts, proc));
CREATE TABLE IF NOT EXISTS conn_log (
    id INTEGER PRIMARY KEY, ts REAL, proc TEXT, remote TEXT, port INTEGER, host TEXT);
CREATE INDEX IF NOT EXISTS conn_ts ON conn_log (ts);
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY, ts REAL, kind TEXT, title TEXT, detail TEXT, proc TEXT,
    seen INTEGER DEFAULT 0);
"""


class History:
    def __init__(self, path):
        self.path = path
        self.lock = threading.Lock()   # una sola escritura a la vez
        with self._db() as c:
            c.executescript(SCHEMA)
            c.execute("PRAGMA journal_mode=WAL")

    @contextlib.contextmanager
    def _db(self):
        c = sqlite3.connect(self.path, timeout=15)
        c.row_factory = sqlite3.Row
        try:
            yield c
            c.commit()
        finally:
            c.close()

    def _w(self, sql, args=()):
        with self.lock, self._db() as c:
            return c.execute(sql, args).lastrowid

    def _r(self, sql, args=()):
        with self._db() as c:
            return [dict(r) for r in c.execute(sql, args).fetchall()]

    # ---- informes de páginas
    def add_report(self, r):
        return self._w("INSERT INTO reports (ts, main, grade, score, n_hosts, trackers, "
                       "active_trackers, protected, bytes, body) VALUES (?,?,?,?,?,?,?,?,?,?)",
                       (r["time"], r["main"], r["grade"], r["score"], r["n_hosts"], r["trackers"],
                        r["active_trackers"], r["protected"], r["bytes"], json.dumps(r)))

    def reports(self, limit=200):
        return self._r("SELECT id, ts, main, grade, score, n_hosts, trackers, active_trackers, "
                       "protected, bytes FROM reports ORDER BY ts DESC LIMIT ?", (limit,))

    def report_body(self, rid):
        rows = self._r("SELECT body FROM reports WHERE id=?", (rid,))
        return json.loads(rows[0]["body"]) if rows else None

    # ---- programas
    def program(self, key):
        rows = self._r("SELECT * FROM programs WHERE key=?", (key,))
        return rows[0] if rows else None

    def add_program(self, key, name, path, baseline=False):
        now = time.time()
        self._w("INSERT OR IGNORE INTO programs (key, name, path, first_seen, last_seen, baseline, "
                "conns) VALUES (?,?,?,?,?,?,0)", (key, name, path, now, now, int(baseline)))

    def touch_program(self, key, n=1):
        self._w("UPDATE programs SET last_seen=?, conns=conns+? WHERE key=?", (time.time(), n, key))

    def programs(self):
        return self._r("SELECT * FROM programs ORDER BY last_seen DESC")

    def program_count(self):
        return self._r("SELECT COUNT(*) AS n FROM programs")[0]["n"]

    # ---- tráfico por minuto
    def add_minute(self, ts, down, up):
        self._w("INSERT INTO minute (ts, down, up) VALUES (?,?,?) ON CONFLICT(ts) DO UPDATE SET "
                "down=down+excluded.down, up=up+excluded.up", (ts, down, up))

    def add_proc_minute(self, ts, proc, down, up):
        self._w("INSERT INTO proc_minute (ts, proc, down, up) VALUES (?,?,?,?) ON CONFLICT(ts, proc) "
                "DO UPDATE SET down=down+excluded.down, up=up+excluded.up", (ts, proc, down, up))

    def timeline(self, since, until, bin_s):
        """Suma por intervalos de bin_s segundos: [{t, down, up}]."""
        return self._r("SELECT (ts / ?) * ? AS t, SUM(down) AS down, SUM(up) AS up FROM minute "
                       "WHERE ts >= ? AND ts < ? GROUP BY t ORDER BY t",
                       (bin_s, bin_s, since, until))

    def totals(self, since, until):
        """(bajado, subido) en bytes entre dos instantes, según los contadores de la tarjeta."""
        r = self._r("SELECT COALESCE(SUM(down),0) AS d, COALESCE(SUM(up),0) AS u FROM minute "
                    "WHERE ts >= ? AND ts < ?", (since, until))[0]
        return int(r["d"]), int(r["u"])

    def daily(self, since, until):
        """Consumo por día a partir de `since`: [{d: nº de día, down, up}]."""
        return self._r("SELECT CAST((ts - ?) / 86400 AS INTEGER) AS d, SUM(down) AS down, SUM(up) AS up "
                       "FROM minute WHERE ts >= ? AND ts < ? GROUP BY d ORDER BY d",
                       (since, since, until))

    def alert_since(self, kind, since):
        return bool(self._r("SELECT 1 FROM alerts WHERE kind = ? AND ts >= ? LIMIT 1", (kind, since)))

    def top_programs(self, since, until, limit=12):
        return self._r("SELECT proc, SUM(down) AS down, SUM(up) AS up FROM proc_minute "
                       "WHERE ts >= ? AND ts < ? GROUP BY proc ORDER BY SUM(down)+SUM(up) DESC "
                       "LIMIT ?", (since, until, limit))

    # ---- conexiones
    def add_conn(self, ts, proc, remote, port, host=""):
        self._w("INSERT INTO conn_log (ts, proc, remote, port, host) VALUES (?,?,?,?,?)",
                (ts, proc, remote, port, host))

    def conns(self, since, until, proc_like="", limit=1500):
        return self._r("SELECT ts, proc, remote, port, host FROM conn_log WHERE ts >= ? AND ts < ? "
                       "AND proc LIKE ? ORDER BY ts DESC LIMIT ?",
                       (since, until, f"%{proc_like}%", limit))

    # ---- alertas
    def add_alert(self, kind, title, detail, proc=""):
        return self._w("INSERT INTO alerts (ts, kind, title, detail, proc) VALUES (?,?,?,?,?)",
                       (time.time(), kind, title, detail, proc))

    def alerts(self, limit=300):
        return self._r("SELECT * FROM alerts ORDER BY ts DESC LIMIT ?", (limit,))

    def alerts_by_kind(self, kind, limit=300):
        return self._r("SELECT * FROM alerts WHERE kind=? ORDER BY ts DESC LIMIT ?", (kind, limit))

    def unseen_alerts(self, kind=None):
        if kind is None:
            return self._r("SELECT COUNT(*) AS n FROM alerts WHERE seen=0")[0]["n"]
        return self._r("SELECT COUNT(*) AS n FROM alerts WHERE seen=0 AND kind=?", (kind,))[0]["n"]

    def mark_alerts_seen(self, kind=None):
        if kind is None:
            self._w("UPDATE alerts SET seen=1 WHERE seen=0")
        else:
            self._w("UPDATE alerts SET seen=1 WHERE seen=0 AND kind=?", (kind,))

    # ---- mantenimiento
    def clear_all(self):
        """Borra todo el historial (páginas, tráfico, conexiones y alertas). Los programas
        conocidos se conservan para no volver a avisar de lo que ya se aprendió."""
        for table in ("reports", "minute", "proc_minute", "conn_log", "alerts"):
            self._w(f"DELETE FROM {table}")  # nosec B608: nombres fijos, sin datos externos
        with self.lock, self._db() as c:
            c.execute("VACUUM")

    def purge(self, days=30, traffic_days=62):
        """El tráfico por minuto se conserva más (62 días) para poder calcular la cuota mensual."""
        for table, keep in (("reports", days), ("minute", max(days, traffic_days)),
                            ("proc_minute", max(days, traffic_days)), ("conn_log", days),
                            ("alerts", days)):
            self._w(f"DELETE FROM {table} WHERE ts < ?",  # nosec B608: nombres fijos
                    (time.time() - keep * 86400,))
