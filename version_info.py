"""Genera version_info.txt (metadatos de versión del .exe: nombre del producto, versión, autor).

SignPath y los antivirus esperan que el ejecutable declare quién es y qué versión es. Lee la versión de NavTool.iss:

    python version_info.py
"""
import os
import re

AQUI = os.path.dirname(os.path.abspath(__file__))


def version():
    with open(os.path.join(AQUI, "NavTool.iss"), encoding="utf-8-sig") as f:
        return re.search(r'#define AppVersion "([^"]+)"', f.read()).group(1)


def contenido(v):
    p = ([int(x) for x in re.findall(r"\d+", v)] + [0, 0, 0, 0])[:4]
    tupla = ", ".join(map(str, p))
    campos = [("CompanyName", "Fernando Erazo"), ("FileDescription", "NavTool - network monitor and filter"),
              ("FileVersion", ".".join(map(str, p))), ("InternalName", "NavTool"),
              ("LegalCopyright", "Copyright (C) 2026 Fernando Erazo. GNU GPL v3."),
              ("OriginalFilename", "NavTool.exe"), ("ProductName", "NavTool"),
              ("ProductVersion", v)]
    filas = ",\n        ".join(f"StringStruct('{k}', '{x}')" for k, x in campos)
    return (f"VSVersionInfo(\n  ffi=FixedFileInfo(filevers=({tupla}), prodvers=({tupla}), mask=0x3f, flags=0x0,\n"
            f"    OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),\n  kids=[\n"
            f"    StringFileInfo([StringTable('040904B0', [\n        {filas}])]),\n"
            f"    VarFileInfo([VarStruct('Translation', [1033, 1200])])\n  ]\n)\n")


if __name__ == "__main__":
    v = version()
    with open(os.path.join(AQUI, "version_info.txt"), "w", encoding="utf-8") as f:
        f.write(contenido(v))
    print("version_info.txt para", v)
