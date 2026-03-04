"""
tests/test_idle_detector.py
No GUI, no screen capture needed. Pure unit tests.
"""

import time
import threading
import numpy as np
import pytest

from focusguard.modules.idle_detector import (
    IdleDetector,
    IdleConfig,
    IdleSignal,
    make_detector,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _solid_frame(color=(128, 128, 128), h=90, w=160) -> np.ndarray:
    return np.full((h, w, 3), color, dtype=np.uint8)


def _noisy_frame(h=90, w=160) -> np.ndarray:
    return np.random.randint(0, 255, (h, w, 3), dtype=np.uint8)


# ── frame_diff ────────────────────────────────────────────────────────────────

class TestFrameDiff:
    def test_identical_frames_return_zero(self):
        f = _solid_frame()
        assert IdleDetector._frame_diff(f, f) < 0.001

    def test_completely_different_frames(self):
        a = _solid_frame((0, 0, 0))
        b = _solid_frame((255, 255, 255))
        diff = IdleDetector._frame_diff(a, b)
        assert diff > 0.9

    def test_slightly_different_frames(self):
        a = _solid_frame((100, 100, 100))
        b = _solid_frame((110, 110, 110))
        diff = IdleDetector._frame_diff(a, b)
        assert 0 < diff < 0.1

    def test_mismatched_shapes_return_safe_value(self):
        a = _solid_frame(h=90, w=160)
        b = _solid_frame(h=45, w=80)
        # Should not raise; returns 1.0 (assume changed)
        result = IdleDetector._frame_diff(a, b)
        assert result == 1.0

    def test_random_frames_differ_significantly(self):
        a = _noisy_frame()
        b = _noisy_frame()
        diff = IdleDetector._frame_diff(a, b)
        assert diff > 0.05


# ── Screen freeze detection ───────────────────────────────────────────────────

class TestScreenFreeze:
    def test_frozen_screen_fires_callback(self):
        fired: list = []
        frame = _solid_frame()
        call_count = 0

        def capture():
            nonlocal call_count
            call_count += 1
            return frame  # always same → frozen

        cfg = IdleConfig(
            screen_idle_enabled=True,
            screen_idle_seconds=0,          # fire immediately
            screen_diff_threshold=0.01,
            screen_check_interval=0.05,
            mouse_idle_enabled=False,
            keyboard_idle_enabled=False,
            cooldown_seconds=0,
        )
        det = IdleDetector(cfg=cfg, on_idle=lambda s, t: fired.append(s), capture_fn=capture)
        det.start()
        time.sleep(0.4)
        det.stop()
        assert IdleSignal.SCREEN_FREEZE in fired

    def test_changing_screen_does_not_fire(self):
        fired: list = []
        toggle = [True]

        def capture():
            toggle[0] = not toggle[0]
            return _solid_frame((0, 0, 0)) if toggle[0] else _solid_frame((255, 255, 255))

        cfg = IdleConfig(
            screen_idle_enabled=True,
            screen_idle_seconds=0,
            screen_diff_threshold=0.01,
            screen_check_interval=0.05,
            mouse_idle_enabled=False,
            keyboard_idle_enabled=False,
        )
        det = IdleDetector(cfg=cfg, on_idle=lambda s, t: fired.append(s), capture_fn=capture)
        det.start()
        time.sleep(0.4)
        det.stop()
        assert IdleSignal.SCREEN_FREEZE not in fired

    def test_reset_clears_idle_timer(self):
        fired: list = []
        frame = _solid_frame()

        cfg = IdleConfig(
            screen_idle_enabled=True,
            screen_idle_seconds=0,
            screen_diff_threshold=0.01,
            screen_check_interval=0.05,
            mouse_idle_enabled=False,
            keyboard_idle_enabled=False,
            cooldown_seconds=999,  # prevent second fire
        )
        det = IdleDetector(cfg=cfg, on_idle=lambda s, t: fired.append(s), capture_fn=lambda: frame)
        det.start()
        time.sleep(0.15)
        initial_count = len(fired)
        det.reset()
        # After reset, cooldown_seconds=999 prevents re-fire quickly
        time.sleep(0.15)
        det.stop()
        assert len(fired) == initial_count  # no new fires after reset+cooldown


# ── i18n ─────────────────────────────────────────────────────────────────────

class TestI18n:
    def test_english_default(self):
        from focusguard.i18n import set_locale, t
        set_locale("en")
        assert t("btn_focus") == "▶  FOCUS"

    def test_turkish_locale(self):
        from focusguard.i18n import set_locale, t
        set_locale("tr")
        assert t("btn_focus") == "▶  ODAKLAN"

    def test_format_args(self):
        from focusguard.i18n import set_locale, t
        set_locale("en")
        result = t("level_label", n=7)
        assert "7" in result

    def test_missing_key_returns_key(self):
        from focusguard.i18n import set_locale, t
        set_locale("en")
        assert t("this_key_does_not_exist_xyz") == "this_key_does_not_exist_xyz"

    def test_switch_locale_mid_session(self):
        from focusguard.i18n import set_locale, t, current_lang
        set_locale("tr")
        assert current_lang() == "tr"
        set_locale("en")
        assert current_lang() == "en"

    def test_list_values_accessible(self):
        from focusguard.i18n import set_locale, t
        set_locale("en")
        shame = t("shame")
        assert isinstance(shame, list)
        assert len(shame) > 0

    def test_unknown_lang_falls_back_to_english(self):
        from focusguard.i18n import set_locale, t
        set_locale("zh")  # not supported
        assert t("btn_stop") == "⏹ STOP"


# ── Config ────────────────────────────────────────────────────────────────────

class TestConfig:
    def test_default_language_is_en(self):
        from focusguard.config import FocusGuardConfig
        cfg = FocusGuardConfig()
        assert cfg.language == "en"

    def test_idle_defaults_reasonable(self):
        from focusguard.config import FocusGuardConfig
        cfg = FocusGuardConfig()
        assert cfg.idle_screen_seconds >= 60
        assert cfg.idle_mouse_seconds >= 60
        assert cfg.idle_keyboard_seconds >= 120
        assert cfg.idle_action in ("pause", "warn", "both")

    def test_saveable_keys_lists_idle_fields(self):
        from focusguard.config import SAVEABLE_KEYS
        assert "idle_screen_seconds" in SAVEABLE_KEYS
        assert "idle_mouse_seconds"  in SAVEABLE_KEYS
        assert "idle_action"         in SAVEABLE_KEYS

    def test_all_saveable_keys_exist_on_config(self):
        from focusguard.config import FocusGuardConfig, SAVEABLE_KEYS
        cfg = FocusGuardConfig()
        for key in SAVEABLE_KEYS:
            assert hasattr(cfg, key), f"Missing config field: {key}"


# ── make_detector factory ─────────────────────────────────────────────────────

class TestMakeDetector:
    def test_factory_creates_detector(self):
        det = make_detector(screen_seconds=60, mouse_seconds=30, keyboard_seconds=120)
        assert det.cfg.screen_idle_seconds == 60
        assert det.cfg.mouse_idle_seconds  == 30
        assert det.cfg.keyboard_idle_seconds == 120

    def test_stop_without_start_is_safe(self):
        det = make_detector()
        det.stop()  # should not raise

    def test_double_stop_is_safe(self):
        det = make_detector()
        det.start()
        time.sleep(0.05)
        det.stop()
        det.stop()  # second stop should not raise


# ── Cooldown ──────────────────────────────────────────────────────────────────

class TestCooldown:
    def test_cooldown_prevents_rapid_refiring(self):
        fired: list = []
        frame = _solid_frame()

        cfg = IdleConfig(
            screen_idle_enabled=True,
            screen_idle_seconds=0,
            screen_diff_threshold=0.01,
            screen_check_interval=0.02,
            mouse_idle_enabled=False,
            keyboard_idle_enabled=False,
            cooldown_seconds=999,
        )
        det = IdleDetector(cfg=cfg, on_idle=lambda s, t: fired.append(s), capture_fn=lambda: frame)
        det.start()
        time.sleep(0.3)
        det.stop()
        # Even though many checks ran, cooldown should limit fires to 1
        screen_fires = fired.count(IdleSignal.SCREEN_FREEZE)
        assert screen_fires == 1
