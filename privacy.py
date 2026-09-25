"""Informe de privacidad de una carga de página.

A partir de las conexiones que hizo la página (sitio, bytes, estado) decide cuáles son
propias, de terceros, de publicidad, de analítica o de redes sociales, y da una nota A–F.
"""
import time

from traffic_monitor import company_of

ADS = (
    "doubleclick.net", "googlesyndication.com", "googleadservices.com", "adservice.google.com",
    "adnxs.com", "adsrvr.org", "advertising.com", "taboola.com", "outbrain.com", "criteo.com",
    "criteo.net", "pubmatic.com", "rubiconproject.com", "openx.net", "moatads.com", "zedo.com",
    "popads.net", "popcash.net", "propellerads.com", "exoclick.com", "adsterra.com",
    "revcontent.com", "mgid.com", "amazon-adsystem.com", "adform.net", "smartadserver.com",
    "casalemedia.com", "3lift.com", "teads.tv", "yieldmo.com", "media.net", "ads-twitter.com",
    "bidswitch.net", "sharethrough.com", "indexww.com", "serving-sys.com", "everesttech.net",
    "demdex.net", "bluekai.com", "krxd.net", "adtelligent.com", "contextweb.com",
)
ANALYTICS = (
    "google-analytics.com", "googletagmanager.com", "analytics.google.com", "scorecardresearch.com",
    "quantserve.com", "hotjar.com", "hotjar.io", "clarity.ms", "segment.io", "segment.com",
    "mixpanel.com", "amplitude.com", "heap.io", "fullstory.com", "mouseflow.com", "newrelic.com",
    "nr-data.net", "sentry.io", "datadoghq.com", "chartbeat.com", "chartbeat.net", "parsely.com",
    "optimizely.com", "branch.io", "adjust.com", "appsflyer.com", "crazyegg.com",
    "luckyorange.com", "statcounter.com", "bat.bing.com", "analytics.tiktok.com",
    "px.ads.linkedin.com", "stats.wp.com", "pixel.wp.com", "omtrdc.net", "2o7.net",
)
SOCIAL = (
    "facebook.net", "connect.facebook.net", "facebook.com", "twitter.com", "platform.twitter.com",
    "t.co", "linkedin.com", "licdn.com", "pinterest.com", "pinimg.com", "instagram.com",
    "tiktok.com", "snapchat.com", "sc-static.net", "addthis.com", "sharethis.com",
)
INFRA = (
    "cloudfront.net", "akamaized.net", "akamai.net", "akamaiedge.net", "edgekey.net",
    "fastly.net", "fastlylb.net", "cloudflare.com", "cdnjs.cloudflare.com", "jsdelivr.net",
    "unpkg.com", "gstatic.com", "googleapis.com", "azureedge.net", "b-cdn.net", "cdn77.org",
    "bootstrapcdn.com", "fontawesome.com", "typekit.net", "jquery.com", "amazonaws.com",
)

CATS = {  # clave: (etiqueta, color, explicación corta)
    "ads": ("Publicidad", "#ff6b6b", "Muestra anuncios y te sigue entre sitios"),
    "analytics": ("Analítica", "#ffa94d", "Mide y registra lo que haces en la página"),
    "social": ("Redes sociales", "#c39bff", "Widgets y botones que avisan a la red social"),
    "third": ("Otro tercero", "#ffd166", "Servicio externo a la página"),
    "infra": ("Infraestructura", "#8fa0b5", "Servidores de contenido (CDN), normalmente inocuos"),
    "own": ("Propio", "#7fd6a6", "Del propio sitio o de su misma empresa"),
}
GRADE_COLOR = {"A": "#3fb97f", "B": "#7fd6a6", "C": "#ffd166", "D": "#ffa94d", "F": "#ff6b6b"}
_SECOND_LEVEL = {"co", "com", "org", "net", "gob", "gov", "edu", "ac", "or", "go", "ne"}


