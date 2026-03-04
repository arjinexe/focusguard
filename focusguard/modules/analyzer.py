"""
Hybrid distraction analysis pipeline.

Three layers run in sequence:
  1. OpenCV     — scroll motion and card layout detection (fast, CPU-only)
  2. EasyOCR    — reads the address bar for known distraction domains
  3. Ollama     — vision model inspects page content (optional, most accurate)

Design notes:
  - OpenCV (layer 1) is intentionally conservative. Scroll motion and card
    layouts appear on plenty of productive sites: GitHub issue lists, email
    clients, scrollable docs pages. It contributes to the fused score but
    cannot trigger an alert on its own — it needs support from OCR or Ollama.

  - OCR (layer 2) only reads the address bar strip, not the page body.
    Scanning the full page caused false positives whenever a keyword like
    "trending" appeared anywhere in page content.

  - Ollama (layer 3) sees the cropped page content (tab bar removed) and
    makes the final call for ambiguous cases. Its explicit is_distraction
    judgment is used as a confidence floor so weighted averaging cannot
    suppress a clear positive signal.

  - The tab bar is always cropped before sending frames to Ollama. This
    prevents background tab titles (e.g. an Instagram tab the user has open
    but is not actively viewing) from influencing the result.
"""

import json
import logging
import re
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

import cv2
import numpy as np
import requests

from focusguard.config import CONFIG, OLLAMA_VISION_PROMPT

logger = logging.getLogger("focusguard.analyzer")


@dataclass
class AnalysisResult:
    is_distraction: bool
    confidence:     float
    reason:         str
    backend_used:   str
    analysis_ms:    float
    keywords_found: List[str] = field(default_factory=list)


# ── Layer 1: Scroll detector ──────────────────────────────────────────────────

class ScrollDetector:
    _HISTORY = 6

    def __init__(self):
        self._frames: deque = deque(maxlen=self._HISTORY)
        self._score  = 0.0

    def update(self, frame: np.ndarray) -> Tuple[bool, float]:
        gray  = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
        small = cv2.resize(gray, (160, 90), interpolation=cv2.INTER_AREA)

        if len(self._frames) >= 2:
            diff = cv2.absdiff(small, self._frames[-1]).mean()
            # Scroll-like motion: not static, not a rapid scene change
            if 2.5 < diff < 30.0:
                self._score = min(1.0, self._score + 0.30)
            else:
                self._score = max(0.0, self._score - 0.20)

        self._frames.append(small)
        return self._score >= CONFIG.scroll_streak_threshold / 5.0, round(self._score, 3)

    def reset(self):
        self._score = 0.0
        self._frames.clear()


# ── Layer 2: Card layout detector ─────────────────────────────────────────────

class CardLayoutDetector:
    """Detects the regular horizontal-band pattern common in social media feeds."""

    @staticmethod
    def detect(frame: np.ndarray) -> Tuple[bool, float]:
        gray    = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
        sobel_y = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
        row_e   = np.abs(sobel_y).mean(axis=1)
        mx = row_e.max()
        if mx < 1e-6:
            return False, 0.0

        norm  = row_e / mx
        peaks = [i for i in range(1, len(norm) - 1)
                 if norm[i] > 0.28 and norm[i] >= norm[i-1] and norm[i] >= norm[i+1]]

        if len(peaks) < 5:
            return False, 0.0

        gaps     = [peaks[i+1] - peaks[i] for i in range(len(peaks)-1)]
        mean_gap = float(np.mean(gaps))
        if mean_gap < 5:
            return False, 0.0

        regularity = 1.0 - min(1.0, float(np.std(gaps)) / (mean_gap + 1e-6))
        ok = regularity > CONFIG.card_regularity_threshold and len(peaks) >= 6
        return ok, round(regularity, 3)


# ── Layer 3: OCR ─────────────────────────────────────────────────────────────

