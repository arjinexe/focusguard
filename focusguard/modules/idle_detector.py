"""
FocusGuard — Idle Detector  (focusguard/modules/idle_detector.py)

Detects three independent idle signals:

  1. SCREEN FREEZE  — consecutive frames are too similar (SSIM-based diff)
  2. MOUSE IDLE     — cursor hasn't moved beyond a dead-zone for N seconds
  3. KEYBOARD IDLE  — no key presses for N seconds  (pynput, optional)

Each signal fires an on_idle callback with (signal_type, idle_seconds).
The detector is designed to be thread-safe and restartable.

Why this matters:
  "User is browsing social media" ≠ the only way to waste time.
  Staring at the wall, phone in hand, coffee in the other — the screen
  stays still. FocusGuard should notice that too.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable, Dict, Optional, Tuple

import cv2
import numpy as np
import pyautogui

logger = logging.getLogger("focusguard.idle")

# Signal types

class IdleSignal(Enum):
    SCREEN_FREEZE = auto()   # screen has not changed
    MOUSE_IDLE    = auto()   # mouse has not moved
    KEYBOARD_IDLE = auto()   # keyboard has been idle


# Config

@dataclass
class IdleConfig:
    # Screen freeze
    screen_idle_enabled: bool  = True
    screen_idle_seconds: int   = 180     # 3 dk sabit = idle
    screen_diff_threshold: float = 0.015 # normalized mean diff — below this = "frozen"
    screen_check_interval: float = 5.0   # seconds between screen hash checks

    # Mouse idle
    mouse_idle_enabled: bool  = True
    mouse_idle_seconds: int   = 120      # seconds without mouse movement before idle
    mouse_dead_zone:    int   = 8        # px — movements smaller than this are ignored
    mouse_check_interval: float = 2.0

    # Keyboard idle (pynput optional)
    keyboard_idle_enabled: bool  = True
    keyboard_idle_seconds: int   = 300   # seconds without keystrokes before idle
    # keyboard check interval is event-driven (no poll needed)

    # Cooldown: minimum seconds before the same signal can fire again
    cooldown_seconds: int = 60


# Status snapshot

@dataclass
class IdleStatus:
    screen_idle_since:   Optional[float] = None   # monotonic timestamp or None
    mouse_idle_since:    Optional[float] = None
    keyboard_idle_since: Optional[float] = None
    last_mouse_pos:      Tuple[int, int] = (0, 0)
    last_key_time:       float = field(default_factory=time.monotonic)

    def screen_idle_seconds(self) -> float:
        return (time.monotonic() - self.screen_idle_since) if self.screen_idle_since else 0.0

    def mouse_idle_seconds(self) -> float:
        return (time.monotonic() - self.mouse_idle_since) if self.mouse_idle_since else 0.0

    def keyboard_idle_seconds(self) -> float:
        return time.monotonic() - self.last_key_time


# Main detector

class IdleDetector:
    """
    Runs three background threads. Fires on_idle(signal, idle_secs) on the
    calling thread via a queue — never blocks the GUI.

    Usage:
        detector = IdleDetector(cfg, on_idle=my_callback)
        detector.start()
        ...
        detector.stop()
    """

    def __init__(
        self,
        cfg: Optional[IdleConfig] = None,
        on_idle: Optional[Callable[[IdleSignal, float], None]] = None,
        capture_fn: Optional[Callable[[], Optional[np.ndarray]]] = None,
    ):
        self.cfg = cfg or IdleConfig()
        self._on_idle    = on_idle
        self._capture_fn = capture_fn   # inject screen capture (avoids double MSS)

        self._status  = IdleStatus()
        self._lock    = threading.Lock()
        self._stop    = threading.Event()
        self._threads: list = []
        self._last_fired: Dict[IdleSignal, float] = {}
        self._kb_listener = None

    # Public API

    def start(self) -> None:
        self._stop.clear()
        self._status = IdleStatus()
        self._threads = []

        if self.cfg.screen_idle_enabled:
            self._spawn(self._screen_loop, "idle-screen")

        if self.cfg.mouse_idle_enabled:
            self._status.last_mouse_pos = self._get_mouse_pos()
            self._spawn(self._mouse_loop, "idle-mouse")

        if self.cfg.keyboard_idle_enabled:
            self._status.last_key_time = time.monotonic()
            self._start_kb_listener()

        logger.info("IdleDetector started")

    def stop(self) -> None:
        self._stop.set()
        self._stop_kb_listener()
        for t in self._threads:
            t.join(timeout=3.0)
        self._threads.clear()
        # Close cached mss context to free resources
        if hasattr(self, "_sct") and self._sct is not None:
            try:
                self._sct.close()
            except Exception:
                pass
            self._sct = None
        logger.info("IdleDetector stopped")

    def reset(self) -> None:
        """Call when user returns — clears all idle timers."""
        with self._lock:
            self._status.screen_idle_since   = None
            self._status.mouse_idle_since     = None
            self._status.last_key_time        = time.monotonic()
            self._status.last_mouse_pos       = self._get_mouse_pos()
            self._last_fired.clear()
        logger.debug("IdleDetector reset")

    def get_status(self) -> IdleStatus:
        with self._lock:
            return self._status

    # Internal

    def _spawn(self, target, name: str) -> None:
        t = threading.Thread(target=target, name=name, daemon=True)
        t.start()
        self._threads.append(t)

    def _fire(self, signal: IdleSignal, idle_secs: float) -> None:
        now = time.monotonic()
        last = self._last_fired.get(signal, 0.0)
        if now - last < self.cfg.cooldown_seconds:
            return
        self._last_fired[signal] = now
        if self._on_idle:
            try:
                self._on_idle(signal, idle_secs)
            except Exception as e:
                logger.debug(f"on_idle callback error: {e}")

    # Screen freeze loop

    def _screen_loop(self) -> None:
        prev_frame: Optional[np.ndarray] = None
        idle_since: Optional[float] = None

        while not self._stop.is_set():
            try:
                frame = self._grab_frame()
                if frame is not None:
                    if prev_frame is not None and prev_frame.shape == frame.shape:
                        diff = self._frame_diff(prev_frame, frame)
                        if diff < self.cfg.screen_diff_threshold:
                            # Frame essentially unchanged
                            if idle_since is None:
                                idle_since = time.monotonic()
                            with self._lock:
                                self._status.screen_idle_since = idle_since
                            elapsed = time.monotonic() - idle_since
                            if elapsed >= self.cfg.screen_idle_seconds:
                                self._fire(IdleSignal.SCREEN_FREEZE, elapsed)
                        else:
                            # Screen changed — reset
                            idle_since = None
                            with self._lock:
                                self._status.screen_idle_since = None
                    prev_frame = frame

            except Exception as e:
                logger.debug(f"screen_loop error: {e}")

            self._stop.wait(timeout=self.cfg.screen_check_interval)

    def _grab_frame(self) -> Optional[np.ndarray]:
        if self._capture_fn:
            return self._capture_fn()
        # Use cached mss context to avoid re-opening the display on every call
        try:
            if not hasattr(self, "_sct") or self._sct is None:
                import mss as _mss
                self._sct = _mss.mss()
            sct = self._sct
            from PIL import Image
            raw = sct.grab(sct.monitors[1])
            img = Image.frombytes("RGBA", raw.size, bytes(raw.bgra)).convert("RGB")
            img = img.resize((320, 180), Image.LANCZOS)
            return np.asarray(img, dtype=np.uint8)
        except Exception:
            self._sct = None  # reset on error so next call re-opens
            return None

    @staticmethod
    def _frame_diff(a: np.ndarray, b: np.ndarray) -> float:
        """Normalized mean absolute difference, 0.0–1.0."""
        try:
            ga = cv2.cvtColor(a, cv2.COLOR_RGB2GRAY).astype(np.float32)
            gb = cv2.cvtColor(b, cv2.COLOR_RGB2GRAY).astype(np.float32)
            return float(np.mean(np.abs(ga - gb))) / 255.0
        except Exception:
            return 1.0  # assume changed on error

    # Mouse idle loop

    def _mouse_loop(self) -> None:
        while not self._stop.is_set():
            try:
                pos = self._get_mouse_pos()
                with self._lock:
                    last = self._status.last_mouse_pos
                    dx   = abs(pos[0] - last[0])
                    dy   = abs(pos[1] - last[1])

                    if dx > self.cfg.mouse_dead_zone or dy > self.cfg.mouse_dead_zone:
                        # Mouse moved
                        self._status.last_mouse_pos   = pos
                        self._status.mouse_idle_since  = None
                    else:
                        # Mouse still
                        if self._status.mouse_idle_since is None:
                            self._status.mouse_idle_since = time.monotonic()
                        elapsed = time.monotonic() - self._status.mouse_idle_since
                        if elapsed >= self.cfg.mouse_idle_seconds:
                            self._fire(IdleSignal.MOUSE_IDLE, elapsed)

            except Exception as e:
                logger.debug(f"mouse_loop error: {e}")

            self._stop.wait(timeout=self.cfg.mouse_check_interval)

    @staticmethod
    def _get_mouse_pos() -> Tuple[int, int]:
        try:
            return pyautogui.position()
        except Exception:
            return (0, 0)

    # Keyboard idle (pynput)

    def _start_kb_listener(self) -> None:
        try:
            from pynput import keyboard

            def _on_press(_key):
                with self._lock:
                    self._status.last_key_time = time.monotonic()
                    self._status.keyboard_idle_since = None  # reset

            self._kb_listener = keyboard.Listener(on_press=_on_press, daemon=True)
            self._kb_listener.start()
            logger.debug("pynput keyboard listener started")

            # Separate thread to fire callback when threshold exceeded
            self._spawn(self._keyboard_check_loop, "idle-keyboard-check")

        except ImportError:
            logger.info("pynput not installed — keyboard idle detection disabled. "
                        "Install with: pip install pynput")
        except Exception as e:
            logger.warning(f"Could not start keyboard listener: {e}")

    def _keyboard_check_loop(self) -> None:
        while not self._stop.is_set():
            with self._lock:
                elapsed = time.monotonic() - self._status.last_key_time
            if elapsed >= self.cfg.keyboard_idle_seconds:
                self._fire(IdleSignal.KEYBOARD_IDLE, elapsed)
            self._stop.wait(timeout=10.0)

    def _stop_kb_listener(self) -> None:
        if self._kb_listener:
            try:
                self._kb_listener.stop()
            except Exception:
                pass
            self._kb_listener = None


# Convenience factory

def make_detector(
    screen_seconds: int = 180,
    mouse_seconds:  int = 120,
    keyboard_seconds: int = 300,
    on_idle: Optional[Callable] = None,
    capture_fn: Optional[Callable] = None,
) -> IdleDetector:
    cfg = IdleConfig(
        screen_idle_seconds=screen_seconds,
        mouse_idle_seconds=mouse_seconds,
        keyboard_idle_seconds=keyboard_seconds,
    )
    return IdleDetector(cfg=cfg, on_idle=on_idle, capture_fn=capture_fn)
