"""Headless driver for the game, used by the GUI tests and for screenshots."""
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pygame  # noqa: E402

from gui.app import App  # noqa: E402

DT = 1 / 60


def make_app():
    """A headless App whose internal error handler fails loudly."""
    app = App(headless=True)
    app.errors = []

    def report(exc):
        import traceback
        app.errors.append("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
    app._report = report
    return app


def run(app, seconds, dt=DT):
    for _ in range(max(1, int(seconds / dt))):
        app.frame(dt)


def run_until(app, condition, timeout=120.0, dt=DT, each=None):
    """Advance frames until ``condition()`` is true.  Returns False on timeout."""
    t = 0.0
    while t < timeout:
        if condition():
            return True
        app.frame(dt)
        if each:
            each()
        t += dt
    return condition()


def click(app, pos, button=1):
    pos = (int(pos[0]), int(pos[1]))
    app.frame(DT, [pygame.event.Event(pygame.MOUSEMOTION, pos=pos, rel=(0, 0), buttons=(0, 0, 0)),
                   pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=button),
                   pygame.event.Event(pygame.MOUSEBUTTONUP, pos=pos, button=button)])


def press(app, button):
    """Click a ui.Button through the real event path."""
    assert button.visible and button.enabled, f"button {button.label!r} is not clickable"
    click(app, button.rect.center)


def key(app, k, unicode=""):
    app.frame(DT, [pygame.event.Event(pygame.KEYDOWN, key=k, unicode=unicode, mod=0)])


def find(screen, label):
    """Find a button on a screen by its label."""
    groups = [getattr(screen, name) for name in ("widgets", "buttons") if hasattr(screen, name)]
    for g in groups:
        for w in g.items:
            if getattr(w, "label", None) == label:
                return w
    raise KeyError(label)


def shot(app, path):
    pygame.image.save(app.canvas, path)
