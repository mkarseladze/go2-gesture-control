"""Gesture logic for the Go2 gesture-control project.

Pure Python: no camera, no MediaPipe, no robot. It takes 21 hand points and
returns a robot command, so stage 3 can import it unchanged.
"""
import math
from enum import Enum

from gestures import DANCE1, HEART, MOVEMENTS, SIT, STAND_UP, UNKNOWN


class Command(Enum):
    FORWARD = "forward"
    BACKWARD = "backward"
    TURN_LEFT = "turn_left"
    TURN_RIGHT = "turn_right"
    STOP = "stop"


LABELS_EN = {
    Command.FORWARD: "FORWARD",
    Command.BACKWARD: "BACKWARD",
    Command.TURN_LEFT: "LEFT",
    Command.TURN_RIGHT: "RIGHT",
    Command.STOP: "STOP",
}

# MediaPipe hand landmark indices
WRIST = 0
THUMB_TIP = 4
INDEX_MCP = 5
PINKY_MCP = 17
# (PIP joint, fingertip) for index, middle, ring, pinky
FINGER_JOINTS = ((6, 8), (10, 12), (14, 16), (18, 20))

# --- Tuning knobs (watch the debug numbers on screen while adjusting) ---
# A finger counts as raised if its tip is this much farther from the wrist
# than its middle (PIP) joint. Curled fingers are ~0.8-1.0, straight ~1.3.
FINGER_EXTENDED_RATIO = 1.15
# The thumb counts as out if its tip is this far from the pinky knuckle,
# measured in palm widths. Tucked ~0.6, alongside index ~1.2, out ~1.8+.
THUMB_EXTENDED_RATIO = 1.5

# Finger pattern (thumb, index, middle, ring, pinky) -> command.
# Anything not in this table is "unknown" and treated as STOP.
GESTURES = {
    (False, True, False, False, False): Command.FORWARD,     # 1 finger
    (False, True, True, False, False): Command.BACKWARD,     # 2 fingers
    (False, True, True, True, False): Command.TURN_LEFT,     # 3 fingers
    (False, True, True, True, True): Command.TURN_RIGHT,     # 4 fingers
    (True, True, True, True, True): Command.STOP,            # open palm
}


def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def thumb_ratio(points):
    """Thumb-tip distance from the pinky knuckle, in palm widths."""
    palm_width = _dist(points[INDEX_MCP], points[PINKY_MCP])
    if palm_width < 1e-6:
        return 0.0
    return _dist(points[THUMB_TIP], points[PINKY_MCP]) / palm_width


def finger_states(points):
    """points: 21 (x, y) pairs in PIXELS (not normalized - aspect ratio matters).

    Returns (thumb, index, middle, ring, pinky) as booleans. Uses distances
    from the wrist rather than "tip above joint", so it still works when the
    hand is tilted.
    """
    wrist = points[WRIST]
    thumb = thumb_ratio(points) > THUMB_EXTENDED_RATIO
    others = tuple(
        _dist(wrist, points[tip]) > _dist(wrist, points[pip]) * FINGER_EXTENDED_RATIO
        for pip, tip in FINGER_JOINTS
    )
    return (thumb,) + others


def classify(points):
    """Returns (command or None, finger_states). None means unrecognized."""
    states = finger_states(points)
    return GESTURES.get(states), states


def is_finger_heart(points, fingers):
    """Recognize a crossed index finger and thumb with the other fingers curled."""
    if not fingers[0] or any(fingers[2:]):
        return False
    palm = max(_dist(points[0], points[9]), _dist(points[5], points[17]))
    if not math.isfinite(palm) or palm < 12:
        return False
    thumb, index = points[4], points[8]
    # The visible tips form a compact V near the index finger's last joint.
    return (
        _dist(thumb, index) < 0.90 * palm
        and _dist(thumb, points[7]) < 0.55 * palm
        and _dist(thumb, points[0]) > 1.20 * palm
        and _dist(index, points[0]) > 1.20 * palm
    )


def classify_control(points):
    """Keep downward pointing separate from upright movement gestures."""
    gesture, fingers = classify(points)
    if is_finger_heart(points, fingers):
        return HEART, fingers
    if fingers == (True, False, False, False, True):
        return DANCE1, fingers
    label = LABELS_EN.get(gesture, UNKNOWN)
    if label == "FORWARD" and _points_vertically(points[6], points[8], down=True):
        return SIT, fingers
    if label in MOVEMENTS:
        upright = _points_vertically(points[WRIST], points[9])
        raised_upright = all(
            _points_vertically(points[joint], points[tip])
            for raised, (joint, tip) in zip(fingers[1:], FINGER_JOINTS)
            if raised
        )
        if not upright or not raised_upright:
            return UNKNOWN, fingers
    return label, fingers


def _points_vertically(base, tip, *, down=False):
    dx, dy = tip[0] - base[0], tip[1] - base[1]
    vertical = dy if down else -dy
    return vertical > 0.65 * math.hypot(dx, dy)


def classify_two_hands(hands):
    if len(hands) == 2 and all(classify_control(points)[0] == "FORWARD" for points in hands):
        return STAND_UP
    return UNKNOWN
