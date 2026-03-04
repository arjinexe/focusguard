# Changelog

---

## [Unreleased]

### Fixed

- macOS autostart pointed at non-existent `main.py` → now uses `python -m focusguard`
- `analytics.py`, `intentions.py`, `detection_cache.py` wrote to repo root → moved to `~/.focusguard/`
- `on_idle` callback was `None` in GUI mode — idle events silently dropped instead of toasting
- `WindowTracker.record_detection()` was never called — per-app stats were always 0
- `SurpriseJitterScheduler` was never started during sessions
- DWI was computed but never displayed — now shown in Stats tab and session summary
- Break suggestions were computed but never surfaced in the UI
- `store.record_session()` missing `dwi` and `idle_events` parameters
- Motivation cycle thread leaked after window close
- `pomodoro_master` achievement threshold was 100 (should be 50)
- `ghost_fighter` achievement used wrong time window (last 30 days, not all-time)
- `idle_catcher`, `comeback_kid`, `speed_demon` achievements could never unlock
- `_session_count` not reset on stop — Pomodoro ring showed wrong session number
- Break suggestion label not cleared on focus resume
- Auto-break check was inside the wrong state branch — never fired
- LRU cache eviction loop broke early on user-marked entries, exceeding max size
- Analytics `get_best_hours()` included zero-count hours in results

### Added

- Idle Detection settings section — all thresholds and action mode configurable
- Ambient sound section in Settings — type and volume slider
- Language selector (English / Türkçe)
- Pre-session intention dialog with quick-pick templates
- Achievement locale strings (EN + TR) for all 13 achievements
- Platform-adaptive font selection (Segoe UI / Helvetica / DejaVu Sans)
- Full i18n coverage — zero hardcoded UI strings outside locale files

---

## [5.0.0] — 2025-03

### Added

- Idle detection — screen freeze (SSIM diff), mouse idle, keyboard idle (pynput)
- i18n / localisation — English + Turkish, locale switcher in Settings
- `focusguard/locales/en.py`, `focusguard/locales/tr.py`
- `focusguard/i18n.py` with `t(key)` helper
- `pyproject.toml` — proper Python packaging
- `focusguard/__main__.py` — `python -m focusguard` entry point
- GitHub Actions CI — lint + test across Python 3.9–3.12 on Win/macOS/Linux
- `CONTRIBUTING.md`
- `tests/test_idle_detector.py` — 15 unit tests
- `idle_action` config: `"pause"` / `"warn"` / `"both"`
- `--lang` CLI argument

### Changed

- Package restructured: all imports use `focusguard.*` namespace
- `config.py` now exports `SAVEABLE_KEYS` as single source of truth

---

## [4.x] — 2024

- Original internal release. Single-file script, no packaging, Turkish-only UI.
