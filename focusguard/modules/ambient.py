"""
FocusGuard — Ambient Sound Player  (focusguard/modules/ambient.py)

Plays procedurally generated ambient sounds for focus:
  • White noise (flat spectrum)
  • Pink noise  (1/f spectrum — more natural sounding)
  • Rain        (pink noise + random droplets)
  • Cafe        (pink noise + low murmur simulation)
  • Brown noise (1/f² — deep, rumbling)
  • Binaural beats (optional — subtle frequency difference between ears)

No internet. No audio files. Pure numpy → sounddevice.
Falls back gracefully if sounddevice is not installed.

Usage:
    player = AmbientPlayer()
    player.play("rain", volume=0.4)
    player.set_volume(0.6)
    player.stop()
    print(player.available)    # False if sounddevice missing
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional

import numpy as np

logger = logging.getLogger("focusguard.ambient")

_SR    = 44100   # sample rate
_CHUNK = 2048    # samples per audio callback chunk
_FADE  = 0.5     # fade in/out seconds


def _try_import_sd():
    try:
        import sounddevice as sd
        # Probe that PortAudio is actually usable (raises OSError if library missing)
        _ = sd.query_devices()
        return sd
    except ImportError:
        return None
    except Exception:
        # PortAudio not installed at system level, sounddevice unusable
        return None


# Noise generators

def _white_noise(n: int) -> np.ndarray:
    """Flat spectrum — bright hiss, like TV static."""
    return np.random.uniform(-1.0, 1.0, n).astype(np.float32)


def _pink_noise(n: int) -> np.ndarray:
    """1/f spectrum — softer than white, like a gentle waterfall hiss."""
    max_key = 0x1f
    keys    = np.zeros(5, dtype=np.float32)
    key     = 0
    out     = np.empty(n, dtype=np.float32)
    running = np.random.uniform(-1.0, 1.0)
    for i in range(n):
        last = key
        key  = (key + 1) & max_key
        diff = last ^ key
        for b in range(5):
            if diff >> b & 1:
                keys[b] = np.random.uniform(-1.0, 1.0)
        running = keys.sum() / 5.0
        out[i]  = running
    return out


def _brown_noise(n: int) -> np.ndarray:
    """1/f² — deep rumbling, like distant thunder or a powerful HVAC."""
    white  = np.random.randn(n).astype(np.float32)
    brown  = np.cumsum(white) * 0.02
    brown -= brown.mean()
    peak = np.abs(brown).max()
    if peak > 0:
        brown /= peak
    return brown


def _rain_noise(n: int, intensity: float = 0.65) -> np.ndarray:
    """
    Realistic rain: pink-noise backdrop + prominent droplet pops.
    Noticeably different from plain noise — rhythmic splashes audible.
    """
    base = _pink_noise(n) * 0.35
    # Many medium drops
    for _ in range(int(0.012 * n)):
        pos = np.random.randint(0, n)
        dur = np.random.randint(30, 180)
        end = min(n, pos + dur)
        t   = np.linspace(0, 1, end - pos, dtype=np.float32)
        amp = np.random.uniform(0.4, 1.0)
        base[pos:end] += amp * np.exp(-t * 12)
    # Occasional heavy drops
    for _ in range(int(0.001 * n)):
        pos = np.random.randint(0, n)
        dur = np.random.randint(80, 300)
        end = min(n, pos + dur)
        t   = np.linspace(0, 1, end - pos, dtype=np.float32)
        base[pos:end] += np.random.uniform(0.8, 1.5) * np.exp(-t * 5)
    base = np.clip(base * intensity, -1.0, 1.0)
    return base.astype(np.float32)


def _cafe_noise(n: int) -> np.ndarray:
    """
    Coffee-shop ambience: low-mid murmur, rhythmic modulation, occasional clinks.
    Clearly different from plain noise — has a sense of life and rhythm.
    """
    t    = np.linspace(0, n / _SR, n, dtype=np.float32)
    # Background chatter — band-pass shaped noise
    base = _pink_noise(n) * 0.3
    # Slow amplitude modulation — natural conversation ebb-and-flow
    mod  = 0.5 + 0.25 * np.sin(2 * np.pi * 0.07 * t) \
               + 0.15 * np.sin(2 * np.pi * 0.13 * t) \
               + 0.10 * np.sin(2 * np.pi * 0.31 * t)
    sig = (base * mod).astype(np.float32)
    # Occasional clink/tap sounds (cups, spoons)
    for _ in range(int(0.0005 * n)):
        pos = np.random.randint(0, n)
        dur = np.random.randint(15, 60)
        end = min(n, pos + dur)
        t2  = np.linspace(0, 1, end - pos, dtype=np.float32)
        freq = np.random.uniform(600, 2000)
        sig[pos:end] += 0.35 * np.sin(2 * np.pi * freq * t2) * np.exp(-t2 * 30)
    return np.clip(sig, -1.0, 1.0)


def _binaural(n: int, base_freq: float = 200.0, beat_freq: float = 10.0) -> np.ndarray:
    """
    Binaural beat: left = base_freq, right = base_freq + beat_freq.
    The perceived difference creates the beat. Requires headphones.
    beat_freq 8-13 Hz = alpha waves (relaxed focus).
    """
    t  = np.linspace(0, n / _SR, n, dtype=np.float32)
    L  = 0.3 * np.sin(2 * np.pi * base_freq * t)
    R  = 0.3 * np.sin(2 * np.pi * (base_freq + beat_freq) * t)
    pink = _pink_noise(n) * 0.12   # subtle carrier
    return np.stack([L + pink, R + pink], axis=1)


GENERATORS = {
    "white":    lambda n: np.stack([_white_noise(n), _white_noise(n)], axis=1),
    "pink":     lambda n: np.stack([_pink_noise(n),  _pink_noise(n)],  axis=1),
    "brown":    lambda n: np.stack([_brown_noise(n), _brown_noise(n)], axis=1),
    "rain":     lambda n: np.stack([_rain_noise(n),  _rain_noise(n)],  axis=1),
    "cafe":     lambda n: np.stack([_cafe_noise(n),  _cafe_noise(n)],  axis=1),
    "binaural": _binaural,
}

SOUND_NAMES = list(GENERATORS.keys())
SOUND_LABELS = {
    "white":    "⬜ White Noise",
    "pink":     "🌸 Pink Noise",
    "brown":    "🟫 Brown Noise",
    "rain":     "🌧 Rain",
    "cafe":     "☕ Cafe",
    "binaural": "🎧 Binaural (α)",
}


class AmbientPlayer:
    def __init__(self):
        self._sd          = _try_import_sd()
        self.available    = self._sd is not None
        self._stream      = None
        self._lock        = threading.Lock()
        self._current     = None   # current sound name
        self._volume      = 0.5
        self._target_vol  = 0.5
        self._fade_step   = 0.0
        self._buf_cache: dict = {}

        if not self.available:
            logger.info(
                "sounddevice not installed — ambient sounds disabled. "
                "Install: pip install sounddevice"
            )

    # Public API

    def play(self, sound: str = "rain", volume: float = 0.5) -> bool:
        if not self.available:
            return False
        sound = sound if sound in GENERATORS else "rain"
        self.stop()

        with self._lock:
            self._current    = sound
            self._volume     = 0.0        # start at 0 for fade-in
            self._target_vol = max(0.0, min(1.0, volume))
            self._fade_step  = self._target_vol / max(1, int(_SR / _CHUNK * _FADE))
            buf = self._get_buf(sound)

        try:
            pos = [0]

            def callback(outdata, frames, _t, status):
                nonlocal buf
                with self._lock:
                    # Fade volume
                    if self._volume < self._target_vol:
                        self._volume = min(self._target_vol, self._volume + self._fade_step)
                    elif self._volume > self._target_vol:
                        self._volume = max(self._target_vol, self._volume - self._fade_step)
                    vol = self._volume

                if vol < 0.001:
                    outdata[:] = 0
                    return

                # Loop the pre-generated buffer
                buf_len = len(buf)
                start = pos[0]
                end   = start + frames
                if end <= buf_len:
                    outdata[:] = buf[start:end] * vol
                    pos[0] = end % buf_len
                else:
                    # Wrap around
                    first_part = buf_len - start
                    outdata[:first_part] = buf[start:] * vol
                    remainder  = frames - first_part
                    outdata[first_part:] = buf[:remainder] * vol
                    pos[0] = remainder

            self._stream = self._sd.OutputStream(
                samplerate=_SR,
                channels=2,
                dtype="float32",
                blocksize=_CHUNK,
                callback=callback,
            )
            self._stream.start()
            logger.info(f"Ambient: playing '{sound}' at {volume:.0%}")
            return True
        except Exception as e:
            logger.warning(f"Ambient play error: {e}")
            self._stream = None
            return False

    def stop(self) -> None:
        stream = self._stream
        self._stream = None
        with self._lock:
            self._current = None

        if stream:
            def _do_stop():
                try:
                    # Fade out first
                    with self._lock:
                        self._target_vol = 0.0
                    time.sleep(_FADE * 0.4)   # short fade, off the main thread
                    stream.stop()
                    stream.close()
                except Exception:
                    pass
            threading.Thread(target=_do_stop, daemon=True, name="ambient-stop").start()

    def set_volume(self, volume: float) -> None:
        with self._lock:
            self._target_vol = max(0.0, min(1.0, volume))

    def is_playing(self) -> bool:
        return self._stream is not None and self._stream.active

    @property
    def current_sound(self) -> Optional[str]:
        return self._current

    # Internal

    def _get_buf(self, sound: str) -> np.ndarray:
        """Generate and cache a 10-second buffer for the given sound type."""
        if sound not in self._buf_cache:
            n = _SR * 10   # 10 second loop
            gen = GENERATORS[sound]
            arr = gen(n).astype(np.float32)
            # Ensure shape is (n, 2)
            if arr.ndim == 1:
                arr = np.stack([arr, arr], axis=1)
            self._buf_cache[sound] = arr
            logger.debug(f"Generated {sound} buffer {arr.shape}")
        return self._buf_cache[sound]

    def __del__(self):
        try:
            self.stop()
        except Exception:
            pass
