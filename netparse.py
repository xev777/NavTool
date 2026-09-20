"""Lectura de paquetes en bruto (Ethernet · IPv4/IPv6 · TCP/UDP · DNS), sin dependencias externas.

Todo lo que llega aquí viene de la red y es hostil por definición: cada lectura comprueba límites y
nunca lanza excepciones; un paquete raro simplemente no se interpreta (devuelve None).
"""
import collections
import socket

Frame = collections.namedtuple("Frame", "proto src dst sport dport flags poff pend")
Dns = collections.namedtuple("Dns", "id qr rcode qname qtype answers")

MAX_DNS_NAME = 255
MAX_DNS_RECORDS = 32


def parse_frame(raw):
    """Trama Ethernet → Frame(proto, src, dst, sport, dport, flags, poff, pend) o None.

    proto: "TCP", "UDP" o "ICMP" (cualquier otro protocolo, sin puertos, como hacía el monitor).
    src/dst: bytes de 4 o 16. La carga útil de TCP/UDP es raw[poff:pend]."""
    n = len(raw)
    if n < 34:
        return None
    et, o = (raw[12] << 8) | raw[13], 14
    for _ in range(2):                                       # hasta dos etiquetas VLAN (802.1Q / QinQ)
        if et in (0x8100, 0x88A8):
            if n < o + 4 + 20:
                return None
            et, o = (raw[o + 2] << 8) | raw[o + 3], o + 4
    if et == 0x0800:                                          # IPv4
        if raw[o] >> 4 != 4:
            return None
        ihl = (raw[o] & 15) * 4
        if ihl < 20 or n < o + ihl:
            return None
        total = (raw[o + 2] << 8) | raw[o + 3]
        end = min(n, o + total) if total >= ihl else n
        proto, frag = raw[o + 9], ((raw[o + 6] & 0x1F) << 8) | raw[o + 7]
        src, dst, l4 = bytes(raw[o + 12:o + 16]), bytes(raw[o + 16:o + 20]), o + ihl
        if frag:                                              # fragmento que no es el primero: sin cabecera L4
            proto = 0
    elif et == 0x86DD:                                        # IPv6
        if raw[o] >> 4 != 6 or n < o + 40:
            return None
        plen = (raw[o + 4] << 8) | raw[o + 5]
        end = min(n, o + 40 + plen) if plen else n
        proto = raw[o + 6]
        src, dst, l4 = bytes(raw[o + 8:o + 24]), bytes(raw[o + 24:o + 40]), o + 40
        for _ in range(6):                                    # cabeceras de extensión
            if proto in (0, 43, 60) and l4 + 2 <= end:
                proto, l4 = raw[l4], l4 + (raw[l4 + 1] + 1) * 8
            elif proto == 44 and l4 + 8 <= end:              # fragmentación
                if ((raw[l4 + 2] << 8) | raw[l4 + 3]) >> 3:
                    proto = 0
                    break
                proto, l4 = raw[l4], l4 + 8
            else:
                break
    else:
        return None
    if proto == 6 and end >= l4 + 20:                         # TCP
        off = (raw[l4 + 12] >> 4) * 4
        if off < 20 or l4 + off > end:
            return None
        return Frame("TCP", src, dst, (raw[l4] << 8) | raw[l4 + 1], (raw[l4 + 2] << 8) | raw[l4 + 3],
                     raw[l4 + 13], l4 + off, end)
    if proto == 17 and end >= l4 + 8:                         # UDP
        return Frame("UDP", src, dst, (raw[l4] << 8) | raw[l4 + 1], (raw[l4 + 2] << 8) | raw[l4 + 3],
                     0, l4 + 8, end)
    return Frame("ICMP", src, dst, 0, 0, 0, l4, end)


def ip_text(b):
    return socket.inet_ntop(socket.AF_INET if len(b) == 4 else socket.AF_INET6, b)


# ------------------------------------------------------------------------------------------ DNS
def _name(d, i):
    """Lee un nombre DNS (con compresión) en d[i:]. Devuelve (nombre, posición tras el nombre) o None."""
    labels, jumps, end, total = [], 0, None, 0
    while True:
        if i >= len(d):
            return None
        c = d[i]
        if c == 0:
            i += 1
            break
        if c & 0xC0 == 0xC0:                                  # puntero de compresión
            if i + 1 >= len(d) or jumps >= 10:
                return None
            if end is None:
                end = i + 2
            i, jumps = ((c & 0x3F) << 8) | d[i + 1], jumps + 1
            continue
        if c & 0xC0 or i + 1 + c > len(d):
            return None
        total += c + 1
        if total > MAX_DNS_NAME:
            return None
        labels.append(bytes(d[i + 1:i + 1 + c]).decode("ascii", "ignore"))
        i += 1 + c
    return ".".join(labels), (end if end is not None else i)


def parse_dns(d):
    """Mensaje DNS → Dns(id, qr, rcode, qname, qtype, answers) o None. `answers` = IPs de los registros
    A/AAAA (máx. 32). Solo interpreta la primera pregunta."""
    if not d or len(d) < 12:
        return None
    ident, flags, qd, an = (d[0] << 8) | d[1], (d[2] << 8) | d[3], (d[4] << 8) | d[5], (d[6] << 8) | d[7]
    if qd < 1:
        return None
    r = _name(d, 12)
    if r is None or r[1] + 4 > len(d):
        return None
    qname, i = r
    qtype = (d[i] << 8) | d[i + 1]
    i += 4
    for _ in range(qd - 1):                                   # otras preguntas: solo se saltan
        r = _name(d, i)
        if r is None or r[1] + 4 > len(d):
            return None
        i = r[1] + 4
    ips = []
    for _ in range(min(an, MAX_DNS_RECORDS)):
        r = _name(d, i)
        if r is None or r[1] + 10 > len(d):
            break
        i = r[1]
        rtype, rdlen = (d[i] << 8) | d[i + 1], (d[i + 8] << 8) | d[i + 9]
        i += 10
        if i + rdlen > len(d):
            break
        if rtype == 1 and rdlen == 4:
            ips.append(socket.inet_ntop(socket.AF_INET, bytes(d[i:i + 4])))
        elif rtype == 28 and rdlen == 16:
            ips.append(socket.inet_ntop(socket.AF_INET6, bytes(d[i:i + 16])))
        i += rdlen
    return Dns(ident, flags >> 15, flags & 15, qname, qtype, ips)
