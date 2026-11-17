"""OPTISWEEP AI - Autonomous Cleaning Robot Simulator.

Run with:  python main.py
"""
import sys

# Must happen before pygame/SDL is imported so the window is never
# bitmap-upscaled by Windows (which would blur the entire GUI).
from config.dpi import enable_hidpi

enable_hidpi()


def main():
    try:
        import pygame  # noqa: F401
    except ImportError:
        print("Pygame is required.  Install the dependencies with:\n    pip install -r requirements.txt")
        return 1
    from gui.app import App
    App(sound="--mute" not in sys.argv).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
