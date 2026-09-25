"""Bloqueo del acceso a Internet de un programa mediante el Cortafuegos de Windows.

TrafficBar crea dos reglas (entrada y salida) con un nombre propio «TrafficBar block: …». Necesita permisos
de administrador. Es reversible: el gestor de bloqueados las quita, y las temporales caducan solas
mientras TrafficBar esté abierto como administrador. NUNCA bloquea componentes de Windows ni a TrafficBar.
"""
import ctypes
import hashlib
import json
import os
import re
import subprocess  # nosec B404
import sys
import time
import tkinter as tk
from tkinter import messagebox, ttk

from safety import clean_text, system_dir, system_exe

PREFIJO = "TrafficBar block: "
PROTEGIDOS = {
    "system", "svchost.exe", "csrss.exe", "lsass.exe", "services.exe", "wininit.exe", "winlogon.exe",
    "smss.exe", "explorer.exe", "dwm.exe", "spoolsv.exe", "taskhostw.exe", "searchhost.exe",
    "msmpeng.exe", "sihost.exe", "ctfmon.exe", "fontdrvhost.exe", "trafficbar.exe", "python.exe",
    "pythonw.exe", "wudfhost.exe", "audiodg.exe", "runtimebroker.exe", "yogadns.exe",
}
BG, PANEL, FG, MUTED, ACC = "#1b2a41", "#0f1a2b", "#e8eef7", "#8ea3bd", "#3fa9f5"
_estado = {"ruta": None}


def configurar(ruta_estado):
    _estado["ruta"] = ruta_estado


def es_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


# ---------------------------------------------------------------- estado en disco
def _cargar():
    try:
        with open(_estado["ruta"], encoding="utf-8") as f:
            datos = json.load(f)
    except (OSError, ValueError, TypeError):
        return []
    out = []
    for d in datos if isinstance(datos, list) else []:
        if isinstance(d, dict) and isinstance(d.get("ruta"), str) and isinstance(d.get("regla"), str) \
                and d["regla"].startswith(PREFIJO):           # nunca se toca una regla ajena a TrafficBar
            out.append({"nombre": clean_text(str(d.get("nombre", "")), 60), "ruta": d["ruta"],
                        "regla": d["regla"][:200], "desde": float(d.get("desde") or 0),
                        "hasta": float(d.get("hasta") or 0)})
    return out[:500]


def _guardar(lista):
    if not _estado["ruta"]:
        return
    tmp = _estado["ruta"] + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(lista, f, ensure_ascii=False, indent=1)
    os.replace(tmp, _estado["ruta"])


# ---------------------------------------------------------------- validación
def validar(ruta):
    """(ok, motivo). Solo rutas absolutas a un .exe que exista y que no sea de Windows ni de TrafficBar."""
    if not isinstance(ruta, str) or not ruta or len(ruta) > 259 or re.search(r'[\x00-\x1f"<>|*?]', ruta):
        return False, "La ruta del programa no es válida."
    if not os.path.isabs(ruta) or not ruta.lower().endswith(".exe") or not os.path.isfile(ruta):
        return False, "No se pudo localizar el archivo .exe del programa."
    norm = os.path.normcase(os.path.realpath(ruta))
    windir = os.path.normcase(os.path.dirname(system_dir()))
    if norm.startswith(windir + os.sep):
        return False, "Es un componente de Windows: bloquearlo podría dejar el sistema sin funcionar."
    if os.path.basename(norm) in PROTEGIDOS:
        return False, "Es un programa protegido (necesario para Windows o para TrafficBar)."
    if getattr(sys, "frozen", False) and norm == os.path.normcase(os.path.realpath(sys.executable)):
        return False, "No se puede bloquear a TrafficBar desde sí mismo."
    return True, ""


def nombre_regla(ruta):
    base = re.sub(r"[^\w.\- ]", "_", os.path.basename(ruta).lower())[:50]
    return f"{PREFIJO}{base} [{hashlib.sha1(ruta.lower().encode('utf-8')).hexdigest()[:8]}]"  # nosec B324


