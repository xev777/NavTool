"""Ventana «Historial y alertas»: línea de tiempo, conexiones, alertas, programas y páginas."""
import time
import tkinter as tk
from tkinter import messagebox, ttk

from privacy import GRADE_COLOR
from tooltip import tip

BG, PANEL, FG, MUTED, ACC = "#14202f", "#1b2a41", "#e8eef7", "#8ea3bd", "#3fa9f5"
DOWN_C, UP_C = "#3fa9f5", "#ffa94d"
RANGES = {"1 hora": (3600, 60), "6 horas": (6 * 3600, 300), "24 horas": (86400, 900),
          "7 días": (7 * 86400, 7200)}
ALERT_ICON = {"new": "🆕", "path": "⚠", "upload": "📤", "proc_upload": "📤", "telemetry": "📊"}


def human(n):
    n = n or 0
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {u}" if u == "B" else f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} TB"


def fmt(ts, f="%d/%m %H:%M"):
    return time.strftime(f, time.localtime(ts)) if ts else "—"


class HistoryWindow(tk.Toplevel):
    def __init__(self, app, hist, cfg, save_cfg, open_report, set_monitor, monitor_state):
        super().__init__(app, bg=BG)
        self.app, self.hist, self.cfg, self.save_cfg = app, hist, cfg, save_cfg
        self.open_report, self.set_monitor, self.monitor_state = open_report, set_monitor, monitor_state
        self.title("TrafficBar – Historial y alertas")
        self.geometry("1020x700")
        if hasattr(app, "place_near"):
            app.place_near(self, 1020, 700)
        self.range_name = tk.StringVar(value="24 horas")
        self.bins = []
        self.custom = None          # (desde, hasta) elegido en la línea de tiempo
        self._style()
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=8, pady=8)
        self.tabs = {}
        for key, title, builder in (("timeline", "  Línea de tiempo  ", self._build_timeline),
                                    ("conns", "  Conexiones  ", self._build_conns),
                                    ("alerts", "  Alertas  ", self._build_alerts),
                                    ("programs", "  Programas  ", self._build_programs),
                                    ("pages", "  Páginas visitadas  ", self._build_pages)):
            f = tk.Frame(self.nb, bg=BG)
            self.nb.add(f, text=title)
            self.tabs[key] = f
            builder(f)
        foot = tk.Frame(self, bg=BG)
        foot.pack(fill="x", padx=10, pady=(0, 8))
        tk.Label(foot, text="Todo se guarda solo en este equipo (carpeta de datos de TrafficBar) y "
                            "se borra solo a los 30 días.", bg=BG, fg=MUTED,
                 font=("Segoe UI", 8)).pack(side="left")
        tip(self._button(foot, "🗑 Borrar todo el historial", self._clear_all, "#7a2a2a", side="right"),
            "Borra páginas visitadas, tráfico, conexiones y alertas guardados. Pide confirmar.")
        self.nb.bind("<<NotebookTabChanged>>", lambda e: self.refresh())
        self.refresh()
        self.after(5000, self._auto)
        self.lift()
        self.attributes("-topmost", True)      # al frente al abrir; luego se comporta normal
        self.after(500, lambda: self.attributes("-topmost", False))

    def _style(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure("H.Treeview", background="#0f1a2b", fieldbackground="#0f1a2b", foreground=FG,
                    rowheight=int(26 * getattr(self.master, 'ui_scale', 1.0)), borderwidth=0, font=("Segoe UI", 9))
        s.configure("H.Treeview.Heading", background=PANEL, foreground=MUTED, relief="flat",
                    font=("Segoe UI", 9, "bold"))
        s.map("H.Treeview", background=[("selected", "#27405f")])
        s.configure("TNotebook", background=BG, borderwidth=0)
        s.configure("TNotebook.Tab", background=PANEL, foreground=MUTED, padding=(14, 6),
                    font=("Segoe UI", 10))
        s.map("TNotebook.Tab", background=[("selected", "#27405f")],
              foreground=[("selected", "white")])
        s.configure("Vertical.TScrollbar", background="#27405f", troughcolor="#0f1a2b",
                    bordercolor="#0f1a2b", arrowcolor=FG, lightcolor="#27405f",
                    darkcolor="#27405f")
        s.configure("TCombobox", fieldbackground="#0f1a2b", background=PANEL, foreground=FG)
        s.map("TCombobox", fieldbackground=[("readonly", "#0f1a2b")],
              foreground=[("readonly", FG)])

    # ---- utilidades de interfaz
    def _tree(self, parent, cols, widths, anchors=None, height=None):
        box = tk.Frame(parent, bg=BG)
        tree = ttk.Treeview(box, columns=[c[0] for c in cols], show="headings",
                            style="H.Treeview", **({"height": height} if height else {}))
        for i, (cid, text) in enumerate(cols):
            tree.heading(cid, text=text)
            tree.column(cid, width=widths[i], anchor=(anchors or {}).get(cid, "w"))
        sb = ttk.Scrollbar(box, command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        tree.pack(fill="both", expand=True)
        return box, tree

    def _button(self, parent, text, cmd, bg="#27405f", side="left"):
        b = tk.Button(parent, text=text, command=cmd, bg=bg, fg="white", relief="flat", bd=0,
                      padx=12, pady=4, font=("Segoe UI", 9), cursor="hand2",
                      activebackground=ACC)
        b.pack(side=side, padx=3)
        return b

    def _note(self, parent, text):
        return tk.Label(parent, text=text, bg=BG, fg=MUTED, anchor="w", justify="left",
                        font=("Segoe UI", 9), wraplength=940)

    # ---- línea de tiempo
    def _build_timeline(self, f):
        top = tk.Frame(f, bg=BG)
        top.pack(fill="x", padx=8, pady=8)
        tk.Label(top, text="Tráfico de todo el equipo:", bg=BG, fg=FG).pack(side="left")
        for name in RANGES:
            tk.Radiobutton(top, text=name, value=name, variable=self.range_name,
                           command=self.refresh, indicatoron=False, bg=PANEL, fg=FG,
                           selectcolor="#27405f", activebackground="#27405f", relief="flat",
                           padx=10, pady=3, bd=0).pack(side="left", padx=2)
        self.tl_canvas = tk.Canvas(f, height=280, bg="#0f1a2b", highlightthickness=0)
        self.tl_canvas.pack(fill="x", padx=8)
        self.tl_canvas.bind("<Motion>", self._tl_hover)
        self.tl_canvas.bind("<Button-1>", self._tl_click)
        tip(self.tl_canvas, area=self._tl_tip)
        self.tl_info = tk.Label(f, text="Pasa el ratón por las barras. Clic en una barra = ver qué "
                                        "programas se conectaron en ese momento.", bg=BG, fg=MUTED,
                                anchor="w", font=("Segoe UI", 9))
        self.tl_info.pack(fill="x", padx=10, pady=4)
        self.tl_top_lbl = tk.Label(f, text="", bg=BG, fg=FG, anchor="w", font=("Segoe UI", 10, "bold"))
        self.tl_top_lbl.pack(fill="x", padx=10)
        box, self.tl_tree = self._tree(f, (("p", "Programa"), ("d", "↓ bajado"), ("u", "↑ subido")),
                                       (360, 140, 140), {"d": "e", "u": "e"})
        box.pack(fill="both", expand=True, padx=8, pady=(2, 8))
        self.tl_note = self._note(f, "")
        self.tl_note.pack(fill="x", padx=10, pady=(0, 8))

    def _tl_range(self):
        span, bin_s = RANGES[self.range_name.get()]
        until = int(time.time() // bin_s + 1) * bin_s
        return until - span, until, bin_s

    def _draw_timeline(self):
        since, until, bin_s = self._tl_range()
        data = {r["t"]: r for r in self.hist.timeline(since, until, bin_s)}
        n = (until - since) // bin_s
        self.bins = [(since + i * bin_s, data.get(since + i * bin_s, {"down": 0, "up": 0}))
                     for i in range(n)]
        c = self.tl_canvas
        c.delete("all")
        w = max(c.winfo_width(), 600)
        h, pad_l, pad_b = 280, 62, 26
        peak = max([max(b["down"], b["up"]) for _, b in self.bins] or [0]) or 1
        for i in range(0, 5):
            y = h - pad_b - (h - pad_b - 14) * i / 4
            c.create_line(pad_l, y, w - 8, y, fill="#1d2c42")
            c.create_text(pad_l - 6, y, anchor="e", fill=MUTED, font=("Segoe UI", 8),
                          text=human(peak * i / 4))
        step = (w - pad_l - 8) / max(n, 1)
        self._geom = (pad_l, step, h, pad_b)
        for i, (t, b) in enumerate(self.bins):
            x = pad_l + i * step
            for k, (val, col) in enumerate(((b["down"], DOWN_C), (b["up"], UP_C))):
                if val:
                    bh = (h - pad_b - 14) * val / peak
                    half = max(1, step / 2 - 1)
                    c.create_rectangle(x + k * half, h - pad_b - bh, x + (k + 1) * half,
                                       h - pad_b, fill=col, width=0)
        fmt_t = "%H:%M" if bin_s < 86400 and self.range_name.get() != "7 días" else "%d/%m"
        for i in range(0, n, max(1, n // 8)):
            c.create_text(pad_l + i * step, h - 10, anchor="w", fill=MUTED, font=("Segoe UI", 8),
                          text=fmt(self.bins[i][0], fmt_t))
        c.create_text(w - 8, 4, anchor="ne", fill=DOWN_C, font=("Segoe UI", 9, "bold"), text="■ bajada")
        c.create_text(w - 78, 4, anchor="ne", fill=UP_C, font=("Segoe UI", 9, "bold"), text="■ subida")
        if not any(b["down"] or b["up"] for _, b in self.bins):
            c.create_text(w / 2, h / 2, fill=MUTED, font=("Segoe UI", 11),
                          text="Sin datos todavía en este rango: TrafficBar los va guardando cada minuto.")
        rows = self.hist.top_programs(since, until)
        self.tl_tree.delete(*self.tl_tree.get_children())
        for r in rows:
            self.tl_tree.insert("", "end", values=(r["proc"], human(r["down"]), human(r["up"])))
        self.tl_top_lbl.config(text="Programas que más tráfico movieron en este rango")
        self.tl_note.config(text="" if rows else
                            "El desglose por programa se llena con el «monitoreo por programa» "
                            "(pestaña Alertas → requiere Npcap y TrafficBar como administrador).")

    def _bin_at(self, x):
        pad_l, step, _, _ = self._geom
        i = int((x - pad_l) // step) if step else -1
        return self.bins[i] if 0 <= i < len(self.bins) else None

    def _tl_tip(self, x, _y):
        b = self._bin_at(x) if self.bins else None
        if not b:
            return "Cada barra es un intervalo de tiempo. Azul = bajada, naranja = subida."
        t, v = b
        _, _, bin_s = self._tl_range()
        return (f"{fmt(t)} – {fmt(t + bin_s, '%H:%M')}\n↓ {human(v['down'])}   ↑ {human(v['up'])}\n"
                "Clic: ver qué programas se conectaron en ese momento.")

    def _tl_hover(self, e):
        b = self._bin_at(e.x) if self.bins else None
        if b:
            t, v = b
            _, _, bin_s = self._tl_range()
            self.tl_info.config(text=f"{fmt(t)} – {fmt(t + bin_s, '%H:%M')}    ↓ {human(v['down'])}"
                                     f"    ↑ {human(v['up'])}    (clic: ver conexiones de ese momento)")

    def _tl_click(self, e):
        b = self._bin_at(e.x) if self.bins else None
        if b:
            _, _, bin_s = self._tl_range()
            self.custom = (b[0] - bin_s, b[0] + 2 * bin_s)
            self.preset_cb.current(4)
            self.nb.select(self.tabs["conns"])

    # ---- conexiones
    def _build_conns(self, f):
        bar = tk.Frame(f, bg=BG)
        bar.pack(fill="x", padx=8, pady=8)
        tk.Label(bar, text="Periodo:", bg=BG, fg=FG).pack(side="left")
        cb = self.preset_cb = ttk.Combobox(bar, state="readonly", width=38, values=[
            "Última hora", "Últimas 24 horas", "Hoy", "Anoche (22:00 – 06:00)",
            "Momento elegido en la línea de tiempo"])
        cb.current(1)
        cb.pack(side="left", padx=6)
        tk.Label(bar, text="Programa:", bg=BG, fg=FG).pack(side="left", padx=(10, 0))
        self.proc_filter = tk.StringVar()
        e = tk.Entry(bar, textvariable=self.proc_filter, width=18, bg="#0f1a2b", fg=FG,
                     insertbackground=FG, relief="flat", highlightthickness=1,
                     highlightbackground="#27405f", highlightcolor=ACC)
        e.pack(side="left", padx=6, ipady=3)
        e.bind("<Return>", lambda ev: self._fill_conns())
        cb.bind("<<ComboboxSelected>>", lambda ev: self._fill_conns())
        tip(self._button(bar, "Buscar", self._fill_conns, ACC),
            "Aplica el periodo y el filtro de programa. También funciona con Enter en el campo.")
        self.conn_count = tk.Label(bar, text="", bg=BG, fg=MUTED)
        self.conn_count.pack(side="right")
        box, self.conn_tree = self._tree(f, (("t", "Hora"), ("p", "Programa"), ("d", "Se conectó a"),
                                             ("o", "Puerto")), (140, 200, 480, 80), {"o": "e"})
        box.pack(fill="both", expand=True, padx=8, pady=(0, 4))
        self._note(f, "Cada fila es la primera vez (por hora) que un programa habló con esa "
                      "dirección de Internet. Sirve para responder «¿qué se conectó anoche?».").pack(
            fill="x", padx=10, pady=(0, 8))

    def _conn_range(self):
        now = time.time()
        p = self.preset_cb.current()          # 0 hora · 1 24 h · 2 hoy · 3 anoche · 4 momento elegido
        lt = time.localtime(now)
        midnight = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))
        if p == 0:
            return now - 3600, now + 1
        if p == 2:
            return midnight, now + 1
        if p == 3:
            start = midnight - 2 * 3600                    # ayer 22:00
            end = midnight + 6 * 3600                      # hoy 06:00
            if now < end:                                  # antes de las 6: sigue siendo "anoche"
                return start, now + 1
            return start, end
        if p == 4 and self.custom:
            return self.custom
        return now - 86400, now + 1

    def _fill_conns(self):
        since, until = self._conn_range()
        rows = self.hist.conns(since, until, self.proc_filter.get().strip())
        self.conn_tree.delete(*self.conn_tree.get_children())
        for r in rows:
            dest = r["host"] + f"  ({r['remote']})" if r["host"] else r["remote"]
            self.conn_tree.insert("", "end", values=(fmt(r["ts"], "%d/%m %H:%M:%S"), r["proc"],
                                                      dest, r["port"]))
        self.conn_count.config(text=f"{len(rows)} conexiones · {fmt(since)} → {fmt(until)}")

    # ---- alertas
    def _build_alerts(self, f):
        box, self.alert_tree = self._tree(f, (("t", "Hora"), ("k", ""), ("p", "Programa"),
                                              ("m", "Qué pasó")), (120, 34, 160, 640))
        self.alert_tree.tag_configure("unseen", foreground="#ffd166")
        self.alert_tree.bind("<Double-1>", self._alert_detail)
        box.pack(fill="both", expand=True, padx=8, pady=(8, 4))
        row = tk.Frame(f, bg=BG)
        row.pack(fill="x", padx=8)
        tip(self._button(row, "Marcar todas como leídas", self._mark_seen),
            "Quita el aviso de «nuevas» de las alertas. Las alertas se conservan en la lista.")
        self._note(f, "Doble clic en una alerta para leerla completa.").pack(fill="x", padx=10)

        cfgf = tk.LabelFrame(f, text=" Cuándo avisarte ", bg=BG, fg=MUTED, padx=10, pady=8)
        cfgf.pack(fill="x", padx=8, pady=8)
        self.up_var = tk.DoubleVar(value=self.cfg.get("alert_up_mb_s", 3.0))
        self.proc_var = tk.DoubleVar(value=self.cfg.get("alert_proc_mb_min", 100.0))
        r1 = tk.Frame(cfgf, bg=BG)
        r1.pack(fill="x")
        tk.Label(r1, text="Subida sostenida del equipo (20 s) mayor que", bg=BG, fg=FG).pack(side="left")
        tk.Spinbox(r1, from_=0.5, to=200, increment=0.5, width=6, textvariable=self.up_var,
                   bg="#0f1a2b", fg=FG, buttonbackground=PANEL, relief="flat").pack(side="left", padx=6)
        tk.Label(r1, text="MB/s", bg=BG, fg=MUTED).pack(side="left")
        r2 = tk.Frame(cfgf, bg=BG)
        r2.pack(fill="x", pady=4)
        tk.Label(r2, text="Un programa que envía más de", bg=BG, fg=FG).pack(side="left")
        tk.Spinbox(r2, from_=10, to=5000, increment=10, width=6, textvariable=self.proc_var,
                   bg="#0f1a2b", fg=FG, buttonbackground=PANEL, relief="flat").pack(side="left", padx=6)
        tk.Label(r2, text="MB en un minuto", bg=BG, fg=MUTED).pack(side="left")
        self.mon_var = tk.BooleanVar(value=self.monitor_state()[0])
        tk.Checkbutton(cfgf, text="Monitoreo continuo por programa (Npcap; requiere TrafficBar como "
                                  "administrador)", variable=self.mon_var, bg=BG, fg=FG,
                       selectcolor=PANEL, activebackground=BG, activeforeground=FG,
                       anchor="w").pack(fill="x", pady=(4, 0))
        self.mon_msg = tk.Label(cfgf, text=self.monitor_state()[1], bg=BG, fg=MUTED, anchor="w",
                                font=("Segoe UI", 8))
        self.mon_msg.pack(fill="x")
        tip(self._button(cfgf, "Guardar", self._save_cfg, ACC, side="right"),
            "Guarda los umbrales y aplica el monitoreo por programa si lo marcaste.")

    def _save_cfg(self):
        try:
            self.cfg["alert_up_mb_s"] = max(0.5, float(self.up_var.get()))
            self.cfg["alert_proc_mb_min"] = max(10.0, float(self.proc_var.get()))
        except tk.TclError:
            messagebox.showwarning("TrafficBar", "Escribe números válidos.", parent=self)
            return
        self.save_cfg(self.cfg)
        msg = self.set_monitor(self.mon_var.get())
        self.mon_msg.config(text=msg)
        self.mon_var.set(self.monitor_state()[0])

    def _mark_seen(self):
        self.hist.mark_alerts_seen()
        self.app.refresh_alert_badge()
        self._fill_alerts()

    def _fill_alerts(self):
        self.alert_tree.delete(*self.alert_tree.get_children())
        self.alert_rows = {}
        for a in self.hist.alerts():
            iid = str(a["id"])
            self.alert_rows[iid] = a
            self.alert_tree.insert("", "end", iid=iid, tags=(() if a["seen"] else ("unseen",)),
                                   values=(fmt(a["ts"], "%d/%m %H:%M"), ALERT_ICON.get(a["kind"], "•"),
                                           a["proc"] or "—", a["title"] + " — " + a["detail"]))
        if self.hist.unseen_alerts():        # ya las estás viendo: dejan de contar como nuevas
            self.hist.mark_alerts_seen()
            self.app.refresh_alert_badge()

    def _alert_detail(self, _e=None):
        sel = self.alert_tree.selection()
        if sel:
            a = self.alert_rows[sel[0]]
            messagebox.showinfo(a["title"], f"{fmt(a['ts'], '%d/%m/%Y %H:%M:%S')}\n\n{a['detail']}",
                                parent=self)

    # ---- programas
    def _build_programs(self, f):
        self._note(f, "Programas que han usado Internet desde este equipo. «Nuevo» = apareció "
                      "en los últimos 7 días.").pack(fill="x", padx=10, pady=8)
        box, self.prog_tree = self._tree(f, (("n", "Programa"), ("r", "Ruta"), ("f", "Primera vez"),
                                             ("l", "Última vez"), ("c", "Conexiones"),
                                             ("s", "Estado")), (150, 380, 110, 110, 90, 120),
                                         {"c": "e"})
        self.prog_tree.tag_configure("new", foreground="#ffa94d")
        box.pack(fill="both", expand=True, padx=8, pady=(0, 8))

    def _fill_programs(self):
        self.prog_tree.delete(*self.prog_tree.get_children())
        week = time.time() - 7 * 86400
        for p in self.hist.programs():
            new = p["first_seen"] > week and not p["baseline"]
            state = "nuevo" if new else "conocido" if not p["baseline"] else "ya existía"
            self.prog_tree.insert("", "end", tags=("new",) if new else (), values=(
                p["name"], p["path"] or "(ruta no disponible)", fmt(p["first_seen"]),
                fmt(p["last_seen"]), p["conns"], state))

    # ---- páginas
    def _build_pages(self, f):
        self._note(f, "Informes de privacidad de las páginas que cargaste con el proxy encendido. "
                      "Doble clic para abrir el informe.").pack(fill="x", padx=10, pady=8)
        box, self.page_tree = self._tree(f, (("t", "Hora"), ("s", "Sitio"), ("g", "Nota"),
                                             ("a", "Rastreadores activos"), ("b", "Bloqueados"),
                                             ("w", "Peso")), (120, 380, 70, 150, 100, 100),
                                         {"g": "center", "a": "e", "b": "e", "w": "e"})
        for g, col in GRADE_COLOR.items():
            self.page_tree.tag_configure(g, foreground=col)
        self.page_tree.bind("<Double-1>", self._open_page)
        box.pack(fill="both", expand=True, padx=8, pady=(0, 8))

    def _fill_pages(self):
        self.page_tree.delete(*self.page_tree.get_children())
        for r in self.hist.reports():
            self.page_tree.insert("", "end", iid=str(r["id"]), tags=(r["grade"],), values=(
                fmt(r["ts"]), r["main"], f"{r['grade']} · {r['score']}", r["active_trackers"],
                r["protected"], human(r["bytes"])))

    def _open_page(self, _e=None):
        sel = self.page_tree.selection()
        if sel:
            rep = self.hist.report_body(int(sel[0]))
            if rep:
                self.open_report(rep)

    def _clear_all(self):
        if messagebox.askyesno("TrafficBar", "¿Borrar TODO el historial (páginas visitadas, tráfico, "
                               "conexiones y alertas)?\n\nNo se puede deshacer.", parent=self):
            self.hist.clear_all()
            self.app.refresh_alert_badge()
            self.refresh()

    # ---- refresco
    def refresh(self):
        if not self.winfo_exists():
            return
        try:
            tab = self.nb.index("current")
        except tk.TclError:
            return
        if tab == 0:
            self.after(30, self._draw_timeline)
        elif tab == 1:
            self._fill_conns()
        elif tab == 2:
            self._fill_alerts()
        elif tab == 3:
            self._fill_programs()
        elif tab == 4:
            self._fill_pages()

    def _auto(self):
        if self.winfo_exists():
            if self.nb.index("current") in (0, 2):
                self.refresh()
            self.after(5000, self._auto)
