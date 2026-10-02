import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "apps", "micropython"))

from ventilastation.shuffler import shuffled

class TestShuffler(unittest.TestCase):
    def test_shuffled_returns_permutation(self):
        # Ten elements: the chance that a correct shuffle leaves them in their
        # original order is 1 in 3.6 million. With five it was 1 in 120, which
        # made this test fail about once in a hundred runs.
        arr = list(range(1, 11))
        result = shuffled(arr)
        self.assertEqual(sorted(result), sorted(arr))
        self.assertNotEqual(result, arr)

    def test_shuffled_does_not_modify_original(self):
        arr = [1, 2, 3, 4, 5]
        arr_copy = arr[:]
        shuffled(arr)
        self.assertEqual(arr, arr_copy)

    def test_shuffled_empty_array(self):
        arr = []
        result = shuffled(arr)
        self.assertEqual(result, [])

    def test_shuffled_single_element(self):
        arr = [42]
        result = shuffled(arr)
        self.assertEqual(result, [42])

    def test_shuffled_multiple_runs(self):
        arr = [1, 2, 3, 4, 5]
        results = {tuple(shuffled(arr)) for _ in range(100)}
        # There should be more than one unique permutation in 100 runs
        self.assertGreater(len(results), 1)

if __name__ == "__main__":
    unittest.main()