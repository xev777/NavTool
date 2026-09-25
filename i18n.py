"""Idiomas de TrafficBar: packs de idioma que se pueden instalar y cargar.

El texto original de la aplicación es español. Un pack de idioma es un archivo .json:

    {"meta": {"code": "en", "name": "English", "version": 1, "author": "…"},
     "strings": {"Guardar": "Save", "Bloqueadas: {}": "Blocked: {}"}}

Los marcadores {} (o {1}, {2}… para reordenar) se sustituyen por las partes variables del texto
(números, nombres). No se usa str.format: un pack no puede ejecutar nada ni leer atributos.

TrafficBar traduce en el momento de mostrar los textos (botones, menús, títulos, tablas, avisos), así que
los packs de terceros usan exactamente el mismo formato. `python extraer_textos.py` genera la
plantilla con todos los textos.
"""
import json
import os
import re
import shutil
import tkinter as tk
from tkinter import ttk

MAX_PACK_BYTES = 2_000_000
MAX_ENTRIES = 6000
MAX_KEY, MAX_VALUE = 2500, 5000
CODE_RE = re.compile(r"^[a-z]{2,3}(-[A-Za-z]{2,4})?$")
CTRL_RE = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\u202a-\u202e\u2066-\u2069]")   # controles y marcas RTL
HOLE_RE = re.compile(r"\{(\d*)\}")
SOURCE_LANG = "es"

_st = {"lang": SOURCE_LANG, "exact": {}, "tmpl": [], "cache": {}, "misses": None}


# ----------------------------------------------------------------------------- validación
def _limpia(s, maxlen):
    return CTRL_RE.sub("", s)[:maxlen]


def validar_pack(datos):
    """(pack, error). Devuelve un pack limpio {code, name, version, author, strings} o un error legible."""
    if not isinstance(datos, dict) or not isinstance(datos.get("strings"), dict):
        return None, "El archivo no tiene el formato de un pack de idioma (falta «strings»)."
    meta = datos.get("meta") if isinstance(datos.get("meta"), dict) else {}
    code = str(meta.get("code", "")).strip()
    if not CODE_RE.match(code) or code == SOURCE_LANG:
        return None, "Código de idioma no válido (usa por ejemplo «en», «fr», «pt-BR»; «es» es el original)."
    name = _limpia(str(meta.get("name", "")).strip(), 40) or code
    if len(datos["strings"]) > MAX_ENTRIES:
        return None, f"Demasiadas entradas (máximo {MAX_ENTRIES})."
    strings = {}
    for k, v in datos["strings"].items():
        if not isinstance(k, str) or not isinstance(v, str) or not v.strip() or len(k) > MAX_KEY:
            continue
        k = k.strip()
        v = _limpia(v, MAX_VALUE)
        n = len(HOLE_RE.findall(k))
        if any(g and not 1 <= int(g) <= n for g in HOLE_RE.findall(v)):
            continue                                        # índice de marcador imposible: se descarta
        if sum(1 for g in HOLE_RE.findall(v) if g == "") > n:
            continue                                        # más {} que partes variables: se descarta
        strings[k] = v
    if not strings:
        return None, "El pack no contiene traducciones."
    ver = meta.get("version")
    return {"code": code, "name": name, "version": ver if isinstance(ver, (int, float)) else 1,
            "author": _limpia(str(meta.get("author", "")), 60), "strings": strings}, ""


def leer_pack(ruta):
    try:
        if os.path.getsize(ruta) > MAX_PACK_BYTES:
            return None, "El archivo es demasiado grande para ser un pack de idioma."
        with open(ruta, encoding="utf-8-sig") as f:
            return validar_pack(json.load(f))
    except (OSError, ValueError, UnicodeDecodeError) as e:
        return None, f"No se pudo leer el archivo: {e}"


def paquetes(dirs):
    """{code: {name, path, builtin}} de los packs válidos en las carpetas dadas (la última manda)."""
    out = {}
    for d, builtin in dirs:
        try:
            names = sorted(os.listdir(d))
        except OSError:
            continue
        for fn in names:
            if not fn.lower().endswith(".json") or fn.startswith("_") or fn.lower().startswith("plantilla"):
                continue
            pack, _ = leer_pack(os.path.join(d, fn))
            if pack:
                out[pack["code"]] = {"name": pack["name"], "path": os.path.join(d, fn),
                                     "builtin": builtin, "author": pack["author"]}
    return out


