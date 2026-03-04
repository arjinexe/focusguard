"""
FocusGuard persistence layer.
Handles config, daily stats, achievements, and XP — stored as JSON in ~/.focusguard/.
"""

import csv
import json
import logging
import os
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from focusguard.config import ACHIEVEMENTS, SAVEABLE_KEYS

logger = logging.getLogger("focusguard.store")

# User data directory
# When installed via pip the repo root is not writable.
# Use ~/.focusguard/ (XDG-compliant on Linux, correct on Win/macOS).
from focusguard.paths import DATA_DIR as _DATA_DIR

SETTINGS_PATH = os.path.join(_DATA_DIR, "user_settings.json")
STATS_PATH    = os.path.join(_DATA_DIR, "daily_stats.json")
ACHIEVE_PATH  = os.path.join(_DATA_DIR, "achievements.json")
XP_PATH       = os.path.join(_DATA_DIR, "xp_data.json")

# _SAVEABLE replaced by SAVEABLE_KEYS from config
_SAVEABLE = SAVEABLE_KEYS


# Settings

def save_settings(config) -> bool:
    try:
        data = {}
        for k in _SAVEABLE:
            if hasattr(config, k):
                v = getattr(config, k)
                # lists are serializable
                data[k] = v
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.debug("Settings saved")
        return True
    except Exception as e:
        logger.warning(f"Settings save error: {e}")
        return False


def load_settings(config) -> bool:
    if not os.path.exists(SETTINGS_PATH):
        return False
    try:
        with open(SETTINGS_PATH, encoding="utf-8") as f:
            data: Dict[str, Any] = json.load(f)
        for k, v in data.items():
            if k in _SAVEABLE and hasattr(config, k):
                setattr(config, k, v)
        logger.info("Settings loaded")
        return True
    except Exception as e:
        logger.warning(f"Settings load error: {e}")
        return False


# Daily Stats

