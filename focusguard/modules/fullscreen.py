"""
Fullscreen detection — cross-platform.

Games, streaming apps, and video players almost always go fullscreen.
Productive apps (editors, terminals, browsers) almost never do.

By checking whether the foreground window covers the entire display we can
catch unknown games and locally-played videos without maintaining a name list.
A few productive apps that legitimately go fullscreen (Zoom, Keynote, VS Code
presentation mode, PDF readers) are explicitly excluded.
"""

from __future__ import annotations

import logging
import platform
import subprocess
from typing import Tuple

logger = logging.getLogger("focusguard.fullscreen")

_SYS = platform.system()

# Apps allowed to be fullscreen without triggering a distraction alert.
# All matched case-insensitively against the process/window hint string.
_PRODUCTIVE_FS = {
    "code", "vscode", "idea", "pycharm", "webstorm", "clion",
    "android studio", "xcode", "eclipse", "vim", "nvim", "neovim",
    "terminal", "iterm2", "alacritty", "kitty", "konsole", "wezterm",
    "word", "excel", "powerpoint", "libreoffice", "keynote", "pages",
    "figma", "sketch", "blender",
    "zoom", "teams", "meet",
    # pdf / readers — people study fullscreen
    "foxit", "acrobat", "sumatrapdf", "okular", "evince", "calibre",
    "kindle",
    "focusguard", "python",
}


def is_productive_fullscreen(hint: str) -> bool:
    h = hint.lower()
    return any(k in h for k in _PRODUCTIVE_FS)


def is_fullscreen() -> Tuple[bool, str]:
    """Return (fullscreen, app_hint). app_hint is lowercase for matching."""
    try:
        if _SYS == "Windows":
            return _windows()
        elif _SYS == "Darwin":
            return _macos()
        else:
            return _linux()
    except Exception as e:
        logger.debug(f"fullscreen check failed: {e}")
        return False, ""


def _windows() -> Tuple[bool, str]:
    import ctypes
    import ctypes.wintypes as wt

    u32  = ctypes.windll.user32
    hwnd = u32.GetForegroundWindow()
    if not hwnd:
        return False, ""

    rect = wt.RECT()
    u32.GetWindowRect(hwnd, ctypes.byref(rect))

    MONITOR_DEFAULTTONEAREST = 2
    hmon = u32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)

    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_ulong), ("rcMonitor", wt.RECT),
                    ("rcWork", wt.RECT), ("dwFlags", ctypes.c_ulong)]

    mi = MONITORINFO()
    mi.cbSize = ctypes.sizeof(MONITORINFO)
    u32.GetMonitorInfoW(hmon, ctypes.byref(mi))
    m = mi.rcMonitor

    tol = 2
    if not (rect.left <= m.left + tol and rect.top <= m.top + tol
            and rect.right >= m.right - tol and rect.bottom >= m.bottom - tol):
        return False, ""

    # Get window title + process name for the hint
    ln  = u32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(ln + 1)
    u32.GetWindowTextW(hwnd, buf, ln + 1)
    title = buf.value.strip()

    pid = ctypes.c_ulong()
    u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    try:
        import psutil
        hint = psutil.Process(pid.value).name().replace(".exe", "").lower()
    except Exception:
        hint = title[:40].lower()

    return True, hint


def _macos() -> Tuple[bool, str]:
    # Try Quartz first
    try:
        import Quartz  # type: ignore
        disp_w = Quartz.CGDisplayPixelsWide(Quartz.CGMainDisplayID())
        disp_h = Quartz.CGDisplayPixelsHigh(Quartz.CGMainDisplayID())
        wins   = Quartz.CGWindowListCopyWindowInfo(
            Quartz.kCGWindowListOptionOnScreenOnly |
            Quartz.kCGWindowListExcludeDesktopElements,
            Quartz.kCGNullWindowID,
        )
        for w in wins:
            if w.get("kCGWindowLayer", 999) != 0:
                continue
            b = w.get("kCGWindowBounds", {})
            if b.get("Width", 0) >= disp_w - 2 and b.get("Height", 0) >= disp_h - 2:
                return True, w.get("kCGWindowOwnerName", "").lower()
        return False, ""
    except ImportError:
        pass

    # AppleScript fallback
    try:
        r = subprocess.run(
            ["osascript", "-e",
             'tell application "System Events" to tell (first process whose frontmost '
             'is true) to get value of attribute "AXFullScreen" of first window'],
            capture_output=True, text=True, timeout=1.0,
        )
        if r.returncode == 0 and "true" in r.stdout.lower():
            r2 = subprocess.run(
                ["osascript", "-e",
                 'tell application "System Events" to get name of '
                 'first process whose frontmost is true'],
                capture_output=True, text=True, timeout=0.5,
            )
            return True, r2.stdout.strip().lower()
    except Exception:
        pass

    return False, ""


def _linux() -> Tuple[bool, str]:
    import re as _re

    # Method 1: _NET_WM_STATE_FULLSCREEN via xprop (most reliable on X11)
    try:
        wid = subprocess.run(
            ["xdotool", "getactivewindow"],
            capture_output=True, text=True, timeout=0.5,
        ).stdout.strip()

        if wid:
            state = subprocess.run(
                ["xprop", "-id", wid, "_NET_WM_STATE"],
                capture_output=True, text=True, timeout=0.5,
            )
            if state.returncode == 0:
                if "_NET_WM_STATE_FULLSCREEN" not in state.stdout:
                    return False, ""
                name = subprocess.run(
                    ["xdotool", "getactivewindow", "getwindowname"],
                    capture_output=True, text=True, timeout=0.5,
                )
                return True, name.stdout.strip().lower()
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.debug(f"linux fullscreen xprop: {e}")

    # Method 2: geometry vs display size (Wayland / no xprop)
    try:
        res = subprocess.run(["xrandr", "--current"], capture_output=True, text=True, timeout=1.0)
        m   = _re.search(r"current (\d+) x (\d+)", res.stdout)
        if not m:
            return False, ""
        dw, dh = int(m.group(1)), int(m.group(2))

        wid = subprocess.run(["xdotool", "getactivewindow"],
                             capture_output=True, text=True, timeout=0.5).stdout.strip()
        if not wid:
            return False, ""

        geo = subprocess.run(["xdotool", "getwindowgeometry", wid],
                             capture_output=True, text=True, timeout=0.5)
        mg  = _re.search(r"Geometry: (\d+)x(\d+)", geo.stdout)
        if mg and int(mg.group(1)) >= dw - 4 and int(mg.group(2)) >= dh - 4:
            title = subprocess.run(
                ["xdotool", "getactivewindow", "getwindowname"],
                capture_output=True, text=True, timeout=0.5,
            )
            return True, title.stdout.strip().lower()
    except Exception as e:
        logger.debug(f"linux fullscreen fallback: {e}")

    return False, ""
