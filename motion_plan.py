"""Display-only motion requests. No Unitree imports, sockets, or robot control."""
from dataclasses import dataclass
from math import isfinite

MAX_FRAME_AGE = 0.25
PREVIEW_LINEAR_SPEED = 0.15  # requested metres/second, not measured robot speed
PREVIEW_TURN_SPEED = 0.30   # requested radians/second


@dataclass(frozen=True)
class MotionPlan:
    command: str = 'STOP'
    vx: float = 0.0
    vy: float = 0.0
    vyaw: float = 0.0

    @property
    def text(self):
        if self.command == 'STOP':
            return 'StopMove()'
        return f'Move({self.vx:.2f}, {self.vy:.2f}, {self.vyaw:.2f})'


def plan_for(command, *, enabled, frame_age):
    """Build a proposed SDK request; never execute it.

    LEFT/RIGHT mean turning in place, not stepping sideways. Yaw signs follow
    the planned +left/-right convention; verify direction on the actual robot
    during the later low-speed hardware checks. This function is not a timer
    or independent watchdog: real control will need its own stop mechanism.
    """
    if not enabled or not isfinite(frame_age) or not 0 <= frame_age <= MAX_FRAME_AGE:
        return MotionPlan()
    if command == 'FORWARD':
        return MotionPlan(command, vx=PREVIEW_LINEAR_SPEED)
    if command == 'BACKWARD':
        return MotionPlan(command, vx=-PREVIEW_LINEAR_SPEED)
    if command == 'LEFT':
        return MotionPlan(command, vyaw=PREVIEW_TURN_SPEED)
    if command == 'RIGHT':
        return MotionPlan(command, vyaw=-PREVIEW_TURN_SPEED)
    return MotionPlan()


if __name__ == '__main__':
    print('PREVIEW ONLY - no robot connection')
    for command in ['FORWARD', 'BACKWARD', 'LEFT', 'RIGHT', 'STOP', 'UNKNOWN']:
        print(f'{command:10} -> {plan_for(command, enabled=True, frame_age=0).text}')
    print('Disabled   ->', plan_for('FORWARD', enabled=False, frame_age=0).text)
    print('Stale      ->', plan_for('FORWARD', enabled=True, frame_age=1).text)