def base_domain(host):
    """Dominio 'registrable' aproximado: www.bbc.co.uk → bbc.co.uk, a.b.example.com → example.com."""
    parts = (host or "").lower().strip(".").split(".")
    if len(parts) >= 3 and len(parts[-1]) == 2 and parts[-2] in _SECOND_LEVEL:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def _match(host, suffixes):
    h = host.lower()
    return any(h == s or h.endswith("." + s) for s in suffixes)


def classify(host, main_base, main_company, in_user_list):
    if in_user_list(host) or _match(host, ADS):
        return "ads"
    if _match(host, ANALYTICS):
        return "analytics"
    base = base_domain(host)
    if base == main_base or (main_company and company_of(host) == main_company):
        return "own"
    if _match(host, SOCIAL):
        return "social"
    if _match(host, INFRA):
        return "infra"
    return "third"


def _grade(score):
    return "A" if score >= 90 else "B" if score >= 75 else "C" if score >= 60 else \
        "D" if score >= 40 else "F"


def build_report(rows, in_user_list, now=None):
    """rows: filas de Loader.rows(). Devuelve un dict con la nota y el detalle por sitio."""
    now = now or time.time()
    rows = [r for r in rows if r.get("host")]
    if not rows:
        return None
    rows.sort(key=lambda r: r["start"])
    # página principal (estimada): la primera conexión que no es publicidad/analítica/CDN
    main = next((r["host"] for r in rows if r["state"] != "blocked"
                 and not _match(r["host"], ADS + ANALYTICS + INFRA)), rows[0]["host"])
    main_base, main_company = base_domain(main), company_of(main)

    hosts = {}
    for r in rows:
        h = hosts.setdefault(r["host"], {"host": r["host"], "bytes": 0, "conns": 0,
                                         "states": set()})
        h["bytes"] += r["bytes"]
        h["conns"] += 1
        h["states"].add(r["state"])
    out = []
    for h in hosts.values():
        st = h["states"]
        status = "blocked" if st == {"blocked"} else "cut" if "cut" in st and "done" not in st \
            and "active" not in st else "done"
        h["status"] = status
        h["cat"] = classify(h["host"], main_base, main_company, in_user_list)
        del h["states"]
        out.append(h)
    order = list(CATS)
    out.sort(key=lambda h: (order.index(h["cat"]), -h["bytes"]))

    count = {k: 0 for k in CATS}
    protected = 0
    penalty = 0
    caps = {"ads": (9, 45), "analytics": (6, 30), "social": (5, 15), "third": (1, 10)}
    spent = {k: 0 for k in caps}
    for h in out:
        count[h["cat"]] += 1
        if h["status"] == "blocked":
            protected += h["cat"] in ("ads", "analytics", "social", "third")
            continue  # bloqueado = no llegó a enviar nada
        if h["cat"] in caps:
            each, cap = caps[h["cat"]]
            spent[h["cat"]] = min(cap, spent[h["cat"]] + each)
    penalty = sum(spent.values())
    score = max(0, 100 - penalty)
    grade = _grade(score)
    third = sum(count[k] for k in ("ads", "analytics", "social", "third", "infra"))
    trackers = count["ads"] + count["analytics"] + count["social"]
    active_trackers = sum(1 for h in out if h["cat"] in ("ads", "analytics", "social")
                          and h["status"] != "blocked")
    start = min(r["start"] for r in rows)
    end = max((r["end"] or now) for r in rows)
    total_bytes = sum(h["bytes"] for h in out)

    if active_trackers == 0 and trackers == 0:
        verdict = "Página limpia: no contactó con rastreadores conocidos."
    elif active_trackers == 0:
        verdict = f"Contactó con {trackers} rastreador(es), pero TrafficBar los bloqueó todos."
    else:
        verdict = (f"{active_trackers} rastreador(es) recibieron datos de tu visita; TrafficBar bloqueó "
                   f"{protected} más." if protected else
                   f"{active_trackers} rastreador(es) recibieron datos de tu visita.")
    return {
        "time": now, "main": main, "score": score, "grade": grade, "hosts": out,
        "n_hosts": len(out), "n_third": third, "trackers": trackers,
        "active_trackers": active_trackers, "protected": protected, "count": count,
        "bytes": total_bytes, "seconds": max(0.1, end - start), "verdict": verdict,
    }
