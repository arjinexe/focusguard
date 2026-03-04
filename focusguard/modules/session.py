"""
FocusGuard session manager.
Manages session state, runs the analysis loop, fires resistance and idle detection.
"""

from __future__ import annotations

import copy
import logging
import re
import threading
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable, List, Optional

from focusguard.config import CONFIG
from focusguard.modules.analyzer import AnalysisResult, HybridAnalyzer
from focusguard.modules.resistance import ResistanceController
from focusguard.modules.screen_capture import ScreenCapture
from focusguard.modules.idle_detector import IdleDetector, IdleSignal, make_detector
from focusguard.modules.detection_cache import CACHE
from focusguard.modules.window_tracker import WindowTracker
from focusguard.modules.analytics import HEATMAP, PERF_LOG, compute_dwi, get_break_suggestion
from focusguard.modules.intentions import INTENTIONS

logger = logging.getLogger("focusguard.session")


def _make_result(is_distraction: bool, confidence: float, reason: str, backend: str) -> AnalysisResult:
    return AnalysisResult(
        is_distraction=is_distraction,
        confidence=confidence,
        reason=reason,
        backend_used=backend,
        analysis_ms=0.0,
    )


class State(Enum):
    IDLE    = auto()
    WORKING = auto()
    BREAK   = auto()
    PAUSED  = auto()


@dataclass
class DetectionEntry:
    timestamp:  float
    confidence: float
    reason:     str
    backend:    str


@dataclass
class SessionStats:
    state:               State = State.IDLE
    session_start:       float = 0.0
    total_caught:        int   = 0
    escalation_level:    int   = 0
    last_confidence:     float = 0.0
    last_reason:         str   = ""
    last_backend:        str   = ""
    last_analysis_ms:    float = 0.0
    clean_streak:        int   = 0
    best_clean_streak:   int   = 0
    pomodoros_completed: int   = 0
    idle_events:         int   = 0
    detections:          List[DetectionEntry] = field(default_factory=list)
    xp_earned:           int   = 0
    deep_work_index:     int   = 0
    current_app:         str   = ""


