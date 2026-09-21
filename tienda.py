"""Compatibilidad con las apps de la Tienda de Windows (UWP): WhatsApp, Microsoft Store, etc.

Windows aísla esas apps y NO les deja conectarse a 127.0.0.1, que es donde escucha el proxy de NavTool. Con el
proxy encendido parecen «bloqueadas». La solución oficial es la «exención de loopback» de cada app
(`CheckNetIsolation LoopbackExempt`), que necesita administrador. Este módulo la gestiona de forma acotada:

* Solo se exentan paquetes que están INSTALADOS (se comprueba justo antes de aplicar).
* Solo se quitan las exenciones que hizo NavTool (se guardan en un archivo), nunca las de otros programas.
* Sin shell: los argumentos van en lista y el nombre del paquete se valida con una expresión estricta.
"""
import ctypes
import json
import os
import re
import subprocess  # nosec B404
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

from safety import clean_text, powershell_exe, system_exe

PFN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.\-]{1,100}_[a-z0-9]{13}$")
PFN_BUSCA = re.compile(r"([A-Za-z0-9][A-Za-z0-9.\-]{1,100}_[a-z0-9]{13})")
RECOMENDADAS = ("WhatsAppDesktop", "Microsoft.WindowsStore", "WindowsStore")
BG, PANEL, FG, MUTED, ACC = "#1b2a41", "#0f1a2b", "#e8eef7", "#8ea3bd", "#3fa9f5"
_cfg = {"estado": None, "pedido": None, "resultado": None}


def configurar(carpeta_datos):
    _cfg["estado"] = os.path.join(carpeta_datos, "tienda_exenciones.json")
    _cfg["pedido"] = os.path.join(carpeta_datos, "tienda_pedido.json")
    _cfg["resultado"] = os.path.join(carpeta_datos, "tienda_resultado.json")


def es_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


# ------------------------------------------------------------------------------ consultas (sin admin)
def _run(args, timeout=40):
    r = subprocess.run(args, capture_output=True, timeout=timeout,  # nosec B603
                       creationflags=0x08000000)
    return r.returncode, r.stdout.decode("utf-8", "replace") + r.stderr.decode("utf-8", "replace")


def apps_instaladas():
    """[{nombre, pfn}] de las apps instaladas (sin bibliotecas ni paquetes de idioma), por orden alfabético."""
    script = ("[Console]::OutputEncoding=[Text.Encoding]::UTF8;"
              "Get-AppxPackage | Where-Object { -not $_.IsFramework -and -not $_.IsResourcePackage } | "
              "Select-Object Name,PackageFamilyName | ConvertTo-Json -Compress")
    rc, out = _run([powershell_exe(), "-NoProfile", "-NonInteractive", "-Command", script], 60)
    try:
        datos = json.loads(out) if out.strip() else []
    except ValueError:
        return []
    if isinstance(datos, dict):
        datos = [datos]
    vistos, res = set(), []
    for d in datos:
        pfn = str(d.get("PackageFamilyName") or "")
        if PFN_RE.match(pfn) and pfn.lower() not in vistos:
            vistos.add(pfn.lower())
            res.append({"nombre": clean_text(str(d.get("Name") or pfn), 80), "pfn": pfn})
    return sorted(res, key=lambda x: x["nombre"].lower())


def exentas():
    """Conjunto (en minúsculas) de los paquetes que ya tienen exención de loopback."""
    rc, out = _run([system_exe("CheckNetIsolation"), "LoopbackExempt", "-s"])
    return {m.lower() for m in PFN_BUSCA.findall(out)}


def _cargar_estado():
    try:
        with open(_cfg["estado"], encoding="utf-8") as f:
            d = json.load(f)
        return [p for p in d if isinstance(p, str) and PFN_RE.match(p)][:500] if isinstance(d, list) else []
    except (OSError, ValueError, TypeError):
        return []


def _guardar_estado(lista):
    tmp = _cfg["estado"] + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(sorted({p for p in lista if isinstance(p, str) and PFN_RE.match(p)}), f, indent=1)
    os.replace(tmp, _cfg["estado"])


