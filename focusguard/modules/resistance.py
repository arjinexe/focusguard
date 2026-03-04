"""
FocusGuard resistance mechanisms.

Escalates through levels based on distraction frequency.
"""

import logging
import math
import random
import sys
import threading
import time
from typing import Callable, Optional

import pyautogui

from focusguard.config import CONFIG, SHAME_MESSAGES, SCREEN_TEXT_MESSAGES

logger = logging.getLogger("focusguard.resistance")

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.0


# Lazy import helper for screen_brightness_control
def _get_sbc():
    try:
        import screen_brightness_control as sbc
        return sbc
    except ImportError:
        return None


class MouseJitter:
    """
    Moves the cursor in a configurable wave pattern to interrupt distraction scrolling.
    """

    PATTERNS = ["sine", "chaos", "spiral", "bounce"]

    def __init__(self):
        self._lock = threading.Lock()
        self._active = False
        self._thread: Optional[threading.Thread] = None
        self._pattern = "sine"

    def start(self, intensity: int, duration: float, pattern: str = None):
        with self._lock:
            if self._active:
                return
            self._active = True
            self._pattern = pattern or random.choice(self.PATTERNS)
            self._thread = threading.Thread(
                target=self._loop,
                args=(intensity, duration),
                daemon=True,
                name="jitter",
            )
            self._thread.start()
        logger.debug(f"Jitter started ±{intensity}px / {duration:.1f}s / {self._pattern}")

    def _loop(self, intensity: int, duration: float):
        deadline = time.monotonic() + duration
        try:
            t_start = time.monotonic()
            while self._active and time.monotonic() < deadline:
                t = time.monotonic() - t_start
                pattern = self._pattern

                if pattern == "sine":
                    dx = int(intensity * math.sin(t * 17.3) * random.uniform(0.6, 1.0))
                    dy = int(intensity * math.cos(t * 13.7) * random.uniform(0.6, 1.0))
                elif pattern == "chaos":
                    dx = random.randint(-intensity, intensity)
                    dy = random.randint(-intensity, intensity)
                elif pattern == "spiral":
                    angle = t * 5
                    radius = intensity * min(1.0, t / 2)
                    dx = int(radius * math.cos(angle))
                    dy = int(radius * math.sin(angle))
                elif pattern == "bounce":
                    dx = int(intensity * math.sin(t * 8) * math.sin(t * 3.7))
                    dy = int(intensity * math.cos(t * 6) * random.uniform(0.5, 1.0))
                else:
                    dx = int(intensity * math.sin(t * 17.3))
                    dy = int(intensity * math.cos(t * 13.7))

                # Add an extra random kick for unpredictability
                dx += random.randint(-intensity // 3, intensity // 3)
                dy += random.randint(-intensity // 3, intensity // 3)

                pyautogui.moveRel(dx, dy, _pause=False)

                # Variable sleep to make the pattern less predictable
                time.sleep(random.uniform(0.02, 0.06))

        except pyautogui.FailSafeException:
            logger.debug("Jitter: PyAutoGUI FailSafe triggered")
        except Exception as e:
            logger.debug(f"Jitter loop error: {e}")
        finally:
            with self._lock:
                self._active = False

    def stop(self):
        with self._lock:
            self._active = False

    @property
    def is_active(self) -> bool:
        return self._active


class BrightnessDimmer:
    """Gradually dims the screen. Restores original brightness when focus resumes."""

    def __init__(self):
        self._sbc = _get_sbc()
        self.available = self._sbc is not None
        self._original: Optional[int] = None
        self._lock = threading.Lock()
        self._active = False

        if not self.available:
            logger.warning("screen-brightness-control not installed — brightness dimming disabled.")

    def start(self, target: int = None):
        if not self.available:
            return
        with self._lock:
            if self._active:
                return
            self._active = True

        target = target if target is not None else CONFIG.brightness_dim_target
        t = threading.Thread(
            target=self._dim_loop, args=(target,), daemon=True, name="dimmer"
        )
        t.start()

    def _dim_loop(self, target: int):
        try:
            current = self._sbc.get_brightness(display=0)
            current = current[0] if isinstance(current, list) else current
            self._original = int(current)
            while self._active and current > target:
                current = max(target, current - 5)
                self._sbc.set_brightness(int(current), display=0)
                time.sleep(CONFIG.brightness_step_delay)
        except Exception as e:
            logger.debug(f"Dimmer error: {e}")
        finally:
            with self._lock:
                self._active = False

    def restore(self):
        if not self.available:
            return
        with self._lock:
            self._active = False
        if self._original is not None:
            try:
                self._sbc.set_brightness(self._original, display=0)
            except Exception as e:
                logger.debug(f"Brightness restore error: {e}")
            self._original = None

    @property
    def is_active(self) -> bool:
        return self._active


class TerminalShamer:
    """Prints escalating messages to the terminal."""

    def fire(self, level: int, reason: str = ""):
        idx = min(level, len(SHAME_MESSAGES) - 1)
        msg = SHAME_MESSAGES[idx]
        bar = "━" * 62
        print(f"\n\033[91m{bar}\033[0m")
        print(f"\033[1;91m  ⚠  FocusGuard UYARI — Seviye {level + 1}  |  {reason[:40]}\033[0m")
        print(f"\033[93m  {msg}\033[0m")
        print(f"\033[91m{bar}\033[0m\n", flush=True)
        logger.info(f"Resistance warning level {level}: {msg}")


class SoundAlerter:
    """
    Cross-platform system alert sound.
    Uses winsound on Windows, terminal bell on Linux/macOS.
    """

    @staticmethod
    def beep(level: int = 0):
        try:
            if sys.platform == "win32":
                import winsound
                freq = 440 + level * 110
                dur  = 200 + level * 100
                for _ in range(min(level + 1, 3)):
                    winsound.Beep(freq, dur)
                    time.sleep(0.1)
            else:
                # Linux/macOS: terminal bell veya paplay
                for _ in range(min(level + 1, 3)):
                    print("\a", end="", flush=True)
                    time.sleep(0.2)
        except Exception as e:
            logger.debug(f"Sound alert error: {e}")


class SurpriseJitterScheduler:
    """
    Fires random micro-jitters during a session at unpredictable intervals
    (15–45 seconds apart). Unpredictability makes the deterrent more effective.
    """

    def __init__(self, jitter: MouseJitter):
        self._jitter = jitter
        self._active = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def start_random_schedule(self, intensity: int, session_duration: float):
        """Trigger jitter at random intervals throughout the session."""
        with self._lock:
            if self._active:
                return
            self._active = True
        self._thread = threading.Thread(
            target=self._schedule_loop,
            args=(intensity, session_duration),
            daemon=True,
            name="surprise-jitter",
        )
        self._thread.start()

    def _schedule_loop(self, intensity: int, duration: float):
        deadline = time.monotonic() + duration
        while self._active and time.monotonic() < deadline:
            # Random wait between 15 and 45 seconds
            wait = random.uniform(15, 45)
            t_wait = time.monotonic() + wait
            while self._active and time.monotonic() < t_wait:
                time.sleep(1)
            if self._active and not self._jitter.is_active:
                # Fire a brief unexpected jitter burst
                micro_intensity = max(4, intensity // 3)
                self._jitter.start(micro_intensity, random.uniform(1.0, 2.5))
        with self._lock:
            self._active = False

    def stop(self):
        with self._lock:
            self._active = False


class ResistanceController:
    """
    Orchestrates all resistance mechanisms.
    Escalates response intensity with each consecutive distraction detection.
    """

    def __init__(self, overlay_fn: Optional[Callable] = None,
                 screen_text_fn: Optional[Callable] = None):
        self.jitter   = MouseJitter()
        self.dimmer   = BrightnessDimmer()
        self.shamer   = TerminalShamer()
        self.sounder  = SoundAlerter()
        self.surprise = SurpriseJitterScheduler(self.jitter)

        self._overlay_fn     = overlay_fn
        self._screen_text_fn = screen_text_fn

        self._level       = 0
        self._consecutive = 0
        self._last_trigger_t = 0.0
        self._lock = threading.Lock()

    def trigger(self, reason: str = "", confidence: float = 0.0):
        """A distraction was detected — intervene at the appropriate escalation level."""
        now = time.monotonic()

        with self._lock:
            gap = now - self._last_trigger_t

            # Cooldown: don't re-trigger if last trigger was too recent.
            # Without this, resistance fires every 1.5s (each tick) = spam.
            # Level 0 → 15s cooldown, level 1 → 12s, level 2+ → 8s
            cooldown = max(8.0, 15.0 - self._level * 3)
            if self._last_trigger_t > 0 and gap < cooldown:
                return

            if gap > CONFIG.escalation_reset_minutes * 60:
                self._level = 0
                self._consecutive = 0

            self._consecutive += 1
            self._last_trigger_t = now

            if self._consecutive % CONFIG.escalation_per_n_detections == 0:
                self._level = min(self._level + 1, CONFIG.max_escalation)

            level = self._level

        logger.warning(f"DISTRACTION [{confidence:.0%}] — {reason} — level {level}")

        # Intensity increases with each escalation level
        intensity = CONFIG.jitter_base_intensity + level * 8
        duration  = CONFIG.jitter_base_duration  + level * 2.5

        # Delay only on level 0; higher levels fire immediately for impact
        delay = random.uniform(0, min(0.5, level * 0.1))

        def _fire():
            time.sleep(delay)

            if CONFIG.enable_mouse_jitter:
                # Stop any running jitter and restart with current (possibly escalated) params
                if self.jitter.is_active:
                    self.jitter.stop()
                    time.sleep(0.05)
                pattern = "chaos" if level >= 4 else None
                self.jitter.start(intensity=intensity, duration=duration, pattern=pattern)

            # Stealth mode: jitter only — no visible overlays or screen effects
            if CONFIG.stealth_mode:
                if CONFIG.enable_terminal_shaming:
                    self.shamer.fire(level, reason)
                return

            if CONFIG.enable_brightness_dim and not self.dimmer.is_active:
                self.dimmer.start()

            if CONFIG.enable_terminal_shaming:
                self.shamer.fire(level, reason)

            if CONFIG.enable_sound_alert:
                self.sounder.beep(level)

            # Overlay warning
            if CONFIG.enable_overlay_warning and self._overlay_fn:
                shame_idx = min(level, len(SHAME_MESSAGES) - 1)
                shame_msg = SHAME_MESSAGES[shame_idx]
                try:
                    self._overlay_fn(shame_msg, level)
                except Exception as e:
                    logger.debug(f"Overlay callback error: {e}")

            # Screen text bomb fires from level 1 (not level 2)
            if level >= 1 and CONFIG.enable_fullscreen_blast and self._screen_text_fn:
                msg = random.choice(SCREEN_TEXT_MESSAGES)
                try:
                    self._screen_text_fn(msg, level)
                except Exception as e:
                    logger.debug(f"Screen text callback error: {e}")

        t = threading.Thread(target=_fire, daemon=True, name="resist-fire")
        t.start()
        # Thread is daemon — OS will clean up on exit; no accumulation risk
        # since trigger() rate is limited by screenshot_interval

    def reset(self):
        """Clean frame detected — de-escalate."""
        self.jitter.stop()
        self.dimmer.restore()
        self.surprise.stop()
        with self._lock:
            self._consecutive = 0
        logger.debug("Resistance reset")  # was INFO, caused spam every ~5 s

    def full_reset(self):
        self.reset()
        with self._lock:
            self._level = 0

    def start_surprise_mode(self, intensity: int, duration_minutes: float):
        """Schedule random micro-jitters throughout the session."""
        self.surprise.start_random_schedule(intensity, duration_minutes * 60)

    @property
    def level(self) -> int:
        with self._lock:
            return self._level

    @property
    def consecutive(self) -> int:
        with self._lock:
            return self._consecutive