def _netsh(*args):
    r = subprocess.run([system_exe("netsh"), "advfirewall", "firewall", *args],  # nosec B603
                       capture_output=True, timeout=25, creationflags=0x08000000)
    return r.returncode, r.stdout.decode("cp850", "replace") + r.stderr.decode("cp850", "replace")


def _regla_existe(regla):
    return _netsh("show", "rule", f"name={regla}")[0] == 0


# ---------------------------------------------------------------- operaciones
def bloquear(ruta, minutos=0):
    ok, motivo = validar(ruta)
    if not ok:
        return False, motivo
    if not es_admin():
        return False, "Hacen falta permisos de administrador (abre 📡 Tráfico y acepta reiniciar como administrador)."
    regla = nombre_regla(ruta)
    _netsh("delete", "rule", f"name={regla}")                       # evita reglas duplicadas
    for d in ("out", "in"):
        rc, out = _netsh("add", "rule", f"name={regla}", f"dir={d}", "action=block",
                         f"program={ruta}", "enable=yes", "profile=any")
        if rc != 0:
            _netsh("delete", "rule", f"name={regla}")
            return False, "Windows rechazó la regla: " + clean_text(out.strip(), 200)
    lista = [x for x in _cargar() if x["regla"] != regla]
    now = time.time()
    lista.append({"nombre": clean_text(os.path.basename(ruta), 60), "ruta": ruta, "regla": regla,
                  "desde": now, "hasta": now + minutos * 60 if minutos else 0})
    _guardar(lista)
    return True, ""


def desbloquear(ruta_o_regla):
    if not es_admin():
        return False, "Hacen falta permisos de administrador."
    lista = _cargar()
    item = next((x for x in lista if x["ruta"] == ruta_o_regla or x["regla"] == ruta_o_regla), None)
    if not item:
        return False, "Ese programa no está en la lista de bloqueados por TrafficBar."
    _netsh("delete", "rule", f"name={item['regla']}")
    _guardar([x for x in lista if x is not item])
    return True, ""


def listar():
    return _cargar()


def bloqueado(ruta):
    return any(x["ruta"] == ruta for x in _cargar())


def caducados():
    """Quita los bloqueos temporales vencidos. Devuelve los nombres desbloqueados."""
    if not es_admin():
        return []
    now, out = time.time(), []
    for x in _cargar():
        if x["hasta"] and x["hasta"] <= now and desbloquear(x["regla"])[0]:
            out.append(x["nombre"])
    return out


def quitar_todos():
    """Al desinstalar: elimina todas las reglas creadas por TrafficBar."""
    n = 0
    for x in _cargar():
        _netsh("delete", "rule", f"name={x['regla']}")
        n += 1
    _guardar([])
    return n


