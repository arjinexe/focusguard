"""
FocusGuard — Active Window Tracker  (focusguard/modules/window_tracker.py)

Tracks which application / window title is active, how long, and what
distraction detections happened while it was in focus.

Cross-platform:
  Windows   — ctypes.windll.user32
  macOS     — AppKit via pyobjc (optional) or subprocess/osascript
  Linux     — xdotool / xprop (subprocess, no extra pip needed)

No heavy dependencies required. Gracefully degrades on unsupported platforms.

Usage:
    tracker = WindowTracker(on_switch=my_callback)
    tracker.start()
    tracker.record_detection("twitter.com")   # call when distraction fires
    stats = tracker.get_stats()               # {app: {seconds, detections, ...}}
    tracker.stop()
"""

from __future__ import annotations

import logging
import platform
import re
import subprocess
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

logger = logging.getLogger("focusguard.window_tracker")

_SYSTEM = platform.system()  # "Windows" | "Darwin" | "Linux"


# Window info

@dataclass
class WindowInfo:
    app_name:    str    # e.g. "Google Chrome", "Visual Studio Code"
    title:       str    # full window title
    timestamp:   float = field(default_factory=time.monotonic)

    def is_productive(self) -> bool:
        """Heuristic: is this window likely productive work?"""
        low = (self.app_name + " " + self.title).lower()
        productive_keywords = [
            "code", "vscode", "pycharm", "intellij", "vim", "neovim", "emacs",
            "terminal", "iterm", "konsole", "alacritty", "wezterm",
            "word", "excel", "powerpoint", "sheets", "docs", "notion",
            "figma", "sketch", "affinity", "illustrator", "photoshop",
            "xcode", "android studio", "eclipse", "netbeans",
            "slack", "teams", "zoom", "meet", "outlook", "thunderbird",
            "github", "gitlab", "jira", "linear", "asana", "trello",
            "focusguard",
        ]
        return any(k in low for k in productive_keywords)


# Platform-specific getters

def _get_window_windows() -> Optional[WindowInfo]:
    try:
        import ctypes
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value.strip()

        # Get process name via GetWindowThreadProcessId + OpenProcess
        pid = ctypes.c_ulong()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        try:
            import psutil
            proc = psutil.Process(pid.value)
            app  = proc.name().replace(".exe", "")
        except Exception:
            app = title.split(" - ")[-1] if " - " in title else title[:30]

        return WindowInfo(app_name=app, title=title)
    except Exception as e:
        logger.debug(f"window_windows error: {e}")
        return None


def _get_window_macos() -> Optional[WindowInfo]:
    try:
        # Try pyobjc first (fastest, no subprocess)
        from AppKit import NSWorkspace  # type: ignore
        ws    = NSWorkspace.sharedWorkspace()
        app   = ws.activeApplication()
        name  = app.get("NSApplicationName", "") if app else ""
        # Get window title via osascript
        script = f'tell application "{name}" to get name of front window'
        r = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=0.5
        )
        title = r.stdout.strip() if r.returncode == 0 else name
        return WindowInfo(app_name=name, title=title)
    except ImportError:
        pass
    except Exception:
        pass

    # Fallback: osascript only
    try:
        script = (
            'tell application "System Events" to get name of '
            'first process whose frontmost is true'
        )
        r = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=0.5
        )
        if r.returncode == 0:
            app = r.stdout.strip()
            return WindowInfo(app_name=app, title=app)
    except Exception as e:
        logger.debug(f"window_macos error: {e}")
    return None


def _get_window_linux() -> Optional[WindowInfo]:
    try:
        # xdotool is most reliable
        r = subprocess.run(
            ["xdotool", "getactivewindow", "getwindowname"],
            capture_output=True, text=True, timeout=0.5,
        )
        if r.returncode == 0:
            title = r.stdout.strip()
            # Extract app from title (usually "Title — AppName" or "Title - AppName")
            parts = re.split(r" [—\-] | – ", title)
            app = parts[-1].strip() if len(parts) > 1 else title[:30]
            return WindowInfo(app_name=app, title=title)
    except FileNotFoundError:
        pass  # xdotool not installed
    except Exception:
        pass

    # Fallback: xprop
    try:
        r = subprocess.run(
            ["xprop", "-id",
             subprocess.run(["xdotool", "getactivewindow"],
                            capture_output=True, text=True).stdout.strip(),
             "WM_NAME"],
            capture_output=True, text=True, timeout=0.5,
        )
        if r.returncode == 0:
            m = re.search(r'"(.+)"', r.stdout)
            if m:
                title = m.group(1)
                return WindowInfo(app_name=title[:30], title=title)
    except Exception as e:
        logger.debug(f"window_linux xprop error: {e}")
    return None