def importar(ruta, carpeta_usuario):
    """Copia un pack válido a la carpeta de packs del usuario. Devuelve (pack, error)."""
    pack, err = leer_pack(ruta)
    if not pack:
        return None, err
    os.makedirs(carpeta_usuario, exist_ok=True)
    destino = os.path.join(carpeta_usuario, f"{pack['code']}.json")
    tmp = destino + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:              # se guarda el pack ya limpio, no el original
        json.dump({"meta": {k: pack[k] for k in ("code", "name", "version", "author")},
                   "strings": pack["strings"]}, f, ensure_ascii=False, indent=1)
    shutil.move(tmp, destino)
    return pack, ""


def exportar_plantilla(origen, destino):
    """Copia la plantilla (todos los textos, sin traducir) para que alguien la traduzca."""
    shutil.copyfile(origen, destino)


# ----------------------------------------------------------------------------- activación
def activar(code, dirs):
    """Activa un idioma. «es» = texto original. Devuelve True si quedó activo."""
    _st["cache"] = {}
    _st["exact"], _st["tmpl"] = {}, []
    if code == SOURCE_LANG:
        _st["lang"] = SOURCE_LANG
        return True
    info = paquetes(dirs).get(code)
    if not info:
        _st["lang"] = SOURCE_LANG
        return False
    pack, _ = leer_pack(info["path"])
    if not pack:
        _st["lang"] = SOURCE_LANG
        return False
    tmpl = []
    for k, v in pack["strings"].items():
        if "{}" in k or HOLE_RE.search(k):
            partes = HOLE_RE.split(k)[::2]
            tmpl.append((partes[0], partes, v))
        else:
            _st["exact"][k] = v
    tmpl.sort(key=lambda t: -len(t[0]))                  # las plantillas más específicas primero
    _st["tmpl"] = tmpl
    _st["lang"] = code
    return True


def idioma():
    return _st["lang"]


def registrar_faltantes(ruta):
    """Modo de desarrollo: anota en `ruta` los textos que se pidieron traducir y no tenían traducción."""
    _st["misses"] = set() if ruta else None
    _st["misses_path"] = ruta


def guardar_faltantes():
    if _st.get("misses") is not None and _st.get("misses_path"):
        with open(_st["misses_path"], "w", encoding="utf-8") as f:
            json.dump(sorted(_st["misses"]), f, ensure_ascii=False, indent=1)


def _sustituye(destino, grupos):
    def rep(m):
        i = int(m.group(1)) - 1 if m.group(1) else rep.n
        if not m.group(1):
            rep.n += 1
        return grupos[i] if 0 <= i < len(grupos) else m.group(0)
    rep.n = 0
    return HOLE_RE.sub(rep, destino)


def _encaja(partes, s):
    """¿`s` encaja con la plantilla `partes` (los textos fijos entre los huecos)? Devuelve el contenido
    de cada hueco. Búsqueda lineal (sin expresiones regulares): no puede colgarse con textos largos."""
    primera, ultima = partes[0], partes[-1]
    fin = len(s) - len(ultima)
    if not s.startswith(primera) or fin < len(primera) or (ultima and not s.endswith(ultima)):
        return None
    pos, grupos = len(primera), []
    for mid in partes[1:-1]:
        j = s.find(mid, pos, fin)
        if j < 0:
            return None
        grupos.append(s[pos:j])
        pos = j + len(mid)
    grupos.append(s[pos:fin])
    return grupos


def _tr1(s, hondo=0):
    ex = _st["exact"]
    if s in ex:
        return ex[s]
    if len(s) > 4000 or hondo >= 3:          # tope de anidamiento: un texto hostil no puede recursar sin fin
        return None
    for pre, partes, dest in _st["tmpl"]:
        if pre and not s.startswith(pre):
            continue
        grupos = _encaja(partes, s)
        if grupos is not None:
            return _sustituye(dest, [tr(g, hondo + 1) for g in grupos])
    return None


