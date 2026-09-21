"""Pruebas de las funciones nuevas: cuota mensual, bloqueo de programas, idiomas y créditos.

    python pruebas_funciones.py

Usa carpetas temporales y un cortafuegos simulado (no crea reglas reales).
"""
import faulthandler; faulthandler.dump_traceback_later(240, exit=True)
import os, shutil, sys, tempfile, time
os.environ["NAVTOOL_LANG"] = "es"        # las comprobaciones de textos son sobre el original
tmp = tempfile.mkdtemp(prefix="navfeat_")
os.environ["APPDATA"] = os.path.join(tmp, "r"); os.environ["LOCALAPPDATA"] = os.path.join(tmp, "l")
os.makedirs(os.environ["APPDATA"]); os.makedirs(os.environ["LOCALAPPDATA"])
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import navtool as n, cuota, programas
from history import History

ok = fail = 0
def check(name, cond, detail=""):
    global ok, fail
    ok += cond; fail += (not cond)
    print(f"[{'OK   ' if cond else 'FALLA'}] {name}" + (f"  → {detail}" if detail else ""))

# ---------------- cuota
h = History(os.path.join(tmp, "h.db"))
now = time.mktime((2026, 9, 20, 12, 0, 0, 0, 0, -1))
s, e = cuota.ciclo(now, 1)
check("Ciclo día 1: del 1 sep al 1 oct", time.localtime(s)[:3] == (2026, 9, 1) and time.localtime(e)[:3] == (2026, 10, 1))
s2, e2 = cuota.ciclo(now, 25)
check("Ciclo día 25 (hoy es 20): del 25 ago al 25 sep", time.localtime(s2)[:3] == (2026, 8, 25) and time.localtime(e2)[:3] == (2026, 9, 25))
s3, _ = cuota.ciclo(time.mktime((2026, 1, 10, 0, 0, 0, 0, 0, -1)), 15)
check("Ciclo cruza el año (10 ene, día 15 → 15 dic)", time.localtime(s3)[:3] == (2025, 12, 15))
check("El día se limita a 1-28", cuota.ciclo(now, 99)[0] == cuota.ciclo(now, 28)[0])
GB = 1024 ** 3
for d in range(0, 19):                                    # 2 GB de bajada y 0,5 de subida por día
    h.add_minute(s + d * 86400 + 600, 2 * GB, GB // 2)
cfg = {"quota_gb": 50.0, "quota_day": 1, "quota_count": "both"}
r = cuota.resumen(h, cfg, now)
check("Suma exacta del ciclo", r["used"] == 19 * int(2.5 * GB), f"{r['used'] / GB:.1f} GB")
check("Porcentaje y días restantes", abs(r["pct"] - 95.0) < 0.1 and r["days_left"] == 10, f"{r['pct']:.1f} %, {r['days_left']} días")
check("Proyección supera la cuota", r["projected"] > r["quota"])
cfg2 = dict(cfg, quota_count="down")
check("«Solo bajada» cuenta menos", cuota.resumen(h, cfg2, now)["used"] == 19 * 2 * GB)
check("Sin cuota → porcentaje 0 y sin error", cuota.resumen(h, {"quota_gb": 0, "quota_day": 1}, now)["pct"] == 0)
got = []
cuota.comprobar_alertas(h, cfg, lambda k, t, d: (got.append(k), h.add_alert(k, t, d)), now)
cuota.comprobar_alertas(h, cfg, lambda k, t, d: (got.append(k), h.add_alert(k, t, d)), now)
check("Avisa una sola vez por umbral (80 % sí, 100 % aún no)", got == ["quota80"], str(got))
h.add_minute(s + 20 * 86400, 5 * GB, 0)
now2 = now + 86400 * 2
cuota.comprobar_alertas(h, cfg, lambda k, t, d: (got.append(k), h.add_alert(k, t, d)), now2)
check("Al superar el 100 % avisa una vez más", got == ["quota80", "quota100"], str(got))
d = h.daily(s, e)
check("Consumo por día agrupado", len(d) >= 19 and d[0]["d"] == 0)
h.add_minute(int(time.time() - 40 * 86400), 1, 1); h.add_alert("x", "viejo", "", "")
h.purge(30)
check("La purga conserva 62 días de tráfico", h.totals(time.time() - 45 * 86400, time.time() - 35 * 86400) == (1, 1))

# ---------------- programas
progdir = os.path.join(tmp, "app"); os.makedirs(progdir)
exe = os.path.join(progdir, "Mi Programa (x86).exe"); open(exe, "wb").write(b"MZ")
programas.configurar(os.path.join(tmp, "bloq.json"))
check("Acepta un .exe normal", programas.validar(exe)[0])
sysexe = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "notepad.exe")
check("Rechaza componentes de Windows", not programas.validar(sysexe)[0], programas.validar(sysexe)[1])
for bad in ("", "svchost.exe", r"C:\x\..\y.exe", 'C:\\a"b.exe', exe.replace(".exe", ".txt"), exe + "x", "a" * 400 + ".exe", "C:\\x\x00.exe"):
    check(f"Rechaza ruta inválida {bad[:22]!r}", not programas.validar(bad)[0])
