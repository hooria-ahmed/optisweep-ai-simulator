"""Global settings for the OptiSweep AI game (colours, layout, tuning)."""
import os

APP_NAME = "OPTISWEEP AI"
APP_SUBTITLE = "Autonomous Cleaning Robot Simulator"

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CUSTOM_ENV_DIR = os.path.join(ROOT_DIR, "environments")

# Logical resolution.  Everything is laid out for this size and the frame is
# scaled to whatever the real window is.
WIDTH, HEIGHT = 1600, 900
FPS = 60

# ----------------------------------------------------------------- palette --
BG = (0x10, 0x15, 0x1F)
BG2 = (0x17, 0x1F, 0x2B)
PANEL = (0x1C, 0x27, 0x35)
PANEL_HI = (0x24, 0x32, 0x44)
BORDER = (0x2C, 0x3B, 0x4F)
CYAN = (0x00, 0xD9, 0xFF)
BLUE = (0x00, 0x8C, 0xFF)
GREEN = (0x39, 0xD9, 0x8A)
ORANGE = (0xFF, 0xB5, 0x47)
RED = (0xFF, 0x5C, 0x65)
WHITE = (0xF4, 0xF7, 0xFA)
MUTED = (0x8D, 0x9B, 0xAA)
PURPLE = (0x9B, 0x7B, 0xFF)
DARK = (0x0B, 0x10, 0x18)

ALGO_COLOR = {"BFS": ORANGE, "A*": CYAN}

# ------------------------------------------------------------- simulation --
SPEEDS = [("SLOW", 0.5), ("NORMAL", 1.0), ("FAST", 2.0), ("VERY FAST", 4.0)]
MOVE_SECONDS = 0.30        # one cell at NORMAL speed
CLEAN_SECONDS = 1.00
CHARGE_SECONDS = 1.80
CSP_EVENT_SECONDS = 0.38   # one solver event at NORMAL speed
SEARCH_STEP_SECONDS = 0.07 # one node expansion at NORMAL speed
BATTERY_PER_MOVE = 0.9     # % drained per cell (cosmetic)

# ---------------------------------------------------------------- missions --
MISSIONS = [
    {"id": "01", "title": "SAMPLE ENVIRONMENT", "env": "Environment_Sample.txt",
     "sched": "Schedule_Sample.txt", "color": CYAN,
     "blurb": "The reference 8x8 floor with a central wall. A clean first run."},
    {"id": "02", "title": "CUSTOM ENVIRONMENT", "env": "Environment.txt",
     "sched": "Schedule.txt", "color": GREEN,
     "blurb": "A 10x10 multi-corridor map with five targets and tight deadlines."},
    {"id": "03", "title": "FAILURE TEST", "env": "Environment_Error.txt",
     "sched": "Schedule_Error.txt", "color": RED,
     "blurb": "A contradictory schedule and a walled-off target. Watch the AI fail safely."},
]

EDITOR_MIN, EDITOR_MAX = 8, 16
