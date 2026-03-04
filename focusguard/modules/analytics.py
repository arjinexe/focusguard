"""
FocusGuard analytics — DWI, heatmap, performance log.

Deep Work Index (DWI) is a 0–100 session quality score:
  clean streak ratio (40%), distraction density (30%),
  session continuity (20%), idle fraction (10%).
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections import defaultdict
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("focusguard.analytics")

from focusguard.paths import DATA_DIR as _DATA_DIR
_HEAT_PATH = os.path.join(_DATA_DIR, "heatmap_data.json")
_PERF_PATH = os.path.join(_DATA_DIR, "performance_log.json")


# Deep Work Index

def compute_dwi(
    work_seconds:       float,
    detections:         int,
    best_clean_streak:  int,    # frames (at session_interval per frame)
    idle_events:        int,
    session_interval:   float = 1.5,
) -> int:
    """
    Deep Work Index (0-100). Components:
      clean_ratio  40%  best uninterrupted block as % of session
      density      30%  inverse of detections/hr
      continuity   20%  penalise idle interruptions
      idle_penalty 10%  time lost to idle pauses
    """
    if work_seconds < 60:
        return 0
    focus_hours   = work_seconds / 3600.0
    clean_seconds = best_clean_streak * session_interval
    clean_ratio   = min(1.0, clean_seconds / max(1, work_seconds))
    c1 = clean_ratio * 40
    det_per_hour  = detections / max(0.01, focus_hours)
    c2 = max(0.0, 1.0 - det_per_hour / 20.0) * 30
    idle_per_hour = idle_events / max(0.01, focus_hours)
    c3 = max(0.0, 1.0 - idle_per_hour * 0.15) * 20
    idle_fraction = min(1.0, (idle_events * 120) / max(1, work_seconds))
    c4 = (1.0 - idle_fraction) * 10
    return max(0, min(100, round(c1 + c2 + c3 + c4)))


def dwi_label(score: int) -> Tuple[str, str]:
    """Return (label, color) for a DWI score."""
    if score >= 90:
        return "🌊 FLOW STATE",   "#00FF88"
    if score >= 75:
        return "⚡ DEEP WORK",    "#00E5FF"
    if score >= 60:
        return "🎯 FOCUSED",      "#2979FF"
    if score >= 45:
        return "📉 DISTRACTED",   "#FFB300"
    if score >= 25:
        return "⚠ FRAGMENTED",   "#FF6040"
    return "💤 SCATTERED",        "#FF2055"


# Distraction Heatmap

class DistractionHeatmap:
    """
    Records when (hour of day) distractions happen.
    Persists to JSON. Renders as 24-bucket histogram.
    """

    def __init__(self):
        self._data: Dict[str, Dict[int, int]] = {}   # date → {hour: count}
        self._load()

    def record(self, timestamp: Optional[float] = None) -> None:
        ts   = timestamp or time.time()
        dt   = datetime.fromtimestamp(ts)
        day  = dt.strftime("%Y-%m-%d")
        hour = dt.hour
        self._data.setdefault(day, {str(h): 0 for h in range(24)})
        self._data[day][str(hour)] = self._data[day].get(str(hour), 0) + 1
        self._save()

    def get_today(self) -> Dict[int, int]:
        day = date.today().isoformat()
        raw = self._data.get(day, {})
        return {h: raw.get(str(h), 0) for h in range(24)}

    def get_aggregate(self, days: int = 30) -> Dict[int, int]:
        """Aggregate hourly counts over the last N days."""
        result: Dict[int, int] = defaultdict(int)
        cutoff = date.today() - timedelta(days=days)
        for day_str, hourly in self._data.items():
            try:
                d = date.fromisoformat(day_str)
                if d >= cutoff:
                    for h, cnt in hourly.items():
                        result[int(h)] += cnt
            except Exception:
                pass
        return dict(result)

    def get_worst_hours(self, n: int = 3, days: int = 30) -> List[Tuple[int, int]]:
        """Return top N worst hours (hour, total_detections)."""
        agg = self.get_aggregate(days)
        return sorted(agg.items(), key=lambda x: x[1], reverse=True)[:n]

    def get_best_hours(self, n: int = 3, days: int = 30) -> List[Tuple[int, int]]:
        """Return top N cleanest hours (fewest distractions)."""
        agg = self.get_aggregate(days)
        # Only include hours with some data
        non_zero = [(h, c) for h, c in agg.items() if c > 0]
        return sorted(non_zero, key=lambda x: x[1])[:n]

    def _save(self) -> None:
        try:
            with open(_HEAT_PATH, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2)
        except Exception as e:
            logger.debug(f"Heatmap save error: {e}")

    def _load(self) -> None:
        if not os.path.exists(_HEAT_PATH):
            return
        try:
            with open(_HEAT_PATH, encoding="utf-8") as f:
                self._data = json.load(f)
        except Exception as e:
            logger.warning(f"Heatmap load error: {e}")


# Performance log

class PerformanceLog:
    """
    Stores per-session DWI scores for trend analysis.
    Answers: "Am I improving over time?"
    """

    def __init__(self):
        self._entries: List[dict] = []
        self._load()

    def record_session(
        self,
        dwi:            int,
        work_seconds:   float,
        detections:     int,
        pomodoros:      int,
        intention_text: str = "",
        intention_met:  Optional[bool] = None,
    ) -> None:
        entry = {
            "ts":           time.time(),
            "date":         date.today().isoformat(),
            "dwi":          dwi,
            "work_min":     round(work_seconds / 60, 1),
            "detections":   detections,
            "pomodoros":    pomodoros,
            "intention":    intention_text,
            "achieved":     intention_met,
        }
        self._entries.append(entry)
        self._save()

    def get_dwi_trend(self, days: int = 14) -> List[Tuple[str, float]]:
        """
        Return (date, avg_dwi) per day for the last N days.
        Used to draw a trend line in the Stats tab.
        """
        cutoff = time.time() - days * 86400
        by_day: Dict[str, List[int]] = defaultdict(list)
        for e in self._entries:
            if e.get("ts", 0) >= cutoff:
                by_day[e["date"]].append(e.get("dwi", 0))
        today = date.today()
        result = []
        for i in range(days - 1, -1, -1):
            d = (today - timedelta(days=i)).isoformat()
            scores = by_day.get(d, [])
            avg = round(sum(scores) / len(scores), 1) if scores else 0.0
            result.append((d, avg))
        return result

    def get_summary(self) -> dict:
        if not self._entries:
            return {"sessions": 0, "avg_dwi": 0, "best_dwi": 0, "trend": "—"}
        scores = [e.get("dwi", 0) for e in self._entries]
        avg    = round(sum(scores) / len(scores), 1)
        best   = max(scores)
        # Simple trend: compare last 5 vs previous 5
        if len(scores) >= 10:
            recent = sum(scores[-5:]) / 5
            older  = sum(scores[-10:-5]) / 5
            trend  = "📈 Improving" if recent > older + 3 else ("📉 Declining" if recent < older - 3 else "➡ Stable")
        else:
            trend = "—"
        return {
            "sessions": len(self._entries),
            "avg_dwi":  avg,
            "best_dwi": best,
            "trend":    trend,
        }

    def _save(self) -> None:
        try:
            # Keep last 365 sessions
            if len(self._entries) > 365:
                self._entries = self._entries[-365:]
            with open(_PERF_PATH, "w", encoding="utf-8") as f:
                json.dump(self._entries, f, indent=2)
        except Exception as e:
            logger.debug(f"PerfLog save error: {e}")

    def _load(self) -> None:
        if not os.path.exists(_PERF_PATH):
            return
        try:
            with open(_PERF_PATH, encoding="utf-8") as f:
                self._entries = json.load(f)
        except Exception as e:
            logger.warning(f"PerfLog load error: {e}")


# Smart break suggestions

BREAK_SUGGESTIONS: Dict[int, List[str]] = {
    1: [   # After 1 pomodoro
        "💧 Drink a glass of water",
        "👀 Look at something 20m away for 20 seconds (20-20-20 rule)",
        "🙆 Roll your shoulders 5 times",
        "🌬 Take 3 deep breaths",
    ],
    2: [   # After 2 pomodoros
        "🚶 Walk around for 5 minutes",
        "🤸 5 minutes of light stretching",
        "🧘 Short meditation or breathing exercise",
        "☕ Make a hot drink, away from screens",
    ],
    3: [   # After 3 pomodoros
        "🌤 Go outside for 10 minutes — natural light resets your focus",
        "🏃 Do 10 jumping jacks or a short walk",
        "🥗 Eat something nutritious if you haven't",
        "💬 Brief non-work conversation (social recharge)",
    ],
    4: [   # After 4+ pomodoros (long break time)
        "🛋 Lie down for 10-20 minutes — power nap if tired",
        "🌳 20 minute walk, ideally in nature",
        "🍽 Proper meal — don't eat at the desk",
        "🎵 Listen to music with your eyes closed",
    ],
}


def get_break_suggestion(pomodoros_completed: int) -> str:
    """Return a contextual break suggestion based on fatigue level."""
    import random
    tier = min(4, max(1, pomodoros_completed))
    suggestions = BREAK_SUGGESTIONS.get(tier, BREAK_SUGGESTIONS[1])
    return random.choice(suggestions)


# Global singletons
HEATMAP  = DistractionHeatmap()
PERF_LOG = PerformanceLog()