prot = os.path.join(progdir, "svchost.exe"); open(prot, "wb").write(b"MZ")
check("Rechaza nombres protegidos aunque estén en otra carpeta", not programas.validar(prot)[0])
check("El nombre de regla es estable y lleva el prefijo", programas.nombre_regla(exe) == programas.nombre_regla(exe.upper()) and programas.nombre_regla(exe).startswith(programas.PREFIJO))

calls = []
def fake(*a):
    calls.append(a); return 0, "Aceptar"
programas._netsh = fake
programas.es_admin = lambda: False
ok1, why = programas.bloquear(exe, 60)
check("Sin administrador no toca el cortafuegos", not ok1 and not calls, why[:50])
programas.es_admin = lambda: True
ok2, _ = programas.bloquear(exe, 60)
adds = [c for c in calls if c[0] == "add"]
check("Crea dos reglas (salida y entrada) con argumentos separados", ok2 and len(adds) == 2 and {c[3] for c in adds} == {"dir=out", "dir=in"} and f"program={exe}" in adds[0], str(adds[0])[:110])
check("El estado queda guardado con caducidad", programas.listar()[0]["hasta"] > time.time() and programas.bloqueado(exe))
calls.clear(); ok3, _ = programas.desbloquear(exe)
check("Desbloquear borra la regla y el estado", ok3 and calls and calls[0][0] == "delete" and not programas.listar())
programas.bloquear(exe, 1)
lst = programas.listar(); lst[0]["hasta"] = time.time() - 5; programas._guardar(lst)
check("Los bloqueos vencidos se levantan solos", programas.caducados() == ["Mi Programa (x86).exe"] and not programas.listar())
import json
json.dump([{"nombre": "x", "ruta": exe, "regla": "Regla de OTRO programa", "desde": 0, "hasta": 0}], open(os.path.join(tmp, "bloq.json"), "w"))
check("Ignora reglas que no son de NavTool (no las toca)", programas.listar() == [])
open(os.path.join(tmp, "bloq.json"), "w").write("{corrupto")
check("Estado corrupto no rompe nada", programas.listar() == [])
programas.bloquear(exe, 0); calls.clear()
check("«Quitar todos» (desinstalación) borra las reglas", programas.quitar_todos() == 1 and calls[0][0] == "delete" and not programas.listar())

# ---------------- ventanas
app = n.Floating(); app.geometry("+300+60"); app.update(); app.watcher.stop()
def pump(s=.4):
    t = time.time()
    while time.time() - t < s: app.update(); time.sleep(0.02)
n.HIST = h
app.win_quota(); pump(.6)
w = app._quota
check("Ventana de cuota abre y muestra el ciclo", "usados" in w.head.cget("text"), w.head.cget("text"))
w.gb.set("40"); w.day.set("5"); w.mode.set("solo bajada"); w.save(); pump(.2)
check("Guardar cuota persiste en la configuración", n.CFG["quota_gb"] == 40.0 and n.CFG["quota_day"] == 5 and n.CFG["quota_count"] == "down")
programas.configurar(os.path.join(tmp, "bloq2.json")); programas.bloquear(exe, 0)
app.win_blocked(); pump(.4)
check("Ventana de bloqueados lista el programa", len(app._blocked.tree.get_children()) == 1)
app._blocked.tree.selection_set(app._blocked.tree.get_children()[0]); app._blocked.unblock(); pump(.2)
check("Desbloquear desde la ventana", not programas.listar())
json.dump({"quota_gb": "abc", "quota_day": 99, "quota_count": "x"}, open(n.CFG_FILE, "w"))
c = n.load_cfg()
check("Una configuración de cuota dañada se sanea", c["quota_gb"] == 0.0 and c["quota_day"] == 28 and c["quota_count"] == "both")

