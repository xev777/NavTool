"""Cuota mensual de datos: cuánto llevas gastado en tu ciclo de facturación, cuánto te queda y a qué
ritmo vas. Usa los contadores reales de la tarjeta de red que NavTool ya guarda cada minuto."""
import time
import tkinter as tk
from tkinter import ttk

from i18n import tr

GIB = 1024 ** 3
BG, PANEL, FG, MUTED, ACC = "#1b2a41", "#0f1a2b", "#e8eef7", "#8ea3bd", "#3fa9f5"
UMBRALES = (80, 100)


def ciclo(now, dia):
    """(inicio, fin) del ciclo de facturación que contiene `now`; el ciclo empieza el día `dia` (1-28)."""
    dia = max(1, min(28, int(dia)))
    t = time.localtime(now)
    y, m = t.tm_year, t.tm_mon
    if t.tm_mday < dia:
        y, m = (y - 1, 12) if m == 1 else (y, m - 1)
    ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
    return (time.mktime((y, m, dia, 0, 0, 0, 0, 0, -1)), time.mktime((ny, nm, dia, 0, 0, 0, 0, 0, -1)))


def resumen(hist, cfg, now=None):
    now = now or time.time()
    start, end = ciclo(now, cfg.get("quota_day", 1))
    down, up = hist.totals(start, min(now + 60, end))
    used = down + (0 if cfg.get("quota_count") == "down" else up)
    quota = float(cfg.get("quota_gb") or 0) * GIB
    days_total = max(1.0, (end - start) / 86400)
    days_gone = max(0.05, (now - start) / 86400)
    projected = used / days_gone * days_total
    return {"start": start, "end": end, "down": down, "up": up, "used": used, "quota": quota,
            "pct": (used * 100 / quota) if quota else 0.0, "projected": projected,
            "days_left": max(0, int((end - now) // 86400)), "days_total": int(round(days_total)),
            "left": max(0.0, quota - used) if quota else 0.0,
            "per_day_left": max(0.0, quota - used) / max(1.0, (end - now) / 86400) if quota else 0.0}


def comprobar_alertas(hist, cfg, alert, now=None):
    """Avisa una sola vez por ciclo al llegar al 80 % y al 100 %. `alert(kind, título, detalle)`."""
    if not float(cfg.get("quota_gb") or 0):
        return
    r = resumen(hist, cfg, now)
    for u in UMBRALES:
        kind = f"quota{u}"
        if r["pct"] >= u and not hist.alert_since(kind, r["start"]):
            alert(kind, f"Has usado el {u} % de tu cuota mensual" if u < 100 else "Superaste tu cuota mensual",
                  f"Llevas {human(r['used'])} de {human(r['quota'])} ({r['pct']:.0f} %). "
                  f"Faltan {r['days_left']} días para que cierre el ciclo.")


def human(n):
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {u}" if u == "B" else f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.2f} TB"


class QuotaWindow(tk.Toplevel):
    def __init__(self, app, hist, cfg, save_cfg):
        super().__init__(app, bg=BG)
        self.app, self.hist, self.cfg, self.save_cfg = app, hist, cfg, save_cfg
        self.title("NavTool – Cuota mensual")
        self.attributes("-topmost", True)
        app.place_near(self, 640, 620)
        self._build()
        self.refresh()
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def _build(self):
        f = tk.Frame(self, bg=BG)
        f.pack(fill="x", padx=12, pady=(12, 4))
        tk.Label(f, text="Tu plan: ", bg=BG, fg=FG).pack(side="left")
        self.gb = tk.StringVar(value=str(self.cfg.get("quota_gb") or ""))
        e = tk.Entry(f, textvariable=self.gb, width=7, bg=PANEL, fg=FG, insertbackground=FG, relief="flat")
        e.pack(side="left", ipady=3)
        tk.Label(f, text=" GB al mes · el ciclo empieza el día ", bg=BG, fg=FG).pack(side="left")
        self.day = tk.StringVar(value=str(self.cfg.get("quota_day", 1)))
        tk.Spinbox(f, from_=1, to=28, textvariable=self.day, width=3, bg=PANEL, fg=FG,
                   buttonbackground="#27405f", relief="flat").pack(side="left")
        tk.Label(f, text=" · cuenta ", bg=BG, fg=FG).pack(side="left")
        self.mode = ttk.Combobox(f, state="readonly", width=22,
                                 values=("bajada + subida", "solo bajada"))
        self.mode.current(1 if self.cfg.get("quota_count") == "down" else 0)
        self.mode.pack(side="left")
        tk.Button(f, text="Guardar", command=self.save, bg=ACC, fg="white", relief="flat",
                  padx=10, cursor="hand2").pack(side="left", padx=8)
        tk.Label(self, text="Deja el plan vacío o en 0 para no usar cuota (solo verás el consumo).",
                 bg=BG, fg=MUTED, font=("Segoe UI", 8), anchor="w").pack(fill="x", padx=14)
        self.head = tk.Label(self, text="", bg=BG, fg=FG, font=("Segoe UI", 12, "bold"), anchor="w")
        self.head.pack(fill="x", padx=14, pady=(10, 2))
        self.bar = tk.Canvas(self, height=26, bg=PANEL, highlightthickness=0)
        self.bar.pack(fill="x", padx=14, pady=4)
        self.info = tk.Label(self, text="", bg=BG, fg=FG, anchor="w", justify="left", wraplength=600)
        self.info.pack(fill="x", padx=14, pady=4)
        self.chart = tk.Canvas(self, height=150, bg=PANEL, highlightthickness=0)
        self.chart.pack(fill="x", padx=14, pady=6)
        self.top = tk.Text(self, height=9, bg=PANEL, fg=FG, relief="flat", font=("Consolas", 9),
                           padx=8, pady=6)
        self.top.pack(fill="both", expand=True, padx=14, pady=(0, 12))
        self.bar.bind("<Configure>", lambda e: self.refresh())

    def save(self):
        try:
            gb = float(self.gb.get().replace(",", ".") or 0)
            day = int(self.day.get())
        except ValueError:
            return
        self.cfg["quota_gb"] = max(0.0, min(gb, 100000.0))
        self.cfg["quota_day"] = max(1, min(28, day))
        self.cfg["quota_count"] = "down" if self.mode.current() == 1 else "both"
        self.save_cfg(self.cfg)
        self.refresh()

    def refresh(self):
        if not self.winfo_exists():
            return
        r = resumen(self.hist, self.cfg)
        f = lambda t: time.strftime("%d %b", time.localtime(t))
        self.head.config(text=f"Ciclo {f(r['start'])} → {f(r['end'] - 1)}:  {human(r['used'])} usados")
        c = self.bar
        c.delete("all")
        w = max(c.winfo_width(), 300)
        if r["quota"]:
            frac = min(r["pct"] / 100, 1.0)
            col = "#3fb97f" if r["pct"] < 80 else ("#ffa94d" if r["pct"] < 100 else "#ff6b6b")
            c.create_rectangle(0, 0, w * frac, 26, fill=col, width=0)
            c.create_text(w / 2, 13, fill="white", font=("Segoe UI", 10, "bold"),
                          text=f"{r['pct']:.0f} %  de {human(r['quota'])}")
            proj = r["projected"]
            ritmo = (f"A este ritmo cerrarás el ciclo en {human(proj)} (⚠ te pasarías de tu cuota)."
                     if proj > r["quota"] else
                     f"A este ritmo cerrarás el ciclo en {human(proj)} (dentro de tu cuota).")
            info = (f"Te quedan {human(r['left'])} y {r['days_left']} días: puedes gastar unos "
                    f"{human(r['per_day_left'])} por día.\n{ritmo}")
        else:
            c.create_text(w / 2, 13, fill=MUTED, text="Sin cuota definida")
            info = (f"Bajado {human(r['down'])} · subido {human(r['up'])}. "
                    f"Ritmo actual: cerrarías el ciclo en ≈ {human(r['projected'])}.")
        self.info.config(text=info)
        self._chart(r)
        self._top(r)

    def _chart(self, r):
        c = self.chart
        c.delete("all")
        rows = {d["d"]: d for d in self.hist.daily(r["start"], r["end"])}
        n = max(r["days_total"], 28)
        w, h = max(c.winfo_width(), 300), 150
        top = max([(d["down"] + (0 if self.cfg.get("quota_count") == "down" else d["up"])) for d in rows.values()] or [1]) or 1
        bw = (w - 20) / n
        for i in range(n):
            d = rows.get(i)
            if not d:
                continue
            v = d["down"] + (0 if self.cfg.get("quota_count") == "down" else d["up"])
            bh = (h - 34) * v / top
            c.create_rectangle(10 + i * bw + 1, h - 18 - bh, 10 + (i + 1) * bw - 1, h - 18,
                               fill=ACC, width=0)
        c.create_text(10, 4, anchor="nw", fill=MUTED, font=("Segoe UI", 8),
                      text=f"Consumo por día (máximo: {human(top)})")
        c.create_text(10, h - 3, anchor="sw", fill=MUTED, font=("Segoe UI", 8), text="día 1")
        c.create_text(w - 10, h - 3, anchor="se", fill=MUTED, font=("Segoe UI", 8),
                      text=f"día {n}")

    def _top(self, r):
        t = self.top
        t.config(state="normal")
        t.delete("1.0", "end")
        rows = self.hist.top_programs(r["start"], r["end"], 10)
        if rows:
            t.insert("end", "Programas que más han usado en este ciclo\n\n")
            for p in rows:
                t.insert("end", f"{p['proc'][:30]:<32}↓ {human(p['down']):>10}   ↑ {human(p['up']):>10}\n")
            t.insert("end", "\n(Solo cuenta el tiempo con el monitor por programa activo: "
                            "📡 Tráfico como administrador o «Historial → monitoreo».)")
        else:
            t.insert("end", "El desglose por programa aparecerá cuando actives el monitoreo por "
                            "programa (📡 Tráfico como administrador). El total de arriba sí es "
                            "completo: viene de los contadores de tu tarjeta de red.")
        t.config(state="disabled")
