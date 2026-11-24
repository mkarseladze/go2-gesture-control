"""Regression checks for folded thumb vs open palm, with either hand."""
import unittest
from gestures import classify_thumb, UNKNOWN


def hand(thumb_points):
    points = [(0, 0)] * 21
    points[0], points[5], points[9], points[17] = (385, 775), (330, 604), (371, 596), (444, 635)
    points[2], points[3], points[4] = thumb_points
    return points


class ThumbTests(unittest.TestCase):
    def test_folded_thumb_across_palm_is_recognized(self):
        # A tip near the middle of the palm is >0.45 palm widths from the
        # index knuckle. The previous distance-only rule rejected this pose.
        points = hand([(316, 695), (354, 657), (400, 649)])
        self.assertEqual(classify_thumb(points), 'FOLDED')

    def test_open_palm_remains_distinct(self):
        points = hand([(310, 700), (285, 670), (260, 640)])
        self.assertEqual(classify_thumb(points), 'OPEN')

    def test_mirroring_scaling_and_translation_do_not_change_result(self):
        for pose, expected in [([(316, 695), (354, 657), (400, 649)], 'FOLDED'),
                               ([(310, 700), (285, 670), (260, 640)], 'OPEN')]:
            points = hand(pose)
            for scale in [.5, 2]:
                for mirror in [-1, 1]:
                    transformed = [(x * scale * mirror + 100, y * scale + 50) for x, y in points]
                    with self.subTest(expected=expected, scale=scale, mirror=mirror):
                        self.assertEqual(classify_thumb(transformed), expected)

    def test_ambiguous_thumb_stays_unknown(self):
        points = hand([(310, 700), (315, 670), (310, 630)])
        self.assertEqual(classify_thumb(points), UNKNOWN)

    def test_degenerate_palm_is_not_a_movement(self):
        self.assertEqual(classify_thumb([(0, 0)] * 21), UNKNOWN)


if __name__ == '__main__':
    unittest.main()