# ---------------- idiomas
import re
import i18n, json as _j
AQUI = os.path.dirname(os.path.abspath(__file__))
IDIOMAS = os.path.join(AQUI, "idiomas")
d = os.path.join(tmp, "packs"); os.makedirs(d)
def pack(name, datos):
    p = os.path.join(d, name); open(p, "w", encoding="utf-8").write(_j.dumps(datos, ensure_ascii=False)); return p
good = {"meta": {"code": "fr", "name": "Français", "version": 1, "author": "x"},
        "strings": {"Guardar": "Enregistrer", "Bloqueadas: {}": "Bloquées : {}", "{} de {}": "{2} sur {1}", "Hola\nmundo": "Salut\nmonde"}}
p, e = i18n.leer_pack(pack("good.json", good))
check("Un pack válido se lee", p and p["code"] == "fr" and len(p["strings"]) == 4)
for nombre, datos in {
    "no es un dict": [1, 2], "sin strings": {"meta": {"code": "fr"}}, "código «es» (reservado)": {"meta": {"code": "es"}, "strings": {"a": "b"}},
    "código con ruta": {"meta": {"code": "../evil"}, "strings": {"a": "b"}}, "código en mayúsculas": {"meta": {"code": "FR"}, "strings": {"a": "b"}},
    "código larguísimo": {"meta": {"code": "x" * 50}, "strings": {"a": "b"}}, "sin entradas útiles": {"meta": {"code": "fr"}, "strings": {"a": "", "b": 3}},
}.items():
    check(f"Rechaza pack: {nombre}", i18n.leer_pack(pack("m.json", datos))[0] is None)
big = {"meta": {"code": "fr"}, "strings": {str(i): "x" for i in range(7000)}}
check("Rechaza demasiadas entradas", i18n.leer_pack(pack("big.json", big))[0] is None)
open(os.path.join(d, "huge.json"), "w").write("{" + " " * 3_000_000 + "}")
check("Rechaza un archivo enorme sin leerlo", i18n.leer_pack(os.path.join(d, "huge.json"))[0] is None)
open(os.path.join(d, "roto.json"), "w").write("{no es json")
check("Un JSON roto no rompe nada", i18n.leer_pack(os.path.join(d, "roto.json"))[0] is None)
open(os.path.join(d, "bin.json"), "wb").write(b"\xff\xfe\x00\x01" * 50)
check("Un archivo binario no rompe nada", i18n.leer_pack(os.path.join(d, "bin.json"))[0] is None)
hostil = {"meta": {"code": "de", "name": "Deutsch\u202e\x00" + "N" * 100}, "strings": {
    "Guardar": "Sp\u202eeichern\x07", "Uno {}": "Eins {5}", "Dos {}": "Zwei {} {}", "Tres {} y {}": "{2}-{1}", "Ok": "{__class__}"}}
