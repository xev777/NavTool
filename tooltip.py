"""Globos de ayuda (tooltips) de NavTool.

    tip(widget, "texto")                      texto fijo
    tip(widget, lambda: f"...{estado}...")    texto que cambia (se calcula al mostrarse)
    tip(canvas, None, area=lambda x, y: ...)  distinto texto según la zona bajo el ratón

Salen tras una pausa del ratón, no roban el foco, se ajustan a todos los monitores y
desaparecen al salir, hacer clic o cerrar el widget.
"""
import tkinter as tk

from safety import monitor_work_area

BG_TIP, FG_TIP, BORDER = "#0f1a2b", "#e8eef7", "#3fa9f5"
DELAY_MS = 500


class Tooltip:
    def __init__(self, widget, text=None, area=None):
        self.widget, self.text, self.area = widget, text, area
        self.tip = None
        self.job = None
        self.current = None
        self._event = None
        widget.bind("<Enter>", self._enter, add="+")
        widget.bind("<Leave>", self.hide, add="+")
        widget.bind("<ButtonPress>", self.hide, add="+")
        widget.bind("<Destroy>", self.hide, add="+")
        if area:
            widget.bind("<Motion>", self._motion, add="+")

    # ---- texto
    def _resolve(self, event):
        try:
            if self.area:
                return self.area(event.x, event.y) if event else None
            return self.text() if callable(self.text) else self.text
        except Exception:
            return None            # un tooltip nunca debe romper la interfaz

    # ---- eventos
    def _enter(self, event):
        self._schedule(event)

    def _motion(self, event):
        text = self._resolve(event)
        if text != self.current:               # cambió de zona: se oculta y se espera de nuevo
            self.hide()
            if text:
                self._schedule(event)

    def _schedule(self, event):
        self._cancel()
        self._event = event
        try:
            self.job = self.widget.after(DELAY_MS, self._show)
        except tk.TclError:
            self.job = None

    def _cancel(self):
        if self.job is not None:
            try:
                self.widget.after_cancel(self.job)
            except (tk.TclError, ValueError):
                pass
            self.job = None

    # ---- mostrar / ocultar
    def _show(self):
        self.job = None
        text = self._resolve(self._event)
        if not text:
            return
        self.current = text
        try:
            self._build(text)
        except tk.TclError:
            self.tip = None

    def _build(self, text):
        px, py = self.widget.winfo_pointerxy()
        tw = tk.Toplevel(self.widget)
        tw.overrideredirect(True)
        tw.attributes("-topmost", True)
        tw.configure(bg=BORDER)
        tk.Label(tw, text=text, justify="left", wraplength=340, bg=BG_TIP, fg=FG_TIP,
                 font=("Segoe UI", 9), padx=9, pady=6).pack(padx=1, pady=1)
        tw.update_idletasks()
        w, h = tw.winfo_reqwidth(), tw.winfo_reqheight()
        left, top, right, bottom = monitor_work_area(px, py)     # el monitor donde está el puntero
        x = max(left + 4, min(px + 14, right - w - 4))
        y = py + 22
        if y + h > bottom - 4:                  # no cabe debajo: se pone encima del puntero
            y = py - h - 12
        tw.geometry(f"+{x}+{max(top + 2, y)}")
        self.tip = tw

    def hide(self, _event=None):
        self._cancel()
        self.current = None
        if self.tip is not None:
            try:
                self.tip.destroy()
            except tk.TclError:
                pass
            self.tip = None


def tip(widget, text=None, area=None):
    """Atajo: añade un tooltip y lo devuelve."""
    return Tooltip(widget, text, area)
