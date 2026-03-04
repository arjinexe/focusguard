"""
FocusGuard — GUI
CustomTkinter interface with 7 tabs, sidebar navigation,
gamification (XP/levels/achievements), screen text bomber,
Pomodoro timer, analytics, and full settings panel.
"""

import logging
import queue
import random
import sys
import threading
import time
import tkinter as tk
from collections import deque
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import customtkinter as ctk

from focusguard.config import CONFIG, MOTIVATION_MESSAGES, SCREEN_TEXT_MESSAGES, ACHIEVEMENTS
from focusguard.i18n import t
from focusguard.modules.session import FocusSession, SessionStats, State, DetectionEntry
from focusguard.modules.analyzer import AnalysisResult
from focusguard.modules import store

logger = logging.getLogger("focusguard.gui")

# Theme
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

C = {
    # Base surfaces — softer dark tones, easier on eyes
    "bg":          "#0E1117",
    "surface":     "#141921",
    "card":        "#1A2230",
    "card_hi":     "#1F2A3C",
    "sidebar":     "#0E1117",
    "border":      "#252F42",
    "border_hi":   "#35445C",

    # Accent colours — slightly desaturated, less harsh
    "red":         "#E8314A",
    "red_dim":     "#3A0E18",
    "red_glow":    "#FF4D68",
    "green":       "#10C97A",
    "green_dim":   "#0A3321",
    "amber":       "#F0A030",
    "amber_dim":   "#3A2200",
    "blue":        "#4A90D9",
    "blue_dim":    "#162040",
    "purple":      "#9A7FE0",
    "purple_dim":  "#2A1850",
    "cyan":        "#38BDF8",
    "cyan_dim":    "#0A2535",
    "gold":        "#F5C518",
    "gold_dim":    "#3A2D00",

    # Text hierarchy — higher contrast, more readable
    "text":        "#E2E8F0",    # primary — near-white but soft
    "text2":       "#94A3B8",    # secondary
    "text3":       "#4A5568",    # muted / labels

    # Canvas backgrounds
    "wave_bg":     "#0E1117",
    "wave_grid":   "#171E2B",
    "nav_active":  "#1A2230",

    # XP / gamification
    "xp_bar":      "#6D28D9",
    "xp_fill":     "#8B5CF6",
}

import platform as _platform
_sys_platform = _platform.system()
FM      = "Segoe UI"       if _sys_platform == "Windows" else \
          "Helvetica"      if _sys_platform == "Darwin"  else \
          "DejaVu Sans"
FM_MONO = "Courier New"    if _sys_platform == "Windows" else \
          "Menlo"          if _sys_platform == "Darwin"  else \
          "DejaVu Sans Mono"
MAX_LOG_LINES = 150

# UI scale factor — all lbl() calls get +_FS to their font size for readability
_FS = 3  # bumps sz=9→12, sz=10→13, sz=11→14 etc.


# Helpers
def lbl(parent, text="", sz=10, bold=False, col=None, **kw):
    """Label with consistent font scaling. Minimum rendered size = 12px."""
    actual_sz = max(12, sz + _FS)
    return ctk.CTkLabel(
        parent, text=text,
        font=(FM, actual_sz, "bold" if bold else "normal"),
        text_color=col or C["text"],
        **kw,
    )


def sep(parent, axis="x", thickness=1, color=None, pad=12):
    f = ctk.CTkFrame(
        parent,
        height=thickness if axis == "x" else 0,
        width=thickness if axis == "y" else 0,
        fg_color=color or C["border"],
        corner_radius=0,
    )
    if axis == "x":
        f.pack(fill="x", padx=pad)
    return f


def card_frame(parent, **kw):
    return ctk.CTkFrame(
        parent, fg_color=C["card"], corner_radius=10,
        border_width=1, border_color=C["border"], **kw
    )