ph, _ = i18n.leer_pack(pack("h.json", hostil))
check("Quita controles y marcas RTL de nombres y textos", ph and "\u202e" not in ph["name"] and "\x00" not in ph["name"] and ph["strings"]["Guardar"] == "Speichern" and len(ph["name"]) <= 40, str(ph["name"])[:30])
check("Descarta marcadores imposibles ({5}, más huecos de los que hay)", "Uno {}" not in ph["strings"] and "Dos {}" not in ph["strings"])
check("Conserva los reordenados válidos", ph["strings"].get("Tres {} y {}") == "{2}-{1}")
i18n.activar("fr", [(d, False)])
check("Traducción exacta", i18n.tr("Guardar") == "Enregistrer")
check("Plantilla con partes variables", i18n.tr("Bloqueadas: 42") == "Bloquées : 42")
check("Marcadores reordenados", i18n.tr("3 de 9") == "9 sur 3")
check("Conserva espacios de los bordes", i18n.tr("  Guardar  ") == "  Enregistrer  ")
check("Texto de varias líneas, línea a línea", i18n.tr("Hola\nmundo") == "Salut\nmonde" and i18n.tr("Guardar\nBloqueadas: 7") == "Enregistrer\nBloquées : 7")
check("Lo que no está traducido queda igual", i18n.tr("Algo raro 123") == "Algo raro 123")
t0 = time.time(); i18n.tr("x" * 200000); i18n.tr(("{} de " * 500) + "fin"); i18n.tr("a de " * 40000)
check("Textos gigantes no cuelgan (sin regex)", time.time() - t0 < 1.0, f"{time.time() - t0:.3f} s")
i18n._st["tmpl"].append(("Z", ["Z", "", "", "", "", "", "Q"], "{}{}{}{}{}"))
t0 = time.time(); i18n.tr("Z" + "a" * 3000 + "x"); check("Plantilla con muchos huecos no explota", time.time() - t0 < 0.5)
i18n.activar("fr", [(d, False)])
check("«{__class__}» no se evalúa como código", i18n.tr("Ok") in ("{__class__}", "Ok"))
user = os.path.join(tmp, "userlang")
pk, err = i18n.importar(pack("good2.json", good), user)
check("Importar guarda una copia limpia con el nombre del código", pk and os.path.exists(os.path.join(user, "fr.json")) and not os.path.exists(os.path.join(user, "good2.json")))
pk2, err2 = i18n.importar(pack("evil.json", {"meta": {"code": "../../evil"}, "strings": {"a": "b"}}), user)
check("Un código con ruta no puede escribir fuera de la carpeta", pk2 is None and not os.path.exists(os.path.join(tmp, "evil.json")) and len(os.listdir(user)) == 1)
lst = i18n.paquetes([(IDIOMAS, True), (user, False)])
check("Se listan el inglés incluido y el pack del usuario", "en" in lst and "fr" in lst and lst["en"]["builtin"] and not lst["fr"]["builtin"])
check("La plantilla no cuenta como idioma", "xx" not in lst)
check("Un idioma inexistente vuelve al original", i18n.activar("zz", [(user, False)]) is False and i18n.idioma() == "es")
ok_en = i18n.activar("en", [(IDIOMAS, True)])
check("El inglés incluido carga y traduce", ok_en and i18n.tr("Guardar") == "Save" and i18n.tr("12 bloq.") == "12 blocked")
en, _ = i18n.leer_pack(os.path.join(IDIOMAS, "en.json"))
malos = [k for k, v in en["strings"].items() if len(i18n.HOLE_RE.findall(v)) != len(i18n.HOLE_RE.findall(k))]
check("En el pack de inglés cada traducción conserva sus {}", not malos, str(malos[:2]))
import extraer_textos as ex
ids = set(ex.extraer())
falta = [k for k in ids if k not in en["strings"] and len(k) > 12 and " " in k and not k.startswith(("<script", "Get-", "%", "[", '"'))
         and not re.fullmatch(r"[\w.\-() /{}]+", k) and k not in ("NavTool block:", "pcap_activate = {}", "🌐 Idioma / Language")]
check("El inglés cubre las frases de la interfaz", len(falta) == 0, f"{len(falta)} sin traducir: {falta[:2]}")
import tkinter as tk
from tkinter import ttk
lb = tk.Label(app, text="Guardar"); mn = tk.Menu(app, tearoff=0); mn.add_command(label="Cerrar")
tv = ttk.Treeview(app, columns=("a",), show="headings"); tv.heading("a", text="Programa"); tv.insert("", "end", values=("Hoy",))
tx = tk.Text(app); tx.insert("end", "Cancelar")
check("Etiquetas, menús, tablas y cuadros de texto se traducen", lb.cget("text") == "Save" and mn.entrycget(0, "label") == "Close" and tv.heading("a", "text") == "Program" and tv.item(tv.get_children()[0], "values")[0] == "Today" and tx.get("1.0", "end").strip() == "Cancel")
i18n.activar("es", [])
check("En español todo queda como el original", tk.Label(app, text="Guardar").cget("text") == "Guardar")
import ayuda
check("Los créditos incluyen al autor", ayuda.CREDITOS["autor"] == "Fernando Erazo")
def about_text(dons=None, repo=""):
    ayuda.CREDITOS["donaciones"] = dons or []; ayuda.CREDITOS["repo"] = repo
    hw = ayuda.HelpWindow(app, "Acerca de", n.CFG, n.save_cfg, n.DATA_DIR); t = hw.txt.get("1.0", "end"); hw.destroy(); return t
