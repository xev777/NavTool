"""Mide cuántos datos ahorra NavTool al cargar páginas REALES.

Carga cada página con Edge (modo sin ventana, perfil nuevo = sin caché) a través del proxy de
NavTool con distintas configuraciones de bloqueo y compara los bytes que pasan por la red.
No toca el proxy de Windows ni tu configuración (usa carpetas y puertos temporales).

    python medir_ahorro.py                     # A (sin bloqueo) vs B (lista inicial)
    python medir_ahorro.py --configs A,B,C     # C = listas ampliadas (si existen)
    python medir_ahorro.py --sitios https://a.com,https://b.com --salida resultados.json

Límites (se muestran también en el informe): una sola carga por sitio y configuración, sin
desplazarse ni interactuar, los anuncios cambian en cada visita y algunos sitios detectan el
navegador sin ventana. Sirve para órdenes de magnitud, no para cifras exactas.
"""
import argparse
import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse

tmp_env = tempfile.mkdtemp(prefix="navmed_env_")
os.environ["APPDATA"] = os.path.join(tmp_env, "r")
os.environ["LOCALAPPDATA"] = os.path.join(tmp_env, "l")
for _d in (os.environ["APPDATA"], os.environ["LOCALAPPDATA"]):
    os.makedirs(_d)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import privacy                      # noqa: E402
from loadtrack import Loader        # noqa: E402
from proxy_core import Proxy        # noqa: E402
from traffic_monitor import company_of   # noqa: E402

EDGE = next((p for p in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                         r"C:\Program Files\Microsoft\Edge\Application\msedge.exe") if os.path.exists(p)), None)
SITIOS = [
    "https://www.elcomercio.pe", "https://larepublica.pe", "https://www.infobae.com",
    "https://www.marca.com", "https://as.com", "https://www.cnn.com", "https://www.bbc.com",
    "https://www.nytimes.com", "https://www.dailymail.co.uk", "https://www.forbes.com",
]
# tráfico propio del navegador (actualizaciones, telemetría...): no es de la página
RUIDO = ("microsoft.com", "msedge.net", "windows.com", "live.com", "bing.com", "windowsupdate.com",
         "msftconnecttest.com", "gvt1.com", "gvt2.com", "googleapis.com/edge")


class Stats:
    def __init__(self):
        self.blocked = 0
        self.recent_blocked = []
        self.lock = threading.Lock()

    def add(self, **kw):
        pass

    def block(self, host):
        with self.lock:
            self.blocked += 1


def suffix_set_blocker(domains):
    domains = {d.lower() for d in domains}

    def blocked(host):
        parts = (host or "").lower().split(".")
        return any(".".join(parts[i:]) in domains for i in range(len(parts) - 1))
    return blocked


def construir_configs(nombres):
    import navtool
    lista_inicial = [l.strip() for l in navtool.DEFAULT_BLOCKLIST.splitlines() if l.strip()]
    cfgs = {"A": ("Sin bloqueo", lambda h: False),
            "B": ("NavTool: lista inicial (27 dominios)", suffix_set_blocker(lista_inicial))}
    if "C" in nombres or "D" in nombres:
        import blocklists
        if "C" in nombres:
            cfgs["C"] = ("NavTool: incluida + Peter Lowe", blocklists.medicion_blocker(("pgl",)))
        if "D" in nombres:
            cfgs["D"] = ("NavTool: incluida + Peter Lowe + StevenBlack",
                         blocklists.medicion_blocker(("pgl", "stevenblack")))
    return {k: v for k, v in cfgs.items() if k in nombres}


def es_ruido(host):
    h = host.lower()
    return any(h == r or h.endswith("." + r) for r in RUIDO if "/" not in r)


def cargar(url, is_blocked, perfil_dir, segundos=90):
    """Carga `url` con Edge a través de un proxy nuevo. Devuelve el detalle de conexiones."""
    stats, loader = Stats(), Loader()
    cfg = {"block_domains": True}
    proxy = Proxy(stats, loader, cfg, is_blocked)
    port = proxy.start()
    args = [EDGE, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
            "--disable-extensions", "--disable-background-networking", "--disable-component-update",
            "--disable-sync", "--disable-default-apps", "--disable-domain-reliability", "--no-pings",
            "--metrics-recording-only", "--mute-audio", "--window-size=1366,2400",
            f"--user-data-dir={perfil_dir}", f"--proxy-server=http://127.0.0.1:{port}",
            "--virtual-time-budget=25000", "--dump-dom", url]
    inicio, error = time.time(), None
    p = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        p.wait(timeout=segundos)
    except subprocess.TimeoutExpired:
        error = "tiempo agotado"
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True)
    time.sleep(2.0)                                # que terminen los túneles abiertos
    loader.poll()
    rows = loader.rows()
    proxy.stop()
    main = urllib.parse.urlsplit(url).hostname
    main_base, main_co = privacy.base_domain(main), company_of(main)
    por_cat, hosts_bloq, total, n_conn, por_host = {}, [], 0, 0, {}
    for r in rows:
        h = r["host"]
        if not h or es_ruido(h):
            continue
        if r["state"] == "blocked":
            hosts_bloq.append(h)
            continue
        cat = privacy.classify(h, main_base, main_co, lambda x: False)
        por_cat[cat] = por_cat.get(cat, 0) + r["bytes"]
        por_host[h] = por_host.get(h, 0) + r["bytes"]
        total += r["bytes"]
        n_conn += 1
    return {"url": url, "bytes": total, "hosts": por_host, "conexiones": n_conn, "por_categoria": por_cat,
            "bloqueados": len(hosts_bloq), "hosts_bloqueados": sorted(set(hosts_bloq)),
            "segundos": round(time.time() - inicio, 1), "error": error}


