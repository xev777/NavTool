# Third-party components / Componentes de terceros

NavTool 1.1 has **one** runtime dependency besides Python itself.

| Component | Version | License | Use in NavTool | In the executable? |
|---|---|---|---|---|
| Python / Tkinter | 3.14 | PSF License | runtime and UI | yes |
| psutil | 7.2.2 | BSD-3-Clause | processes, connections, network counters | yes |
| PyInstaller | 6.22.0 | GPL-2.0-or-later **with a bootloader exception** (output may use any license) | builds the executable (build time only) | bootloader only |
| Npcap | installed by the user | Npcap license (free for personal use) | packet-capture driver | **no** — not redistributed; NavTool loads `wpcap.dll` from `System32\Npcap` if present |
| Peter Lowe / StevenBlack lists | downloaded on demand by the user | see each project | optional block lists | **no** — never bundled |

Packet capture, packet parsing (Ethernet / IPv4 / IPv6 / TCP / UDP / DNS) and the tray icon are implemented in the
project itself (`pcap.py`, `netparse.py`, `tray.py`) using Windows APIs through `ctypes`. NavTool previously used
Scapy (GPL-2.0-only), pystray (LGPL-3.0) and Pillow; **they were removed in 1.1**, which also made the executable
smaller and the capture faster.

## What this means for licensing

NavTool is released under the **GNU GPL v3** (see `LICENSE`). Every component that ends up in the executable is compatible with it:
psutil (BSD-3-Clause) and Python (PSF) are permissive; PyInstaller's bootloader has an exception that allows any license for the output.
Npcap is never bundled.

Anyone who receives the executable must be able to get the corresponding source code: that is what this repository is for.
Keep the `Releases` page linked to the exact commit each binary was built from.

Notes
* Npcap's own license restricts redistribution and commercial use; that is why NavTool asks the user to install it
  from npcap.com instead of shipping it.
* The block lists have their own terms. NavTool downloads them only when the user asks and stores them locally.

This file is informational, not legal advice.