def _load_raw() -> dict:
    if not os.path.exists(STATS_PATH):
        return {}
    try:
        with open(STATS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_raw(data: dict):
    try:
        with open(STATS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.warning(f"Stats save error: {e}")


def _default_day() -> dict:
    return {
        "detections": 0,
        "work_seconds": 0,
        "sessions": 0,
        "pomodoros": 0,
        "best_clean_streak": 0,
        "max_escalation": 0,
        "xp_earned": 0,
        "avg_dwi": 0,
        "idle_events": 0,
    }


def record_session(detections: int, work_seconds: int, pomodoros: int = 0,
                   best_streak: int = 0, max_esc: int = 0, xp: int = 0,
                   dwi: int = 0, idle_events: int = 0):
    today = date.today().isoformat()
    raw = _load_raw()
    if today not in raw:
        raw[today] = _default_day()
    raw[today]["detections"]       += detections
    raw[today]["work_seconds"]     += work_seconds
    raw[today]["sessions"]         += 1
    raw[today]["pomodoros"]        += pomodoros
    raw[today]["best_clean_streak"] = max(raw[today].get("best_clean_streak", 0), best_streak)
    raw[today]["max_escalation"]    = max(raw[today].get("max_escalation", 0), max_esc)
    raw[today]["xp_earned"]        += xp
    # Update daily average DWI
    prev_dwi = raw[today].get("avg_dwi", 0)
    ses_count = raw[today]["sessions"]
    raw[today]["avg_dwi"] = round((prev_dwi * (ses_count - 1) + dwi) / ses_count, 1) if ses_count > 0 else dwi
    raw[today]["idle_events"] = raw[today].get("idle_events", 0) + idle_events
    _save_raw(raw)
    logger.debug(f"Stats updated: {today}")


def get_last_n_days(n: int = 7) -> list:
    raw = _load_raw()
    result = []
    today = date.today()
    for i in range(n - 1, -1, -1):
        d = (today - timedelta(days=i)).isoformat()
        entry = raw.get(d, _default_day())
        result.append({"date": d, **entry})
    return result


def get_today() -> dict:
    raw = _load_raw()
    today = date.today().isoformat()
    return raw.get(today, _default_day())


def get_total_focus_hours() -> float:
    raw = _load_raw()
    total_secs = sum(v.get("work_seconds", 0) for v in raw.values())
    return round(total_secs / 3600, 1)


def get_total_sessions() -> int:
    raw = _load_raw()
    return sum(v.get("sessions", 0) for v in raw.values())


def get_streak_days() -> int:
    """Return the current consecutive-day streak."""
    raw = _load_raw()
    streak = 0
    today = date.today()
    for i in range(365):
        d = (today - timedelta(days=i)).isoformat()
        if d in raw and raw[d].get("sessions", 0) > 0:
            streak += 1
        else:
            break
    return streak


def get_weekly_focus_hours() -> float:
    days = get_last_n_days(7)
    total = sum(d.get("work_seconds", 0) for d in days)
    return round(total / 3600, 1)


# XP System

def _load_xp() -> dict:
    if not os.path.exists(XP_PATH):
        return {"total_xp": 0, "level": 1, "history": []}
    try:
        with open(XP_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"total_xp": 0, "level": 1, "history": []}


def _save_xp(data: dict):
    try:
        with open(XP_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.warning(f"XP save error: {e}")


def xp_for_level(level: int) -> int:
    """Cumulative XP required to START a given level (level 1 = 0 XP)."""
    if level <= 1:
        return 0
    return 100 * (level - 1) * level // 2


def get_xp_info() -> dict:
    data = _load_xp()
    total = data.get("total_xp", 0)
    level = 1
    while xp_for_level(level + 1) <= total:
        level += 1
    current_xp = total - xp_for_level(level)
    next_xp    = xp_for_level(level + 1) - xp_for_level(level)
    return {
        "total_xp":   total,
        "level":      level,
        "current_xp": current_xp,
        "next_xp":    next_xp,
        "progress":   current_xp / max(1, next_xp),
    }


def add_xp(amount: int, reason: str = "") -> dict:
    """Add XP. Returns level-up info if the user advanced."""
    data = _load_xp()
    old_level = data.get("level", 1)
    data["total_xp"] = data.get("total_xp", 0) + amount
    data.setdefault("history", []).append({
        "ts": datetime.now().isoformat(),
        "amount": amount,
        "reason": reason,
    })
    # Recalculate level
    total = data["total_xp"]
    level = 1
    while xp_for_level(level + 1) <= total:
        level += 1
    data["level"] = level
    _save_xp(data)

    leveled_up = level > old_level
    return {"leveled_up": leveled_up, "new_level": level, "old_level": old_level}


def calculate_session_xp(work_seconds: int, detections: int, clean_streak: int) -> int:
    """Calculate XP earned at end of session — always returns a positive value."""
    base    = max(0, work_seconds // 60) * 2   # 2 XP per minute worked
    penalty = detections * 3                    # -3 XP per detection (reduced from 5)
    bonus   = clean_streak * 3                  # +3 XP per clean-streak tick
    # Minimum 5 XP for any completed session; penalty can never exceed the base earned
    return max(5, base + bonus - min(penalty, base))


# Achievements

def _load_achievements() -> dict:
    if not os.path.exists(ACHIEVE_PATH):
        return {}
    try:
        with open(ACHIEVE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_achievements(data: dict):
    try:
        with open(ACHIEVE_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.warning(f"Achievements save error: {e}")


def check_and_unlock_achievements(
    work_seconds: int,
    detections: int,
    sessions_today: int,
    clean_streak: int,
    pomodoros_total: int,
    idle_events_total: int = 0,
    strict_mode_session: bool = False,
) -> List[dict]:
    """Check conditions and unlock any new achievements. Returns newly unlocked ones."""
    unlocked_data = _load_achievements()
    newly_unlocked = []
    now = datetime.now().isoformat()

    hour = datetime.now().hour

    total_detections_ever = sum(d.get("detections", 0) for d in _load_raw().values())
    checks = {
        "first_session":   sessions_today >= 1,
        "clean_hour":      work_seconds >= 3600 and detections == 0,
        "no_distractions": detections == 0 and work_seconds >= 1200,
        "early_bird":      hour < 8 and sessions_today >= 1,
        "night_owl":       hour >= 23 and sessions_today >= 1,
        "marathon":        get_total_focus_hours() >= 5,
        "week_streak":     get_streak_days() >= 7,
        "pomodoro_master": pomodoros_total >= 50,       # desc says 50, was wrongly 100
        "ghost_fighter":   total_detections_ever >= 100, # all-time, was wrongly 10 + 30-day
        "deep_work":       clean_streak >= 60,           # 90 min at 1.5s interval ≈ 60 frames
        # Previously missing — these could never be unlocked:
        "idle_catcher":    idle_events_total >= 10,
        "comeback_kid":    idle_events_total >= 5,
        "speed_demon":     strict_mode_session and detections == 0 and work_seconds >= 1200,
    }

    for key, condition in checks.items():
        if condition and key not in unlocked_data:
            unlocked_data[key] = {"unlocked_at": now}
            achievement = ACHIEVEMENTS.get(key, {})
            newly_unlocked.append({
                "key": key,
                **achievement,
            })
            # XP ver
            xp = achievement.get("xp", 50)
            add_xp(xp, f"Achievement: {achievement.get('title', key)}")
            logger.info(f"Achievement unlocked: {key}")

    if newly_unlocked:
        _save_achievements(unlocked_data)

    return newly_unlocked


def get_all_achievements() -> List[dict]:
    """Return all achievements (locked and unlocked)."""
    unlocked = _load_achievements()
    result = []
    for key, info in ACHIEVEMENTS.items():
        result.append({
            "key": key,
            **info,
            "unlocked": key in unlocked,
            "unlocked_at": unlocked.get(key, {}).get("unlocked_at") if key in unlocked else None,
        })
    return result


def get_total_pomodoros() -> int:
    raw = _load_raw()
    return sum(v.get("pomodoros", 0) for v in raw.values())


def get_total_idle_events() -> int:
    raw = _load_raw()
    return sum(v.get("idle_events", 0) for v in raw.values())


# Export

def export_log(filepath: str, detections: list) -> bool:
    try:
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Time", "Confidence", "Reason", "Backend"])
            for d in detections:
                ts = datetime.fromtimestamp(d.timestamp).strftime("%Y-%m-%d %H:%M:%S")
                writer.writerow([ts, f"{d.confidence:.1%}", d.reason, d.backend])
        return True
    except Exception as e:
        logger.warning(f"Export error: {e}")
        return False


def export_stats_csv(filepath: str) -> bool:
    try:
        days = get_last_n_days(30)
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Date", "Detections", "Focus(min)", "Sessions", "Pomodoros", "XP", "AvgDWI"])
            for d in days:
                writer.writerow([
                    d["date"],
                    d["detections"],
                    d["work_seconds"] // 60,
                    d["sessions"],
                    d.get("pomodoros", 0),
                    d.get("xp_earned", 0),
                    d.get("avg_dwi", 0),
                ])
        return True
    except Exception as e:
        logger.warning(f"Stats export error: {e}")
        return False


# Autostart

def setup_autostart(enabled: bool, minimized: bool = True) -> bool:
    """
    Register FocusGuard to start with the OS.
    Windows: Registry, macOS: LaunchAgent, Linux: .desktop
    """
    import sys

    exe  = sys.executable
    args = "--minimized" if minimized else ""
    # Use `python -m focusguard` — works for both repo and installed package.
    cmd  = f'"{exe}" -m focusguard {args}'.strip()

    try:
        if sys.platform == "win32":
            import winreg
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, key_path, 0,
                winreg.KEY_SET_VALUE | winreg.KEY_READ
            )
            if enabled:
                winreg.SetValueEx(key, "FocusGuard", 0, winreg.REG_SZ, cmd)
                logger.info("Windows autostart added")
            else:
                try:
                    winreg.DeleteValue(key, "FocusGuard")
                    logger.info("Windows autostart removed")
                except FileNotFoundError:
                    pass
            winreg.CloseKey(key)
            return True

        elif sys.platform == "darwin":
            plist_dir = os.path.expanduser("~/Library/LaunchAgents")
            plist_path = os.path.join(plist_dir, "com.focusguard.plist")
            os.makedirs(plist_dir, exist_ok=True)
            if enabled:
                args_xml = f"        <string>{args}</string>" if args else ""
                plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.focusguard</string>
    <key>ProgramArguments</key>
    <array>
        <string>{exe}</string>
        <string>-m</string>
        <string>focusguard</string>
{args_xml}
    </array>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><false/>
</dict>
</plist>"""
                with open(plist_path, "w") as pf:
                    pf.write(plist)
                os.system(f"launchctl load {plist_path} 2>/dev/null")
                logger.info("macOS LaunchAgent added")
            else:
                if os.path.exists(plist_path):
                    os.system(f"launchctl unload {plist_path} 2>/dev/null")
                    os.remove(plist_path)
                logger.info("macOS LaunchAgent removed")
            return True

        else:  # Linux
            desktop_dir = os.path.expanduser("~/.config/autostart")
            desktop_path = os.path.join(desktop_dir, "focusguard.desktop")
            os.makedirs(desktop_dir, exist_ok=True)
            if enabled:
                desktop = f"""[Desktop Entry]
Type=Application
Name=FocusGuard
Exec={cmd}
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
Comment=FocusGuard - Focus enforcement tool
"""
                with open(desktop_path, "w") as df:
                    df.write(desktop)
                logger.info("Linux autostart .desktop added")
            else:
                if os.path.exists(desktop_path):
                    os.remove(desktop_path)
                logger.info("Linux autostart removed")
            return True

    except Exception as e:
        logger.error(f"Autostart error: {e}")
        return False


def is_autostart_enabled() -> bool:
    """Autostart aktif mi kontrol et."""
    import sys
    try:
        if sys.platform == "win32":
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0, winreg.KEY_READ
            )
            try:
                winreg.QueryValueEx(key, "FocusGuard")
                winreg.CloseKey(key)
                return True
            except FileNotFoundError:
                winreg.CloseKey(key)
                return False
        elif sys.platform == "darwin":
            plist = os.path.expanduser("~/Library/LaunchAgents/com.focusguard.plist")
            return os.path.exists(plist)
        else:
            desktop = os.path.expanduser("~/.config/autostart/focusguard.desktop")
            return os.path.exists(desktop)
    except Exception:
        return False