t0_ = about_text()
check("Acerca de muestra los créditos", "Diseño y desarrollo: Fernando" in t0_ and "Claude" in t0_)
check("Sin donaciones configuradas no aparece nada de donar", "Apoyar el proyecto" not in t0_ and "Código fuente" not in t0_)
t1_ = about_text([{"nombre": "PayPal", "url": "https://paypal.me/x"}, {"nombre": "Malo", "url": "javascript:alert(1)"}, {"nombre": "Cartera", "texto": "abc123"}], "https://github.com/x/NavTool")
btns = []
def walk(w):
    for c in w.winfo_children(): yield c; yield from walk(c)
hw = ayuda.HelpWindow(app, "Acerca de", n.CFG, n.save_cfg, n.DATA_DIR)
etiquetas = [b.cget("text") for b in walk(hw.txt) if b.winfo_class() == "Button"]
hw.destroy()
check("Con donaciones válidas aparece la sección opcional", "Apoyar el proyecto (opcional)" in t1_ and "Comprueba siempre" in t1_)
check("Solo se aceptan enlaces https:// (no javascript:)", any("PayPal" in x for x in etiquetas) and not any("Malo" in x for x in etiquetas), str(etiquetas))
ayuda.CREDITOS["donaciones"] = []; ayuda.CREDITOS["repo"] = ""


# ---------------- apps de la Tienda (exención de loopback)
import tienda
tienda.configurar(os.path.join(tmp, "datos_tienda")); os.makedirs(os.path.join(tmp, "datos_tienda"))
WA, ST, EV = "5319275A.WhatsAppDesktop_cv1g1gvanyjgm", "Microsoft.WindowsStore_8wekyb3d8bbwe", "Malo.App_" + "a" * 13
llamadas = []
listado = _j.dumps([{"Name": "5319275A.WhatsAppDesktop", "PackageFamilyName": WA},
                    {"Name": "Microsoft.WindowsStore", "PackageFamilyName": ST},
                    {"Name": "Otra.App", "PackageFamilyName": "Otra.App_8wekyb3d8bbwe"},
                    {"Name": "Sin.Formato", "PackageFamilyName": "no valido; calc"}])
salida_s = ("Lista de exenciones de bucle invertido de aplicaciones\\n\\n    [1] -----------------------------------------------------------------\\n"
            "        Nombre: microsoft.windowsstore_8wekyb3d8bbwe\\n        SID: S-1-15-2-1\\n")


def fake_run(args, timeout=40):
    llamadas.append(list(args))
    if "LoopbackExempt" in " ".join(map(str, args)) and "-s" in args:
        return 0, salida_s
    if "LoopbackExempt" in " ".join(map(str, args)):
        return 0, "Aceptar"
    return 0, listado


