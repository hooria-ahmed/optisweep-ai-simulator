"""Procedurally generated sound effects (no asset files needed).

If no audio device is available the game silently runs without sound.
"""
import array
import math
import random

import pygame

RATE = 22050


def _tone(freqs, seconds, volume=0.35, attack=0.005, decay=None, slide=0.0, noise=0.0,
          tremolo=0.0):
    n = int(RATE * seconds)
    decay = seconds if decay is None else decay
    rng = random.Random(7)
    out = array.array("h")
    phases = [0.0] * len(freqs)
    low = 0.0
    for i in range(n):
        t = i / RATE
        env = min(1.0, t / attack) * max(0.0, 1.0 - t / decay) ** 1.6
        v = 0.0
        for k, f in enumerate(freqs):
            phases[k] += 2 * math.pi * (f + slide * t) / RATE
            v += math.sin(phases[k])
        v /= max(1, len(freqs))
        if noise:
            low += (rng.uniform(-1, 1) - low) * 0.25
            v = v * (1 - noise) + low * noise * 2.2
        if tremolo:
            v *= 0.75 + 0.25 * math.sin(2 * math.pi * tremolo * t)
        out.append(int(max(-1.0, min(1.0, v * env * volume)) * 32767))
    return out


def _concat(*parts):
    out = array.array("h")
    for p in parts:
        out.extend(p)
    return out


def _music():
    """A calm four-second ambient loop."""
    n = RATE * 4
    out = array.array("h")
    chord = [110.0, 164.81, 220.0, 329.63]
    for i in range(n):
        t = i / RATE
        v = sum(math.sin(2 * math.pi * f * t) * (0.5 + 0.5 * math.sin(2 * math.pi * (0.25 * (k + 1)) * t))
                for k, f in enumerate(chord)) / len(chord)
        out.append(int(v * 0.16 * 32767))
    return out


class Audio:
    def __init__(self, enabled=True):
        self.available = False
        self.muted = False
        self.music_muted = False
        self.music_volume = 0.35
        self.sounds = {}
        self.music = None
        self.music_channel = None
        if not enabled:
            return
        try:
            pygame.mixer.init(RATE, -16, 1, 512)
            self.available = True
        except pygame.error:
            return
        try:
            make = lambda data: pygame.mixer.Sound(buffer=data.tobytes())
            self.sounds = {
                "click": make(_tone([880, 1320], 0.07, 0.25)),
                "move": make(_tone([190], 0.06, 0.10, slide=-400)),
                "tick": make(_tone([1500], 0.025, 0.06)),
                "clean": make(_tone([140], 0.9, 0.30, attack=0.15, noise=0.85, tremolo=18)),
                "cleaned": make(_concat(_tone([988], 0.09, 0.25), _tone([1319], 0.16, 0.25))),
                "charge": make(_tone([330, 660], 0.8, 0.22, attack=0.2, slide=500)),
                "success": make(_concat(*[_tone([f, f * 2], 0.14, 0.3) for f in (523, 659, 784)],
                                        _tone([1047, 1568], 0.5, 0.32))),
                "fail": make(_concat(_tone([330], 0.2, 0.3), _tone([262], 0.2, 0.3),
                                     _tone([196], 0.5, 0.3))),
                "start": make(_tone([440, 880], 0.3, 0.25, slide=900)),
                "error": make(_tone([180, 190], 0.22, 0.3)),
            }
            self.music = make(_music())
            self.music.set_volume(self.music_volume)
            self.music_channel = self.music.play(loops=-1, fade_ms=1500)
        except Exception:
            self.available = False

    def play(self, name):
        if self.available and not self.muted and name in self.sounds:
            self.sounds[name].play()

    def toggle(self):
        self.muted = not self.muted
        self._sync_music()
        return self.muted

    def toggle_music(self):
        self.music_muted = not self.music_muted
        self._sync_music()
        return self.music_muted

    def set_music_volume(self, vol):
        self.music_volume = max(0.0, min(1.0, vol))
        self._sync_music()

    def _sync_music(self):
        if self.available and self.music:
            self.music.set_volume(0.0 if (self.muted or self.music_muted) else self.music_volume)
