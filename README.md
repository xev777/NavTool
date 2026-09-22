# NavTool

**A floating bar for Windows that shows and controls what happens with your Internet connection** —
how pages load, who tracks you, and which programs use your network. Works with every browser.

*(Español: [README.es.md](README.es.md))*

## What it does

| | |
|---|---|
| **Page-load bar** | Watch every connection of a page while it loads, and **cut** it with one click (pop-ups, chained loads). |
| **Privacy report** | A grade (A–F) for each page: which trackers it contacted and which NavTool blocked. |
| **Block lists** | Built-in list plus optional Peter Lowe / StevenBlack lists, personal list and exceptions. |
| **Network monitor** | Every program, who it talks to, how much it moves. Npcap capture, exact totals. |
| **Block a program** | Right-click a program in the monitor → Windows Firewall rules (1 h / 4 h / until you unblock). |
| **Store apps compatibility** | WhatsApp / Microsoft Store and other Store apps work with the proxy on (Windows loopback exemption, one click). |
| **Monthly data quota** | Set your plan and billing day: usage, projection and warnings at 80 % / 100 %. |
| **History and alerts** | Per-minute usage, per-program usage, new programs, sustained uploads. Kept on your PC only. |
| **Search bar** | Up to 5 search engines, one keystroke to search in all. |
| **Languages** | English (default) and Spanish included; load more language packs (`.json`). |
| **Bar** | Large / medium / collapsed, magnetic docking, tray icon, tooltips, multi-monitor aware. |

Everything runs locally. **No telemetry, no accounts, no automatic updates.**

## Code signing policy

Free code signing provided by [SignPath.io](https://about.signpath.io/), certificate by [SignPath Foundation](https://signpath.org/) *(application in progress: until it is approved, releases are unsigned)*. See [CODE_SIGNING_POLICY.md](CODE_SIGNING_POLICY.md) and the [privacy policy](PRIVACY.md).

## Install

Download from the [Releases](../../releases) page:

* `NavTool-Setup-<version>.exe` — installer (English by default; Spanish available in the first screen).
* `NavTool-Portable-<version>.zip` — portable, leaves nothing on the PC.

Check the SHA-256 shown in the release notes. The executables are **not code-signed** yet, so Windows
SmartScreen may warn.

The traffic monitor needs [Npcap](https://npcap.com) and administrator rights (NavTool does not bundle Npcap).

## Run from source

```powershell
python -m pip install -r requirements.txt
python navtool.py
```

Build the installer and the portable zip (needs [Inno Setup 6](https://jrsoftware.org/isinfo.php)):

```powershell
powershell -ExecutionPolicy Bypass -File .\compilar.ps1
```

## Tests

```powershell
python pruebas_seguridad.py    # 52 attack + regression tests (proxy, packet parser, downloads…)
python pruebas_funciones.py    # quota, program blocking, Store apps, language packs, credits
python -m pip_audit -r requirements.txt
python -m bandit -r . -ll --exclude ./dist,./build
```

## Documentation

* [SEGURIDAD.md](SEGURIDAD.md) — security audit, attacks reproduced, residual risks *(Spanish)*.
* [MEDICION.md](MEDICION.md) — does blocking ads save data? Measured. *(Spanish)*
* [TRADUCIR.md](TRADUCIR.md) — how to add a language.
* [CHANGELOG.md](CHANGELOG.md) — what changed in each version.
* [LICENCIAS-TERCEROS.md](LICENCIAS-TERCEROS.md) — third-party components and license notes.

## Contributing

Bug reports, translations and pull requests are welcome. For a new language see [TRADUCIR.md](TRADUCIR.md).
Security issues: please open a private security advisory instead of a public issue.

## License

Copyright (C) 2026 Fernando Erazo. NavTool is free software: you can redistribute it and/or modify it under the
terms of the **GNU General Public License version 3** (see [LICENSE](LICENSE)). It is distributed in the hope that it will be
useful, but **without any warranty**.

## Credits

Design and development: Fernando Erazo ([@xev777](https://github.com/xev777)). Programming assistance: Claude (Anthropic).
Third-party components: Npcap (user-installed), psutil, Python/Tkinter. See [LICENCIAS-TERCEROS.md](LICENCIAS-TERCEROS.md).

## Support the project

NavTool is free and always will be. If it's useful to you, you can support its development via PayPal
(xev667@hotmail.com) — entirely optional, and also available from the app's About screen.
