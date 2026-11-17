"""Windows high-DPI setup, applied *before* pygame/SDL is imported.

OptiSweep renders into a fixed 1600x900 logical canvas.  When the process is
DPI-unaware, Windows lies to SDL about the desktop size (a 1920x1080 screen at
150% scaling is reported as 1280x720).  The app then builds a smaller window,
downscales its canvas, and Windows finally bitmap-upscales the result by 1.5x.
That double scaling is what makes the whole GUI - and text in particular -
look blurry.

Marking the process per-monitor DPI aware makes SDL report physical pixels,
so the window is sized in real pixels and the canvas is blitted 1:1.
"""
import os
import sys

_DONE = False


def enable_hidpi():
    """Enable per-monitor DPI awareness on Windows (safe to call repeatedly).

    Must run before ``import pygame`` for SDL's hint to take effect.  The
    ctypes calls are a fallback for SDL builds that don't read the hint.
    """
    global _DONE
    if _DONE or sys.platform != "win32":
        return
    _DONE = True

    # SDL >= 2.24 hint (pygame-ce 2.5 ships SDL 2.32).
    os.environ.setdefault("SDL_WINDOWS_DPI_AWARENESS", "permonitorv2")

    try:
        import ctypes
        # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 (Windows 10 1607+).
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            import ctypes
            ctypes.windll.user32.SetProcessDPIAware()  # Windows Vista+
        except Exception:
            pass  # Non-Windows or locked-down environment: carry on.