class OCRAnalyzer:
    def __init__(self, ready_callback: Optional[Callable] = None):
        self._reader  = None
        self.is_ready = False
        self._cb      = ready_callback
        threading.Thread(target=self._load, daemon=True).start()

    def _load(self):
        try:
            import easyocr
            try:
                self._reader = easyocr.Reader(["en"], gpu=True,  verbose=False)
            except Exception:
                self._reader = easyocr.Reader(["en"], gpu=False, verbose=False)
            self.is_ready = True
            logger.info("EasyOCR ready")
            if self._cb:
                self._cb("ocr", True)
        except ImportError:
            logger.warning("EasyOCR not installed — OCR layer disabled")
            if self._cb:
                self._cb("ocr", False)
        except Exception as e:
            logger.warning(f"EasyOCR init failed: {e}")
            if self._cb:
                self._cb("ocr", False)

    def analyze(
        self,
        frame: np.ndarray,
        nav_fullres: Optional[np.ndarray] = None,
    ) -> Tuple[bool, float, List[str]]:
        """Read only the address bar strip and match against known distraction domains.

        We deliberately skip page body text. A word like "reels" in a Reddit
        thread about social media is not a distraction signal. The URL in the
        address bar is the only unambiguous indicator of what site is loaded.
        """
        if not self.is_ready or self._reader is None:
            return False, 0.0, []
        try:
            src = nav_fullres if nav_fullres is not None else frame[:max(80, frame.shape[0] // 8), :]
            nh, nw = src.shape[:2]

            # Upscale 2× so small address-bar text becomes readable
            up   = cv2.resize(src, (nw * 2, nh * 2), interpolation=cv2.INTER_CUBIC)
            gray = cv2.cvtColor(up, cv2.COLOR_RGB2GRAY)
            eq3  = cv2.cvtColor(cv2.equalizeHist(gray), cv2.COLOR_GRAY2RGB)

            texts: List[str] = []
            for strip in (up, eq3):
                texts.extend(self._reader.readtext(strip, detail=0, paragraph=True))

            joined = " ".join(texts).lower()
            found  = [kw for kw in CONFIG.ocr_domains if kw in joined]
            if not found:
                return False, 0.0, []

            conf = min(1.0, 0.82 + len(found) * 0.06)
            return True, round(conf, 3), found[:4]

        except Exception as e:
            logger.debug(f"OCR error: {e}")
            return False, 0.0, []


# ── Layer 4: Ollama vision ─────────────────────────────────────────────────────

class OllamaAnalyzer:
    def __init__(self, ready_callback: Optional[Callable] = None):
        self.is_ready = False
        self.last_ms  = 0.0
        self._cb      = ready_callback
        self._check()

    def _check(self):
        try:
            r = requests.get(f"{CONFIG.ollama_host}/api/tags", timeout=3)
            r.raise_for_status()
            models = [m["name"] for m in r.json().get("models", [])]
            if any(CONFIG.ollama_model in m for m in models):
                self.is_ready = True
                logger.info(f"Ollama ready — {CONFIG.ollama_model}")
                if self._cb:
                    self._cb("ollama", True)
            else:
                logger.warning(
                    f"Ollama: model '{CONFIG.ollama_model}' not found. "
                    f"Run: ollama pull {CONFIG.ollama_model}"
                )
                if self._cb:
                    self._cb("ollama", False)
        except Exception:
            logger.info("Ollama not available — running OCR+CV only")
            if self._cb:
                self._cb("ollama", False)

    def analyze(self, image_b64: str) -> Tuple[bool, float, str]:
        if not self.is_ready:
            return False, 0.0, ""
        t0 = time.perf_counter()
        try:
            r = requests.post(
                f"{CONFIG.ollama_host}/api/generate",
                json={
                    "model":   CONFIG.ollama_model,
                    "prompt":  OLLAMA_VISION_PROMPT,
                    "images":  [image_b64],
                    "stream":  False,
                    "format":  "json",
                    "options": {"temperature": 0.05, "num_predict": 80},
                },
                timeout=CONFIG.ollama_timeout,
            )
            r.raise_for_status()
            raw  = r.json().get("response", "{}")
            raw  = re.sub(r"```(?:json)?|```", "", raw).strip()
            m    = re.search(r"\{[^}]+\}", raw, re.DOTALL)
            if not m:
                return False, 0.0, "parse_error"
            data   = json.loads(m.group())
            is_d   = bool(data.get("is_distraction", False))
            conf   = float(data.get("confidence", 0.0))
            reason = str(data.get("reason", "")).strip()[:80]
            self.last_ms = (time.perf_counter() - t0) * 1000
            return is_d, round(conf, 3), reason
        except requests.Timeout:
            return False, 0.0, "timeout"
        except Exception as e:
            logger.debug(f"Ollama error: {e}")
            return False, 0.0, "error"


# ── Master: Hybrid analyzer ────────────────────────────────────────────────────

class HybridAnalyzer:
    # Weights used for the weighted fusion of all signals.
    # Ollama and OCR domain matches also bypass fusion via floor logic.
    _W = {"ollama": 0.50, "ocr": 0.30, "scroll": 0.12, "cards": 0.08}

    def __init__(self, backend_status_callback: Optional[Callable] = None):
        self._cb    = backend_status_callback
        self.scroll = ScrollDetector()
        self.cards  = CardLayoutDetector()
        self.ocr    = OCRAnalyzer(ready_callback=self._on_backend)
        self.ollama = OllamaAnalyzer(ready_callback=self._on_backend)
        self.latency: Dict[str, float] = {}
        if self._cb:
            self._cb("opencv", True)

    def _on_backend(self, name: str, status: bool):
        if self._cb:
            self._cb(name, status)

    def analyze(
        self,
        frame: np.ndarray,
        image_b64: str,
        nav_fullres: Optional[np.ndarray] = None,
        win_title: str = "",
    ) -> AnalysisResult:
        t0       = time.perf_counter()
        signals  = {}
        reasons  = []
        keywords = []
        floors   = []   # signals strong enough to anchor the final score

        # Layer 1: OpenCV — always runs, fast
        scroll_ok, scroll_c = self.scroll.update(frame)
        card_ok,   card_c   = self.cards.detect(frame)
        signals["scroll"] = scroll_c
        signals["cards"]  = card_c
        if scroll_ok: reasons.append("scroll")
        if card_ok:   reasons.append("feed layout")
        self.latency["opencv"] = (time.perf_counter() - t0) * 1000

        # Layer 2: OCR — address bar only
        if self.ocr.is_ready:
            t1 = time.perf_counter()
            _, ocr_c, keywords = self.ocr.analyze(frame, nav_fullres=nav_fullres)
            signals["ocr"] = ocr_c
            self.latency["ocr"] = (time.perf_counter() - t1) * 1000
            if keywords:
                reasons.append(f"url:{','.join(keywords[:2])}")
                if ocr_c >= 0.60:
                    floors.append(ocr_c)

        # Layer 3: Ollama — page content (tab bar cropped)
        if self.ollama.is_ready:
            t2 = time.perf_counter()
            oll_dist, oll_c, oll_r = self.ollama.analyze(image_b64)
            signals["ollama"] = oll_c
            self.latency["ollama"] = (time.perf_counter() - t2) * 1000
            if oll_r and oll_r not in ("timeout", "error", "parse_error"):
                reasons.append(oll_r)
            if oll_dist and oll_c >= 0.50:
                floors.append(oll_c)

        # Weighted fusion
        total_w = sum(self._W[k] for k in signals)
        fused   = (
            sum(signals[k] * self._W[k] for k in signals) / total_w
            if total_w else 0.0
        )

        # Authoritative signals set a floor — they cannot be diluted by zeros
        if floors:
            fused = max(fused, max(floors))

        # OpenCV alone is insufficient. Scroll patterns and card layouts appear on
        # plenty of productive pages (GitHub issues, email, documentation). Apply a
        # penalty when CV is the only evidence so it cannot fire without confirmation.
        cv_only = not keywords and not (self.ollama.is_ready and signals.get("ollama", 0) > 0.1)
        if cv_only and fused > 0:
            fused *= 0.55

        conf = round(min(1.0, fused), 3)
        used = [k for k in ("ollama", "ocr") if k in signals] + ["cv"]

        return AnalysisResult(
            is_distraction=conf >= CONFIG.confidence_threshold,
            confidence=conf,
            reason=" · ".join(reasons) or "clean",
            backend_used="+".join(used),
            analysis_ms=round((time.perf_counter() - t0) * 1000, 1),
            keywords_found=keywords,
        )

    def reset_scroll(self):
        self.scroll.reset()
