"""Ventana del informe de privacidad de una página."""
import time
import tkinter as tk
from tkinter import ttk

from privacy import CATS, GRADE_COLOR, base_domain
from tooltip import tip

BG, PANEL, FG, MUTED, ACC = "#14202f", "#1b2a41", "#e8eef7", "#8ea3bd", "#3fa9f5"


def human(n):
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {u}" if u == "B" else f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} TB"


STATUS_TEXT = {"done": "✓ cargó", "blocked": "🚫 bloqueado", "cut": "✂ cortado"}


class ReportWindow(tk.Toplevel):
    def __init__(self, app, report, on_block, is_listed, on_allow=None):
        super().__init__(app, bg=BG)
        self.report, self.on_block, self.is_listed = report, on_block, is_listed
        self.on_allow = on_allow
        self.title(f"TrafficBar – Informe de privacidad · {report['main']}")
        self.geometry("820x640")
        if hasattr(app, "place_near"):
            app.place_near(self, 820, 640)
        self._style()
        self._header()
        self._chips()
        self._table()
        self._buttons()
        self.lift()
        self.attributes("-topmost", True)
        self.after(300, lambda: self.attributes("-topmost", False))

    def _style(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure("R.Treeview", background="#0f1a2b", fieldbackground="#0f1a2b", foreground=FG,
                    rowheight=int(26 * getattr(self.master, 'ui_scale', 1.0)), borderwidth=0, font=("Segoe UI", 9))
        s.configure("R.Treeview.Heading", background=PANEL, foreground=MUTED, relief="flat",
                    font=("Segoe UI", 9, "bold"))
        s.map("R.Treeview", background=[("selected", "#27405f")])

    def _header(self):
        r = self.report
        c = tk.Canvas(self, height=118, bg=PANEL, highlightthickness=0)
        c.pack(fill="x", padx=10, pady=(10, 4))
        col = GRADE_COLOR[r["grade"]]
        c.create_oval(18, 14, 102, 98, fill="#0f1a2b", outline=col, width=6)
        c.create_text(60, 56, text=r["grade"], fill=col, font=("Segoe UI", 38, "bold"))
        c.create_text(122, 24, anchor="w", fill=FG, font=("Segoe UI", 16, "bold"), text=r["main"])
        c.create_text(122, 50, anchor="w", fill=col, font=("Segoe UI", 11, "bold"),
                      text=f"Nota de privacidad: {r['score']} / 100")
        c.create_text(122, 74, anchor="w", fill=FG, font=("Segoe UI", 10), text=r["verdict"],
                      width=660)
        c.create_text(122, 100, anchor="w", fill=MUTED, font=("Segoe UI", 8),
                      text=f"Página principal estimada por la primera conexión de la carga · "
                           f"{time.strftime('%H:%M:%S', time.localtime(r['time']))}")

    def _chips(self):
        r, cnt = self.report, self.report["count"]
        row = tk.Frame(self, bg=BG)
        row.pack(fill="x", padx=10, pady=4)
        for label, value, color in (
                ("Sitios contactados", r["n_hosts"], FG),
                ("De terceros", r["n_third"], "#ffd166"),
                ("Publicidad", cnt["ads"], CATS["ads"][1]),
                ("Analítica", cnt["analytics"], CATS["analytics"][1]),
                ("Redes sociales", cnt["social"], CATS["social"][1]),
                ("Bloqueados", r["protected"], "#7fd6a6"),
                ("Peso", human(r["bytes"]), FG),
                ("Tiempo", f"{r['seconds']:.1f} s", FG)):
            f = tk.Frame(row, bg=PANEL, padx=8, pady=4)
            f.pack(side="left", expand=True, fill="x", padx=2)
            tk.Label(f, text=str(value), bg=PANEL, fg=color, font=("Segoe UI", 14, "bold")).pack()
            tk.Label(f, text=label, bg=PANEL, fg=MUTED, font=("Segoe UI", 8)).pack()

    def _table(self):
        box = tk.Frame(self, bg=BG)
        box.pack(fill="both", expand=True, padx=10, pady=4)
        cols = ("site", "type", "size", "conns", "state")
        self.tree = ttk.Treeview(box, columns=cols, show="headings", style="R.Treeview",
                                 selectmode="extended")
        for c, txt, w, a in (("site", "Sitio", 300, "w"), ("type", "Qué es", 130, "w"),
                             ("size", "Peso", 80, "e"), ("conns", "Conex.", 60, "e"),
                             ("state", "Estado", 120, "w")):
            self.tree.heading(c, text=txt)
            self.tree.column(c, width=w, anchor=a)
        for key, (_, color, _) in CATS.items():
            self.tree.tag_configure(key, foreground=color)
        self.tree.tag_configure("blocked", foreground="#5f7390")
        sb = ttk.Scrollbar(box, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<Double-1>", lambda e: self.block_selected())
        tip(self.tree, area=self._row_tip)
        self.tip = tk.Label(self, text="", bg=BG, fg=MUTED, font=("Segoe UI", 9), anchor="w")
        self.tip.pack(fill="x", padx=12)
        self.tree.bind("<<TreeviewSelect>>", self._select)
        self._fill()

    def _fill(self):
        self.tree.delete(*self.tree.get_children())
        for i, h in enumerate(self.report["hosts"]):
            label = CATS[h["cat"]][0]
            state = STATUS_TEXT[h["status"]]
            if h["status"] != "blocked" and self.is_listed(h["host"]):
                state = "🚫 bloqueado ahora"
            tags = ("blocked",) if h["status"] == "blocked" else (h["cat"],)
            self.tree.insert("", "end", iid=str(i), tags=tags, values=(
                h["host"], label, human(h["bytes"]) if h["bytes"] else "·", h["conns"], state))

    def _row_tip(self, x, y):
        iid = self.tree.identify_row(y)
        if not iid:
            return None
        h = self.report["hosts"][int(iid)]
        label, _, why = CATS[h["cat"]]
        state = {"blocked": "Bloqueado: no llegó a enviar ni recibir nada.",
                 "cut": "Lo cortaste tú.", "done": "Cargó con normalidad."}[h["status"]]
        return f"{h['host']}\n{label}: {why}.\n{state}\nDoble clic: añadirlo a tu lista de bloqueo."

    def _select(self, _e=None):
        sel = self.tree.selection()
        if len(sel) == 1:
            h = self.report["hosts"][int(sel[0])]
            self.tip.config(text=f"{CATS[h['cat']][0]}: {CATS[h['cat']][2]}.  "
                                 "Doble clic o «Bloquear» para no volver a contactarlo.")
        else:
            self.tip.config(text="")

    def _buttons(self):
        row = tk.Frame(self, bg=BG)
        row.pack(fill="x", padx=10, pady=(4, 10))
        tip(self._btn(row, "🚫 Bloquear seleccionados", self.block_selected, "#7a2a2a"),
            "Añade los sitios seleccionados a tu lista de bloqueo. Surte efecto en la próxima carga.")
        n = sum(1 for h in self.report["hosts"] if h["cat"] in ("ads", "analytics", "social")
                and h["status"] != "blocked" and not self.is_listed(h["host"]))
        self.all_btn = self._btn(row, f"🚫 Bloquear todos los rastreadores ({n})",
                                 self.block_all_trackers, "#7a2a2a")
        if self.on_allow:
            tip(self._btn(row, "✅ Permitir seleccionados", self.allow_selected, "#2e6b4a"),
                "Añade el sitio a tus excepciones: TrafficBar dejará de bloquearlo (útil si la página "
                "se rompe sin él).")
        self._btn(row, "Cerrar", self.destroy, "#27405f", side="right")

    def _btn(self, parent, text, cmd, bg, side="left"):
        b = tk.Button(parent, text=text, command=cmd, bg=bg, fg="white", relief="flat", bd=0,
                      padx=12, pady=5, font=("Segoe UI", 9), cursor="hand2",
                      activebackground="#ff6b6b")
        b.pack(side=side, padx=3)
        return b

    def _block(self, hosts):
        added = [h for h in hosts if self.on_block(h)]
        self._fill()
        self.tip.config(text=f"Bloqueado(s): {', '.join(sorted({base_domain(h) for h in added}))}. "
                             "Tendrá efecto en la próxima carga." if added else
                             "Nada nuevo que bloquear.")
        self.all_btn.config(text="🚫 Bloquear todos los rastreadores (0)")

    def allow_selected(self):
        hosts = [self.report["hosts"][int(i)]["host"] for i in self.tree.selection()]
        added = [h for h in hosts if self.on_allow(h)]
        self._fill()
        self.tip.config(text=("Permitido(s): " + ", ".join(sorted({base_domain(h) for h in added}))
                              + ". Tendrá efecto en la próxima carga.") if added else
                        "Selecciona uno o más sitios de la lista.")

    def block_selected(self):
        hosts = [self.report["hosts"][int(i)]["host"] for i in self.tree.selection()]
        if hosts:
            self._block(hosts)

    def block_all_trackers(self):
        self._block([h["host"] for h in self.report["hosts"]
                     if h["cat"] in ("ads", "analytics", "social")
                     and h["status"] != "blocked" and not self.is_listed(h["host"])])