# Screen Text Bomber
class ScreenTextBomber:
    """
    Displays large motivational/shame messages at random screen positions.
    Combined with mouse jitter for maximum disruption.
    """

    def __init__(self, root: ctk.CTk):
        self._root = root
        self._active_windows: List[tk.Toplevel] = []
        self._lock = threading.Lock()

    def fire(self, message: str, level: int = 0):
        """Display text at a random position on screen."""
        try:
            sw = self._root.winfo_screenwidth()
            sh = self._root.winfo_screenheight()

            # Rastgele boyut ve konum
            font_size = 28 + level * 8
            ow = max(300, min(sw - 100, len(message) * (font_size // 2) + 80))
            oh = font_size * 3 + 40

            # Divide screen into 9 zones and pick one at random
            zones = []
            margin = 80
            for xi in range(3):
                for yi in range(3):
                    xz = margin + xi * ((sw - 2*margin) // 3)
                    yz = margin + yi * ((sh - 2*margin) // 3)
                    zones.append((xz, yz))
            x, y = random.choice(zones)
            x = max(0, min(x, sw - ow))
            y = max(0, min(y, sh - oh))

            # Color depends on current escalation level
            colors = [C["amber"], C["red"], C["red_glow"], "#FF0000", "#FF0000"]
            color = colors[min(level, len(colors) - 1)]

            win = tk.Toplevel(self._root)
            win.overrideredirect(True)
            win.attributes("-topmost", True)
            win.attributes("-alpha", 0.92)
            win.configure(bg=C["bg"])
            win.geometry(f"{ow}x{oh}+{x}+{y}")

            c = tk.Canvas(win, bg=C["bg"], highlightthickness=0)
            c.pack(fill="both", expand=True)

            # Border
            c.create_rectangle(2, 2, ow-2, oh-2, outline=color, width=2)

            # Text label
            c.create_text(
                ow // 2, oh // 2,
                text=message,
                fill=color,
                font=(FM, font_size, "bold"),
                width=ow - 20,
                justify="center",
            )

            with self._lock:
                self._active_windows.append(win)

            # Animated fade-out
            duration = 2500 + level * 500
            self._root.after(duration, lambda w=win: self._destroy(w))

            # Sallanma efekti
            self._shake_window(win, ow, oh, x, y, level)

        except Exception as e:
            logger.debug(f"ScreenTextBomber hata: {e}")

    def _shake_window(self, win, ow, oh, x, y, level):
        if level < 2:
            return
        shake_px = CONFIG.shake_intensity + level * 3
        steps = 8

        def do_shake(step=0):
            try:
                if not win.winfo_exists():
                    return
                if step < steps:
                    dx = random.randint(-shake_px, shake_px)
                    dy = random.randint(-shake_px, shake_px)
                    win.geometry(f"{ow}x{oh}+{x+dx}+{y+dy}")
                    self._root.after(60, lambda: do_shake(step + 1))
                else:
                    win.geometry(f"{ow}x{oh}+{x}+{y}")
            except Exception:
                pass

        self._root.after(200, do_shake)

    def _destroy(self, win):
        try:
            if win.winfo_exists():
                win.destroy()
            with self._lock:
                if win in self._active_windows:
                    self._active_windows.remove(win)
        except Exception:
            pass

    def destroy_all(self):
        with self._lock:
            wins = list(self._active_windows)
        for w in wins:
            self._destroy(w)


# Waveform Canvas
class WaveformCanvas(tk.Canvas):
    POINTS = 90

    def __init__(self, parent, h=130, **kw):
        super().__init__(parent, height=h, bg=C["wave_bg"], highlightthickness=0, **kw)
        self._data: deque = deque([0.0] * self.POINTS, maxlen=self.POINTS)
        self._width = 1   # renamed from _w — avoids overwriting tkinter's internal _w (Tcl widget name)
        self._height = h
        self.bind("<Configure>", lambda e: self._resize(e.width, e.height))
        self.after_idle(self._draw)   # defer: widget must be mapped before first draw

    def push(self, v: float):
        self._data.append(max(0.0, min(1.0, float(v))))
        self._draw()

    def _resize(self, w, h):
        self._width, self._height = w, h
        self._draw()

    def _draw(self):
        try:
            self.delete("all")
        except tk.TclError:
            return
        w, h = self._width, self._height
        if w < 10 or h < 10:
            return
        px, py = 32, 8
        pw = w - px - 8
        ph = h - py * 2

        for frac, label in ((0.25, "25"), (0.50, "50"), (0.75, "75")):
            gy = py + ph * (1 - frac)
            self.create_line(px, gy, w - 8, gy, fill=C["wave_grid"], width=1, dash=(3, 4))
            self.create_text(px - 4, gy, text=label, fill=C["text3"], font=(FM, 14), anchor="e")

        thresh = CONFIG.confidence_threshold
        ty = py + ph * (1 - thresh)
        self.create_line(px, ty, w - 8, ty, fill=C["amber"], width=1, dash=(6, 4))
        self.create_text(px - 4, ty, text=f"{int(thresh*100)}", fill=C["amber"], font=(FM, 14), anchor="e")

        data = list(self._data)
        n    = len(data)
        if n < 2:
            return
        step = pw / (n - 1)

        def pt(i, v):
            return px + i * step, py + ph * (1 - v)

        recent = max(data[-10:])
        if recent >= thresh:
            fill = "#1A0308"
        elif recent > 0.3:
            fill = "#1A1400"
        else:
            fill = "#001608"

        poly = [px, py + ph]
        for i, v in enumerate(data):
            x_, y_ = pt(i, v)
            poly += [x_, y_]
        poly += [px + (n-1) * step, py + ph]
        if len(poly) >= 6:
            self.create_polygon(poly, fill=fill, outline="")

        for i in range(n - 1):
            x1, y1 = pt(i,   data[i])
            x2, y2 = pt(i+1, data[i+1])
            v = data[i]
            col = C["red"] if v >= thresh else (C["amber"] if v > 0.3 else C["green"])
            self.create_line(x1, y1, x2, y2, fill=col, width=2, smooth=True)

        last = data[-1]
        lx, ly = pt(n-1, last)
        dc = C["red"] if last >= thresh else (C["amber"] if last > 0.3 else C["green"])
        self.create_oval(lx-5, ly-5, lx+5, ly+5, fill=dc, outline=C["bg"], width=2)
        self.create_text(w - 6, ly, text=f"{last:.0%}", fill=dc, font=(FM, 13, "bold"), anchor="e")


# Pomodoro Ring
class PomodoroRing(tk.Canvas):
    SIZE   = 270
    STROKE = 16
    GAP    = 4

    def __init__(self, parent, **kw):
        s = self.SIZE
        super().__init__(parent, width=s, height=s, bg=C["bg"], highlightthickness=0, **kw)
        self._progress  = 1.0
        self._mode      = "focus"
        self._label     = "25:00"
        self._sublabel  = t("ring_focus")
        self._session_n = 1
        self.after_idle(self._draw)   # defer: widget must be mapped before first draw

    def update_ring(self, progress: float, mm_ss: str, mode: str, session_n: int):
        self._progress  = max(0.0, min(1.0, progress))
        self._label     = mm_ss
        self._mode      = mode
        self._session_n = session_n
        self._sublabel  = t("ring_focus") if mode == "focus" else (t("ring_long_break") if mode == "long_break" else t("ring_break"))
        self._draw()

    def _draw(self):
        try:
            self.delete("all")
        except tk.TclError:
            return
        s  = self.SIZE
        cx = cy = s // 2
        r  = cx - self.STROKE // 2 - self.GAP
        x0, y0, x1, y1 = cx - r, cy - r, cx + r, cy + r

        if self._mode == "focus":
            ring_col = C["green"]
            ring_dim = C["green_dim"]
        elif self._mode == "long_break":
            ring_col = C["purple"]
            ring_dim = C["purple_dim"]
        else:
            ring_col = C["amber"]
            ring_dim = C["amber_dim"]

        gr = r + self.STROKE // 2 + 2
        self.create_oval(cx-gr, cy-gr, cx+gr, cy+gr, fill=C["bg"], outline=ring_dim, width=1)
        self.create_arc(x0, y0, x1, y1, start=90, extent=-360,
                        outline=C["border_hi"], width=self.STROKE, style="arc")

        extent = -self._progress * 359.9
        if abs(extent) > 0.5:
            self.create_arc(x0, y0, x1, y1, start=90, extent=extent,
                            outline=ring_col, width=self.STROKE, style="arc")

        self.create_text(cx, cy - 54, text=t("session_num").format(n=self._session_n),
                         fill=C["text3"], font=(FM, 14))
        self.create_text(cx, cy - 8, text=self._label,
                         fill=C["text"], font=(FM, 34, "bold"))
        self.create_text(cx, cy + 34, text=self._sublabel,
                         fill=ring_col, font=(FM, 13, "bold"))

        dot_y = cy + 55
        dots = min(self._session_n, 8)
        total_dots = CONFIG.long_break_after_sessions
        for i in range(total_dots):
            dx = cx - (total_dots * 12 // 2) + i * 14
            filled = i < dots % (total_dots + 1)
            fill_c = ring_col if filled else C["border_hi"]
            self.create_oval(dx-4, dot_y-4, dx+4, dot_y+4, fill=fill_c, outline="")


# Stat Card
class StatCard(ctk.CTkFrame):
    def __init__(self, parent, title: str, value: str = "—", sub: str = "", **kw):
        super().__init__(parent, fg_color=C["card"], corner_radius=10,
                         border_width=1, border_color=C["border"], **kw)
        # Thin accent line at top edge
        ctk.CTkFrame(self, fg_color=C["border_hi"], height=2,
                     corner_radius=0).pack(fill="x")
        lbl(self, title, 9, bold=True, col=C["text3"]).pack(pady=(10, 0), padx=12)
        self._val = lbl(self, value, 24, bold=True, col=C["text"])
        self._val.pack(pady=(4, 0))
        self._sub = lbl(self, sub, 9, col=C["text2"])
        self._sub.pack(pady=(2, 12))

    def set(self, value: str, col=None, sub: str = None):
        self._val.configure(text=value, text_color=col or C["text"])
        if sub is not None:
            self._sub.configure(text=sub)


# XP Bar
class XPBar(ctk.CTkFrame):
    def __init__(self, parent, **kw):
        super().__init__(parent, fg_color="transparent", **kw)
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x")

        self._level_lbl = lbl(top, "LVL 1", 11, bold=True, col=C["xp_fill"])
        self._level_lbl.pack(side="left")

        self._xp_lbl = lbl(top, "0 / 200 XP", 9, col=C["text3"])
        self._xp_lbl.pack(side="right")

        self._bar = ctk.CTkProgressBar(
            self, progress_color=C["xp_fill"], fg_color=C["border"],
            height=6, corner_radius=3,
        )
        self._bar.set(0)
        self._bar.pack(fill="x", pady=(4, 0))

    def update(self, xp_info: dict):
        level    = xp_info.get("level", 1)
        cur      = xp_info.get("current_xp", 0)
        nxt      = xp_info.get("next_xp", 200)
        progress = xp_info.get("progress", 0)

        self._level_lbl.configure(text=f"LVL {level}")
        self._xp_lbl.configure(text=f"{cur} / {nxt} XP")
        self._bar.set(progress)


# Engine Card
class EngineCard(ctk.CTkFrame):
    def __init__(self, parent, name: str, desc: str = "", **kw):
        super().__init__(parent, fg_color=C["card"], corner_radius=10,
                         border_width=1, border_color=C["border"], **kw)
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=14, pady=(12, 4))
        self._led = lbl(top, "●", 13, col=C["text3"])
        self._led.pack(side="left", padx=(0, 6))
        lbl(top, name, 10, bold=True).pack(side="left")
        self._ms = lbl(top, "", 9, col=C["text3"])
        self._ms.pack(side="right")
        lbl(self, desc, 8, col=C["text2"]).pack(anchor="w", padx=12, pady=(0, 8))

    def set_status(self, state: str, ms: float = 0.0):
        col = {"ready": C["green"], "loading": C["amber"], "off": C["text3"]}.get(state, C["text3"])
        self._led.configure(text_color=col)
        if ms > 0:
            self._ms.configure(text=f"{ms:.0f}ms")


# Bar Chart
class BarChart(tk.Canvas):
    def __init__(self, parent, w=400, h=160, **kw):
        super().__init__(parent, width=w, height=h, bg=C["wave_bg"], highlightthickness=0, **kw)
        self._data = []
        self._width, self._height = w, h   # renamed from _w/_h — avoids overwriting tkinter's internal _w
        self.bind("<Configure>", lambda e: self._resize(e.width, e.height))

    def _resize(self, w, h):
        self._width, self._height = w, h
        self._draw()

    def set_data(self, days: list):
        self._data = days
        self._draw()

    def _draw(self):
        try:
            self.delete("all")
        except tk.TclError:
            return
        data = self._data
        if not data:
            self.create_text(self._width // 2, self._height // 2, text=t("no_data"),
                             fill=C["text3"], font=(FM, 13))
            return
        w, h   = self._width, self._height
        px, py = 8, 10
        pw     = w - px * 2
        ph     = h - py - 26
        n      = len(data)
        bw     = max(4, (pw - (n-1)*4) / n)
        max_v  = max(1, max(d["detections"] for d in data))

        from datetime import date
        today = date.today().isoformat()
        for i, d in enumerate(data):
            bx = px + i * (bw + 4)
            v  = d["detections"]
            # Always draw a minimum visible bar (4px) so the chart looks active
            bh = max(4, ph * v / max_v) if v > 0 else 4
            by = py + ph - bh
            col = C["red"] if d["date"] == today else C["blue"]
            # Background track
            self.create_rectangle(bx, py, bx+bw, py+ph, fill=C["wave_grid"], outline="")
            # Bar — even 0-detection days show a tiny stub at the bottom
            bar_col = col if v > 0 else C["border"]
            self.create_rectangle(bx, by, bx+bw, py+ph, fill=bar_col, outline="")
            day_str = d["date"][5:]
            self.create_text(bx + bw//2, h - 12, text=day_str, fill=C["text3"], font=(FM, 14))
            if v > 0:
                self.create_text(bx + bw//2, by - 8, text=str(v), fill=col, font=(FM, 13, "bold"))


# Nav Button
class NavButton(tk.Frame):
    def __init__(self, parent, icon: str, tooltip: str, command, **kw):
        super().__init__(parent, bg=C["sidebar"], cursor="hand2", **kw)
        self._active = False
        self._cmd    = command
        # Left indicator bar (3px, coloured when active)
        self._indicator = tk.Frame(self, bg=C["sidebar"], width=3)
        self._indicator.pack(side="left", fill="y")
        inner = tk.Frame(self, bg=C["sidebar"])
        inner.pack(fill="both", expand=True)
        self._icon_lbl = tk.Label(inner, text=icon, bg=C["sidebar"],
                                  fg=C["text3"], font=(FM, 14))
        self._icon_lbl.pack(expand=True, pady=(5, 0))
        self._tooltip = tk.Label(inner, text=tooltip, bg=C["sidebar"],
                                 fg=C["text3"], font=(FM, 9))
        self._tooltip.pack(pady=(0, 5))
        for w in (self, inner, self._icon_lbl, self._tooltip):
            w.bind("<Button-1>", self._click)
            w.bind("<Enter>",    self._hover_in)
            w.bind("<Leave>",    self._hover_out)

    def _click(self, _e=None): self._cmd()

    def _hover_in(self, _e=None):
        if not self._active:
            self._set_bg(C["nav_active"])

    def _hover_out(self, _e=None):
        if not self._active:
            self._set_bg(C["sidebar"])

    def _set_bg(self, color: str):
        all_widgets = [self, self._icon_lbl, self._tooltip]
        for w in self.winfo_children():
            all_widgets.append(w)
            for ww in w.winfo_children():
                all_widgets.append(ww)
        for w in all_widgets:
            try:
                w.configure(bg=color)
            except Exception:
                pass

    def set_active(self, active: bool):
        self._active = active
        if active:
            self._indicator.configure(bg=C["red"])
            self._icon_lbl.configure(fg=C["text"])
            self._tooltip.configure(fg=C["text2"])
            self._set_bg(C["nav_active"])
        else:
            self._indicator.configure(bg=C["sidebar"])
            self._icon_lbl.configure(fg=C["text3"])
            self._tooltip.configure(fg=C["text3"])
            self._set_bg(C["sidebar"])


# MAIN APPLICATION
class FocusGuardApp(ctk.CTk):
    """
    FocusGuard main application window.
    7-tab layout with sidebar navigation and full session management.
    """

    TABS = ["dashboard", "session", "engines", "achievements", "stats", "settings", "about"]

    def __init__(self, minimized: bool = False):
        super().__init__()
        store.load_settings(CONFIG)

        self.title("FocusGuard")
        self.geometry("1120x740")
        self.minsize(900, 600)
        self.resizable(True, True)
        self.configure(fg_color=C["bg"])

        # State
        self._q: queue.Queue = queue.Queue(maxsize=256)
        self._session_start: float = 0.0
        self._pomodoro_end:  float = 0.0
        self._pomodoro_mode  = "focus"
        self._session_count  = 1
        self._backends: Dict[str, str] = {"ollama": "off", "ocr": "loading", "opencv": "ready"}
        self._backend_ms: Dict[str, float] = {}
        self._last_detection_idx = -1
        self._log_line_count = 0
        self._active_tab = "dashboard"
        self._tab_frames: dict = {}
        self._nav_btns:   dict = {}
        self._motivation_idx = 0

        # Pause-time tracking — so session clock doesn't count paused seconds
        self._pause_start:          float = 0.0   # wall-clock time when last paused
        self._pause_accumulated:    float = 0.0   # total seconds spent paused in this session
        self._frozen_ring_remaining: float = 0.0  # ring countdown frozen while paused
        # Break rate-limiting — require minimum work before manual break
        self._last_break_time:   float = 0.0   # wall-clock when last manual break started
        _MIN_WORK_BEFORE_BREAK   = 5 * 60      # 5 minutes

        # Screen text bomber
        self._text_bomber = ScreenTextBomber(self)

        # Session
        self._session = FocusSession(
            on_update=lambda s, r: self._q.put_nowait(("upd", s, r)),
            on_backend_status=lambda n, ok: self._q.put_nowait(("eng", n, ok)),
            overlay_fn=lambda msg, lvl: self._q.put_nowait(("ovl", msg, lvl)),
            screen_text_fn=lambda msg, lvl: self._q.put_nowait(("txt", msg, lvl)),
            on_session_end=lambda s: self._q.put_nowait(("end", s)),
            on_achievement=lambda a: self._q.put_nowait(("ach", a)),
            on_level_up=lambda o, n: self._q.put_nowait(("lvl", o, n)),
            on_idle=lambda sig, secs: self._q.put_nowait(("idle", sig, secs)),
        )

        self._build_skeleton()
        self._build_all_tabs()
        self._switch_tab("dashboard")
        self._bind_keys()
        self._poll()
        self._tick_second()
        self._refresh_xp_display()
        self._start_motivation_cycle()

        # Autostart session
        if CONFIG.autostart_session:
            self.after(2000, self._toggle_session)

        # Always on top
        if CONFIG.window_always_on_top:
            self.attributes("-topmost", True)

        if minimized:
            self.after(100, self.iconify)

    # Skeleton

    def _build_skeleton(self):
        self._hdr = ctk.CTkFrame(self, fg_color=C["surface"], corner_radius=0, height=62)
        self._hdr.pack(fill="x")
        self._hdr.pack_propagate(False)
        self._build_header()

        mid = tk.Frame(self, bg=C["bg"])
        mid.pack(fill="both", expand=True)

        self._sidebar = tk.Frame(mid, bg=C["sidebar"], width=88)
        self._sidebar.pack(side="left", fill="y")
        self._sidebar.pack_propagate(False)
        self._build_sidebar()

        self._content = ctk.CTkFrame(mid, fg_color=C["bg"], corner_radius=0)
        self._content.pack(side="left", fill="both", expand=True)

        self._ftr = ctk.CTkFrame(self, fg_color=C["surface"], corner_radius=0, height=60)
        self._ftr.pack(fill="x", side="bottom")
        self._ftr.pack_propagate(False)
        self._build_footer()

    def _build_header(self):
        # Left: logo + status
        left = ctk.CTkFrame(self._hdr, fg_color="transparent")
        left.pack(side="left", padx=20, pady=0, fill="y")

        logo_row = ctk.CTkFrame(left, fg_color="transparent")
        logo_row.pack(side="left", fill="y")

        lbl(logo_row, "FOCUS", 15, bold=True, col=C["text"]).pack(side="left")
        lbl(logo_row, "GUARD", 15, bold=True, col=C["red"]).pack(side="left")

        # Vertical divider
        ctk.CTkFrame(left, fg_color=C["border"], width=1,
                     corner_radius=0).pack(side="left", fill="y", padx=(16, 16), pady=14)

        status_col = ctk.CTkFrame(left, fg_color="transparent")
        status_col.pack(side="left", fill="y")
        self._status_dot = lbl(status_col, "●", 11, col=C["text3"])
        self._status_dot.pack(anchor="w")
        self._status_label = lbl(status_col, t("state_idle"), 9, bold=True, col=C["text3"])
        self._status_label.pack(anchor="w")

        # Centre: XP bar
        centre = ctk.CTkFrame(self._hdr, fg_color="transparent")
        centre.pack(side="left", expand=True, fill="both", padx=20, pady=14)
        self._header_xp = XPBar(centre)
        self._header_xp.pack(fill="x")

        # Right: timer + mode badges
        right = ctk.CTkFrame(self._hdr, fg_color="transparent")
        right.pack(side="right", padx=20, fill="y")

        self._mode_badge = lbl(right, "", 8, bold=True, col=C["text3"])
        self._mode_badge.pack(anchor="e")

        timer_row = ctk.CTkFrame(right, fg_color="transparent")
        timer_row.pack(anchor="e")
        lbl(timer_row, t("card_session") + "  ", 8, col=C["text3"]).pack(side="left")
        self._timer_lbl = lbl(timer_row, "00:00:00", 16, bold=True, col=C["text2"])
        self._timer_lbl.pack(side="left")

    def _build_sidebar(self):
        # Logo mark
        logo = tk.Frame(self._sidebar, bg=C["sidebar"])
        logo.pack(fill="x", pady=(14, 8))
        tk.Label(logo, text="FG", bg=C["sidebar"], fg=C["red"],
                 font=(FM, 13, "bold")).pack()

        tk.Frame(self._sidebar, bg=C["border"], height=1).pack(fill="x", padx=10)

        icons = [
            ("dashboard",    "📊", t("nav_dashboard")),
            ("session",      "⏱",  t("nav_session")),
            ("engines",      "🔬", t("nav_engines")),
            ("achievements", "🏆", t("nav_achievements")),
            ("stats",        "📈", t("nav_stats")),
            ("settings",     "⚙",  t("nav_settings")),
            ("about",        "ℹ",  t("nav_about")),
        ]
        for tab, icon, tip in icons:
            btn = NavButton(
                self._sidebar, icon, tip,
                command=lambda t=tab: self._switch_tab(t),
                width=88, height=64,
            )
            btn.pack(fill="x")
            self._nav_btns[tab] = btn

    def _build_footer(self):
        left = ctk.CTkFrame(self._ftr, fg_color="transparent")
        left.pack(side="left", padx=16, pady=10)

        self._btn_main = ctk.CTkButton(
            left, text=t("btn_focus"),
            font=(FM, 14, "bold"),
            fg_color=C["green_dim"], hover_color=C["green"],
            text_color=C["bg"], corner_radius=7, width=190, height=40,
            command=self._toggle_session,
        )
        self._btn_main.pack(side="left", padx=(0, 8))

        self._btn_break = ctk.CTkButton(
            left, text=t("btn_break"),
            font=(FM, 14), fg_color=C["card"], hover_color=C["border_hi"],
            text_color=C["text2"], corner_radius=7,
            border_width=1, border_color=C["border"],
            width=110, height=40, command=self._do_break,
        )
        self._btn_break.pack(side="left", padx=(0, 8))

        self._btn_stop = ctk.CTkButton(
            left, text=t("btn_stop"),
            font=(FM, 14), fg_color=C["card"], hover_color=C["red_dim"],
            text_color=C["text2"], corner_radius=7,
            border_width=1, border_color=C["border"],
            width=96, height=40, command=self._do_stop,
        )
        self._btn_stop.pack(side="left", padx=(0, 8))

        # Mode buttons
        self._btn_stealth = ctk.CTkButton(
            left, text=t("btn_ghost"),
            font=(FM, 14), fg_color=C["card"], hover_color=C["purple_dim"],
            text_color=C["text3"], corner_radius=7,
            border_width=1, border_color=C["border"],
            width=96, height=40, command=self._toggle_stealth,
        )
        self._btn_stealth.pack(side="left")

        right = ctk.CTkFrame(self._ftr, fg_color="transparent")
        right.pack(side="right", padx=18)
        self._today_lbl = lbl(right, t("today_init"), 9, col=C["text3"])
        self._today_lbl.pack(anchor="e")
        self._shortcut_lbl = lbl(right, t("shortcuts"), 7, col=C["text3"])
        self._shortcut_lbl.pack(anchor="e")

    def _bind_keys(self):
        self.bind("<space>",     lambda _: self._toggle_session())
        self.bind("b",           lambda _: self._do_break())
        self.bind("B",           lambda _: self._do_break())
        self.bind("g",           lambda _: self._toggle_ghost())
        self.bind("G",           lambda _: self._toggle_ghost())
        self.bind("<Escape>",    lambda _: self._do_stop())
        self.bind("<Control-s>", lambda _: self._save_settings())
        for i, tab in enumerate(self.TABS, 1):
            self.bind(f"<Control-{i}>", lambda _, t=tab: self._switch_tab(t))

    # Tab Builder

    def _build_all_tabs(self):
        for tab in self.TABS:
            f = ctk.CTkFrame(self._content, fg_color=C["bg"], corner_radius=0)
            self._tab_frames[tab] = f
            method = getattr(self, f"_build_{tab}_tab", None)
            if method:
                method(f)

    def _switch_tab(self, tab: str):
        for t, f in self._tab_frames.items():
            f.pack_forget()
        self._tab_frames[tab].pack(fill="both", expand=True)
        for t, btn in self._nav_btns.items():
            btn.set_active(t == tab)
        self._active_tab = tab
        if tab == "stats":
            self._refresh_stats_tab()
        elif tab == "achievements":
            self._refresh_achievements_tab()

    # TAB 1: DASHBOARD

    def _build_dashboard_tab(self, parent):
        parent.columnconfigure(0, weight=1)

        # Stat cards
        cards_row = ctk.CTkFrame(parent, fg_color="transparent")
        cards_row.pack(fill="x", padx=16, pady=(16, 10))

        self._card_caught  = StatCard(cards_row, t("card_caught"),  "0",  t("this_session"))
        self._card_session = StatCard(cards_row, t("card_session"), "—",  t("duration"))
        self._card_heat    = StatCard(cards_row, t("card_heat"), "0",  t("escalation"))
        self._card_clean   = StatCard(cards_row, t("card_clean"),   "0",  t("frames"))
        self._card_score   = StatCard(cards_row, t("card_score"),   "—",  t("live_score"))

        for c in (self._card_caught, self._card_session, self._card_heat,
                  self._card_clean, self._card_score):
            c.pack(side="left", expand=True, fill="both", padx=(0, 7))

        # Waveform
        wave_panel = card_frame(parent)
        wave_panel.pack(fill="x", padx=14, pady=(0, 8))
        wave_top = ctk.CTkFrame(wave_panel, fg_color="transparent")
        wave_top.pack(fill="x", padx=14, pady=(10, 4))
        lbl(wave_top, t("distraction_score"), 8, bold=True, col=C["text3"]).pack(side="left")
        self._conf_pct = lbl(wave_top, "0.0%", 13, bold=True, col=C["green"])
        self._conf_pct.pack(side="right")
        self._waveform = WaveformCanvas(wave_panel, h=120)
        self._waveform.pack(fill="x", padx=14, pady=(0, 4))
        self._conf_reason = lbl(wave_panel, t("waiting"), 9, col=C["text2"])
        self._conf_reason.pack(anchor="w", padx=14, pady=(0, 6))

        # Motivation message
        self._motivation_lbl = lbl(wave_panel, "", 8, col=C["green"], justify="center")
        self._motivation_lbl.pack(fill="x", padx=14, pady=(0, 10))

        # Log
        log_panel = card_frame(parent)
        log_panel.pack(fill="both", expand=True, padx=14, pady=(0, 12))
        log_top = ctk.CTkFrame(log_panel, fg_color="transparent")
        log_top.pack(fill="x", padx=12, pady=(10, 6))
        lbl(log_top, t("detection_log"), 8, bold=True, col=C["text3"]).pack(side="left")
        right_btns = ctk.CTkFrame(log_top, fg_color="transparent")
        right_btns.pack(side="right")
        self._log_count_lbl = lbl(right_btns, f"0 {t('records')}", 8, col=C["text3"])
        self._log_count_lbl.pack(side="left", padx=(0, 8))
        ctk.CTkButton(right_btns, text=t("btn_clear"), width=80, height=22,
                      font=(FM, 14), fg_color=C["border"], hover_color=C["red_dim"],
                      text_color=C["text2"], corner_radius=4,
                      command=self._clear_log).pack(side="left")
        sep(log_panel)
        txt_row = ctk.CTkFrame(log_panel, fg_color="transparent")
        txt_row.pack(fill="both", expand=True, padx=10, pady=8)
        self._log_text = tk.Text(
            txt_row, state="disabled", bg=C["card"], fg=C["text2"],
            font=(FM_MONO, 14), relief="flat", borderwidth=0,
            highlightthickness=0, wrap="word", cursor="arrow",
            selectbackground=C["border"],
        )
        self._log_text.pack(side="left", fill="both", expand=True)
        sb = ctk.CTkScrollbar(txt_row, command=self._log_text.yview,
                               fg_color=C["card"], button_color=C["border"],
                               button_hover_color=C["border_hi"])
        sb.pack(side="right", fill="y")
        self._log_text.configure(yscrollcommand=sb.set)
        for tag, col in [("ts", C["text3"]), ("hi", C["red"]), ("md", C["amber"]),
                         ("lo", C["green"]), ("rs", C["text2"])]:
            self._log_text.tag_configure(tag, foreground=col)
        self._log_line_count = 0

    # TAB 2: SESSION (Pomodoro)

    def _build_session_tab(self, parent):
        inner = ctk.CTkFrame(parent, fg_color="transparent")
        inner.pack(expand=True, fill="both")

        center = ctk.CTkFrame(inner, fg_color="transparent")
        center.pack(expand=True)

        self._pomo_ring = PomodoroRing(center)
        self._pomo_ring.pack(pady=(20, 12))

        ctrl = ctk.CTkFrame(center, fg_color="transparent")
        ctrl.pack()

        self._pomo_btn = ctk.CTkButton(
            ctrl, text=t("btn_focus"),
            font=(FM, 14, "bold"), width=160, height=44,
            fg_color=C["green_dim"], hover_color=C["green"],
            text_color=C["bg"], corner_radius=8,
            command=self._toggle_session,
        )
        self._pomo_btn.pack(side="left", padx=(0, 8))

        ctk.CTkButton(ctrl, text=t("btn_break"), font=(FM, 14), width=120, height=44,
                      fg_color=C["card"], hover_color=C["amber_dim"],
                      text_color=C["text2"], corner_radius=8,
                      border_width=1, border_color=C["border"],
                      command=self._do_break).pack(side="left", padx=(0, 8))

        ctk.CTkButton(ctrl, text=t("btn_long_break"), font=(FM, 14), width=150, height=40,
                      fg_color=C["card"], hover_color=C["purple_dim"],
                      text_color=C["text2"], corner_radius=6,
                      border_width=1, border_color=C["border"],
                      command=self._do_long_break).pack(side="left", padx=(0, 8))

        ctk.CTkButton(ctrl, text=t("btn_reset"), font=(FM, 14), width=120, height=44,
                      fg_color=C["card"], hover_color=C["red_dim"],
                      text_color=C["text2"], corner_radius=8,
                      border_width=1, border_color=C["border"],
                      command=self._do_stop).pack(side="left")

        # Mini stats
        today_row = ctk.CTkFrame(center, fg_color="transparent")
        today_row.pack(pady=(16, 0))
        self._pomo_today = lbl(today_row, t("today_summary").format(det=0, min=0), 9, col=C["text3"])
        self._pomo_today.pack()

        # Goal indicator
        goal_row = ctk.CTkFrame(center, fg_color="transparent")
        goal_row.pack(pady=(8, 0))
        self._goal_lbl = lbl(goal_row, "", 9, col=C["blue"])
        self._goal_lbl.pack()

        # Break suggestion
        sugg_row = ctk.CTkFrame(center, fg_color="transparent")
        sugg_row.pack(pady=(8, 0))
        self._break_sugg_lbl = lbl(sugg_row, "", 9, col=C["cyan"], wraplength=420, justify="center")
        self._break_sugg_lbl.pack()

    # TAB 3: ENGINES

    def _build_engines_tab(self, parent):
        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=14, pady=12)

        lbl(scroll, t("engines_title"), 8, bold=True, col=C["text3"]).pack(anchor="w", pady=(0, 6))
        cards_row = ctk.CTkFrame(scroll, fg_color="transparent")
        cards_row.pack(fill="x", pady=(0, 16))

        self._eng_ollama = EngineCard(cards_row, "Ollama / Moondream", t("engine_ollama_desc"))
        self._eng_ollama.pack(side="left", expand=True, fill="both", padx=(0, 8))
        self._eng_ocr = EngineCard(cards_row, "EasyOCR", t("engine_ocr_desc"))
        self._eng_ocr.set_status("loading")
        self._eng_ocr.pack(side="left", expand=True, fill="both", padx=(0, 8))
        self._eng_cv = EngineCard(cards_row, "OpenCV", t("engine_cv_desc"))
        self._eng_cv.set_status("ready")
        self._eng_cv.pack(side="left", expand=True, fill="both")

        sep(scroll, pad=0)
        lbl(scroll, t("analysis_settings"), 8, bold=True, col=C["text3"]).pack(anchor="w", pady=(12, 6))

        interval_panel = card_frame(scroll)
        interval_panel.pack(fill="x", pady=(0, 8))
        ir = ctk.CTkFrame(interval_panel, fg_color="transparent")
        ir.pack(fill="x", padx=14, pady=(10, 4))
        lbl(ir, t("interval_label"), 10, col=C["text"]).pack(side="left")
        self._eng_interval_lbl = lbl(ir, f"{CONFIG.screenshot_interval:.1f}s", 10, bold=True, col=C["amber"])
        self._eng_interval_lbl.pack(side="right")
        self._eng_interval_slider = ctk.CTkSlider(
            interval_panel, from_=0.5, to=5.0, number_of_steps=18,
            command=self._on_interval,
            fg_color=C["border"], progress_color=C["amber"],
            button_color=C["text"], button_hover_color=C["amber"], height=14,
        )
        self._eng_interval_slider.set(CONFIG.screenshot_interval)
        self._eng_interval_slider.pack(fill="x", padx=14, pady=(0, 10))

        sep(scroll, pad=0)
        lbl(scroll, t("resistance_title"), 8, bold=True, col=C["text3"]).pack(anchor="w", pady=(12, 6))

        self._resist_vars = {}
        resist_items = [
            ("enable_mouse_jitter",     "🖱  " + t("resist_jitter_title"),  t("resist_jitter_desc")),
            ("enable_brightness_dim",   "🔅  " + t("resist_dim_title"),    t("resist_dim_desc")),
            ("enable_overlay_warning",  "⚠️  " + t("resist_overlay_title"), t("resist_overlay_desc")),
            ("enable_terminal_shaming", "💬  " + t("resist_terminal_title"), t("resist_terminal_desc")),
            ("enable_sound_alert",      "🔔  " + t("resist_sound_title"),   t("resist_sound_desc")),
            ("enable_fullscreen_blast", "💥  " + t("resist_blast_title"),   t("resist_blast_desc")),
        ]
        for cfg_key, title, desc in resist_items:
            panel = card_frame(scroll)
            panel.pack(fill="x", pady=(0, 6))
            row = ctk.CTkFrame(panel, fg_color="transparent")
            row.pack(fill="x", padx=14, pady=10)
            info = ctk.CTkFrame(row, fg_color="transparent")
            info.pack(side="left", fill="x", expand=True)
            lbl(info, title, 10, col=C["text"]).pack(anchor="w")
            lbl(info, desc, 8, col=C["text2"]).pack(anchor="w")
            var = tk.BooleanVar(value=getattr(CONFIG, cfg_key, False))
            self._resist_vars[cfg_key] = var
            ctk.CTkSwitch(
                row, text="", variable=var, width=44, height=22,
                onvalue=True, offvalue=False,
                fg_color=C["border"], progress_color=C["red"],
                button_color=C["text"],
                command=lambda k=cfg_key, v=var: (setattr(CONFIG, k, v.get()), self._save_settings()),
            ).pack(side="right")

    # TAB 4: ACHIEVEMENTS

    def _build_achievements_tab(self, parent):
        # XP / Level display
        top_panel = card_frame(parent)
        top_panel.pack(fill="x", padx=14, pady=(14, 8))

        top_row = ctk.CTkFrame(top_panel, fg_color="transparent")
        top_row.pack(fill="x", padx=20, pady=16)

        left_info = ctk.CTkFrame(top_row, fg_color="transparent")
        left_info.pack(side="left", expand=True)
        self._ach_level_lbl = lbl(left_info, t("level_label").format(n=1), 24, bold=True, col=C["xp_fill"])
        self._ach_level_lbl.pack(anchor="w")
        self._ach_total_xp = lbl(left_info, t("total_xp").format(n=0), 10, col=C["text2"])
        self._ach_total_xp.pack(anchor="w")
        self._ach_xp_bar = XPBar(left_info)
        self._ach_xp_bar.pack(anchor="w", fill="x", pady=(8, 0))

        right_info = ctk.CTkFrame(top_row, fg_color="transparent")
        right_info.pack(side="right")
        self._ach_streak_lbl = lbl(right_info, t("streak_days").format(n=0), 12, bold=True, col=C["amber"])
        self._ach_streak_lbl.pack(anchor="e")
        self._ach_focus_lbl  = lbl(right_info, t("total_hours").format(h="0.0"), 10, col=C["text2"])
        self._ach_focus_lbl.pack(anchor="e")

        # Achievements grid
        lbl(parent, t("achievements_title"), 8, bold=True, col=C["text3"]).pack(anchor="w", padx=14, pady=(4, 6))

        self._ach_scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        self._ach_scroll.pack(fill="both", expand=True, padx=14, pady=(0, 12))
        self._ach_cards: Dict[str, ctk.CTkFrame] = {}
        self._build_achievement_cards()

    def _build_achievement_cards(self):
        for widget in self._ach_scroll.winfo_children():
            widget.destroy()
        self._ach_cards = {}

        achievements = store.get_all_achievements()
        # 3-column grid
        row_frame = None
        for i, ach in enumerate(achievements):
            if i % 3 == 0:
                row_frame = ctk.CTkFrame(self._ach_scroll, fg_color="transparent")
                row_frame.pack(fill="x", pady=(0, 8))

            unlocked = ach.get("unlocked", False)
            card = ctk.CTkFrame(
                row_frame,
                fg_color=C["card_hi"] if unlocked else C["card"],
                corner_radius=10,
                border_width=2,
                border_color=C["gold"] if unlocked else C["border"],
            )
            card.pack(side="left", expand=True, fill="both", padx=(0, 8))

            icon_col = C["gold"] if unlocked else C["text3"]
            lbl(card, ach.get("icon", "🏅"), 28, col=icon_col).pack(pady=(12, 4))
            ach_title = t(f'ach_{ach["key"]}_title') or ach.get("title", "")
            lbl(card, ach_title, 10, bold=True,
                col=C["text"] if unlocked else C["text3"]).pack()
            lbl(card, ach.get("desc", ""), 8, col=C["text2"] if unlocked else C["text3"],
                wraplength=180).pack(padx=10, pady=(2, 4))

            xp = ach.get("xp", 0)
            xp_lbl = lbl(card, f"+{xp} XP", 9, bold=True,
                         col=C["xp_fill"] if unlocked else C["text3"])
            xp_lbl.pack(pady=(0, 8))

            if unlocked and ach.get("unlocked_at"):
                try:
                    dt = datetime.fromisoformat(ach["unlocked_at"])
                    date_str = dt.strftime("%d.%m.%y")
                    lbl(card, f"✓ {date_str}", 7, col=C["green"]).pack(pady=(0, 6))
                except Exception:
                    pass

            self._ach_cards[ach["key"]] = card

    def _refresh_achievements_tab(self):
        xp_info = store.get_xp_info()
        self._ach_level_lbl.configure(text=t("level_label").format(n=xp_info["level"]))
        self._ach_total_xp.configure(text=t("total_xp").format(n=xp_info['total_xp']))
        self._ach_xp_bar.update(xp_info)
        self._header_xp.update(xp_info)

        streak = store.get_streak_days()
        hours  = store.get_total_focus_hours()
        self._ach_streak_lbl.configure(text=t("streak_days").format(n=streak))
        self._ach_focus_lbl.configure(text=t("total_hours").format(h=hours))

        self._build_achievement_cards()

    # TAB 5: STATS

    def _build_stats_tab(self, parent):
        inner = ctk.CTkFrame(parent, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=14, pady=12)
        self._stats_inner = inner

        # Header + export
        hdr = ctk.CTkFrame(inner, fg_color="transparent")
        hdr.pack(fill="x", pady=(0, 10))
        lbl(hdr, t("stats_title"), 8, bold=True, col=C["text3"]).pack(side="left")

        export_row = ctk.CTkFrame(hdr, fg_color="transparent")
        export_row.pack(side="right")
        ctk.CTkButton(export_row, text=t("btn_csv"), width=80, height=26,
                      font=(FM, 14), fg_color=C["border"], hover_color=C["blue_dim"],
                      text_color=C["text2"], corner_radius=4,
                      command=self._export_log).pack(side="left", padx=(0, 4))
        ctk.CTkButton(export_row, text=t("btn_clear_hist"), width=130, height=26,
                      font=(FM, 14), fg_color=C["border"], hover_color=C["red_dim"],
                      text_color=C["text2"], corner_radius=4,
                      command=self._clear_history).pack(side="left")

        # Summary cards
        cards = ctk.CTkFrame(inner, fg_color="transparent")
        cards.pack(fill="x", pady=(0, 12))
        self._sc_detections = StatCard(cards, t("today_det"), "0")
        self._sc_detections.pack(side="left", expand=True, fill="both", padx=(0, 8))
        self._sc_focus = StatCard(cards, t("today_focus"), "0 min")
        self._sc_focus.pack(side="left", expand=True, fill="both", padx=(0, 8))
        self._sc_sessions = StatCard(cards, t("sessions"), "0")
        self._sc_sessions.pack(side="left", expand=True, fill="both", padx=(0, 8))
        self._sc_pomodoros = StatCard(cards, "POMODORO", "0")
        self._sc_pomodoros.pack(side="left", expand=True, fill="both", padx=(0, 8))
        self._sc_score = StatCard(cards, t("productivity"), "—", "%")
        self._sc_score.pack(side="left", expand=True, fill="both", padx=(0, 8))
        self._sc_dwi = StatCard(cards, t("stat_dwi"), "—", t("stat_dwi_sub"))
        self._sc_dwi.pack(side="left", expand=True, fill="both")

        # Bar chart
        chart_panel = card_frame(inner)
        chart_panel.pack(fill="x", pady=(0, 12))
        lbl(chart_panel, t("chart_title"), 8, bold=True, col=C["text3"]).pack(
            anchor="w", padx=14, pady=(12, 6))
        self._bar_chart = BarChart(chart_panel, h=160)
        self._bar_chart.pack(fill="x", padx=14, pady=(0, 12))

        # Info row
        info_row = ctk.CTkFrame(inner, fg_color="transparent")
        info_row.pack(fill="x")
        self._stats_info = lbl(info_row, "", 9, col=C["text2"])
        self._stats_info.pack(anchor="w")

        # Weekly progress
        weekly_panel = card_frame(inner)
        weekly_panel.pack(fill="x", pady=(8, 0))
        wr = ctk.CTkFrame(weekly_panel, fg_color="transparent")
        wr.pack(fill="x", padx=14, pady=12)
        lbl(wr, "HAFTALIK HEDEF", 9, bold=True, col=C["text3"]).pack(side="left")
        self._weekly_prog = ctk.CTkProgressBar(wr, progress_color=C["green"],
                                                fg_color=C["border"], height=10)
        self._weekly_prog.set(0)
        self._weekly_prog.pack(side="right", fill="x", expand=True, padx=(16, 0))
        self._weekly_lbl = lbl(wr, "0 / 10 saat", 9, col=C["text2"])
        self._weekly_lbl.pack(side="right", padx=(0, 8))

    def _refresh_stats_tab(self):
        days = store.get_last_n_days(7)
        today = store.get_today()
        self._bar_chart.set_data(days)

        focus_min = today["work_seconds"] // 60
        sessions  = today["sessions"]
        det       = today["detections"]
        pomodoros = today.get("pomodoros", 0)

        self._sc_detections.set(str(det), C["red"] if det > 5 else C["text"])
        self._sc_focus.set(f"{focus_min} dk", C["green"] if focus_min >= 25 else C["text2"])
        self._sc_sessions.set(str(sessions))
        self._sc_pomodoros.set(str(pomodoros), C["amber"])

        if focus_min > 0:
            score = max(0, min(100, int(100 - (det / max(1, focus_min / 25)) * 8)))
            col   = C["green"] if score >= 75 else C["amber"] if score >= 50 else C["red"]
            self._sc_score.set(f"{score}", col, "%")
        else:
            self._sc_score.set("—", C["text3"])

        # DWI score from today's avg
        avg_dwi = today.get("avg_dwi", 0)
        if avg_dwi > 0:
            from focusguard.modules.analytics import dwi_label
            dwi_txt, dwi_col = dwi_label(int(avg_dwi))
            self._sc_dwi.set(f"{int(avg_dwi)}", dwi_col, dwi_txt)
        else:
            self._sc_dwi.set("—", C["text3"], "DWI skoru")

        max_det = max(d["detections"] for d in days) if days else 0
        total_sessions = sum(d.get("sessions", 0) for d in days)
        total_focus_min = sum(d.get("work_seconds", 0) for d in days) // 60
        info_str = ""
        if max_det > 0:
            min_det = min(d["detections"] for d in days)
            max_day = next((d["date"] for d in days if d["detections"] == max_det), "")
            min_day = next((d["date"] for d in days if d["detections"] == min_det), "")
            info_str = t("best_day").format(date=max_day, n=max_det)
            if min_day and min_day != max_day:
                info_str += f"  ·  En temiz: {min_day} ({min_det} tespit)"
        elif total_sessions > 0:
            info_str = f"Last 7 days: {total_sessions} sessions · {total_focus_min} min focus — no detections yet"
        self._stats_info.configure(text=info_str or t("no_data"))

        # Weekly
        weekly_h = store.get_weekly_focus_hours()
        goal_h   = CONFIG.weekly_focus_goal_hours
        self._weekly_lbl.configure(text=f"{weekly_h} / {goal_h} saat")
        self._weekly_prog.set(min(1.0, weekly_h / max(1, goal_h)))

    # TAB 6: SETTINGS

    def _build_settings_tab(self, parent):
        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=14, pady=12)

        # Hassasiyet
        self._settings_section(scroll, t("settings_analysis"))

        thresh_panel = card_frame(scroll)
        thresh_panel.pack(fill="x", pady=(0, 8))
        self._slider_row(thresh_panel, t("threshold_label"), f"{int(CONFIG.confidence_threshold*100)}%",
                         0.3, 0.9, 12, CONFIG.confidence_threshold,
                         self._on_threshold, "_thresh_lbl", C["amber"])
        lbl(thresh_panel, t("threshold_hint"),
            8, col=C["text2"]).pack(anchor="w", padx=14, pady=(0, 6))

        interval_panel = card_frame(scroll)
        interval_panel.pack(fill="x", pady=(0, 12))
        self._slider_row(interval_panel, t("interval_label"), f"{CONFIG.screenshot_interval:.1f}s",
                         0.5, 5.0, 18, CONFIG.screenshot_interval,
                         self._on_interval, "_interval_lbl", C["amber"])
        lbl(interval_panel, t("interval_hint"),
            8, col=C["text2"]).pack(anchor="w", padx=14, pady=(0, 6))

        # Pomodoro
        self._settings_section(scroll, t("settings_pomodoro"))
        pomo_panel = card_frame(scroll)
        pomo_panel.pack(fill="x", pady=(0, 12))
        self._slider_row(pomo_panel, t("focus_dur"), f"{CONFIG.work_session_minutes}dk",
                         10, 60, 50, CONFIG.work_session_minutes,
                         lambda v: self._on_pomo_change("work_session_minutes", "_work_lbl", v, "dk"),
                         "_work_lbl", C["green"])
        self._slider_row(pomo_panel, t("short_break"), f"{CONFIG.break_minutes}dk",
                         1, 30, 29, CONFIG.break_minutes,
                         lambda v: self._on_pomo_change("break_minutes", "_break_lbl", v, "dk"),
                         "_break_lbl", C["amber"])
        self._slider_row(pomo_panel, t("long_break"), f"{CONFIG.long_break_minutes}dk",
                         5, 60, 55, CONFIG.long_break_minutes,
                         lambda v: self._on_pomo_change("long_break_minutes", "_lbreak_lbl", v, "dk"),
                         "_lbreak_lbl", C["purple"])
        self._slider_row(pomo_panel, t("long_break_after"), f"{CONFIG.long_break_after_sessions}",
                         2, 8, 6, CONFIG.long_break_after_sessions,
                         lambda v: self._on_pomo_change("long_break_after_sessions", "_lblbreak_lbl", v, ""),
                         "_lblbreak_lbl", C["cyan"])

        # Jitter controls
        self._settings_section(scroll, t("settings_jitter"))
        jitter_panel = card_frame(scroll)
        jitter_panel.pack(fill="x", pady=(0, 12))
        self._slider_row(jitter_panel, t("jitter_label"), f"{CONFIG.jitter_base_intensity}px",
                         3, 60, 57, CONFIG.jitter_base_intensity,
                         self._on_jitter, "_jitter_lbl", C["red"])
        self._slider_row(jitter_panel, t("shake_label"), f"{CONFIG.shake_intensity}px",
                         2, 30, 28, CONFIG.shake_intensity,
                         lambda v: (setattr(CONFIG, "shake_intensity", int(v)),
                                    getattr(self, "_shake_lbl").configure(text=f"{int(v)}px")),
                         "_shake_lbl", C["red_glow"])
        lbl(jitter_panel, t("jitter_warning"),
            8, col=C["amber"]).pack(anchor="w", padx=14, pady=(0, 6))

        # Focus mode toggles
        self._settings_section(scroll, t("settings_modes"))
        modes_panel = card_frame(scroll)
        modes_panel.pack(fill="x", pady=(0, 12))

        mode_items = [
            ("stealth_mode",  "👻 " + t("stealth_title"),  t("stealth_desc")),
            ("ghost_mode",    "🌫 " + t("ghost_title"),    t("ghost_desc")),
            ("strict_mode",   "⚡ " + t("strict_title"),   t("strict_desc")),
        ]
        for cfg_key, title, desc in mode_items:
            row = ctk.CTkFrame(modes_panel, fg_color="transparent")
            row.pack(fill="x", padx=14, pady=8)
            info = ctk.CTkFrame(row, fg_color="transparent")
            info.pack(side="left", fill="x", expand=True)
            lbl(info, title, 10, col=C["text"]).pack(anchor="w")
            lbl(info, desc, 8, col=C["text2"]).pack(anchor="w")
            var = tk.BooleanVar(value=getattr(CONFIG, cfg_key, False))
            ctk.CTkSwitch(
                row, text="", variable=var, width=44, height=22,
                onvalue=True, offvalue=False,
                fg_color=C["border"], progress_color=C["purple"],
                button_color=C["text"],
                command=lambda k=cfg_key, v=var: (setattr(CONFIG, k, v.get()), self._save_settings()),
            ).pack(side="right")

        # Gamification
        self._settings_section(scroll, t("settings_gamification"))
        gami_panel = card_frame(scroll)
        gami_panel.pack(fill="x", pady=(0, 12))

        gami_items = [
            ("enable_achievements", t("achievements_toggle"), t("achievements_desc")),
            ("enable_xp_system",    t("xp_toggle"),       t("xp_desc")),
            ("show_motivational_quotes", t("quotes_toggle"),        t("quotes_desc")),
        ]
        for cfg_key, title, desc in gami_items:
            row = ctk.CTkFrame(gami_panel, fg_color="transparent")
            row.pack(fill="x", padx=14, pady=8)
            info = ctk.CTkFrame(row, fg_color="transparent")
            info.pack(side="left", fill="x", expand=True)
            lbl(info, title, 10, col=C["text"]).pack(anchor="w")
            lbl(info, desc, 8, col=C["text2"]).pack(anchor="w")
            var = tk.BooleanVar(value=getattr(CONFIG, cfg_key, True))
            ctk.CTkSwitch(
                row, text="", variable=var, width=44, height=22,
                onvalue=True, offvalue=False,
                fg_color=C["border"], progress_color=C["gold"],
                button_color=C["text"],
                command=lambda k=cfg_key, v=var: (setattr(CONFIG, k, v.get()), self._save_settings()),
            ).pack(side="right")

        # Hedefler
        self._slider_row(gami_panel, t("daily_goal_label"), f"{CONFIG.daily_focus_goal_minutes}dk",
                         30, 480, 30, CONFIG.daily_focus_goal_minutes,
                         lambda v: (setattr(CONFIG, "daily_focus_goal_minutes", int(v)),
                                    getattr(self, "_dfg_lbl").configure(text=f"{int(v)}dk")),
                         "_dfg_lbl", C["gold"])
        self._slider_row(gami_panel, t("weekly_goal_label"), f"{CONFIG.weekly_focus_goal_hours}sa",
                         1, 40, 39, CONFIG.weekly_focus_goal_hours,
                         lambda v: (setattr(CONFIG, "weekly_focus_goal_hours", int(v)),
                                    getattr(self, "_wfg_lbl").configure(text=f"{int(v)}sa")),
                         "_wfg_lbl", C["gold"])

        # Interface settings
        self._settings_section(scroll, t("settings_ui"))
        ui_panel = card_frame(scroll)
        ui_panel.pack(fill="x", pady=(0, 12))

        # Language
        lang_row = ctk.CTkFrame(ui_panel, fg_color="transparent")
        lang_row.pack(fill="x", padx=14, pady=(10, 4))
        lbl(lang_row, t("lang_label"), 10, col=C["text"]).pack(side="left")
        lang_var = tk.StringVar(value=CONFIG.language)
        for code, name in [("tr", "Turkish"), ("en", "English")]:
            ctk.CTkRadioButton(
                lang_row, text=name, variable=lang_var, value=code,
                font=(FM, 14), text_color=C["text2"],
                fg_color=C["blue"], hover_color=C["blue_dim"],
                command=lambda: [
                    setattr(CONFIG, "language", lang_var.get()),
                    __import__("focusguard.i18n", fromlist=["set_locale"]).set_locale(lang_var.get()),
                    self._save_settings(),
                    self._show_toast(t("toast_lang_changed"), True),
                ],
            ).pack(side="left", padx=(10, 0))

        ui_items = [
            ("window_always_on_top", t("ontop_title"), t("ontop_desc")),
        ]
        for cfg_key, title, desc in ui_items:
            row = ctk.CTkFrame(ui_panel, fg_color="transparent")
            row.pack(fill="x", padx=14, pady=8)
            info = ctk.CTkFrame(row, fg_color="transparent")
            info.pack(side="left", fill="x", expand=True)
            lbl(info, title, 10, col=C["text"]).pack(anchor="w")
            lbl(info, desc, 8, col=C["text2"]).pack(anchor="w")
            var = tk.BooleanVar(value=getattr(CONFIG, cfg_key, False))
            ctk.CTkSwitch(
                row, text="", variable=var, width=44, height=22,
                onvalue=True, offvalue=False,
                fg_color=C["border"], progress_color=C["blue"],
                button_color=C["text"],
                command=lambda k=cfg_key, v=var: (setattr(CONFIG, k, v.get()),
                                                   self._save_settings(),
                                                   self.attributes("-topmost", v.get())),
            ).pack(side="right")

        # Autostart on login
        self._settings_section(scroll, t("settings_autostart"))
        auto_panel = card_frame(scroll)
        auto_panel.pack(fill="x", pady=(0, 12))

        # Autostart toggle
        auto_row = ctk.CTkFrame(auto_panel, fg_color="transparent")
        auto_row.pack(fill="x", padx=14, pady=(12, 4))
        auto_info = ctk.CTkFrame(auto_row, fg_color="transparent")
        auto_info.pack(side="left", fill="x", expand=True)
        lbl(auto_info, t("autostart_title"), 10, col=C["text"]).pack(anchor="w")
        lbl(auto_info, t("autostart_desc"), 8, col=C["text2"]).pack(anchor="w")

        is_auto = store.is_autostart_enabled()
        self._autostart_var = tk.BooleanVar(value=is_auto)
        ctk.CTkSwitch(
            auto_row, text="", variable=self._autostart_var, width=44, height=22,
            onvalue=True, offvalue=False,
            fg_color=C["border"], progress_color=C["cyan"],
            button_color=C["text"],
            command=self._on_autostart_toggle,
        ).pack(side="right")

        # Minimized start
        min_row = ctk.CTkFrame(auto_panel, fg_color="transparent")
        min_row.pack(fill="x", padx=14, pady=(0, 4))
        min_info = ctk.CTkFrame(min_row, fg_color="transparent")
        min_info.pack(side="left", fill="x", expand=True)
        lbl(min_info, t("autostart_min_title"), 10, col=C["text"]).pack(anchor="w")
        lbl(min_info, t("autostart_min_desc"), 8, col=C["text2"]).pack(anchor="w")
        var_min = tk.BooleanVar(value=CONFIG.autostart_minimized)
        ctk.CTkSwitch(
            min_row, text="", variable=var_min, width=44, height=22,
            onvalue=True, offvalue=False,
            fg_color=C["border"], progress_color=C["cyan"],
            button_color=C["text"],
            command=lambda: (setattr(CONFIG, "autostart_minimized", var_min.get()), self._save_settings()),
        ).pack(side="right")

        # Auto session start
        ses_row = ctk.CTkFrame(auto_panel, fg_color="transparent")
        ses_row.pack(fill="x", padx=14, pady=(0, 12))
        ses_info = ctk.CTkFrame(ses_row, fg_color="transparent")
        ses_info.pack(side="left", fill="x", expand=True)
        lbl(ses_info, t("autostart_ses_title"), 10, col=C["text"]).pack(anchor="w")
        lbl(ses_info, t("autostart_ses_desc"), 8, col=C["text2"]).pack(anchor="w")
        var_ses = tk.BooleanVar(value=CONFIG.autostart_session)
        ctk.CTkSwitch(
            ses_row, text="", variable=var_ses, width=44, height=22,
            onvalue=True, offvalue=False,
            fg_color=C["border"], progress_color=C["cyan"],
            button_color=C["text"],
            command=lambda: (setattr(CONFIG, "autostart_session", var_ses.get()), self._save_settings()),
        ).pack(side="right")

        # Allowlist
        self._settings_section(scroll, t("settings_allowlist"))
        al_panel = card_frame(scroll)
        al_panel.pack(fill="x", pady=(0, 12))
        lbl(al_panel, t("allowlist_hint"),
            8, col=C["text2"]).pack(anchor="w", padx=14, pady=(10, 4))
        self._allowlist_text = tk.Text(
            al_panel, height=5, bg=C["card_hi"], fg=C["text"],
            font=(FM, 14), relief="flat", borderwidth=0,
            highlightthickness=1, highlightbackground=C["border"],
            insertbackground=C["text"], wrap="word",
        )
        self._allowlist_text.pack(fill="x", padx=14, pady=(0, 4))
        # Load existing allowlist entries
        if CONFIG.allowlist:
            self._allowlist_text.insert("1.0", "\n".join(CONFIG.allowlist))

        ctk.CTkButton(
            al_panel, text="💾  Listeyi Kaydet", height=30, width=160,
            font=(FM, 14), fg_color=C["border"], hover_color=C["blue_dim"],
            text_color=C["text2"], corner_radius=4,
            command=self._save_allowlist,
        ).pack(anchor="w", padx=14, pady=(0, 10))

        # Idle detection settings
        self._settings_section(scroll, t("settings_idle"))
        idle_panel = card_frame(scroll)
        idle_panel.pack(fill="x", pady=(0, 12))

        idle_enable_row = ctk.CTkFrame(idle_panel, fg_color="transparent")
        idle_enable_row.pack(fill="x", padx=14, pady=(10, 4))
        idle_info = ctk.CTkFrame(idle_enable_row, fg_color="transparent")
        idle_info.pack(side="left", fill="x", expand=True)
        lbl(idle_info, t("idle_enable_title"), 10, col=C["text"]).pack(anchor="w")
        lbl(idle_info, t("idle_enable_desc"), 8, col=C["text2"]).pack(anchor="w")
        var_idle = tk.BooleanVar(value=CONFIG.idle_detection_enabled)
        ctk.CTkSwitch(
            idle_enable_row, text="", variable=var_idle, width=44, height=22,
            onvalue=True, offvalue=False,
            fg_color=C["border"], progress_color=C["cyan"], button_color=C["text"],
            command=lambda: (setattr(CONFIG, "idle_detection_enabled", var_idle.get()), self._save_settings()),
        ).pack(side="right")

        self._slider_row(idle_panel, t("idle_screen_title"), f"{CONFIG.idle_screen_seconds}s",
                         30, 600, 57, CONFIG.idle_screen_seconds,
                         lambda v: (setattr(CONFIG, "idle_screen_seconds", int(v)),
                                    getattr(self, "_idle_screen_lbl").configure(text=f"{int(v)}s")),
                         "_idle_screen_lbl", C["cyan"])
        self._slider_row(idle_panel, t("idle_mouse_title"), f"{CONFIG.idle_mouse_seconds}s",
                         30, 300, 27, CONFIG.idle_mouse_seconds,
                         lambda v: (setattr(CONFIG, "idle_mouse_seconds", int(v)),
                                    getattr(self, "_idle_mouse_lbl").configure(text=f"{int(v)}s")),
                         "_idle_mouse_lbl", C["cyan"])
        self._slider_row(idle_panel, t("idle_keyboard_title"), f"{CONFIG.idle_keyboard_seconds}s",
                         60, 600, 54, CONFIG.idle_keyboard_seconds,
                         lambda v: (setattr(CONFIG, "idle_keyboard_seconds", int(v)),
                                    getattr(self, "_idle_kbd_lbl").configure(text=f"{int(v)}s")),
                         "_idle_kbd_lbl", C["cyan"])

        action_row = ctk.CTkFrame(idle_panel, fg_color="transparent")
        action_row.pack(fill="x", padx=14, pady=(4, 10))
        lbl(action_row, t("idle_action_label"), 10, col=C["text"]).pack(side="left")
        action_var = tk.StringVar(value=CONFIG.idle_action)
        for val, txt in [("pause", t("idle_act_pause")), ("warn", t("idle_act_warn")), ("both", t("idle_act_both"))]:
            ctk.CTkRadioButton(
                action_row, text=txt, variable=action_var, value=val,
                font=(FM, 14), text_color=C["text2"],
                fg_color=C["cyan"], hover_color=C["cyan_dim"],
                command=lambda: (setattr(CONFIG, "idle_action", action_var.get()), self._save_settings()),
            ).pack(side="left", padx=(8, 0))

        # Ortam Sesi
        self._settings_section(scroll, t("settings_ambient"))
        amb_panel = card_frame(scroll)
        amb_panel.pack(fill="x", pady=(0, 12))

        amb_enable_row = ctk.CTkFrame(amb_panel, fg_color="transparent")
        amb_enable_row.pack(fill="x", padx=14, pady=(10, 4))
        amb_info = ctk.CTkFrame(amb_enable_row, fg_color="transparent")
        amb_info.pack(side="left", fill="x", expand=True)
        lbl(amb_info, t("ambient_enable_title"), 10, col=C["text"]).pack(anchor="w")
        lbl(amb_info, t("ambient_enable_desc"), 8, col=C["text2"]).pack(anchor="w")
        self._amb_var = tk.BooleanVar(value=CONFIG.ambient_enabled)
        ctk.CTkSwitch(
            amb_enable_row, text="", variable=self._amb_var, width=44, height=22,
            onvalue=True, offvalue=False,
            fg_color=C["border"], progress_color=C["blue"], button_color=C["text"],
            command=self._on_ambient_toggle,
        ).pack(side="right")

        sound_row = ctk.CTkFrame(amb_panel, fg_color="transparent")
        sound_row.pack(fill="x", padx=14, pady=(0, 4))
        lbl(sound_row, t("ambient_sound_type"), 10, col=C["text"]).pack(side="left")
        self._amb_sound_var = tk.StringVar(value=CONFIG.ambient_sound)
        sounds = [("rain", t("sound_rain")), ("cafe", t("sound_cafe")), ("white", t("sound_white")),
                  ("pink", t("sound_pink")), ("brown", t("sound_brown")), ("binaural", t("sound_binaural"))]
        for val, txt in sounds:
            ctk.CTkRadioButton(
                sound_row, text=txt, variable=self._amb_sound_var, value=val,
                font=(FM, 14), text_color=C["text2"],
                fg_color=C["blue"], hover_color=C["blue_dim"],
                command=self._on_ambient_sound_change,
            ).pack(side="left", padx=(6, 0))

        self._slider_row(amb_panel, t("vol_label"), f"{int(CONFIG.ambient_volume*100)}%",
                         0.0, 1.0, 20, CONFIG.ambient_volume,
                         self._on_ambient_volume, "_amb_vol_lbl", C["blue"])

        # Veri
        self._settings_section(scroll, t("settings_data"))
        data_panel = card_frame(scroll)
        data_panel.pack(fill="x", pady=(0, 12))
        data_row = ctk.CTkFrame(data_panel, fg_color="transparent")
        data_row.pack(fill="x", padx=14, pady=12)
        ctk.CTkButton(data_row, text=t("btn_log_csv"), height=34, width=140,
                      font=(FM, 14), fg_color=C["border"], hover_color=C["blue_dim"],
                      text_color=C["text2"], corner_radius=5,
                      command=self._export_log).pack(side="left", padx=(0, 8))
        ctk.CTkButton(data_row, text=t("btn_stats_csv"), height=34, width=140,
                      font=(FM, 14), fg_color=C["border"], hover_color=C["blue_dim"],
                      text_color=C["text2"], corner_radius=5,
                      command=self._export_stats).pack(side="left", padx=(0, 8))
        ctk.CTkButton(data_row, text=t("btn_clear_hist"), height=34, width=150,
                      font=(FM, 14), fg_color=C["border"], hover_color=C["red_dim"],
                      text_color=C["text2"], corner_radius=5,
                      command=self._clear_history).pack(side="left")

    # TAB 7: ABOUT

    def _build_about_tab(self, parent):
        inner = ctk.CTkFrame(parent, fg_color="transparent")
        inner.pack(expand=True)

        lbl(inner, "FOCUS", 36, bold=True, col=C["text"]).pack()
        lbl(inner, "GUARD", 36, bold=True, col=C["red"]).pack()
        lbl(inner, t("about_subtitle"), 12, col=C["text2"]).pack(pady=(4, 20))

        sep(inner, pad=60)

        features = t("about_features")
        for icon, title, desc in features:
            row = ctk.CTkFrame(inner, fg_color="transparent")
            row.pack(fill="x", padx=60, pady=4)
            lbl(row, icon, 14).pack(side="left", padx=(0, 10))
            lbl(row, title, 10, bold=True).pack(side="left")
            lbl(row, f" — {desc}", 9, col=C["text2"]).pack(side="left")

        sep(inner, pad=60)
        lbl(inner, t("about_tagline"), 9, col=C["text3"]).pack(pady=16)

    # Settings Helpers

    def _settings_section(self, parent, title: str):
        sep(parent, pad=0)
        lbl(parent, title, 9, bold=True, col=C["text3"]).pack(anchor="w", pady=(12, 6))

    def _slider_row(self, parent, title, init_text, lo, hi, steps, init_val,
                    command, attr_name, color):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(10, 4))
        lbl(row, title, 10, col=C["text"]).pack(side="left")
        lbl_w = lbl(row, init_text, 11, bold=True, col=color)
        lbl_w.pack(side="right")
        setattr(self, attr_name, lbl_w)
        slider = ctk.CTkSlider(
            parent, from_=lo, to=hi, number_of_steps=steps,
            fg_color=C["border"], progress_color=color,
            button_color=C["text"], button_hover_color=color, height=14,
            command=command,
        )
        slider.set(init_val)
        slider.pack(fill="x", padx=14, pady=(0, 6))

    def _on_autostart_toggle(self):
        enabled = self._autostart_var.get()
        CONFIG.autostart_enabled = enabled
        ok = store.setup_autostart(enabled, CONFIG.autostart_minimized)
        self._save_settings()
        msg = t("autostart_on") if (ok and enabled) else (t("autostart_off") if ok else t("autostart_fail"))
        self._show_toast(msg, ok)

    # Queue Poll

    def _poll(self):
        try:
            while True:
                item = self._q.get_nowait()
                kind = item[0]
                if kind == "upd":
                    self._apply_update(item[1], item[2])
                elif kind == "eng":
                    self._apply_engine(item[1], item[2])
                elif kind == "ovl":
                    self._show_overlay(item[1], item[2])
                elif kind == "txt":
                    self._text_bomber.fire(item[1], item[2])
                elif kind == "end":
                    self._show_session_summary(item[1])
                elif kind == "ach":
                    self._show_achievement_notification(item[1])
                elif kind == "lvl":
                    self._show_level_up(item[1], item[2])
                elif kind == "idle":
                    self._show_idle_warning(item[1], item[2])
        except queue.Empty:
            pass
        except Exception as e:
            logger.debug(f"poll error: {e}")
        self.after(80, self._poll)

    # Update Apply

    def _apply_update(self, stats: SessionStats, result: AnalysisResult):
        conf   = result.confidence
        thresh = CONFIG.confidence_threshold

        col = C["red"] if conf >= thresh else (C["amber"] if conf > 0.35 else C["green"])

        self._waveform.push(conf)
        self._conf_pct.configure(text=f"{conf:.1%}", text_color=col)
        self._conf_reason.configure(
            text=f"{result.reason or t('clean_label')}  [{result.backend_used} · {result.analysis_ms:.0f}ms]",
            text_color=col,
        )

        heat = stats.escalation_level
        self._card_caught.set(str(stats.total_caught),
                              C["red"] if stats.total_caught > 0 else C["green"])
        self._card_heat.set(
            str(heat),
            C["red"] if heat >= 3 else C["amber"] if heat >= 1 else C["green"],
            f"{'🔥' * min(heat, 5)}" if heat > 0 else t("cold"),
        )
        self._card_clean.set(str(stats.clean_streak), C["text2"])

        # Live productivity score (pause-corrected elapsed time)
        if self._session_start > 0:
            elapsed_min = max(0, time.time() - self._session_start - self._pause_accumulated) / 60
            if elapsed_min > 1:
                score = max(0, min(100, int(100 - (stats.total_caught / max(1, elapsed_min / 5)) * 10)))
                col_s = C["green"] if score >= 75 else C["amber"] if score >= 50 else C["red"]
                self._card_score.set(f"{score}", col_s, "%")

        # Header dot
        if stats.state == State.WORKING:
            self._status_dot.configure(text_color=C["red"] if conf >= thresh else C["green"])

        # Only append to log on new detection, not every tick
        if stats.total_caught > self._last_detection_idx:
            self._last_detection_idx = stats.total_caught
            # Clean up internal prefixes before displaying
            display_reason = result.reason or t("clean_label")
            if display_reason.startswith("cached: "):
                display_reason = display_reason[8:]  # strip "cached: " prefix
            self._append_log(conf, display_reason, result.backend_used)

    def _apply_engine(self, name: str, ready: bool):
        mapping = {"ollama": self._eng_ollama, "ocr": self._eng_ocr, "opencv": self._eng_cv}
        state   = "ready" if ready else "off"
        self._backends[name] = state
        if name in mapping:
            mapping[name].set_status(state if ready else ("loading" if name == "ocr" else "off"))

    # Log Helpers

    def _append_log(self, confidence: float, reason: str, backend: str):
        ts = datetime.now().strftime("%H:%M:%S")
        if confidence >= 0.80:
            tag, marker = "hi", "🔴"
        elif confidence >= 0.65:
            tag, marker = "md", "🟡"
        else:
            tag, marker = "lo", "🟢"

        self._log_text.configure(state="normal")
        if self._log_line_count >= MAX_LOG_LINES:
            self._log_text.delete("1.0", "2.0")
            self._log_line_count -= 1
        if self._log_line_count > 0:
            self._log_text.insert("end", "\n")
        self._log_text.insert("end", f"{ts}  ", "ts")
        self._log_text.insert("end", f"{marker} ", tag)
        self._log_text.insert("end", f"{confidence:.0%}  ", tag)
        self._log_text.insert("end", reason[:60], "rs")
        self._log_text.configure(state="disabled")
        self._log_text.see("end")
        self._log_line_count += 1
        self._log_count_lbl.configure(text=f"{self._log_line_count} {t('records')}")

    def _clear_log(self):
        self._log_text.configure(state="normal")
        self._log_text.delete("1.0", "end")
        self._log_text.configure(state="disabled")
        self._log_line_count    = 0
        self._last_detection_idx = self._session.stats.total_caught
        self._log_count_lbl.configure(text=f"0 {t('records')}")

    # Overlay

    def _show_overlay(self, message: str, level: int = 0):
        try:
            ov = ctk.CTkToplevel(self)
            ov.overrideredirect(True)
            ov.attributes("-topmost", True)
            ov.configure(fg_color="#07020E")
            sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
            ow, oh = 660, 210

            # Rastgele pozisyon (level 3+)
            if level >= 3:
                x = random.randint(50, max(50, sw - ow - 50))
                y = random.randint(50, max(50, sh - oh - 50))
            else:
                x, y = (sw - ow) // 2, (sh - oh) // 2

            ov.geometry(f"{ow}x{oh}+{x}+{y}")

            c = tk.Canvas(ov, bg="#07020E", highlightthickness=0)
            c.pack(fill="both", expand=True)
            glow_col = C["red"] if level >= 3 else C["amber"] if level >= 1 else C["green"]
            border_width = min(4, 2 + level)
            c.create_rectangle(border_width, border_width, ow-border_width, oh-border_width,
                                outline=glow_col, width=border_width)
            c.create_text(ow//2, 38, text=t("overlay_title").format(n=level+1),
                          fill=glow_col, font=(FM, 14, "bold"))
            c.create_text(ow//2, 95, text=message, fill=C["text"],
                          font=(FM, 14), width=600, justify="center")
            remaining = max(0, int(self._pomodoro_end - time.time())) if self._pomodoro_end else 0
            sub = t("overlay_remaining").format(mm=f"{remaining//60:02d}", ss=f"{remaining%60:02d}") if remaining > 0 else t("overlay_no_session")
            c.create_text(ow//2, 148, text=sub, fill=C["text3"], font=(FM, 14))

            # Wait duration based on escalation level
            show_duration = max(2000, 4000 - level * 300)
            c.create_text(ow//2, 178, text=t("overlay_closing").format(n=show_duration//1000),
                          fill=C["text3"], font=(FM, 14))

            # Sallama animasyonu
            def shake(step=0, orig_x=x, orig_y=y):
                try:
                    if not ov.winfo_exists(): return
                    if step < 8 and level >= 2:
                        dx = random.randint(-CONFIG.shake_intensity, CONFIG.shake_intensity)
                        dy = random.randint(-CONFIG.shake_intensity, CONFIG.shake_intensity)
                        ov.geometry(f"{ow}x{oh}+{orig_x+dx}+{orig_y+dy}")
                        ov.after(70, lambda: shake(step+1, orig_x, orig_y))
                    else:
                        ov.geometry(f"{ow}x{oh}+{orig_x}+{orig_y}")
                except Exception:
                    pass
            if level >= 2:
                ov.after(300, shake)

            ov.after(show_duration, lambda: ov.destroy() if ov.winfo_exists() else None)
        except Exception as e:
            logger.debug(f"Overlay hata: {e}")

    # Achievement Notification

    def _show_achievement_notification(self, achievement: dict):
        """Show achievement unlock notification in the bottom-right corner."""
        try:
            sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
            ow, oh = 320, 100
            x, y = sw - ow - 20, sh - oh - 60

            ntf = tk.Toplevel(self)
            ntf.overrideredirect(True)
            ntf.attributes("-topmost", True)
            ntf.configure(bg=C["card"])
            ntf.geometry(f"{ow}x{oh}+{x}+{y}")

            c = tk.Canvas(ntf, bg=C["card"], highlightthickness=0)
            c.pack(fill="both", expand=True)
            c.create_rectangle(2, 2, ow-2, oh-2, outline=C["gold"], width=2)
            c.create_text(20, oh//2, text=achievement.get("icon", "🏅"),
                          fill=C["gold"], font=(FM, 28), anchor="w")
            c.create_text(62, oh//2 - 12, text=t("achievement_unlocked"),
                          fill=C["gold"], font=(FM, 14, "bold"), anchor="w")
            c.create_text(62, oh//2 + 6, text=achievement.get("title", ""),
                          fill=C["text"], font=(FM, 14, "bold"), anchor="w")
            xp = achievement.get("xp", 0)
            c.create_text(62, oh//2 + 22, text=f"+{xp} XP",
                          fill=C["xp_fill"], font=(FM, 14), anchor="w")

            ntf.after(4000, lambda: ntf.destroy() if ntf.winfo_exists() else None)
            self._refresh_xp_display()
        except Exception as e:
            logger.debug(f"Achievement notification hata: {e}")

    def _show_level_up(self, old_level: int, new_level: int):
        """Show level-up celebration overlay in the center of the screen."""
        try:
            sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
            ow, oh = 400, 140
            x, y = (sw - ow) // 2, (sh - oh) // 4

            win = tk.Toplevel(self)
            win.overrideredirect(True)
            win.attributes("-topmost", True)
            win.configure(bg=C["bg"])
            win.geometry(f"{ow}x{oh}+{x}+{y}")

            c = tk.Canvas(win, bg=C["bg"], highlightthickness=0)
            c.pack(fill="both", expand=True)
            c.create_rectangle(3, 3, ow-3, oh-3, outline=C["xp_fill"], width=3)
            c.create_text(ow//2, 40, text="⭐ " + t("level_up_msg") + " ⭐",
                          fill=C["xp_fill"], font=(FM, 14, "bold"))
            c.create_text(ow//2, 80, text=t("level_label").format(n=old_level) + "  →  " + t("level_label").format(n=new_level),
                          fill=C["text"], font=(FM, 18, "bold"))
            c.create_text(ow//2, 115, text=t("keep_going"),
                          fill=C["text2"], font=(FM, 14))

            win.after(3500, lambda: win.destroy() if win.winfo_exists() else None)
        except Exception as e:
            logger.debug(f"Level up hata: {e}")

    # Session Summary

    def _on_session_end_bg(self, stats: SessionStats):
        try:
            self._q.put_nowait(("end", stats))
        except queue.Full:
            pass

    def _show_session_summary(self, stats: SessionStats):
        # Offload disk I/O to a background thread, then pop up dialog on main thread
        pause_acc = self._pause_accumulated

        def _prepare():
            raw_elapsed = int(time.time() - stats.session_start) if stats.session_start else 0
            elapsed     = max(0, raw_elapsed - int(pause_acc))
            xp          = store.calculate_session_xp(elapsed, stats.total_caught, stats.best_clean_streak)
            xp_result   = store.add_xp(xp, "Session complete")

            from focusguard.modules.intentions import INTENTIONS
            pending = INTENTIONS.get_pending()
            if pending:
                INTENTIONS.complete_intention(
                    achieved=stats.total_caught == 0,
                    session_minutes=elapsed / 60,
                    detections=stats.total_caught,
                )

            today = store.get_today()
            new_achievements = store.check_and_unlock_achievements(
                work_seconds=elapsed,
                detections=stats.total_caught,
                sessions_today=today.get("sessions", 0) + 1,
                clean_streak=stats.best_clean_streak,
                pomodoros_total=store.get_total_pomodoros(),
                idle_events_total=store.get_total_idle_events(),
                strict_mode_session=CONFIG.strict_mode,
            )
            store.record_session(
                stats.total_caught, elapsed,
                pomodoros=stats.pomodoros_completed,
                best_streak=stats.best_clean_streak,
                max_esc=stats.escalation_level,
                xp=xp,
                dwi=stats.deep_work_index,
                idle_events=stats.idle_events,
            )
            # Back to main thread for UI — also refresh stats so weekly hours update immediately
            try:
                self.after(0, lambda: self._show_summary_dialog(stats, elapsed, xp, xp_result, new_achievements))
                self.after(0, self._refresh_stats_tab)
            except Exception:
                pass

        threading.Thread(target=_prepare, daemon=True, name="session-summary").start()

    def _show_summary_dialog(self, stats, elapsed: int, xp: int, xp_result: dict, new_achievements: list):
        mm, ss = divmod(elapsed, 60)
        hh, mm = divmod(mm, 60)
        dur_str = f"{hh:02d}:{mm:02d}:{ss:02d}"

        try:
            if not self.winfo_exists():
                return
            dlg = ctk.CTkToplevel(self)
            dlg.title(t("summary_title"))
            dlg.geometry("480x380")
            dlg.resizable(False, False)
            dlg.configure(fg_color=C["surface"])
            dlg.attributes("-topmost", True)
            dlg.grab_set()

            lbl(dlg, t("summary_title"), 13, bold=True, col=C["green"]).pack(pady=(22, 4))
            sep(dlg, pad=20)

            info = [
                (t("summary_dur"),       dur_str,                       C["text"]),
                (t("summary_caught"),    str(stats.total_caught),        C["red"] if stats.total_caught > 0 else C["green"]),
                (t("summary_pomodoros"), str(stats.pomodoros_completed), C["amber"]),
                (t("summary_streak"),    str(stats.best_clean_streak),   C["cyan"]),
                (t("summary_max_level"), str(stats.escalation_level),    C["amber"] if stats.escalation_level > 0 else C["green"]),
                (t("summary_xp"),        f"+{xp} XP",                   C["xp_fill"]),
            ]
            if stats.deep_work_index > 0:
                from focusguard.modules.analytics import dwi_label
                dwi_txt, dwi_col = dwi_label(stats.deep_work_index)
                info.append((t("stat_dwi"), f"{stats.deep_work_index} — {dwi_txt}", dwi_col))
            for title, val, col_v in info:
                row = ctk.CTkFrame(dlg, fg_color="transparent")
                row.pack(fill="x", padx=32, pady=4)
                lbl(row, title, 10, col=C["text2"]).pack(side="left")
                lbl(row, val, 11, bold=True, col=col_v).pack(side="right")

            if xp_result.get("leveled_up"):
                new_lvl = xp_result["new_level"]
                lbl(dlg, "⭐ " + t("level_up_msg") + " → " + t("level_label").format(n=new_lvl),
                    11, bold=True, col=C["xp_fill"]).pack(pady=6)

            if new_achievements:
                ach_row = ctk.CTkFrame(dlg, fg_color="transparent")
                ach_row.pack()
                icons = " ".join(a.get("icon", "") for a in new_achievements[:4])
                lbl(ach_row, t("achievement_unlocked") + f" {icons}", 10, col=C["gold"]).pack()

            ctk.CTkButton(
                dlg, text=t("btn_continue"), width=160, height=40,
                font=(FM, 14, "bold"), fg_color=C["green_dim"], hover_color=C["green"],
                text_color=C["bg"], corner_radius=8,
                command=lambda: (dlg.destroy(), self._refresh_xp_display()),
            ).pack(pady=(14, 18))

        except Exception as e:
            logger.debug(f"Summary dialog error: {e}")

    # Toast

    def _show_toast(self, message: str, success: bool = True):
        try:
            sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
            ow, oh = 280, 50
            x, y = sw - ow - 20, sh - oh - 100
            toast_win = tk.Toplevel(self)
            toast_win.overrideredirect(True)
            toast_win.attributes("-topmost", True)
            toast_win.configure(bg=C["card"])
            toast_win.geometry(f"{ow}x{oh}+{x}+{y}")
            col = C["green"] if success else C["red"]
            c = tk.Canvas(toast_win, bg=C["card"], highlightthickness=0)
            c.pack(fill="both", expand=True)
            c.create_rectangle(2, 2, ow-2, oh-2, outline=col, width=1)
            c.create_text(ow//2, oh//2, text=message, fill=C["text"], font=(FM, 14))
            toast_win.after(2500, lambda: toast_win.destroy() if toast_win.winfo_exists() else None)
        except Exception:
            pass

    # Clock / Pomodoro

    def _tick_second(self):
        state = self._session.state

        # ── Header clock (counts UP, pause-corrected) ─────────────────────────
        if state == State.WORKING and self._session_start > 0:
            elapsed = max(0, int(time.time() - self._session_start - self._pause_accumulated))
            td = str(timedelta(seconds=elapsed))
            self._timer_lbl.configure(text=td, text_color=C["green"])
            self._card_session.set(td, C["green"])
            # Auto-break when pomodoro expires
            if self._pomodoro_end > 0 and time.time() >= self._pomodoro_end:
                self._auto_break()

        # ── Pomodoro ring (counts DOWN) ────────────────────────────────────────
        if self._pomodoro_end > 0:
            if state == State.WORKING:
                # Live countdown during active focus
                remaining     = max(0.0, self._pomodoro_end - time.time())
                mode_duration = CONFIG.work_session_minutes * 60
                progress      = remaining / mode_duration if mode_duration > 0 else 0.0
                mm, ss = divmod(int(remaining), 60)
                self._pomo_ring.update_ring(progress, f"{mm:02d}:{ss:02d}", "focus", self._session_count)

            elif state == State.PAUSED:
                # Frozen — use the snapshot taken at pause time
                remaining     = max(0.0, self._frozen_ring_remaining)
                mode_duration = CONFIG.work_session_minutes * 60
                progress      = remaining / mode_duration if mode_duration > 0 else 0.0
                mm, ss = divmod(int(remaining), 60)
                self._pomo_ring.update_ring(progress, f"{mm:02d}:{ss:02d}", self._pomodoro_mode, self._session_count)

            elif state == State.BREAK:
                # Break countdown — pomodoro_end is break deadline here
                remaining     = max(0.0, self._pomodoro_end - time.time())
                mode_duration = (
                    CONFIG.long_break_minutes if self._pomodoro_mode == "long_break"
                    else CONFIG.break_minutes
                ) * 60
                progress = remaining / mode_duration if mode_duration > 0 else 0.0
                mm, ss   = divmod(int(remaining), 60)
                self._pomo_ring.update_ring(progress, f"{mm:02d}:{ss:02d}", self._pomodoro_mode, self._session_count)
                # When break expires, resume focus without resetting the overall session clock
                if remaining == 0 and self._pomodoro_end > 0:
                    self._pomodoro_end = 0  # clear so this branch doesn't repeat
                    # Resume into next focus interval - keep _session_start intact
                    self._pomodoro_end  = time.time() + CONFIG.work_session_minutes * 60
                    self._pomodoro_mode = "focus"
                    self._last_break_time = 0.0
                    self._session.start()   # resumes from BREAK state safely
                    self._update_state_ui(State.WORKING)

        # Today footer
        t_data = store.get_today()
        fm = t_data["work_seconds"] // 60
        daily_goal = CONFIG.daily_focus_goal_minutes
        self._today_lbl.configure(
            text=t("today_footer").format(det=t_data["detections"], min=fm, goal=daily_goal, ses=t_data["sessions"])
        )
        if hasattr(self, "_pomo_today"):
            self._pomo_today.configure(text=t("today_summary").format(det=t_data["detections"], min=fm))

        # Goal indicator
        if hasattr(self, "_goal_lbl") and daily_goal > 0:
            pct = min(100, int(fm / daily_goal * 100))
            col = C["green"] if pct >= 100 else C["blue"]
            self._goal_lbl.configure(text=t("daily_goal_pct").format(pct=pct, cur=fm, goal=daily_goal), text_color=col)

        # Mode badges
        badges = []
        if CONFIG.stealth_mode: badges.append(t("btn_ghost"))
        if CONFIG.ghost_mode:   badges.append(t("ghost_title"))
        if CONFIG.strict_mode:  badges.append("⚡ STRICT")
        self._mode_badge.configure(text="  ".join(badges))

        self.after(1000, self._tick_second)

    def _auto_break(self):
        """Pomodoro interval ended — switch to break without resetting the session clock."""
        self._session_count += 1
        if self._session_count % CONFIG.long_break_after_sessions == 0:
            self._pomodoro_mode = "long_break"
            duration = CONFIG.long_break_minutes * 60
        else:
            self._pomodoro_mode = "break"
            duration = CONFIG.break_minutes * 60
        self._pomodoro_end = time.time() + duration
        self._last_break_time = time.time()
        self._session.take_break()
        self._update_state_ui(State.BREAK)
        sugg = self._session.get_break_suggestion()
        if hasattr(self, "_break_sugg_lbl"):
            self._break_sugg_lbl.configure(text=sugg)
        break_min = CONFIG.long_break_minutes if self._pomodoro_mode == "long_break" else CONFIG.break_minutes
        self._show_toast(t("pomo_complete").format(min=break_min), True)

    # Motivation Cycle

    def _start_motivation_cycle(self):
        """Periodically show motivational messages."""
        def _cycle():
            while True:
                time.sleep(random.uniform(120, 240))  # random 2-4 minute interval
                if self._session.state == State.WORKING and CONFIG.show_motivational_quotes:
                    msg = MOTIVATION_MESSAGES[self._motivation_idx % len(MOTIVATION_MESSAGES)]
                    self._motivation_idx += 1
                    try:
                        if not self.winfo_exists():
                            return
                        self.after(0, lambda m=msg: self._motivation_lbl.configure(text=m)
                                   if self.winfo_exists() else None)
                        self.after(10000, lambda: self._motivation_lbl.configure(text="")
                                   if self.winfo_exists() else None)
                    except Exception:
                        return  # window destroyed — exit thread cleanly

        threading.Thread(target=_cycle, daemon=True, name="motivation").start()

    # Button Actions

    def _toggle_session(self):
        state = self._session.state
        if state in (State.IDLE, State.BREAK):
            if CONFIG.intentions_enabled and state == State.IDLE:
                self._show_intention_dialog(on_confirm=self._start_session_now)
            else:
                self._start_session_now()
        elif state == State.WORKING:
            # Snapshot ring countdown before handing off to background thread
            self._pause_start = time.time()
            if self._pomodoro_end > 0:
                self._frozen_ring_remaining = max(0.0, self._pomodoro_end - time.time())
            # Update UI immediately so the button responds at once
            self._update_state_ui(State.PAUSED)
            # Run session.pause() off the main thread — it calls window_tracker.stop()
            # which does thread.join(2s) and would freeze the UI if called here directly.
            threading.Thread(
                target=self._session.pause, daemon=True, name="fg-pause"
            ).start()
        elif state == State.PAUSED:
            if self._pause_start > 0:
                paused_secs = time.time() - self._pause_start
                self._pause_accumulated += paused_secs
                if self._pomodoro_end > 0:
                    self._pomodoro_end += paused_secs
                self._pause_start = 0.0
            # Update UI immediately
            self._update_state_ui(State.WORKING)
            # session.resume() is fast but keep symmetry and avoid any future regressions
            threading.Thread(
                target=self._session.resume, daemon=True, name="fg-resume"
            ).start()

    def _start_session_now(self, intention_text: str = ""):
        from focusguard.modules.intentions import INTENTIONS
        if intention_text.strip():
            INTENTIONS.set_intention(intention_text)
        self._session_start           = time.time()
        self._pause_start             = 0.0
        self._pause_accumulated       = 0.0
        self._frozen_ring_remaining   = 0.0
        self._last_break_time         = 0.0
        self._pomodoro_end  = time.time() + CONFIG.work_session_minutes * 60
        self._pomodoro_mode = "focus"
        self._last_detection_idx = self._session.stats.total_caught
        self._session.start()
        self._update_state_ui(State.WORKING)
        if hasattr(self, "_break_sugg_lbl"):
            self._break_sugg_lbl.configure(text="")
        if CONFIG.ambient_enabled:
            self._ambient_play()

    def _show_intention_dialog(self, on_confirm):
        """Pre-session intention dialog."""
        try:
            from focusguard.modules.intentions import INTENTIONS, INTENTION_TEMPLATES
            dlg = ctk.CTkToplevel(self)
            dlg.title(t("intention_dialog_title"))
            dlg.geometry("480x340")
            dlg.resizable(False, False)
            dlg.configure(fg_color=C["surface"])
            dlg.attributes("-topmost", True)
            dlg.grab_set()

            lbl(dlg, "🎯 " + t("intention_set_title"), 13, bold=True, col=C["cyan"]).pack(pady=(18, 4))
            lbl(dlg, t("intention_set_desc"), 9, col=C["text2"]).pack()

            sep(dlg, pad=20)

            entry = ctk.CTkEntry(
                dlg, placeholder_text=t("intention_placeholder"),
                font=(FM, 13), fg_color=C["card"], border_color=C["border"],
                text_color=C["text"], height=38,
            )
            entry.pack(fill="x", padx=24, pady=(10, 6))

            # Quick templates
            tmpl_row = ctk.CTkFrame(dlg, fg_color="transparent")
            tmpl_row.pack(fill="x", padx=24, pady=(0, 8))
            lbl(tmpl_row, t("intention_quick"), 8, col=C["text3"]).pack(side="left", padx=(0, 6))
            import random as _rnd
            samples = _rnd.sample(INTENTION_TEMPLATES.get("general", []), min(3, 3))
            for s in samples:
                short = s[:28] + "…" if len(s) > 28 else s
                ctk.CTkButton(
                    tmpl_row, text=short, font=(FM, 13), height=22,
                    fg_color=C["border"], hover_color=C["blue_dim"],
                    text_color=C["text2"], corner_radius=4,
                    command=lambda t=s: entry.delete(0, "end") or entry.insert(0, t),
                ).pack(side="left", padx=(0, 4))

            btn_row = ctk.CTkFrame(dlg, fg_color="transparent")
            btn_row.pack(pady=(6, 0))

            def _confirm():
                text = entry.get().strip()
                dlg.destroy()
                on_confirm(text)

            def _skip():
                dlg.destroy()
                on_confirm("")

            ctk.CTkButton(
                btn_row, text=t("btn_focus"), font=(FM, 14, "bold"), width=140, height=36,
                fg_color=C["green_dim"], hover_color=C["green"],
                text_color=C["bg"], corner_radius=6, command=_confirm,
            ).pack(side="left", padx=(0, 8))
            ctk.CTkButton(
                btn_row, text=t("btn_skip"), font=(FM, 13), width=80, height=36,
                fg_color=C["card"], hover_color=C["border"],
                text_color=C["text2"], corner_radius=6, command=_skip,
            ).pack(side="left")

            entry.focus()
            entry.bind("<Return>", lambda _: _confirm())
            entry.bind("<Escape>", lambda _: _skip())

        except Exception as e:
            logger.debug(f"Intention dialog error: {e}")
            on_confirm("")

    def _do_break(self):
        if self._session.state not in (State.WORKING, State.PAUSED):
            return
        # Rate-limit: require at least 5 minutes of work since session start or last break
        _MIN_WORK_SECS = 5 * 60
        reference = max(self._session_start, self._last_break_time) if self._last_break_time > 0 else self._session_start
        if reference > 0:
            work_so_far = (time.time() - reference) - self._pause_accumulated
            if work_so_far < _MIN_WORK_SECS:
                need = int(_MIN_WORK_SECS - work_so_far)
                m, s = divmod(need, 60)
                self._show_toast(t("break_too_soon").format(min=m, sec=f"{s:02d}"), False)
                return
        self._last_break_time = time.time()
        self._pomodoro_mode = "break"
        self._pomodoro_end  = time.time() + CONFIG.break_minutes * 60
        self._session.take_break()
        self._update_state_ui(State.BREAK)
        # Show a contextual break suggestion
        sugg = self._session.get_break_suggestion()
        if hasattr(self, "_break_sugg_lbl"):
            self._break_sugg_lbl.configure(text=sugg)

    def _do_long_break(self):
        if self._session.state not in (State.WORKING, State.PAUSED):
            return
        # Long break is only earned after completing the required number of pomodoros
        required = CONFIG.long_break_after_sessions
        completed = self._session.stats.pomodoros_completed
        if completed < required:
            remaining = required - completed
            self._show_toast(
                t("long_break_not_yet").format(n=remaining, total=required),
                False
            )
            return
        self._pomodoro_mode = "long_break"
        self._pomodoro_end  = time.time() + CONFIG.long_break_minutes * 60
        self._session.take_break(long_break=True)
        self._update_state_ui(State.BREAK)
        sugg = self._session.get_break_suggestion()
        if hasattr(self, "_break_sugg_lbl"):
            self._break_sugg_lbl.configure(text=sugg)

    def _do_stop(self):
        self._text_bomber.destroy_all()
        self._session.stop()
        self._ambient_stop()
        self._pomodoro_end            = 0
        self._session_start           = 0
        self._pause_start             = 0.0
        self._pause_accumulated       = 0.0
        self._frozen_ring_remaining   = 0.0
        self._last_break_time         = 0.0
        self._session_count  = 1
        self._update_state_ui(State.IDLE)
        self._timer_lbl.configure(text="00:00:00", text_color=C["text3"])
        self._card_session.set("—", C["text3"])
        self._pomo_ring.update_ring(1.0, f"{CONFIG.work_session_minutes:02d}:00", "focus", 1)
        if hasattr(self, "_break_sugg_lbl"):
            self._break_sugg_lbl.configure(text="")

    def _toggle_stealth(self):
        CONFIG.stealth_mode = not CONFIG.stealth_mode
        if CONFIG.stealth_mode:
            self._btn_stealth.configure(fg_color=C["purple_dim"], text_color=C["purple"])
            self._show_toast(t("toast_ghost_on"), True)
        else:
            self._btn_stealth.configure(fg_color=C["card"], text_color=C["text3"])
            self._show_toast(t("toast_ghost_off"), True)
        self._save_settings()

    def _update_state_ui(self, state: State):
        cfg_map = {
            State.WORKING: (t("btn_pause"),  C["red_dim"],   C["red"],   "text",  t("state_working"), C["green"]),
            State.PAUSED:  (t("btn_resume"),  C["blue_dim"],  C["blue"],  "text",  t("state_paused"), C["amber"]),
            State.BREAK:   (t("btn_focus"),   C["green_dim"], C["green"], "bg",    t("state_break"),  C["amber"]),
            State.IDLE:    (t("btn_focus"),   C["green_dim"], C["green"], "bg",    t("state_idle"),   C["text3"]),
        }
        btn_txt, fg, hov, tc_key, status_txt, dot_col = cfg_map[state]
        tc = C[tc_key]
        self._btn_main.configure(text=btn_txt, fg_color=fg, hover_color=hov, text_color=tc)
        self._status_label.configure(text=status_txt, text_color=dot_col)
        self._status_dot.configure(text_color=dot_col)
        if hasattr(self, "_pomo_btn"):
            self._pomo_btn.configure(text=btn_txt, fg_color=fg, hover_color=hov, text_color=tc)

    # Settings Callbacks

    def _on_ambient_toggle(self):
        enabled = self._amb_var.get()
        CONFIG.ambient_enabled = enabled
        self._save_settings()
        if enabled:
            self._ambient_play()
        else:
            self._ambient_stop()

    def _on_ambient_sound_change(self):
        CONFIG.ambient_sound = self._amb_sound_var.get()
        self._save_settings()
        if CONFIG.ambient_enabled:
            self._ambient_stop()
            self._ambient_play()

    def _on_ambient_volume(self, v: float):
        CONFIG.ambient_volume = round(float(v), 2)
        if hasattr(self, "_amb_vol_lbl"):
            self._amb_vol_lbl.configure(text=f"{int(v*100)}%")
        if hasattr(self, "_ambient_player") and self._ambient_player:
            try:
                self._ambient_player.set_volume(CONFIG.ambient_volume)
            except Exception:
                pass

    def _ambient_play(self):
        try:
            from focusguard.modules.ambient import AmbientPlayer
            if not hasattr(self, "_ambient_player") or self._ambient_player is None:
                self._ambient_player = AmbientPlayer()
            self._ambient_player.play(CONFIG.ambient_sound, CONFIG.ambient_volume)
        except Exception as e:
            logger.debug(f"Ambient play error: {e}")
            self._show_toast(t("toast_ambient_missing"), False)

    def _ambient_stop(self):
        if hasattr(self, "_ambient_player") and self._ambient_player:
            try:
                self._ambient_player.stop()
            except Exception:
                pass

    def _on_threshold(self, v: float):
        CONFIG.confidence_threshold = round(float(v), 2)
        self._thresh_lbl.configure(text=f"{int(v*100)}%")

    def _on_interval(self, v: float):
        CONFIG.screenshot_interval = round(float(v), 1)
        label_text = f"{v:.1f}s"
        # Update both the engines tab label and the settings tab label
        if hasattr(self, "_eng_interval_lbl"):
            self._eng_interval_lbl.configure(text=label_text)
        if hasattr(self, "_interval_lbl"):
            self._interval_lbl.configure(text=label_text)

    def _on_jitter(self, v: float):
        CONFIG.jitter_base_intensity = int(v)
        self._jitter_lbl.configure(text=f"{int(v)}px")

    def _on_pomo_change(self, attr: str, label_attr: str, v: float, unit: str):
        setattr(CONFIG, attr, int(v))
        if hasattr(self, label_attr):
            getattr(self, label_attr).configure(text=f"{int(v)}{unit}")

    def _save_settings(self):
        store.save_settings(CONFIG)

    def _save_allowlist(self):
        raw   = self._allowlist_text.get("1.0", "end").strip()
        items = [line.strip() for line in raw.splitlines() if line.strip()]
        CONFIG.allowlist = items
        self._session.set_allowlist(items)
        store.save_settings(CONFIG)
        self._show_toast(t("list_saved").format(n=len(items)), True)

    def _export_log(self):
        from tkinter import filedialog
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv"), (t("all_files"), "*.*")],
            title=t("save_log_title"),
        )
        if path:
            ok = store.export_log(path, self._session.detections)
            self._show_toast(t("toast_export_ok") + f": {path[-40:]}" if ok else t("toast_export_fail"), ok)

    def _export_stats(self):
        from tkinter import filedialog
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
            title=t("stats_save_title"),
        )
        if path:
            ok = store.export_stats_csv(path)
            self._show_toast(t("toast_export_ok") if ok else t("toast_export_fail"), ok)

    def _clear_history(self):
        import os
        if os.path.exists(store.STATS_PATH):
            os.remove(store.STATS_PATH)
        self._refresh_stats_tab()
        self._show_toast(t("hist_cleared"), True)

    def _refresh_xp_display(self):
        try:
            xp_info = store.get_xp_info()
            self._header_xp.update(xp_info)
        except Exception:
            pass

    # Close

    def _show_idle_warning(self, signal, idle_secs: float):
        """Idle warning popup — also syncs button state and pause timer.

        The session is paused by the idle detector on a background thread. The
        GUI is never notified through the normal _toggle_session path, so the
        button label and pause-time accounting must be updated here instead.
        """
        from focusguard.modules.idle_detector import IdleSignal

        # Sync button to PAUSED if the session was actually paused.
        # Check the real session state rather than assuming idle always pauses,
        # because CONFIG.idle_action may be "warn" (no pause).
        if self._session.state == State.PAUSED:
            # Start tracking paused time from now so the session clock stays accurate.
            if self._pause_start <= 0:
                self._pause_start = time.time()
            if self._pomodoro_end > 0 and self._frozen_ring_remaining <= 0:
                self._frozen_ring_remaining = max(0.0, self._pomodoro_end - time.time())
            self._update_state_ui(State.PAUSED)

        labels = {
            IdleSignal.SCREEN_FREEZE: "📺 " + t("idle_screen"),
            IdleSignal.MOUSE_IDLE:    "🖱 " + t("idle_mouse"),
            IdleSignal.KEYBOARD_IDLE: "⌨️ " + t("idle_keyboard"),
        }
        label = labels.get(signal, "😴 " + t("idle_subtext").split('.')[0])
        mins  = int(idle_secs // 60)
        secs  = int(idle_secs % 60)
        time_str = f"{mins}m {secs}s" if mins else f"{secs}s"
        idle_sub = t("idle_popup_sub")
        self._show_toast(f"{label} — {time_str}. {idle_sub}", False)

    def _toggle_ghost(self):
        CONFIG.ghost_mode = not CONFIG.ghost_mode
        if CONFIG.ghost_mode:
            self._show_toast(t("ghost_title") + " " + t("idle_active").lower(), True)
        else:
            self._show_toast(t("toast_ghost_off"), True)
        self._save_settings()

    def on_close(self):
        store.save_settings(CONFIG)
        self._text_bomber.destroy_all()
        try:
            self._session.stop()
        except Exception:
            pass
        self.destroy()
        self.quit()