def gestionadas():
    """Las exenciones que hizo NavTool (las únicas que NavTool se permite quitar)."""
    return {p.lower() for p in _cargar_estado()}


# ------------------------------------------------------------------------------ cambios (administrador)
def aplicar(agregar, quitar):
    """Aplica los cambios. Requiere administrador. Devuelve {ok: [...], error: [(pfn, motivo)]}."""
    res = {"ok": [], "error": []}
    if not es_admin():
        res["error"].append(("", "Hacen falta permisos de administrador."))
        return res
    instaladas = {a["pfn"].lower(): a["pfn"] for a in apps_instaladas()}
    estado = _cargar_estado()
    propias = {p.lower() for p in estado}
    for pfn in list(dict.fromkeys(agregar))[:200]:
        if not isinstance(pfn, str) or not PFN_RE.match(pfn) or pfn.lower() not in instaladas:
            res["error"].append((str(pfn)[:60], "No es una app instalada."))
            continue
        pfn = instaladas[pfn.lower()]
        rc, out = _run([system_exe("CheckNetIsolation"), "LoopbackExempt", "-a", f"-n={pfn}"])
        if rc == 0:
            res["ok"].append(pfn)
            if pfn.lower() not in propias:
                estado.append(pfn)
                propias.add(pfn.lower())
        else:
            res["error"].append((pfn, clean_text(out.strip(), 120)))
    for pfn in list(dict.fromkeys(quitar))[:200]:
        if not isinstance(pfn, str) or not PFN_RE.match(pfn) or pfn.lower() not in propias:
            res["error"].append((str(pfn)[:60], "NavTool no creó esa exención: no la quita."))
            continue
        rc, out = _run([system_exe("CheckNetIsolation"), "LoopbackExempt", "-d", f"-n={pfn}"])
        if rc == 0:
            res["ok"].append(pfn)
            estado = [p for p in estado if p.lower() != pfn.lower()]
            propias.discard(pfn.lower())
        else:
            res["error"].append((pfn, clean_text(out.strip(), 120)))
    _guardar_estado(estado)
    return res


def quitar_todas():
    """Al desinstalar: quita las exenciones que hizo NavTool."""
    if not es_admin():
        return 0
    n = 0
    for pfn in _cargar_estado():
        if _run([system_exe("CheckNetIsolation"), "LoopbackExempt", "-d", f"-n={pfn}"])[0] == 0:
            n += 1
    _guardar_estado([])
    return n


# ------------------------------------------------------------------------------ elevación (UAC)
def pedir_cambios(agregar, quitar):
    """Escribe el pedido y relanza NavTool con administrador para aplicarlo. Devuelve True si se lanzó."""
    with open(_cfg["pedido"], "w", encoding="utf-8") as f:
        json.dump({"hora": time.time(), "agregar": agregar, "quitar": quitar}, f)
    try:
        os.remove(_cfg["resultado"])
    except OSError:
        pass
    if getattr(sys, "frozen", False):
        exe, args = sys.executable, "--tienda-aplicar"
    else:
        exe, args = sys.executable, f'"{os.path.abspath(sys.argv[0])}" --tienda-aplicar'
    return ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, args, None, 0) > 32


def ejecutar_pedido():
    """Lo que hace la copia elevada (--tienda-aplicar): lee el pedido, lo aplica y deja el resultado."""
    res = {"ok": [], "error": [("", "Pedido no válido o caducado.")]}
    try:
        with open(_cfg["pedido"], encoding="utf-8") as f:
            p = json.load(f)
        if time.time() - float(p.get("hora", 0)) < 300 and isinstance(p.get("agregar"), list) \
                and isinstance(p.get("quitar"), list):
            res = aplicar([str(x) for x in p["agregar"]], [str(x) for x in p["quitar"]])
    except (OSError, ValueError, TypeError):
        pass
    finally:
        try:
            os.remove(_cfg["pedido"])
        except OSError:
            pass
    with open(_cfg["resultado"], "w", encoding="utf-8") as f:
        json.dump(res, f)
    return res