# ---------------------------------------------------------------- interfaz
def preguntar(parent, nombre, ruta):
    """Ventana de confirmación. Devuelve None (cancelar) o los minutos (0 = hasta que lo desbloquees)."""
    ok, motivo = validar(ruta)
    if not ok:
        messagebox.showinfo("TrafficBar", motivo, parent=parent)
        return None
    res = {"v": None}
    t = tk.Toplevel(parent, bg=BG)
    t.title("TrafficBar – Bloquear programa")
    t.attributes("-topmost", True)
    t.resizable(False, False)
    tk.Label(t, text=f"Bloquear el acceso a Internet de «{nombre}»", bg=BG, fg=ACC,
             font=("Segoe UI", 12, "bold"), anchor="w").pack(fill="x", padx=16, pady=(14, 4))
    tk.Label(t, text=(f"Ruta: {ruta}\n\nSe crearán reglas en el Cortafuegos de Windows que impiden que este "
                      "programa envíe o reciba datos por la red (todas las conexiones). Verás el cambio "
                      "en «Bloqueados»; puedes deshacerlo cuando quieras.\n\nEl programa seguirá "
                      "abriéndose y funcionando sin conexión."),
             bg=BG, fg=FG, justify="left", wraplength=460, anchor="w").pack(fill="x", padx=16, pady=4)
    v = tk.IntVar(value=60)
    for txt, val in (("Durante 1 hora", 60), ("Durante 4 horas", 240), ("Hasta que yo lo desbloquee", 0)):
        tk.Radiobutton(t, text=txt, variable=v, value=val, bg=BG, fg=FG, selectcolor=PANEL,
                       activebackground=BG, activeforeground=FG).pack(anchor="w", padx=24)
    tk.Label(t, text="Los bloqueos temporales se levantan solos mientras TrafficBar esté abierto como administrador.",
             bg=BG, fg=MUTED, font=("Segoe UI", 8), wraplength=460, justify="left").pack(padx=16, pady=(4, 0))
    row = tk.Frame(t, bg=BG)
    row.pack(fill="x", padx=16, pady=14)

    def go():
        res["v"] = v.get()
        t.destroy()
    tk.Button(row, text="Bloquear", command=go, bg="#b93c3c", fg="white", relief="flat", padx=16,
              cursor="hand2").pack(side="right")
    tk.Button(row, text="Cancelar", command=t.destroy, bg="#27405f", fg="white", relief="flat",
              padx=12, cursor="hand2").pack(side="right", padx=8)
    t.update_idletasks()
    x = parent.winfo_rootx() + max(0, (parent.winfo_width() - t.winfo_reqwidth()) // 2)
    y = parent.winfo_rooty() + 80
    t.geometry(f"+{x}+{y}")
    t.grab_set()
    parent.wait_window(t)
    return res["v"]


class VentanaBloqueados(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app, bg=BG)
        self.app = app
        self.title("TrafficBar – Programas bloqueados")
        self.attributes("-topmost", True)
        if hasattr(app, "place_near"):
            app.place_near(self, 760, 380)
        tk.Label(self, text="Programas sin acceso a Internet (reglas del Cortafuegos creadas por TrafficBar)",
                 bg=BG, fg=FG, anchor="w").pack(fill="x", padx=12, pady=(10, 2))
        st = ttk.Style(self)
        st.configure("B.Treeview", background=PANEL, fieldbackground=PANEL, foreground=FG,
                     rowheight=int(26 * getattr(app, "ui_scale", 1.0)), borderwidth=0)
        st.configure("B.Treeview.Heading", background="#0f1a2b", foreground=MUTED, relief="flat")
        cols = ("nombre", "hasta", "ruta")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", style="B.Treeview", height=8)
        for c, txt, w in (("nombre", "Programa", 150), ("hasta", "Hasta", 140), ("ruta", "Ruta", 420)):
            self.tree.heading(c, text=txt)
            self.tree.column(c, width=w, anchor="w")
        self.tree.pack(fill="both", expand=True, padx=12, pady=6)
        row = tk.Frame(self, bg=BG)
        row.pack(fill="x", padx=12, pady=(0, 10))
        tk.Button(row, text="✅ Desbloquear seleccionado", command=self.unblock, bg=ACC, fg="white",
                  relief="flat", padx=12, cursor="hand2").pack(side="left")
        tk.Button(row, text="Cerrar", command=self.destroy, bg="#27405f", fg="white", relief="flat",
                  padx=12, cursor="hand2").pack(side="right")
        self.msg = tk.Label(self, text="", bg=BG, fg="#ffa94d", anchor="w")
        self.msg.pack(fill="x", padx=12, pady=(0, 8))
        self.refresh()

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        for x in listar():
            hasta = time.strftime("%d/%m %H:%M", time.localtime(x["hasta"])) if x["hasta"] else "manual"
            self.tree.insert("", "end", iid=x["regla"], values=(x["nombre"], hasta, x["ruta"]))
        if not self.tree.get_children():
            self.msg.config(text="No hay programas bloqueados.")

    def unblock(self):
        sel = self.tree.selection()
        if not sel:
            return
        ok, why = desbloquear(sel[0])
        self.msg.config(text="" if ok else why)
        self.refresh()