def get_active_window() -> Optional[WindowInfo]:
    if _SYSTEM == "Windows":
        return _get_window_windows()
    elif _SYSTEM == "Darwin":
        return _get_window_macos()
    else:
        return _get_window_linux()


# App Usage Stats

@dataclass
class AppStats:
    app_name:   str
    seconds:    float = 0.0
    detections: int   = 0
    switches:   int   = 0    # how many times we switched TO this app

    @property
    def distraction_rate(self) -> float:
        """detections per focus minute"""
        mins = self.seconds / 60.0
        return round(self.detections / max(1.0, mins), 2)

    @property
    def is_distraction_app(self) -> bool:
        return self.distraction_rate > 1.0   # >1 detection/min = problem app

    def to_dict(self) -> dict:
        return {
            "app":              self.app_name,
            "seconds":          round(self.seconds, 1),
            "minutes":          round(self.seconds / 60, 1),
            "detections":       self.detections,
            "switches":         self.switches,
            "distraction_rate": self.distraction_rate,
        }


# Window Tracker

class WindowTracker:
    """
    Polls the active window every poll_interval seconds.
    Thread-safe. Can be started/stopped with the focus session.
    """

    def __init__(
        self,
        poll_interval: float = 2.0,
        on_switch: Optional[Callable[[WindowInfo], None]] = None,
    ):
        self._poll = poll_interval
        self._on_switch = on_switch
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None

        self._current:  Optional[WindowInfo] = None
        self._switch_t: float = time.monotonic()
        self._stats:    Dict[str, AppStats] = {}

        self._supported = self._check_support()

    def _check_support(self) -> bool:
        if _SYSTEM in ("Windows", "Darwin"):
            return True
        # Linux: check xdotool
        try:
            r = subprocess.run(
                ["xdotool", "--version"],
                capture_output=True, timeout=1.0
            )
            return r.returncode == 0
        except (FileNotFoundError, Exception):
            logger.info(
                "xdotool not found — window tracking disabled on Linux. "
                "Install: sudo apt install xdotool"
            )
            return False

    def start(self) -> None:
        if not self._supported:
            return
        # If an old thread is still alive (e.g. stop() was called but the join
        # timed out), signal it again and wait briefly before starting a new one.
        if self._thread is not None and self._thread.is_alive():
            self._stop.set()
            self._thread.join(timeout=1.5)
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="fg-window-tracker"
        )
        self._thread.start()
        logger.info("WindowTracker started")

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        self._thread = None

    def reset(self) -> None:
        """Clear stats for a new session."""
        with self._lock:
            self._stats.clear()
            self._current = None

    def record_detection(self, reason: str = "") -> None:
        """Call when FocusSession detects a distraction."""
        with self._lock:
            if self._current:
                key = self._current.app_name
                if key in self._stats:
                    self._stats[key].detections += 1

    def get_stats(self) -> List[AppStats]:
        """Return sorted list (most time first)."""
        with self._lock:
            # Flush current app's time before returning
            self._flush_current()
            return sorted(self._stats.values(), key=lambda s: s.seconds, reverse=True)

    def get_current_app(self) -> Optional[str]:
        with self._lock:
            return self._current.app_name if self._current else None

    def get_current_window_info(self) -> Optional["WindowInfo"]:
        """Return the full active WindowInfo (app_name + title)."""
        with self._lock:
            return self._current

    def get_current_window_key(self) -> Optional[str]:
        """Return a cache key based on the window TITLE (more specific than app name).
        This allows the cache to differentiate Chrome on Instagram vs Chrome on GitHub."""
        with self._lock:
            if not self._current:
                return None
            # Prefer full title (contains site name) over generic app name
            title = self._current.title.strip()
            if title:
                return title
            return self._current.app_name

    # Internal

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                win = get_active_window()
                if win:
                    with self._lock:
                        self._on_new_window(win)
            except Exception as e:
                logger.debug(f"window_tracker loop: {e}")
            self._stop.wait(timeout=self._poll)

        # Flush on stop
        with self._lock:
            self._flush_current()

    def _on_new_window(self, win: WindowInfo) -> None:
        """Called under lock."""
        # Flush time to previous app
        self._flush_current()

        app_changed = (
            self._current is None or
            self._current.app_name != win.app_name
        )

        self._current  = win
        self._switch_t = time.monotonic()

        if app_changed:
            key = win.app_name
            if key not in self._stats:
                self._stats[key] = AppStats(app_name=key)
            self._stats[key].switches += 1

            if self._on_switch:
                try:
                    self._on_switch(win)
                except Exception:
                    pass

    def _flush_current(self) -> None:
        """Credit elapsed time to current app. Must be called under lock."""
        if self._current is None:
            return
        now     = time.monotonic()
        elapsed = now - self._switch_t
        self._switch_t = now
        key = self._current.app_name
        if key in self._stats:
            self._stats[key].seconds += elapsed
