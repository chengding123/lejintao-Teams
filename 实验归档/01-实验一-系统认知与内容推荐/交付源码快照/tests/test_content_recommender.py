import unittest

from recommender.contracts import Algorithm, RecommendationRequest, recommend
from recommender.data import DATASET, SPLIT


class ContentRecommenderTests(unittest.TestCase):
    def test_returns_real_top10_without_seen_movies(self):
        request = RecommendationRequest("ml", 14, 10, "business", DATASET, SPLIT)
        result = recommend(Algorithm.content, request)
        self.assertEqual(result.algorithm, Algorithm.content)
        self.assertTrue(1 <= len(result.items) <= 10)
        movie_ids = [item.movie_id for item in result.items]
        self.assertEqual(len(movie_ids), len(set(movie_ids)))
        self.assertEqual([item.rank for item in result.items], list(range(1, len(result.items) + 1)))

