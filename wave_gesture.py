"""Recognize an open palm making two horizontal back-and-forth sweeps."""

from math import dist

from wrist_gestures import finger_states


class WaveDetector:
    def __init__(self):
        self.reset()

    def reset(self):
        self.started = None
        self.last_seen = None
        self.extreme = None
        self.direction = 0
        self.sweeps = 0

    def update(self, hands, now):
        if len(hands) != 1:
            self.reset()
            return None
        points = hands[0]
        palm = dist(points[5], points[17])
        if palm < 12 or sum(finger_states(points)[1:]) < 3:
            self.reset()
            return None
        wrist, knuckle = points[0], points[9]
        if wrist[1] - knuckle[1] < 0.25 * palm:
            self.reset()
            return None
        x = (wrist[0] + knuckle[0]) / 2
        if (self.last_seen is None or now - self.last_seen > 0.35
                or (self.started is not None and now - self.started > 3.0)):
            self.reset()
            self.extreme = x
        self.last_seen = now
        delta = x - self.extreme
        if self.direction and delta * self.direction > 0:
            self.extreme = x
        elif abs(delta) >= 0.55 * palm:
            if self.started is None:
                self.started = now
            self.extreme = x
            self.direction = 1 if delta > 0 else -1
            self.sweeps += 1
        if self.sweeps >= 4 and now - self.started >= 0.35:
            started = self.started
            self.reset()
            return started
        return None
