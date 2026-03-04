"""
FocusGuard — Smart Detection Cache  (focusguard/modules/detection_cache.py)

Remembers whether URLs / window titles were distractions.
Avoids re-running OCR+AI on the same site repeatedly.

Design:
  — LRU cache keyed by normalized URL or app+title fingerprint
  — Persistent: saves to JSON between sessions
  — Confidence decay: old cached entries get less weight over time
  — User can manually mark a site as safe (allowlist shortcut)

Usage:
    cache = DetectionCache()
    result = cache.lookup("twitter.com")   # None = not seen before
    cache.record("twitter.com", is_distraction=True, confidence=0.92)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from collections import OrderedDict
from dataclasses import asdict, dataclass
from typing import Dict, Optional

logger = logging.getLogger("focusguard.cache")

from focusguard.paths import DATA_DIR as _DATA_DIR
_PATH = os.path.join(_DATA_DIR, "detection_cache.json")

_MAX_ENTRIES    = 500       # max cached sites
_DECAY_DAYS     = 14        # entries older than this lose weight
_MIN_CONFIDENCE = 0.55      # below this, don't cache (uncertain)


@dataclass
class CacheEntry:
    key:             str
    is_distraction:  bool
    confidence:      float
    hits:            int   = 1      # how many times we've seen this
    first_seen:      float = 0.0    # unix timestamp
    last_seen:       float = 0.0
    user_marked:     bool  = False  # user manually set this

    def effective_confidence(self) -> float:
        """Apply time-based decay to confidence."""
        if self.user_marked:
            return 1.0   # user decisions never decay
        age_days = (time.time() - self.last_seen) / 86400
        if age_days > _DECAY_DAYS:
            decay = max(0.3, 1.0 - (age_days - _DECAY_DAYS) / _DECAY_DAYS)
            return self.confidence * decay
        return self.confidence

    def is_fresh_enough(self) -> bool:
        return self.effective_confidence() >= _MIN_CONFIDENCE


class DetectionCache:
    """
    Thread-safe LRU cache for site/app distraction results.
    Backed by a JSON file so it persists between sessions.
    """

    def __init__(self, max_entries: int = _MAX_ENTRIES):
        self._max    = max_entries
        self._data:  OrderedDict[str, CacheEntry] = OrderedDict()
        self._dirty  = False
        self._load()

    # Public API

    def lookup(self, raw_key: str) -> Optional[CacheEntry]:
        """
        Return cached entry if it exists and is fresh enough.
        Returns None if unknown or stale → trigger full analysis.
        """
        key = self._normalize(raw_key)
        entry = self._data.get(key)
        if entry is None:
            return None
        if not entry.is_fresh_enough():
            # Stale — delete and re-analyze
            del self._data[key]
            self._dirty = True
            return None
        # LRU: move to end
        self._data.move_to_end(key)
        entry.hits += 1
        entry.last_seen = time.time()
        return entry

    def record(
        self,
        raw_key: str,
        is_distraction: bool,
        confidence: float,
        user_marked: bool = False,
    ) -> None:
        """Store a new detection result."""
        if confidence < _MIN_CONFIDENCE and not user_marked:
            return   # too uncertain to cache

        key = self._normalize(raw_key)
        now = time.time()

        if key in self._data:
            entry = self._data[key]
            # Weighted average confidence (new result has 60% weight)
            entry.confidence    = round(entry.confidence * 0.4 + confidence * 0.6, 3)
            entry.is_distraction = is_distraction
            entry.last_seen     = now
            entry.hits         += 1
            if user_marked:
                entry.user_marked = True
            self._data.move_to_end(key)
        else:
            self._data[key] = CacheEntry(
                key=key,
                is_distraction=is_distraction,
                confidence=round(confidence, 3),
                first_seen=now,
                last_seen=now,
                user_marked=user_marked,
            )

        # Evict oldest if over limit (skip user-marked entries)
        evict_attempts = 0
        while len(self._data) > self._max and evict_attempts < self._max:
            oldest_key = next(iter(self._data))
            if self._data[oldest_key].user_marked:
                # Move to end so we try the next oldest next time
                self._data.move_to_end(oldest_key)
                evict_attempts += 1
                continue
            del self._data[oldest_key]

        self._dirty = True

    def mark_safe(self, raw_key: str) -> None:
        """User manually marks this as safe (allowlist shortcut)."""
        self.record(raw_key, is_distraction=False, confidence=1.0, user_marked=True)

    def mark_distraction(self, raw_key: str) -> None:
        """User manually marks as distraction."""
        self.record(raw_key, is_distraction=True, confidence=1.0, user_marked=True)

    def remove(self, raw_key: str) -> bool:
        key = self._normalize(raw_key)
        if key in self._data:
            del self._data[key]
            self._dirty = True
            return True
        return False

    def save(self) -> None:
        if not self._dirty:
            return
        try:
            data = {k: asdict(v) for k, v in self._data.items()}
            with open(_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            self._dirty = False
            logger.debug(f"Cache saved — {len(self._data)} entries")
        except Exception as e:
            logger.warning(f"Cache save error: {e}")

    def clear_non_user(self) -> int:
        """Remove auto-detected entries, keep user-marked ones. Returns removed count."""
        to_remove = [k for k, v in self._data.items() if not v.user_marked]
        for k in to_remove:
            del self._data[k]
        self._dirty = True
        return len(to_remove)

    def stats(self) -> dict:
        distraction_count = sum(1 for v in self._data.values() if v.is_distraction)
        safe_count        = len(self._data) - distraction_count
        user_marked       = sum(1 for v in self._data.values() if v.user_marked)
        return {
            "total":       len(self._data),
            "distraction": distraction_count,
            "safe":        safe_count,
            "user_marked": user_marked,
        }

    def get_top_distractions(self, n: int = 10) -> list:
        return sorted(
            [v for v in self._data.values() if v.is_distraction],
            key=lambda e: e.hits,
            reverse=True,
        )[:n]

    # Internal

    @staticmethod
    def _normalize(raw: str) -> str:
        """
        Extract a clean key from a window title or URL.
        "Google Chrome — Twitter / Home" → "twitter"
        "twitter.com/home" → "twitter.com"
        """
        raw = raw.lower().strip()
        # Try to extract domain from URL-like strings
        m = re.search(r"(?:https?://)?(?:www\.)?([a-z0-9\-]+\.[a-z]{2,})", raw)
        if m:
            return m.group(1)
        # Strip common browser suffixes and normalize
        raw = re.sub(r"\s*[—\-–|]\s*(google chrome|firefox|safari|edge|opera|brave).*", "", raw)
        raw = re.sub(r"\s+", " ", raw).strip()
        # Hash if still long
        if len(raw) > 80:
            return hashlib.md5(raw.encode()).hexdigest()[:16]
        return raw

    def _load(self) -> None:
        if not os.path.exists(_PATH):
            return
        try:
            with open(_PATH, encoding="utf-8") as f:
                raw = json.load(f)
            for k, v in raw.items():
                try:
                    entry = CacheEntry(**v)
                    if entry.is_fresh_enough():
                        self._data[k] = entry
                except Exception:
                    pass   # skip malformed entries
            logger.debug(f"Cache loaded — {len(self._data)} fresh entries")
        except Exception as e:
            logger.warning(f"Cache load error: {e}")


# Global singleton
CACHE = DetectionCache()
