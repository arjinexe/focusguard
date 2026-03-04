"""
FocusGuard — Screen Capture Module

MSS-based screen capture with thread-local context management.
Supports per-thread mss instances to avoid cross-thread state issues.
The capture object can be re-initialized after a stop/start cycle.
"""

import base64
import io
import logging
import threading
from dataclasses import dataclass
from typing import Optional

import mss
import numpy as np
from PIL import Image

logger = logging.getLogger("focusguard.capture")

# Each thread gets its own mss context. Without this, capturing from the
# monitor thread while the object was created on the main thread causes
# a '_thread._local' attribute error on some platforms.
_tls = threading.local()


@dataclass
class ScreenFrame:
    image:      Image.Image
    array:      np.ndarray   # RGB uint8
    width:      int
    height:     int
    monitor_id: int = 1


class ScreenCapture:
    """MSS-based single-shot screen capture. Re-initializable after stop/start."""

    def __init__(self, monitor_id: int = 1, scale: float = 0.5):
        self.monitor_id = monitor_id
        self.scale      = scale
        self._sct:     Optional[mss.mss] = None
        self._monitor: Optional[dict]    = None
        self._open()

    def _open(self):
        if self._sct is not None:
            try:
                self._sct.close()
            except Exception:
                pass
        self._sct = mss.mss()
        monitors = self._sct.monitors
        if self.monitor_id >= len(monitors):
            self.monitor_id = 1
        self._monitor = monitors[self.monitor_id]
        logger.info(
            f"ScreenCapture ready — monitor {self.monitor_id} "
            f"({self._monitor['width']}x{self._monitor['height']})"
        )

    def reinit(self):
        """Re-open after a session restart."""
        self._open()

    def _get_sct(self):
        """Return the mss context for the current thread, creating one if needed."""
        if not hasattr(_tls, "sct") or _tls.sct is None:
            _tls.sct = mss.mss()
            monitors = _tls.sct.monitors
            idx = self.monitor_id if self.monitor_id < len(monitors) else 1
            _tls.monitor = monitors[idx]
        return _tls.sct, _tls.monitor

    def capture(self) -> Optional[ScreenFrame]:
        """Grab a single frame from the configured monitor."""
        try:
            sct, monitor = self._get_sct()
            raw = sct.grab(monitor)

            img = Image.frombytes("RGBA", raw.size, bytes(raw.bgra))
            img = img.convert("RGB")

            if self.scale != 1.0:
                new_w = max(1, int(img.width  * self.scale))
                new_h = max(1, int(img.height * self.scale))
                img = img.resize((new_w, new_h), Image.LANCZOS)

            arr = np.asarray(img, dtype=np.uint8)
            return ScreenFrame(
                image=img, array=arr,
                width=img.width, height=img.height,
                monitor_id=self.monitor_id,
            )
        except Exception as e:
            logger.error(f"Screen capture error: {e}")
            return None

    def capture_nav_fullres(self) -> Optional[np.ndarray]:
        """Capture the top ~14 % of the screen at full resolution for OCR.

        The browser address bar lives in this strip. Capturing it at native
        resolution (rather than the downscaled capture_scale) ensures that
        small URL text is readable by EasyOCR.
        """
        try:
            sct, monitor = self._get_sct()
            full_h   = monitor["height"]
            nav_h    = max(120, full_h // 7)
            nav_mon  = {
                "left":   monitor["left"],
                "top":    monitor["top"],
                "width":  monitor["width"],
                "height": nav_h,
            }
            raw = sct.grab(nav_mon)
            img = Image.frombytes("RGBA", raw.size, bytes(raw.bgra))
            img = img.convert("RGB")
            return np.asarray(img, dtype=np.uint8)
        except Exception as e:
            logger.debug(f"Nav capture error: {e}")
            return None

    def to_jpeg_bytes(self, frame: ScreenFrame, quality: int = 82) -> bytes:
        buf = io.BytesIO()
        frame.image.save(buf, format="JPEG", quality=quality, optimize=True)
        return buf.getvalue()

    def to_base64(self, frame: ScreenFrame) -> str:
        return base64.b64encode(self.to_jpeg_bytes(frame)).decode("utf-8")

    def to_base64_content_only(self, frame: ScreenFrame) -> str:
        """Return base64 of the frame with the browser tab bar cropped out.

        The tab bar shows ALL open tab titles, including background tabs.
        Passing the full frame to Ollama caused false positives: a YouTube or
        Instagram tab title visible in the tab strip would mislead the model
        even when the user was actively on GitHub or a coding tutorial.

        Cropping the top ~8 % removes the tab bar and address bar so the model
        only sees the actual page content the user is reading.
        """
        img      = frame.image
        h        = img.height
        crop_top = max(60, h // 12)
        cropped  = img.crop((0, crop_top, img.width, h))
        buf = io.BytesIO()
        cropped.save(buf, format="JPEG", quality=78, optimize=True)
        return base64.b64encode(buf.getvalue()).decode("utf-8")

    def available_monitors(self) -> list:
        return self._sct.monitors[1:] if self._sct else []

    def close(self):
        if self._sct:
            try:
                self._sct.close()
            except Exception:
                pass
            self._sct = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
