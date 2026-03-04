"""
focusguard.__main__
Entry point: python -m focusguard  OR  the `focusguard` console script.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys


def _setup_logging(log_dir: str, level: str) -> None:
    from focusguard.paths import LOG_DIR
    os.makedirs(LOG_DIR, exist_ok=True)
    fmt = "%(asctime)s  %(levelname)-7s  %(name)s — %(message)s"
    handlers: list = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(LOG_DIR, "focusguard.log"), encoding="utf-8"),
    ]
    logging.basicConfig(level=getattr(logging, level, logging.INFO),
                        format=fmt, datefmt="%H:%M:%S", handlers=handlers)
    for noisy in ("PIL", "easyocr", "torch", "urllib3", "httpx"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="focusguard",
        description="FocusGuard — Local distraction detection & resistance engine",
    )
    parser.add_argument("--cli",        action="store_true", help="Headless terminal mode")
    parser.add_argument("--test",       action="store_true", help="Test resistance mechanisms")
    parser.add_argument("--minimized",  action="store_true", help="Start minimized")
    parser.add_argument("--lang",       choices=["en", "tr"], help="UI language")
    parser.add_argument("--interval",   type=float, metavar="S",  help="Analysis interval (seconds)")
    parser.add_argument("--threshold",  type=float, metavar="F",  help="Confidence threshold 0.0–1.0")
    parser.add_argument("--model",      type=str,                 help="Ollama model name")
    parser.add_argument("--log-level",  default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"], help="Log verbosity")
    args = parser.parse_args()

    # Config + settings
    from focusguard.config import CONFIG
    from focusguard.modules import store
    store.load_settings(CONFIG)

    # i18n — CLI arg overrides saved setting
    lang = args.lang or CONFIG.language or "en"
    CONFIG.language = lang
    from focusguard.i18n import set_locale
    set_locale(lang)

    # CLI overrides
    if args.interval:
        CONFIG.screenshot_interval = max(0.2, args.interval)
    if args.threshold:
        CONFIG.confidence_threshold = max(0.1, min(0.99, args.threshold))
    if args.model:
        CONFIG.ollama_model = args.model

    _setup_logging(None, args.log_level)

    if args.test:
        _run_test()
    elif args.cli:
        _run_cli(CONFIG)
    else:
        _run_gui(CONFIG, minimized=args.minimized or CONFIG.autostart_minimized)


def main_cli() -> None:
    """Alias for `focusguard-cli` console script."""
    sys.argv.insert(1, "--cli")
    main()


# Runners

def _run_gui(config, minimized: bool = False) -> None:
    try:
        from focusguard.modules.gui import FocusGuardApp
    except ImportError as e:
        print(f"\n[ERROR] GUI dependencies missing: {e}")
        print("Fix: pip install focusguard[gui]  or  pip install -r requirements.txt\n")
        sys.exit(1)
    app = FocusGuardApp(minimized=minimized)
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()


def _run_cli(config) -> None:
    import signal, time
    from focusguard.modules.screen_capture import ScreenCapture
    from focusguard.modules.analyzer       import HybridAnalyzer
    from focusguard.modules.resistance     import ResistanceController

    print("\n  FocusGuard — Headless Mode   Ctrl+C to quit\n")
    cap      = ScreenCapture()
    analyzer = HybridAnalyzer()
    resist   = ResistanceController()
    dirty    = 0

    def _exit(sig, frame):
        print("\n\n  [FocusGuard] Session ended. Stay focused. 🎯\n")
        cap.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, _exit)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _exit)

    while True:
        t0    = time.perf_counter()
        frame = cap.capture()
        if frame:
            b64 = cap.to_base64(frame)
            res = analyzer.analyze(frame.array, b64)
            status = "\033[91m🔴 DISTRACTION\033[0m" if res.is_distraction else "\033[92m🟢 CLEAN\033[0m"
            print(f"\r  {status}  conf={res.confidence:.2f}  [{res.backend_used}]  "
                  f"{res.analysis_ms:.0f}ms  {(res.reason or '')[:40]:<40}", end="", flush=True)
            if res.is_distraction:
                dirty += 1
                if dirty >= config.min_dirty_streak:
                    resist.trigger(res.reason, res.confidence)
            else:
                if dirty >= config.min_dirty_streak:
                    resist.reset()
                dirty = 0
        elapsed = time.perf_counter() - t0
        time.sleep(max(0.05, config.screenshot_interval - elapsed))


def _run_test() -> None:
    import time
    from focusguard.modules.resistance import ResistanceController
    print("\n[FocusGuard] Testing resistance mechanisms...\n")
    r = ResistanceController()
    print("  • Mouse jitter test (3s)...")
    r.jitter.start(intensity=15, duration=3.0)
    time.sleep(3.5)
    print("  • Terminal shame test...")
    r.shamer.fire(level=2, reason="test mode")
    time.sleep(0.5)
    print("  • Sound alert test...")
    r.sounder.beep(level=1)
    time.sleep(0.5)
    print("\n[FocusGuard] Test complete ✓\n")


if __name__ == "__main__":
    main()
