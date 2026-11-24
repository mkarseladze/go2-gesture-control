"""Behavior checks for the proposed motion requests, without hardware."""
import unittest
from motion_plan import plan_for


class MotionPlanTests(unittest.TestCase):
    def plan(self, command, **kwargs):
        return plan_for(command, enabled=kwargs.get('enabled', True),
                        frame_age=kwargs.get('frame_age', 0))

    def test_forward_and_backward_have_opposite_longitudinal_velocities(self):
        forward, backward = self.plan('FORWARD'), self.plan('BACKWARD')
        self.assertGreater(forward.vx, 0)
        self.assertEqual(forward.vx, -backward.vx)
        self.assertEqual((forward.vy, forward.vyaw, backward.vy, backward.vyaw), (0, 0, 0, 0))

    def test_turns_are_rotation_in_place_not_sideways_translation(self):
        left, right = self.plan('LEFT'), self.plan('RIGHT')
        self.assertGreater(left.vyaw, 0)
        self.assertEqual(left.vyaw, -right.vyaw)
        self.assertEqual((left.vx, left.vy, right.vx, right.vy), (0, 0, 0, 0))

    def test_disabled_mode_suppresses_every_movement(self):
        for command in ['FORWARD', 'BACKWARD', 'LEFT', 'RIGHT']:
            with self.subTest(command=command):
                self.assertEqual(self.plan(command, enabled=False).text, 'StopMove()')

    def test_old_future_and_invalid_frame_ages_never_propose_movement(self):
        for age in [.251, 1, -0.01, float('nan'), float('inf')]:
            with self.subTest(age=age):
                self.assertEqual(self.plan('FORWARD', frame_age=age).text, 'StopMove()')

    def test_unknown_commands_and_stop_generate_explicit_stop_request(self):
        for command in ['STOP', 'UNKNOWN', '', 'forward', 'JUMP', None]:
            with self.subTest(command=command):
                plan = self.plan(command)
                self.assertEqual((plan.command, plan.vx, plan.vy, plan.vyaw), ('STOP', 0, 0, 0))
                self.assertEqual(plan.text, 'StopMove()')


if __name__ == '__main__':
    unittest.main()
