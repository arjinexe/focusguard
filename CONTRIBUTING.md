# Contributing

## Setup

```bash
git clone https://github.com/your-username/focusguard
cd focusguard
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev,keyboard]"
```

Tests:
```bash
pytest tests/ -v
```

Lint:
```bash
ruff check focusguard/ tests/
```

---

## Making changes

The codebase is straightforward. Each module has a single job:

- **`analyzer.py`** — takes a screenshot, returns `AnalysisResult(confidence, reason, backend_used, ms)`
- **`resistance.py`** — given confidence + escalation level, fires countermeasures
- **`session.py`** — state machine that ties everything together
- **`gui.py`** — CustomTkinter UI, polls a queue from session thread

The main loop is in `session.py._tick()`. That's the place to understand data flow.

---

## Adding a new language

Copy `focusguard/locales/en.py` to `focusguard/locales/xx.py` (ISO 639-1 code), translate every string, add the code to `i18n.set_locale()`, and add a radio button in the Settings language selector in `gui.py`.

Keys that contain `{placeholder}` formatting need to keep the exact placeholder names.

---

## Adding a resistance mechanism

Add a method to `ResistanceController` in `resistance.py`, add a config key to `FocusGuardConfig` in `config.py`, add a toggle + description to the modes list in `gui.py _build_settings_tab()`, and add two locale strings (`your_thing_title`, `your_thing_desc`) to both locale files.

---

## Adding an achievement

One dict entry in `ACHIEVEMENTS` in `config.py`:

```python
{
    "key":       "your_key",
    "icon":      "🎯",
    "xp":        100,
    "condition": lambda stats, store: <bool>,
}
```

Two locale strings per language: `ach_your_key_title` and `ach_your_key_desc`.

Achievement checks run at session end in `store.check_achievements()`.

---

## Tests

Tests live in `tests/`. The current suite covers `IdleDetector` without needing a screen or GUI. New tests should follow the same pattern — no live display required.

---

## Code style

`ruff` for linting, `mypy` for types. Line length is 100. Docstrings where intent isn't obvious from the code. No elaborate section dividers.
