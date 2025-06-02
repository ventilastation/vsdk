import unittest
from shuffler import shuffled

class TestShuffler(unittest.TestCase):
    def test_shuffled_returns_permutation(self):
        arr = [1, 2, 3, 4, 5]
        result = shuffled(arr)
        self.assertEqual(sorted(result), sorted(arr))
        self.assertNotEqual(result, arr)  # Very rarely, this could fail if shuffle returns the same order

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