tienda._run = fake_run
apps = tienda.apps_instaladas()
check("Lista las apps instaladas y descarta nombres inválidos", [a["pfn"] for a in apps] == [WA, "Otra.App_8wekyb3d8bbwe", ST][:0] + sorted([WA, ST, "Otra.App_8wekyb3d8bbwe"], key=str.lower) or len(apps) == 3, str([a["pfn"] for a in apps]))
check("Nunca acepta un nombre con espacios, «;» o comandos", not any(" " in a["pfn"] or ";" in a["pfn"] for a in apps))
check("Lee las exenciones que ya existen (también en Windows en español)", tienda.exentas() == {ST.lower()})
check("Expresión de nombres: rechaza inyección y formatos raros", not any(tienda.PFN_RE.match(x) for x in ("a b_" + "a" * 13, "x;calc_" + "a" * 13, "../x_" + "a" * 13, "x_corto", "x_" + "A" * 13, "")))
tienda.es_admin = lambda: False
r = tienda.aplicar([WA], [])
check("Sin administrador no cambia nada", r["ok"] == [] and r["error"] and not any("-a" in c for c in llamadas))
tienda.es_admin = lambda: True
llamadas.clear()
r = tienda.aplicar([WA, EV, "x; calc"], [])
add = [c for c in llamadas if "-a" in c]
check("Añade solo lo que está instalado y con argumentos separados (sin shell)", r["ok"] == [WA] and len(add) == 1 and add[0][-1] == f"-n={WA}" and len(r["error"]) == 2, str(add[:1]))
check("Se apunta lo que hizo NavTool", tienda.gestionadas() == {WA.lower()})
llamadas.clear()
r = tienda.aplicar([], [ST, WA])
rem = [c for c in llamadas if "-d" in c]
check("Solo quita lo que NavTool creó (nunca una exención ajena)", r["ok"] == [WA] and len(rem) == 1 and any(e[0] == ST for e in r["error"]) and tienda.gestionadas() == set())
tienda.aplicar([WA], [])
n_ = tienda.quitar_todas()
check("Al desinstalar se quitan las de NavTool", n_ == 1 and tienda.gestionadas() == set())
# pedido elevado
import json as _jj
pedido = tienda._cfg["pedido"]
_jj.dump({"hora": time.time(), "agregar": [WA], "quitar": []}, open(pedido, "w"))
res = tienda.ejecutar_pedido()
check("El pedido de la copia elevada se aplica, se borra y deja resultado", res["ok"] == [WA] and not os.path.exists(pedido) and os.path.exists(tienda._cfg["resultado"]))
_jj.dump({"hora": time.time() - 4000, "agregar": [ST], "quitar": []}, open(pedido, "w"))
llamadas.clear(); res = tienda.ejecutar_pedido()
check("Un pedido caducado (más de 5 min) se ignora", res["ok"] == [] and not any("-a" in c for c in llamadas))
open(pedido, "w").write("{corrupto"); res = tienda.ejecutar_pedido()
check("Un pedido corrupto no rompe nada", res["ok"] == [])
tienda._guardar_estado([WA, "x; calc", 5, "../x_" + "a" * 13])
check("El estado en disco solo conserva nombres válidos", tienda.gestionadas() == {WA.lower()})
tienda._guardar_estado([])
# ventana
tienda.es_admin = lambda: False
app.win_tienda(); t1 = time.time()
while time.time() - t1 < 3 and not app._tienda.filas: pump(.1)
w = app._tienda
check("La ventana lista las apps y marca las que ya tienen exención", len(w.filas) == 3 and sum(f["exenta"] for f in w.filas.values()) == 1, str(len(w.filas)))
w.recomendadas()
marcadas = sorted(f["nombre"] for f in w.filas.values() if f["marcada"])
check("«Marcar las recomendadas» marca WhatsApp y la Tienda", any("WhatsApp" in x for x in marcadas) and any("WindowsStore" in x for x in marcadas), str(marcadas))
ajena = next(i for i, f in w.filas.items() if f["exenta"])
w.tree.event_generate("<Button-1>", x=5, y=5)
w.filas[ajena]["propia"] = False
class E_: pass
ev = E_(); ev.x, ev.y = 5, 5
w.tree.identify_row = lambda y: ajena; w.tree.identify_column = lambda x: "#1"
antes = w.filas[ajena]["marcada"]; w._clic(ev)
check("Una exención ajena no se puede desmarcar desde NavTool", w.filas[ajena]["marcada"] == antes)
w.destroy()
# el aviso de una sola vez
n.CFG["store_hint"] = False; avisos = []
app._notify = lambda t, m: avisos.append(t); app._store_hint(); app._store_hint()
check("El aviso de las apps de la Tienda sale una sola vez (sin ventana emergente)", len(avisos) == 1 and n.CFG["store_hint"] is True)


# ---------------- Defender: patrones que se han comportado como malware
import glob as _glob
malos = []
for f in _glob.glob(os.path.join(AQUI, "*.py")):
    if os.path.basename(f).startswith("pruebas_"):
        continue
    for i, ln in enumerate(open(f, encoding="utf-8").read().splitlines(), 1):
        if "ShellExecuteW" in ln and '"runas"' in ln and re.search(r",\s*0\)\s*>\s*32", ln):
            malos.append(f"{os.path.basename(f)}:{i}")
check("Ninguna elevación (runas) se lanza con la ventana OCULTA (Defender lo marca como malware)", not malos, str(malos))

app.quit_app(); shutil.rmtree(tmp, ignore_errors=True)
print(f"\nRESULTADO: {ok} bien, {fail} fallos")
