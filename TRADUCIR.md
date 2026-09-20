# Add a language / Añadir un idioma

NavTool's original texts are Spanish. A **language pack** is a `.json` file that maps each Spanish text to its
translation. NavTool translates on the fly, so no code changes are needed.

## Quick way (from the app)

1. Right-click the bar → **Idioma / Language** → **Export the translation template…** (saves `plantilla-idioma.json`).
2. Open it in any editor. In `"meta"` set your language:
   ```json
   "meta": { "code": "fr", "name": "Français", "version": 1, "author": "Your name" }
   ```
   `code` is 2–3 lowercase letters (`fr`, `pt`, `de`…, optionally `pt-BR`). `es` is reserved (the original).
3. Fill in `"strings"`: put your translation as the value of each Spanish key (leave it empty to keep the Spanish).
4. Right-click the bar → **Idioma / Language** → **Load a language pack…** and choose your file. Activate it.

## Rules

* **Keep the placeholders.** `{}` marks a variable part (number, name). Keep the same count, in any order using
  `{1}`, `{2}`… if your grammar needs it: `"{} de {}": "{2} of {1}"`. Do not put other braces.
* Keep line breaks (`\n`) and symbols (`⏻`, `📡`, `→`) where they are.
* Keys must match exactly (they are the original Spanish). Don't edit the keys.
* Files up to 2 MB and 6,000 entries. Control characters and right-to-left marks are removed on load.
* Packs are only **text**: they cannot run code.

## Share it

Send your `xx.json` as a pull request to `idiomas/` and it will ship with the next release.
Included today: `en` (English). Spanish is the original.

## Developers

`python extraer_textos.py` regenerates `idiomas/plantilla.json` from the source code (AST-based).
`python pruebas_funciones.py` checks the packs (placeholders, coverage, hostile inputs).

---

# Español

Un **pack de idioma** es un `.json` que asocia cada texto original (español) con su traducción.
Pasos: clic derecho en la barra → *Idioma / Language* → *Exportar la plantilla para traducir…*; edita `meta` y
`strings`; luego *Cargar un pack de idioma…*. Conserva los marcadores `{}` y los saltos de línea `\n`.
Los packs solo contienen texto: no pueden ejecutar código.
