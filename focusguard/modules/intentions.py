"""
FocusGuard — Session Intentions  (focusguard/modules/intentions.py)

Research-backed accountability feature:
  Writing what you intend to do before a session increases follow-through
  by 20-30% (implementation intention effect, Gollwitzer 1999).

Features:
  — Pre-session intention setting: "What will you accomplish?"
  — Post-session review: "Did you do it?" + free-form reflection
  — Persistent log (JSON) with streak tracking
  — "Commitment score" derived from completion rate
  — Quick suggestion templates by category

Usage:
    mgr = IntentionManager()
    mgr.set_intention("Finish the auth module", category="code")
    # ... session runs ...
    mgr.complete_intention(achieved=True, reflection="Finished + wrote tests")
    history = mgr.get_history(30)
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger("focusguard.intentions")

from focusguard.paths import DATA_DIR as _DATA_DIR
_PATH = os.path.join(_DATA_DIR, "intentions.json")

# Template suggestions by category
INTENTION_TEMPLATES: Dict[str, List[str]] = {
    "code": [
        "Finish the feature I started yesterday",
        "Write tests for the auth module",
        "Fix the 3 bugs in the backlog",
        "Refactor the payment service",
        "Review and merge open PRs",
    ],
    "write": [
        "Write 500 words of the article",
        "Finish the introduction section",
        "Edit and polish chapter 3",
        "Draft the email to the client",
        "Outline next week's blog post",
    ],
    "study": [
        "Complete the chapter on linear algebra",
        "Watch 2 lecture videos and take notes",
        "Finish the practice problem set",
        "Review yesterday's flashcards",
        "Read 30 pages without distraction",
    ],
    "design": [
        "Complete the landing page mockup",
        "Iterate on the 3 user flow screens",
        "Review design system consistency",
        "Prepare the client presentation",
        "Finish the icon set",
    ],
    "general": [
        "Complete my most important task first",
        "Make meaningful progress on the project",
        "Stay focused for the whole session",
        "No social media for the entire session",
        "Finish what I promised myself yesterday",
    ],
}


@dataclass
class Intention:
    text:       str
    category:   str      = "general"
    created_at: float    = 0.0      # unix timestamp
    session_id: str      = ""

    # Filled in after session
    achieved:    Optional[bool]  = None
    reflection:  str             = ""
    completed_at: float          = 0.0
    session_minutes: float       = 0.0
    detections: int              = 0

    @property
    def is_pending(self) -> bool:
        return self.achieved is None

    @property
    def date_str(self) -> str:
        return datetime.fromtimestamp(self.created_at).strftime("%Y-%m-%d %H:%M")

    def to_dict(self) -> dict:
        return asdict(self)


class IntentionManager:

    def __init__(self):
        self._intentions: List[dict] = []
        self._pending_id: Optional[str] = None
        self._load()

    # API

    def set_intention(self, text: str, category: str = "general") -> str:
        """
        Record intention at session start.
        Returns a session_id to link with completion.
        """
        text = text.strip()
        if not text:
            return ""

        session_id = f"s_{int(time.time())}"
        intent = Intention(
            text=text,
            category=category,
            created_at=time.time(),
            session_id=session_id,
        )
        self._intentions.append(intent.to_dict())
        self._pending_id = session_id
        self._save()
        logger.info(f"Intention set: {text!r}")
        return session_id

    def complete_intention(
        self,
        achieved: bool,
        reflection: str = "",
        session_minutes: float = 0.0,
        detections: int = 0,
        session_id: Optional[str] = None,
    ) -> bool:
        """Mark the current (or specified) intention as completed."""
        target_id = session_id or self._pending_id
        if not target_id:
            return False

        for entry in reversed(self._intentions):
            if entry.get("session_id") == target_id and entry.get("achieved") is None:
                entry["achieved"]        = achieved
                entry["reflection"]      = reflection.strip()
                entry["completed_at"]    = time.time()
                entry["session_minutes"] = round(session_minutes, 1)
                entry["detections"]      = detections
                if self._pending_id == target_id:
                    self._pending_id = None
                self._save()
                logger.info(f"Intention completed: achieved={achieved}")
                return True
        return False

    def get_pending(self) -> Optional[dict]:
        """Return the most recent uncompleted intention, if any."""
        for entry in reversed(self._intentions):
            if entry.get("achieved") is None:
                return entry
        return None

    def get_history(self, days: int = 30) -> List[dict]:
        """Return completed intentions from the last N days."""
        cutoff = time.time() - days * 86400
        return [
            e for e in self._intentions
            if e.get("created_at", 0) >= cutoff and e.get("achieved") is not None
        ]

    def get_commitment_score(self) -> float:
        """
        Percentage of intentions that were marked as achieved.
        0.0–1.0. Only counts sessions with an explicit yes/no.
        """
        completed = [e for e in self._intentions if e.get("achieved") is not None]
        if not completed:
            return 0.0
        achieved = sum(1 for e in completed if e.get("achieved") is True)
        return round(achieved / len(completed), 2)

    def get_stats(self) -> dict:
        completed = [e for e in self._intentions if e.get("achieved") is not None]
        achieved  = [e for e in completed if e.get("achieved")]
        return {
            "total":            len(self._intentions),
            "completed":        len(completed),
            "achieved":         len(achieved),
            "commitment_score": self.get_commitment_score(),
            "avg_session_min":  (
                round(sum(e.get("session_minutes", 0) for e in completed) / max(1, len(completed)), 1)
            ),
        }

    def get_templates(self, category: str = "general") -> List[str]:
        return INTENTION_TEMPLATES.get(category, INTENTION_TEMPLATES["general"])

    def all_categories(self) -> List[str]:
        return list(INTENTION_TEMPLATES.keys())

    # Persistence

    def _save(self) -> None:
        try:
            with open(_PATH, "w", encoding="utf-8") as f:
                json.dump(self._intentions, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"Intentions save error: {e}")

    def _load(self) -> None:
        if not os.path.exists(_PATH):
            return
        try:
            with open(_PATH, encoding="utf-8") as f:
                self._intentions = json.load(f)
            # Find any pending
            for entry in reversed(self._intentions):
                if entry.get("achieved") is None:
                    self._pending_id = entry.get("session_id")
                    break
            logger.debug(f"Intentions loaded: {len(self._intentions)} entries")
        except Exception as e:
            logger.warning(f"Intentions load error: {e}")
            self._intentions = []


# Global singleton
INTENTIONS = IntentionManager()