class FocusSession:

    def __init__(
        self,
        on_update:         Optional[Callable[[SessionStats, AnalysisResult], None]] = None,
        on_backend_status: Optional[Callable[[str, bool], None]] = None,
        overlay_fn:        Optional[Callable[[str, int], None]] = None,
        screen_text_fn:    Optional[Callable[[str, int], None]] = None,
        on_session_end:    Optional[Callable[[SessionStats], None]] = None,
        on_achievement:    Optional[Callable[[dict], None]] = None,
        on_level_up:       Optional[Callable[[int, int], None]] = None,
        on_idle:           Optional[Callable[[IdleSignal, float], None]] = None,
    ):
        self._on_update      = on_update
        self._on_session_end = on_session_end
        self._on_achievement = on_achievement
        self._on_level_up    = on_level_up
        self._on_idle_cb     = on_idle

        self._capture    = ScreenCapture(monitor_id=CONFIG.monitor_id, scale=CONFIG.capture_scale)
        self._analyzer   = HybridAnalyzer(backend_status_callback=on_backend_status)
        self._resistance = ResistanceController(overlay_fn=overlay_fn, screen_text_fn=screen_text_fn)

        self._state      = State.IDLE
        self._lock       = threading.Lock()
        self._stop_event = threading.Event()
        self._thread:    Optional[threading.Thread] = None

        self._stats          = SessionStats()
        self._dirty_streak   = 0
        self._clean_streak   = 0
        self._in_distraction = False
        self._allowlist:     List[str] = []
        self._pomodoro_count = 0

        # Remove stale cache entries keyed by bare process name (no dot, no space)
        try:
            stale = [k for k in list(CACHE._data.keys())
                     if "." not in k and " " not in k and len(k) < 20]
            for k in stale:
                CACHE._data.pop(k, None)
            if stale:
                CACHE._dirty = True
                logger.debug(f"Cleared {len(stale)} stale cache entries")
        except Exception:
            pass

        self._window_tracker = WindowTracker(on_switch=self._on_window_switch)
        self._idle = make_detector(
            screen_seconds=CONFIG.idle_screen_seconds,
            mouse_seconds=CONFIG.idle_mouse_seconds,
            keyboard_seconds=CONFIG.idle_keyboard_seconds,
            on_idle=self._handle_idle,
        )

    # ── Controls ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        with self._lock:
            if self._state == State.WORKING:
                return
            self._dirty_streak   = 0
            self._clean_streak   = 0
            self._in_distraction = False

            if self._state == State.IDLE:
                self._capture.reinit()
                self._stats = SessionStats(state=State.WORKING, session_start=time.time())
                self._resistance.full_reset()
                self._analyzer.reset_scroll()
                self._pomodoro_count = 0
            else:
                self._stats.state = State.WORKING
                self._resistance.reset()

            self._state = State.WORKING

        if self._thread is None or not self._thread.is_alive():
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._loop, daemon=True, name="fg-monitor")
            self._thread.start()

        if CONFIG.idle_detection_enabled:
            self._idle.start()
        self._window_tracker.start()
        logger.info("Session started")

    def pause(self) -> None:
        with self._lock:
            if self._state == State.WORKING:
                self._state = self._stats.state = State.PAUSED
                self._resistance.reset()
        self._idle.reset()
        self._window_tracker.stop()

    def resume(self) -> None:
        with self._lock:
            if self._state == State.PAUSED:
                self._state = self._stats.state = State.WORKING
        self._idle.reset()
        self._window_tracker.start()

    def take_break(self, long_break: bool = False) -> None:
        with self._lock:
            self._state = self._stats.state = State.BREAK
            self._resistance.reset()
            if not long_break:
                self._pomodoro_count += 1
                self._stats.pomodoros_completed += 1
        self._idle.stop()

    def stop(self) -> None:
        with self._lock:
            prev  = self._state
            self._state = self._stats.state = State.IDLE

        self._stop_event.set()
        self._resistance.reset()
        self._idle.stop()
        self._window_tracker.stop()
        CACHE.save()

        if self._stats.session_start > 0:
            elapsed = time.time() - self._stats.session_start
            self._stats.deep_work_index = compute_dwi(
                work_seconds=elapsed,
                detections=self._stats.total_caught,
                best_clean_streak=self._stats.best_clean_streak,
                idle_events=self._stats.idle_events,
            )
            HEATMAP._save()
            PERF_LOG.record_session(
                dwi=self._stats.deep_work_index,
                work_seconds=elapsed,
                detections=self._stats.total_caught,
                pomodoros=self._stats.pomodoros_completed,
            )

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=4.0)

        self._capture.close()

        if self._on_session_end and prev != State.IDLE:
            try:
                self._on_session_end(copy.copy(self._stats))
            except Exception as e:
                logger.debug(f"session_end cb: {e}")

        logger.info("Session stopped")

    def set_allowlist(self, items: List[str]) -> None:
        self._allowlist = [x.lower().strip() for x in items if x.strip()]

    def complete_pomodoro(self) -> None:
        with self._lock:
            self._pomodoro_count += 1
            self._stats.pomodoros_completed += 1

    # ── Idle handler ─────────────────────────────────────────────────────────

    def _handle_idle(self, signal: IdleSignal, idle_secs: float) -> None:
        logger.info(f"Idle signal: {signal.name}  idle={idle_secs:.0f}s")

        with self._lock:
            self._stats.idle_events += 1

        action = CONFIG.idle_action

        if action in ("pause", "both") and self._state == State.WORKING:
            self.pause()

        if self._on_idle_cb:
            try:
                self._on_idle_cb(signal, idle_secs)
            except Exception as e:
                logger.debug(f"on_idle cb: {e}")

    # ── Monitor loop ─────────────────────────────────────────────────────────

    def _loop(self) -> None:
        logger.info("Monitor loop active")
        while not self._stop_event.is_set():
            t0 = time.monotonic()
            with self._lock:
                cur = self._state

            if cur == State.WORKING:
                self._tick()

            interval = CONFIG.screenshot_interval
            if CONFIG.strict_mode:
                interval = max(0.5, interval * 0.7)
            self._stop_event.wait(timeout=max(0.05, interval - (time.monotonic() - t0)))
        logger.info("Monitor loop ended")

    def _tick(self) -> None:
        win       = self._window_tracker.get_current_window_info()
        app_name  = (win.app_name if win else "") or ""
        win_title = (win.title    if win else "") or ""
        self._stats.current_app = app_name

        app_lc   = app_name.lower()
        title_lc = (app_name + " " + win_title).lower()

        # ── Step 1: Skip FocusGuard's own window ─────────────────────────────
        if "focusguard" in title_lc:
            self._clean(reason="self")
            return

        # ── Step 2: Productive native app (IDE, terminal, editor, etc.) ──────
        # Matched against process name, not the browser window title.
        # python.exe is excluded from the blanket bypass because it could be
        # running anything — the title is checked for distraction domains below.
        if self._is_productive_app(app_lc, title_lc):
            self._clean(reason=f"app:{app_name}")
            return

        # ── Step 3: Productive site keyword in browser window title ──────────
        # This is the primary browser detection path. Browsers embed the site
        # name in the window title (e.g. "Pull Request · GitHub").
        # Productive keyword matching runs BEFORE distraction matching so that
        # a title like "Twitter API issue · GitHub" is always treated as clean.
        if self._is_productive_title(title_lc):
            self._clean(reason=f"site:{win_title[:50]}")
            return

        # ── Step 4: Distraction site keyword in browser window title ─────────
        # Only reached if no productive keyword matched above.
        hit = self._find_distraction_title(title_lc)
        if hit:
            result = _make_result(True, 0.95, hit, "title")
            self._process_result(result, title_lc[:80])
            return

        # ── Step 5: Distraction domain in window title (domain-based fallback)─
        # Some browsers or OS title formats include the domain, e.g. "- reddit.com"
        for domain in CONFIG.distraction_domains:
            if domain in title_lc:
                result = _make_result(True, 0.95, domain, "domain")
                self._process_result(result, title_lc[:80])
                return

        # ── Step 6: YouTube video title analysis ─────────────────────────────
        # Browser title format: "<video title> - YouTube — <browser>"
        # Checked separately because YouTube itself is neutral — it's the video
        # content that determines whether this is a distraction.
        if "youtube" in title_lc:
            video_title = _extract_youtube_title(win_title)
            if video_title:
                hit = next((k for k in CONFIG.youtube_distraction_keywords
                            if k in video_title.lower()), None)
                if hit:
                    result = _make_result(True, 0.90, f"yt:{hit}", "title")
                    self._process_result(result, title_lc[:80])
                    return
            # Ambiguous YouTube title — fall through to visual analysis

        # ── Step 7: Fullscreen detection ─────────────────────────────────────
        # Games and video players typically go fullscreen. Productive apps rarely do.
        try:
            from focusguard.modules.fullscreen import is_fullscreen, is_productive_fullscreen
            fs, fs_hint = is_fullscreen()
            if fs and not is_productive_fullscreen(fs_hint):
                result = _make_result(
                    True, 0.88,
                    f"fullscreen:{fs_hint[:40]}" if fs_hint else "fullscreen",
                    "fullscreen",
                )
                self._process_result(result, f"fs:{fs_hint[:40]}")
                return
        except Exception as e:
            logger.debug(f"fullscreen check: {e}")

        # ── Step 8: Detection cache ───────────────────────────────────────────
        # Use the window title as the cache key (it's more specific than app name
        # and differentiates "Chrome on GitHub" from "Chrome on Instagram").
        cache_key = win_title[:80] or app_name
        if cache_key and not CONFIG.ghost_mode:
            hit = CACHE.lookup(cache_key)
            if hit:
                result = _make_result(hit.is_distraction, hit.confidence, hit.key, "cache")
                self._process_result(result, cache_key)
                return

        # ── Step 9: Visual analysis ───────────────────────────────────────────
        # Reached only for genuinely ambiguous cases: browser with an unknown tab
        # title, windowed apps we don't recognise, ambiguous YouTube, etc.
        # OCR reads the address bar for the actual URL.
        # Ollama sees the page content with the tab bar cropped out — this
        # prevents background tab titles from influencing the result.
        frame = self._capture.capture()
        if frame is None:
            return

        b64    = self._capture.to_base64_content_only(frame)
        navfr  = self._capture.capture_nav_fullres()
        result = self._analyzer.analyze(
            frame.array, b64, nav_fullres=navfr, win_title=win_title
        )
        self._process_result(result, cache_key)

    # ── Context classifiers ───────────────────────────────────────────────────

    def _is_productive_app(self, app_lc: str, title_lc: str) -> bool:
        """Return True if the foreground process is a known productive application.

        Python is excluded from the blanket bypass because it runs under many
        different contexts. Instead, python.exe is allowed through only when its
        window title does not contain a known distraction domain.
        """
        if app_lc in ("python", "python3", "python.exe"):
            return not any(d in title_lc for d in CONFIG.distraction_domains)

        return any(k in app_lc for k in CONFIG.productive_apps)

    def _is_productive_title(self, title_lc: str) -> bool:
        """Return True if the window title contains a productive site name.

        This matches how browsers embed site names in window titles.
        e.g. Chrome on GitHub: "My PR · GitHub" → matches "github"
        """
        return any(k in title_lc for k in CONFIG.productive_title_keywords)

    def _find_distraction_title(self, title_lc: str) -> Optional[str]:
        """Return the matched distraction keyword, or None if no match.

        Only called after _is_productive_title() returns False, so there is
        no risk of a productive site like GitHub triggering this path even
        if its title contains a social media platform's name.
        """
        for kw in CONFIG.distraction_title_keywords:
            if kw in title_lc:
                return kw
        return None

    # ── Internal result handling ──────────────────────────────────────────────

    def _clean(self, reason: str = "") -> None:
        self._stats.last_reason     = reason
        self._stats.last_confidence = 0.0
        self._stats.last_backend    = "bypass"
        self._on_clean_tick()

    def _on_clean_tick(self) -> None:
        self._dirty_streak  = 0
        self._clean_streak += 1
        if self._in_distraction and self._clean_streak >= 5:
            self._in_distraction = False
            self._resistance.reset()

    def _process_result(self, result: AnalysisResult, cache_key: str = "") -> None:
        # Apply allowlist
        if self._allowlist:
            low = (result.reason or "").lower()
            if any(w in low for w in self._allowlist):
                result.is_distraction = False
                result.confidence     = 0.0

        threshold = CONFIG.confidence_threshold
        if CONFIG.strict_mode:
            threshold = max(0.3, threshold - 0.15)
        result.is_distraction = result.confidence >= threshold

        self._stats.last_confidence  = result.confidence
        self._stats.last_reason      = result.reason
        self._stats.last_backend     = result.backend_used
        self._stats.last_analysis_ms = result.analysis_ms

        if result.is_distraction:
            self._dirty_streak += 1
            self._clean_streak  = 0

            if self._dirty_streak >= CONFIG.min_dirty_streak:
                if not self._in_distraction:
                    self._in_distraction = True
                    self._stats.total_caught += 1
                    entry = DetectionEntry(
                        timestamp=time.time(),
                        confidence=result.confidence,
                        reason=result.reason,
                        backend=result.backend_used,
                    )
                    self._stats.detections.append(entry)
                    HEATMAP.record()
                    self._window_tracker.record_detection(result.reason or "unknown")
                    if cache_key:
                        CACHE.record(cache_key, True, result.confidence)
                    if len(self._stats.detections) > CONFIG.max_log_entries:
                        self._stats.detections = self._stats.detections[-CONFIG.max_log_entries:]
                    self._idle.reset()

                if not CONFIG.ghost_mode:
                    self._resistance.trigger(result.reason, result.confidence)
                self._stats.escalation_level = self._resistance.level
        else:
            self._dirty_streak  = 0
            self._clean_streak += 1
            if self._in_distraction and self._clean_streak >= 5:
                self._in_distraction = False
                self._resistance.reset()

        if self._on_update:
            snap = copy.copy(self._stats)
            snap.detections = []
            try:
                self._on_update(snap, result)
            except Exception as e:
                logger.debug(f"update cb: {e}")

    def _on_window_switch(self, win) -> None:
        pass

    def get_break_suggestion(self) -> str:
        return get_break_suggestion(self._stats.pomodoros_completed)

    def get_window_stats(self) -> list:
        return [s.to_dict() for s in self._window_tracker.get_stats()]

    @property
    def state(self) -> State:
        with self._lock:
            return self._state

    @property
    def stats(self) -> SessionStats:
        return self._stats

    @property
    def detections(self) -> List[DetectionEntry]:
        return list(self._stats.detections)

    @property
    def resistance_level(self) -> int:
        return self._resistance.level

    @property
    def idle_status(self):
        return self._idle.get_status()


# ── Utilities ─────────────────────────────────────────────────────────────────

def _extract_youtube_title(raw_title: str) -> str:
    """Extract the video name from a YouTube browser window title.

    Input:  'Minecraft Let's Play - YouTube — Opera GX'
    Output: 'Minecraft Let's Play'
    """
    t = re.sub(
        r"\s*[—–-]\s*(google chrome|firefox|opera|opera gx|brave|edge|safari)\s*$",
        "", raw_title, flags=re.IGNORECASE,
    ).strip()
    t = re.sub(r"\s*-\s*YouTube\s*$", "", t, flags=re.IGNORECASE).strip()
    return t
