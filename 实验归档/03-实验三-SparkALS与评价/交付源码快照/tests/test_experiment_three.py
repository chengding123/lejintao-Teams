"""Hand-checked boundaries for Experiment 3's recommendation metrics and ALS ranking."""
import unittest

from recommender.student.als import rank_als_factors
from recommender.student.offline_metrics import macro_top10


class ExperimentThreeTests(unittest.TestCase):
    def test_short_and_empty_lists_remain_in_macro_denominator(self):
        predictions = {"1": ["10", "11"], "2": []}
        relevant = {"1": {"10", "12"}, "2": {"20"}}
        result = macro_top10(predictions, relevant, {"1", "2"})
        self.assertAlmostEqual(result["precision_at_10"], 0.05)
        self.assertAlmostEqual(result["recall_at_10"], 0.25)
        self.assertEqual(result["users_with_recommendations"], 1)

    def test_als_excludes_seen_and_orders_ties_by_numeric_movie_id(self):
        ranked = rank_als_factors([1.0, 0.0], {"20": [2.0, 0.0],
            "3": [1.0, 0.0], "11": [1.0, 0.0]}, {"20"}, 10)
        self.assertEqual([movie for movie, _ in ranked], ["3", "11"])


if __name__ == "__main__":
    unittest.main()
