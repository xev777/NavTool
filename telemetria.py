"""Ventana «Telemetría detectada»: qué programas de este equipo contactaron con servidores de
telemetría/diagnóstico conocidos (informes de fallos, estadísticas de uso...).

Solo informa: TrafficBar no bloquea estas conexiones ni el programa que las hizo. La detección la hace
`traffic_monitor.is_telemetry()` sobre el tráfico capturado; el registro lo guarda `watcher.Watcher`
como una alerta más (`kind="telemetry"`) en el historial.
"""
import time
import tkinter as tk
from tkinter import messagebox, ttk

from safety import bring_to_front
from tooltip import tip

BG, PANEL, FG, MUTED, ACC = "#14202f", "#1b2a41", "#e8eef7", "#8ea3bd", "#3fa9f5"


def fmt(ts):
    return time.strftime("%d/%m %H:%M:%S", time.localtime(ts)) if ts else "—"


class TelemetryWindow(tk.Toplevel):
    def __init__(self, master, hist, refresh_badge):
        super().__init__(master, bg=BG)
        self.hist, self.refresh_badge = hist, refresh_badge
        self.title("TrafficBar – Telemetría detectada")
        self.geometry("880x520")
        if hasattr(master, "place_near"):
            master.place_near(self, 880, 520)
        self.rows = {}
        self._build()
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.lift()
        self.attributes("-topmost", True)
        self.after(400, lambda: self.attributes("-topmost", False))
        bring_to_front(self)
        self.after(200, self.refresh)
        self.after(5000, self._auto)

    def _build(self):
        self._note(
            "TrafficBar anota aquí cuándo un programa de este equipo contacta con un servidor de "
            "telemetría/diagnóstico conocido: informes de fallos, estadísticas de uso u otros datos "
            "que un programa envía a su fabricante. Solo lo registra: no bloquea la conexión ni el "
            "programa. Necesita el monitoreo por programa activado (🕘 Historial y alertas → "
            "pestaña Alertas)."
        ).pack(fill="x", padx=12, pady=(12, 6))
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure("Tel.Treeview", background="#0f1a2b", fieldbackground="#0f1a2b", foreground=FG,
                    rowheight=int(26 * getattr(self.master, "ui_scale", 1.0)), borderwidth=0,
                    font=("Segoe UI", 9))
        s.configure("Tel.Treeview.Heading", background=PANEL, foreground=MUTED, relief="flat",
                    font=("Segoe UI", 9, "bold"))
        s.map("Tel.Treeview", background=[("selected", "#27405f")])
        s.configure("Vertical.TScrollbar", background="#27405f", troughcolor="#0f1a2b",
                    bordercolor="#0f1a2b", arrowcolor=FG, lightcolor="#27405f", darkcolor="#27405f")
        box = tk.Frame(self, bg=BG)
        box.pack(fill="both", expand=True, padx=10, pady=(0, 4))
        self.tree = ttk.Treeview(box, columns=("t", "p", "m"), show="headings", style="Tel.Treeview")
        for c, txt, w in (("t", "Hora", 130), ("p", "Programa", 160), ("m", "Qué se detectó", 560)):
            self.tree.heading(c, text=txt)
            self.tree.column(c, width=w, anchor="w")
        sb = ttk.Scrollbar(box, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<Double-1>", self._detail)
        foot = tk.Frame(self, bg=BG)
        foot.pack(fill="x", padx=10, pady=(0, 10))
        tip(self._button(foot, "Marcar todas como leídas", self._mark_seen),
            "Quita el aviso de «nuevas» de esta lista. Las detecciones se conservan.")
        self.count_lbl = tk.Label(foot, text="", bg=BG, fg=MUTED)
        self.count_lbl.pack(side="right")

    def _button(self, parent, text, cmd):
        b = tk.Button(parent, text=text, command=cmd, relief="flat", bd=0, padx=12, pady=4,
                      bg="#27405f", fg="white", cursor="hand2", activebackground=ACC,
                      font=("Segoe UI", 9))
        b.pack(side="left")
        return b

    def _note(self, text):
        return tk.Label(self, text=text, bg=BG, fg=MUTED, anchor="w", justify="left",
                        font=("Segoe UI", 9), wraplength=840)

    def refresh(self):
        if not self.winfo_exists():
            return
        self.tree.delete(*self.tree.get_children())
        self.rows = {}
        rows = self.hist.alerts_by_kind("telemetry")
        for a in rows:
            iid = str(a["id"])
            self.rows[iid] = a
            self.tree.insert("", "end", iid=iid,
                             values=(fmt(a["ts"]), a["proc"] or "—", a["title"] + " — " + a["detail"]))
        self.count_lbl.config(text=f"{len(rows)} detección(es)" if rows else
                              "Sin detecciones todavía. Necesita el monitoreo por programa (Npcap).")
        if self.hist.unseen_alerts("telemetry"):
            self.hist.mark_alerts_seen("telemetry")
            self.refresh_badge()

    def _mark_seen(self):
        self.hist.mark_alerts_seen("telemetry")
        self.refresh_badge()
        self.refresh()

    def _detail(self, _e=None):
        sel = self.tree.selection()
        if sel:
            a = self.rows[sel[0]]
            messagebox.showinfo(a["title"], f"{fmt(a['ts'])}\n\n{a['detail']}", parent=self)

    def _auto(self):
        if self.winfo_exists():
            self.refresh()
            self.after(5000, self._auto)