# ------------------------------------------------------------------------------ interfaz
class VentanaTienda(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app, bg=BG)
        self.app = app
        self.title("NavTool – Compatibilidad con apps de la Tienda")
        self.attributes("-topmost", True)
        if hasattr(app, "place_near"):
            app.place_near(self, 700, 560)
        self.filas = {}        # iid -> {nombre, pfn, marcada, exenta, propia}
        self.desc = tk.Label(self, text=("Con el proxy de NavTool encendido, las apps de la Tienda de Windows (WhatsApp, "
                             "Microsoft Store…) no pueden conectarse: Windows les prohíbe hablar con este equipo. "
                             "Marca las que quieras usar con el proxy encendido y pulsa «Aplicar». "
                             "Es una excepción de red solo para esas apps y se puede deshacer aquí."),
                 bg=BG, fg=FG, wraplength=560, justify="left", anchor="w")
        self.desc.pack(fill="x", padx=14, pady=(12, 6))
        self.bind("<Configure>", self._ajusta)
        top = tk.Frame(self, bg=BG)
        top.pack(fill="x", padx=14)
        tk.Label(top, text="Buscar:", bg=BG, fg=MUTED).pack(side="left")
        self.q = tk.StringVar()
        e = tk.Entry(top, textvariable=self.q, width=28, bg=PANEL, fg=FG, insertbackground=FG, relief="flat")
        e.pack(side="left", padx=6, ipady=3)
        self.q.trace_add("write", lambda *a: self._pintar())
        tk.Button(top, text="Marcar las recomendadas", command=self.recomendadas, bg="#27405f", fg="white",
                  relief="flat", cursor="hand2", padx=8).pack(side="left", padx=6)
        st = ttk.Style(self)
        st.configure("T.Treeview", background=PANEL, fieldbackground=PANEL, foreground=FG, borderwidth=0,
                     rowheight=int(24 * getattr(app, "ui_scale", 1.0)))
        st.configure("T.Treeview.Heading", background="#0f1a2b", foreground=MUTED, relief="flat")
        cols = ("marca", "app", "estado")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", style="T.Treeview", selectmode="browse")
        for c, t, w, a in (("marca", "", 40, "center"), ("app", "App", 400, "w"), ("estado", "Estado", 190, "w")):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor=a)
        self.tree.pack(fill="both", expand=True, padx=14, pady=8)
        self.tree.bind("<Button-1>", self._clic)
        row = tk.Frame(self, bg=BG)
        row.pack(fill="x", padx=14, pady=(0, 6))
        self.btn = tk.Button(row, text="✅ Aplicar cambios", command=self.aplicar, bg=ACC, fg="white",
                             relief="flat", cursor="hand2", padx=12, state="disabled")
        self.btn.pack(side="left")
        tk.Button(row, text="Cerrar", command=self.destroy, bg="#27405f", fg="white", relief="flat",
                  cursor="hand2", padx=12).pack(side="right")
        self.msg = tk.Label(self, text="Buscando las apps instaladas…", bg=BG, fg="#ffa94d", anchor="w",
                            wraplength=560, justify="left")
        self.msg.pack(fill="x", padx=14, pady=(0, 10))
        threading.Thread(target=self._cargar, daemon=True).start()

    def _ajusta(self, e):
        if e.widget is self:                    # el texto se ajusta al ancho real de la ventana
            w = max(300, self.winfo_width() - 40)
            self.desc.config(wraplength=w)
            self.msg.config(wraplength=w)

    def _cargar(self):
        try:
            apps, ya, propias = apps_instaladas(), exentas(), gestionadas()
        except Exception as e:
            apps, ya, propias = [], set(), set()
            self.app._acts.put(lambda: self.msg.config(text=f"No se pudo leer la lista de apps: {e}"))
            return
        self.app._acts.put(lambda: self._mostrar(apps, ya, propias))

    def _mostrar(self, apps, ya, propias):
        if not self.winfo_exists():
            return
        self.filas = {}
        apps = sorted(apps, key=lambda a: (not any(k.lower() in a["nombre"].lower() for k in RECOMENDADAS),
                                           a["nombre"].lower()))          # las recomendadas, arriba
        for i, a in enumerate(apps):
            ex = a["pfn"].lower() in ya
            self.filas[str(i)] = {"nombre": a["nombre"], "pfn": a["pfn"], "marcada": ex, "exenta": ex,
                                  "propia": a["pfn"].lower() in propias}
        self.btn.config(state="normal")
        self.msg.config(text=f"{len(apps)} apps encontradas." if apps else "No se encontraron apps.")
        self._pintar()

    def _pintar(self):
        if not self.winfo_exists():
            return
        q = self.q.get().strip().lower()
        self.tree.delete(*self.tree.get_children())
        for iid, f in self.filas.items():
            if q and q not in f["nombre"].lower():
                continue
            estado = ("Con excepción (hecha por NavTool)" if f["propia"] else "Con excepción (de otro origen)") \
                if f["exenta"] else "Sin excepción"
            self.tree.insert("", "end", iid=iid, values=("☑" if f["marcada"] else "☐", f["nombre"], estado))

    def _clic(self, e):
        iid = self.tree.identify_row(e.y)
        if not iid or self.tree.identify_column(e.x) != "#1":
            return
        f = self.filas[iid]
        if f["exenta"] and not f["propia"]:
            self.msg.config(text="Esa excepción no la creó NavTool: NavTool no la quita.")
            return
        f["marcada"] = not f["marcada"]
        self._pintar()

    def recomendadas(self):
        for f in self.filas.values():
            if any(k.lower() in f["nombre"].lower() for k in RECOMENDADAS):
                f["marcada"] = True
        self._pintar()

    def aplicar(self):
        agregar = [f["pfn"] for f in self.filas.values() if f["marcada"] and not f["exenta"]]
        quitar = [f["pfn"] for f in self.filas.values() if not f["marcada"] and f["exenta"] and f["propia"]]
        if not agregar and not quitar:
            self.msg.config(text="No hay cambios que aplicar.")
            return
        if not messagebox.askyesno("NavTool", f"Se van a añadir {len(agregar)} excepción(es) y quitar {len(quitar)}.\n\n"
                                   "Windows pedirá permisos de administrador. ¿Continuar?", parent=self):
            return
        self.btn.config(state="disabled")
        if es_admin():
            self._fin(aplicar(agregar, quitar))
            return
        if not pedir_cambios(agregar, quitar):
            self.msg.config(text="Se canceló la petición de administrador.")
            self.btn.config(state="normal")
            return
        self.msg.config(text="Esperando la confirmación de administrador…")
        self._espera = time.time()
        self.after(700, self._sondeo)

    def _sondeo(self):
        if not self.winfo_exists():
            return
        try:
            with open(_cfg["resultado"], encoding="utf-8") as f:
                res = json.load(f)
            os.remove(_cfg["resultado"])
            res["error"] = [tuple(x) for x in res.get("error", [])]
            self._fin(res)
        except (OSError, ValueError):
            if time.time() - self._espera > 90:
                self.msg.config(text="No se recibió respuesta. Si aceptaste el aviso, pulsa «Aplicar» otra vez.")
                self.btn.config(state="normal")
            else:
                self.after(700, self._sondeo)

    def _fin(self, res):
        self.btn.config(state="normal")
        txt = f"Listo: {len(res['ok'])} cambio(s) aplicado(s)."
        if res["error"]:
            txt += f" {len(res['error'])} con error: {res['error'][0][1]}"
        self.msg.config(text=txt)
        threading.Thread(target=self._cargar, daemon=True).start()
        if res["ok"]:
            messagebox.showinfo("NavTool", "Cambios aplicados. Cierra y vuelve a abrir esas apps para que los usen.",
                                parent=self)