def mb(n):
    return f"{n / 1048576:6.2f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--configs", default="A,B")
    ap.add_argument("--sitios", default="")
    ap.add_argument("--salida", default="")
    ap.add_argument("--potencial", action="store_true",
                    help="carga solo SIN bloqueo y calcula cuántos bytes evitaría cada lista sobre esas mismas cargas")
    a = ap.parse_args()
    if not EDGE:
        sys.exit("No encuentro Microsoft Edge.")
    sitios = [s for s in a.sitios.split(",") if s] or SITIOS
    todas = construir_configs(["A", "B", "C", "D"]) if a.potencial else None
    cfgs = construir_configs(["A"] if a.potencial else [c.strip().upper() for c in a.configs.split(",")])
    resultados = []
    for url in sitios:
        fila = {"url": url}
        for clave, (nombre, blocker) in cfgs.items():           # mismo orden alterno para todos
            perfil = tempfile.mkdtemp(prefix="navmed_perfil_")
            try:
                fila[clave] = cargar(url, blocker, perfil)
            finally:
                shutil.rmtree(perfil, ignore_errors=True)
            r = fila[clave]
            print(f"{urllib.parse.urlsplit(url).hostname:<26} {clave}: {mb(r['bytes'])} MB, "
                  f"{r['conexiones']:>3} conexiones, {r['bloqueados']:>3} bloqueadas"
                  f"{'  ⚠ ' + r['error'] if r['error'] else ''}", flush=True)
        resultados.append(fila)
    print("\n" + "=" * 92)
    print(f"{'Sitio':<26}" + "".join(f"{k + ' (MB)':>11}" for k in cfgs)
          + "".join(f"{'ahorro ' + k:>11}" for k in cfgs if k != "A"))
    ahorros = {k: [] for k in cfgs if k != "A"}
    for fila in resultados:
        base = fila["A"]["bytes"] if "A" in fila else 0
        linea = f"{urllib.parse.urlsplit(fila['url']).hostname:<26}"
        linea += "".join(f"{mb(fila[k]['bytes']):>11}" for k in cfgs)
        for k in cfgs:
            if k == "A":
                continue
            pct = (100 * (base - fila[k]["bytes"]) / base) if base > 200_000 else None
            if pct is not None:
                ahorros[k].append(pct)
            linea += f"{('%.0f %%' % pct) if pct is not None else 'n/d':>11}"
        print(linea)
    print("=" * 92)
    for k, vals in ahorros.items():
        if vals:
            print(f"Config {k} ({cfgs[k][0]}): ahorro medio {statistics.mean(vals):.0f} % · mediana "
                  f"{statistics.median(vals):.0f} % · rango {min(vals):.0f} % a {max(vals):.0f} % "
                  f"({len(vals)} sitios)")
    if "A" in cfgs:
        tot = {}
        for fila in resultados:
            for cat, b in fila["A"]["por_categoria"].items():
                tot[cat] = tot.get(cat, 0) + b
        suma = sum(tot.values()) or 1
        print("\nEn qué se gasta (sin bloqueo, todos los sitios):")
        for cat, b in sorted(tot.items(), key=lambda x: -x[1]):
            print(f"  {privacy.CATS[cat][0]:<18} {mb(b)} MB  ({100 * b / suma:.0f} %)")
    if a.potencial:
        print("\nBYTES QUE CADA LISTA EVITARÍA (medidos sobre las mismas cargas sin bloqueo):")
        tot_base = sum(f["A"]["bytes"] for f in resultados)
        tot_hosts = {}
        for f in resultados:
            for h, b in f["A"]["hosts"].items():
                tot_hosts[h] = tot_hosts.get(h, 0) + b
        for k in ("B", "C", "D"):
            blocker = todas[k][1]
            evita = sum(b for h, b in tot_hosts.items() if blocker(h))
            n_h = sum(1 for h in tot_hosts if blocker(h))
            print(f"  {k} {todas[k][0]:<48} evita {mb(evita)} MB de {mb(tot_base)} MB "
                  f"({100 * evita / max(tot_base, 1):.1f} %) · {n_h} servidores distintos")
        print("\nDónde va realmente el peso: servidores con más bytes (todos los sitios):")
        for h, b in sorted(tot_hosts.items(), key=lambda x: -x[1])[:14]:
            marca = "  ← bloqueado por D" if todas["D"][1](h) else ""
            print(f"  {mb(b)} MB  {h}{marca}")
    if a.salida:
        with open(a.salida, "w", encoding="utf-8") as f:
            json.dump(resultados, f, ensure_ascii=False, indent=1)
        print("\nGuardado en", a.salida)
    shutil.rmtree(tmp_env, ignore_errors=True)


if __name__ == "__main__":
    main()
