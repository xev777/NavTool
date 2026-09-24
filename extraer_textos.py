"""Extrae de forma automática todos los textos visibles del código fuente (el español original).

    python extraer_textos.py            → escribe idiomas/plantilla.json (para traductores)
    python extraer_textos.py --lista    → imprime los textos

Las cadenas con partes variables (f-strings) se guardan como plantillas con marcadores {}:
    f"Peticiones: {n}"   →   "Peticiones: {}"
"""
import ast
import json
import os
import re
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
ARCHIVOS = ["navtool.py", "ayuda.py", "traffic_monitor.py", "history_view.py", "report_view.py",
            "load_panel.py", "privacy.py", "tray.py", "watcher.py", "loadtrack.py", "blocklists.py",
            "programas.py", "cuota.py", "i18n.py", "safety.py", "proxy_core.py", "pcap.py", "netparse.py",
            "tienda.py", "telemetria.py"]
LETRAS = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]")
ACENTOS = re.compile(r"[ÁÉÍÓÚÜÑáéíóúüñ¿¡…•→←↑↓✔✖⚠]")
CODIGO = re.compile(r"^[\w.\-/\\:%#@\[\]{}()=<>*+,;'\"|?&$!^~`]+$")      # identificadores, rutas, regex…
TK = {"left", "right", "top", "bottom", "both", "flat", "solid", "sunken", "raised", "normal",
      "disabled", "readonly", "end", "insert", "none", "word", "char", "x", "y", "center", "nw", "ne",
      "sw", "se", "n", "s", "e", "w", "white", "black", "hand2", "arrow", "fleur", "clam", "utf-8"}


def es_texto(s):
    s = s.strip()
    if len(s) < 2 or not LETRAS.search(s):
        return False
    if s.lower() in TK or s.startswith(("http://", "https://", "\\\\", "C:\\", "HK", "Software\\")):
        return False
    if re.fullmatch(r"[A-ZÁÉÍÓÚÑ][a-záéíóúñü]{2,}:?", s):                  # palabra suelta: «Cerrar», «Guardar»…
        return True
    if re.fullmatch(r"#[0-9a-fA-F]{3,8}", s) or re.fullmatch(r"[a-z0-9_]+", s) or CODIGO.match(s) and " " not in s:
        return False
    if re.match(r"^\(\?|^\^|\\[dswb]", s):                                  # expresiones regulares
        return False
    return " " in s or bool(ACENTOS.search(s)) or s[0].isupper()


def plantilla_fstring(nodo):
    partes = []
    for v in nodo.values:
        if isinstance(v, ast.Constant):
            partes.append(str(v.value))
        else:
            partes.append("{}")
    return "".join(partes)


def extraer():
    out = {}
    for nombre in ARCHIVOS:
        ruta = os.path.join(AQUI, nombre)
        if not os.path.exists(ruta):
            continue
        arbol = ast.parse(open(ruta, encoding="utf-8").read())
        docstrings = set()
        for n in ast.walk(arbol):
            if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)):
                if n.body and isinstance(n.body[0], ast.Expr) and isinstance(getattr(n.body[0], "value", None), ast.Constant):
                    docstrings.add(id(n.body[0].value))
        dentro_f = set()
        for n in ast.walk(arbol):
            if isinstance(n, ast.JoinedStr):
                for v in n.values:
                    dentro_f.add(id(v))
        for n in ast.walk(arbol):
            s = None
            if isinstance(n, ast.JoinedStr):
                s = plantilla_fstring(n)
            elif isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docstrings \
                    and id(n) not in dentro_f:
                s = n.value
            if s and es_texto(s):
                out.setdefault(s.strip(), nombre)
    return out


if __name__ == "__main__":
    textos = extraer()
    if "--lista" in sys.argv:
        for k in textos:
            print(repr(k))
    else:
        os.makedirs(os.path.join(AQUI, "idiomas"), exist_ok=True)
        with open(os.path.join(AQUI, "idiomas", "plantilla.json"), "w", encoding="utf-8") as f:
            json.dump({"meta": {"code": "xx", "name": "Nombre del idioma", "version": 1, "author": ""},
                       "strings": {k: "" for k in textos}}, f, ensure_ascii=False, indent=1)
    print(len(textos), "textos", file=sys.stderr)
