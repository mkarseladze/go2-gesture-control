"""Camera-only gesture rules and command filtering. No robot interface."""
from __future__ import annotations

from dataclasses import dataclass
from math import acos, degrees, hypot, isfinite

STOP = "STOP"
UNKNOWN = "UNKNOWN"
HEART = "HEART"
SIT = "SIT"
STAND_UP = "STAND_UP"
HELLO = "HELLO"
DANCE1 = "DANCE1"
ACTIONS = {HEART, SIT, STAND_UP, HELLO, DANCE1}
MOVEMENTS = {"FORWARD", "BACKWARD", "LEFT", "RIGHT"}


def distance(a, b):
    return hypot(a[0] - b[0], a[1] - b[1])


def angle(a, b, c):
    u = (a[0] - b[0], a[1] - b[1])
    v = (c[0] - b[0], c[1] - b[1])
    length = hypot(*u) * hypot(*v)
    if length < 1e-8:
        return 0.0
    cosine = (u[0] * v[0] + u[1] * v[1]) / length
    return degrees(acos(max(-1.0, min(1.0, cosine))))


def classify_thumb(points):
    """Distinguish a thumb across the palm from one spread outside it.

    Palm-relative projections work for both hands and mirrored previews.
    A thumb tip folded toward the middle of the palm can be far from the
    index knuckle, so distance to that knuckle alone is not sufficient.
    """
    side = (points[17][0] - points[5][0], points[17][1] - points[5][1])
    axis = (points[9][0] - points[0][0], points[9][1] - points[0][1])
    width2 = side[0] ** 2 + side[1] ** 2
    length2 = axis[0] ** 2 + axis[1] ** 2
    if min(width2, length2) < 1e-8:
        return UNKNOWN
    across = sum((points[4][i] - points[5][i]) * side[i] for i in (0, 1)) / width2
    along = sum((points[4][i] - points[0][i]) * axis[i] for i in (0, 1)) / length2
    # Outside the index side of the palm, with an extended thumb joint.
    if across < -0.25 and angle(points[2], points[3], points[4]) > 150:
        return "OPEN"
    # Inside the palm's width and below its upper edge: thumb tucked across it.
    if -0.05 <= across <= 1.15 and 0.15 <= along <= 1.05:
        return "FOLDED"
    return UNKNOWN


def classify(landmarks, width, height):
    """Upright palm facing camera; index/middle/ring/little, in that order.

    Conservative geometric heuristic, not a trained gesture classifier.
    Return (command, diagnostic). Thumb is used to distinguish 4 from palm.
    """
    if len(landmarks) != 21:
        return UNKNOWN, "Invalid landmarks"
    points = [(p.x * width, p.y * height) for p in landmarks]
    if any(not isfinite(v) for p in points for v in p):
        return UNKNOWN, "Invalid coordinates"
    if any(x < 4 or y < 4 or x > width - 4 or y > height - 4 for x, y in points):
        return UNKNOWN, "Keep the whole hand inside the image"
    palm_size = distance(points[0], points[9])
    if palm_size < 35:
        return UNKNOWN, "Bring hand closer"
    # This prototype deliberately limits orientation to reduce ambiguity.
    if points[0][1] - points[9][1] < palm_size * 0.55:
        return UNKNOWN, "Point fingers upward, palm toward camera"

    states = []
    for base, pip, dip, tip in [(5, 6, 7, 8), (9, 10, 11, 12),
                                (13, 14, 15, 16), (17, 18, 19, 20)]:
        a = angle(points[base], points[pip], points[dip])
        b = angle(points[pip], points[dip], points[tip])
        tip_distance = distance(points[0], points[tip])
        pip_distance = distance(points[0], points[pip])
        if (a > 155 and b > 150 and tip_distance > pip_distance * 1.15
                and points[tip][1] < points[pip][1] - palm_size * 0.12):
            states.append(True)
        elif a < 125 or tip_distance < pip_distance * 0.95:
            states.append(False)
        else:
            return UNKNOWN, "Fully extend or fold each finger"

    pattern = tuple(states)
    mapping = {(True, False, False, False): "FORWARD",
               (True, True, False, False): "BACKWARD",
               (True, True, True, False): "LEFT"}
    if pattern in mapping:
        return mapping[pattern], "Fingers: " + "".join("1" if s else "0" for s in states)
    if pattern == (True, True, True, True):
        thumb = classify_thumb(points)
        if thumb == "OPEN":
            return STOP, "Open palm"
        if thumb == "FOLDED":
            return "RIGHT", "Four fingers; thumb folded across palm"
        return UNKNOWN, "Open palm fully to stop, or fold thumb fully"
    return UNKNOWN, "Gesture not assigned"


@dataclass
class CommandGate:
    """A display filter, NOT a robot watchdog or emergency stop.

    Unknown input stops immediately; movement needs 0.4 s and >=5 frames.
    A gap >0.25 s discards the previous candidate. Call on fresh frames only.
    """
    hold_seconds: float = 0.4
    max_gap: float = 0.25
    min_frames: int = 5
    armed: bool = False
    candidate: str = STOP
    since: float = 0.0
    count: int = 0
    last_time: float | None = None

    def reset(self):
        self.candidate, self.since, self.count = STOP, 0.0, 0
        self.last_time = None

    def toggle(self):
        self.armed = not self.armed
        self.reset()

    def disarm(self):
        self.armed = False
        self.reset()

    def update(self, command, now):
        if not isfinite(now):
            self.disarm()
            return STOP
        if self.last_time is not None and (now <= self.last_time or now - self.last_time > self.max_gap):
            self.reset()
        self.last_time = now
        if not self.armed or (command not in MOVEMENTS and command not in ACTIONS):
            self.candidate, self.count = STOP, 0
            return STOP
        if command != self.candidate:
            self.candidate, self.since, self.count = command, now, 1
            return STOP
        self.count += 1
        if now - self.since >= self.hold_seconds and self.count >= self.min_frames:
            return command
        return STOP
