import unittest

import numpy as np

from src.app.dictation.pipeline_loop import SlidingAudioWindow


class SlidingAudioWindowTest(unittest.TestCase):
    def test_waits_until_window_and_step_are_ready(self) -> None:
        window = SlidingAudioWindow(window_samples=4, step_samples=2)

        self.assertFalse(window.append(np.array([1], dtype=np.float32)))
        self.assertFalse(window.append(np.array([2], dtype=np.float32)))
        self.assertFalse(window.append(np.array([3], dtype=np.float32)))
        self.assertTrue(window.append(np.array([4], dtype=np.float32)))

        self.assertEqual(window.buffered_samples, 4)
        self.assertEqual(window.concatenate(np).tolist(), [1.0, 2.0, 3.0, 4.0])

    def test_trims_oldest_samples_to_window_size(self) -> None:
        window = SlidingAudioWindow(window_samples=4, step_samples=2)

        self.assertTrue(window.append(np.array([1, 2, 3, 4], dtype=np.float32)))
        self.assertTrue(window.append(np.array([5, 6], dtype=np.float32)))

        self.assertEqual(window.buffered_samples, 4)
        self.assertEqual(window.concatenate(np).tolist(), [3.0, 4.0, 5.0, 6.0])


if __name__ == "__main__":
    unittest.main()