def tr(s, hondo=0):
    """Traduce un texto al idioma activo. Si no hay traducción, devuelve el original."""
    if _st["lang"] == SOURCE_LANG or not isinstance(s, str) or len(s) < 2:
        return s
    c = _st["cache"]
    r = c.get(s)
    if r is not None:
        return r
    core = s.strip()
    out = None
    if core:
        t = _tr1(core, hondo)
        if t is None and "\n" in core:                     # texto de varias líneas: línea a línea
            lineas, alguna = [], False
            for ln in core.split("\n"):
                x = _tr1(ln.strip(), hondo) if ln.strip() else None
                if x is not None:
                    alguna = True
                    lineas.append(ln[:len(ln) - len(ln.lstrip())] + x)
                else:
                    lineas.append(ln)
            t = "\n".join(lineas) if alguna else None
        if t is not None:
            i = s.index(core)
            out = s[:i] + t + s[i + len(core):]
    if out is None:
        out = s
        m = _st["misses"]
        if m is not None and core and re.search(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{3}", core) and len(m) < 5000:
            m.add(core)
    if hondo == 0:
        if len(c) > 6000:
            c.clear()
        c[s] = out
    return out


T = tr


# ----------------------------------------------------------------------------- hooks de Tk
_hooked = {"done": False}


def instalar_hooks():
    """Hace que los textos que Tk muestra pasen por tr(). Se instala una sola vez."""
    if _hooked["done"]:
        return
    _hooked["done"] = True
    from tkinter import messagebox

    orig_options = tk.Misc._options

    def _options(self, cnf, kw=None):
        cnf = dict(tk._cnfmerge((cnf, kw)) if kw else tk._cnfmerge(cnf))
        for k in ("text", "label"):
            if isinstance(cnf.get(k), str):
                cnf[k] = tr(cnf[k])
        v = cnf.get("values")
        if isinstance(v, (list, tuple)) and v and all(isinstance(x, str) for x in v):
            cnf["values"] = tuple(tr(x) for x in v)
        return orig_options(self, cnf)
    tk.Misc._options = _options

    o_title = tk.Wm.wm_title

    def wm_title(self, string=None):
        return o_title(self, tr(string) if isinstance(string, str) else string)
    tk.Wm.wm_title = wm_title
    tk.Wm.title = wm_title

    o_insert = tk.Text.insert

    def insert(self, index, chars, *args):
        return o_insert(self, index, tr(chars) if isinstance(chars, str) else chars, *args)
    tk.Text.insert = insert

    def _valores(v):
        return tuple(tr(x) if isinstance(x, str) else x for x in v) if isinstance(v, (list, tuple)) else v

    o_tv_insert, o_tv_item, o_tv_head = ttk.Treeview.insert, ttk.Treeview.item, ttk.Treeview.heading

    def tv_insert(self, parent, index, iid=None, **kw):
        if "values" in kw:
            kw["values"] = _valores(kw["values"])
        if isinstance(kw.get("text"), str):
            kw["text"] = tr(kw["text"])
        return o_tv_insert(self, parent, index, iid, **kw)

    def tv_item(self, item, option=None, **kw):
        if "values" in kw:
            kw["values"] = _valores(kw["values"])
        return o_tv_item(self, item, option, **kw)

    def tv_heading(self, column, option=None, **kw):
        if isinstance(kw.get("text"), str):
            kw["text"] = tr(kw["text"])
        return o_tv_head(self, column, option, **kw)
    ttk.Treeview.insert, ttk.Treeview.item, ttk.Treeview.heading = tv_insert, tv_item, tv_heading

    o_nb_add, o_nb_tab = ttk.Notebook.add, ttk.Notebook.tab

    def nb_add(self, child, **kw):
        if isinstance(kw.get("text"), str):
            kw["text"] = tr(kw["text"])
        return o_nb_add(self, child, **kw)

    def nb_tab(self, tab_id, option=None, **kw):
        if isinstance(kw.get("text"), str):
            kw["text"] = tr(kw["text"])
        return o_nb_tab(self, tab_id, option, **kw)
    ttk.Notebook.add, ttk.Notebook.tab = nb_add, nb_tab

    o_show = messagebox._show

    def _show(title=None, message=None, *a, **kw):
        return o_show(tr(title) if isinstance(title, str) else title,
                      tr(message) if isinstance(message, str) else message, *a, **kw)
    messagebox._show = _show
