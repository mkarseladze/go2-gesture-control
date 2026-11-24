"""Behavior checks without camera or optional dependencies."""
import unittest
from gestures import CommandGate, STOP, UNKNOWN


class CommandGateTests(unittest.TestCase):
    def feed(self, gate, command, times):
        return [gate.update(command, t) for t in times]

    def test_cannot_move_until_enabled_and_held(self):
        gate = CommandGate()
        self.assertEqual(self.feed(gate, 'FORWARD', [0, .1, .2, .3, .5]), [STOP] * 5)
        gate.toggle()
        outputs = self.feed(gate, 'FORWARD', [1, 1.1, 1.2, 1.3, 1.5])
        self.assertEqual(outputs[:-1], [STOP] * 4)
        self.assertEqual(outputs[-1], 'FORWARD')

    def test_lost_hand_stops_without_delay_and_requires_new_hold(self):
        gate = CommandGate(armed=True)
        self.feed(gate, 'FORWARD', [0, .1, .2, .3, .5])
        self.assertEqual(gate.update(UNKNOWN, .55), STOP)
        self.assertEqual(gate.update('FORWARD', .6), STOP)

    def test_stop_and_direction_change_do_not_inherit_previous_hold(self):
        for next_command in [STOP, 'LEFT', 'BACKWARD', 'RIGHT']:
            with self.subTest(command=next_command):
                gate = CommandGate(armed=True)
                self.feed(gate, 'FORWARD', [0, .1, .2, .3, .5])
                self.assertEqual(gate.update(next_command, .6), STOP)

    def test_slow_or_replayed_frames_discard_previous_hold(self):
        for timestamp in [.9, .5, .4]:
            with self.subTest(timestamp=timestamp):
                gate = CommandGate(armed=True)
                self.feed(gate, 'FORWARD', [0, .1, .2, .3, .5])
                self.assertEqual(gate.update('FORWARD', timestamp), STOP)

    def test_disabling_drops_command_immediately(self):
        gate = CommandGate(armed=True)
        self.feed(gate, 'FORWARD', [0, .1, .2, .3, .5])
        gate.disarm()
        self.assertEqual(gate.update('FORWARD', .6), STOP)

    def test_two_sparse_frames_cannot_enable_motion(self):
        gate = CommandGate(armed=True, max_gap=1)
        self.assertEqual(gate.update('FORWARD', 0), STOP)
        self.assertEqual(gate.update('FORWARD', .5), STOP)

    def test_nonfinite_clock_disables_output(self):
        gate = CommandGate(armed=True)
        self.assertEqual(gate.update('FORWARD', float('nan')), STOP)
        self.assertFalse(gate.armed)


if __name__ == '__main__':
    unittest.main()
