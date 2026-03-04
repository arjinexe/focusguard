"""
Data directory resolution for FocusGuard.

All persistent data (stats, cache, settings, logs) lives under a `data/`
folder inside the project directory — not in the system user profile.
This keeps everything in one place and makes it easy to back up or move.
"""

import os

# Project root = two levels up from this file (focusguard/paths.py → focusguard/ → project/)
_here    = os.path.dirname(os.path.abspath(__file__))
_project = os.path.dirname(_here)

DATA_DIR = os.path.join(_project, "data")
LOG_DIR  = os.path.join(_project, "logs")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(LOG_DIR,  exist_ok=True)


def data(filename: str) -> str:
    return os.path.join(DATA_DIR, filename)


def log(filename: str) -> str:
    return os.path.join(LOG_DIR, filename)
