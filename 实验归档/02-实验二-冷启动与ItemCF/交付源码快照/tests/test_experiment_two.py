import unittest
from types import SimpleNamespace
from unittest.mock import patch

from recommender.contracts import Algorithm, PROVIDERS, RecommendationRequest, register_student_providers
from recommender.data import ContractError, DATASET, SPLIT
from recommender.student import itemcf
from recommender.student import cold_start
from recommender.validation import check_request


def history(ratings=(), favorites=()):
    return SimpleNamespace(ratings=tuple(SimpleNamespace(movie_id=movie, rating=str(rating))
                                         for movie, rating in ratings),
                           favorite_movie_ids=tuple(favorites))


class ItemCFTests(unittest.TestCase):
    def test_course_algorithms_are_registered(self):
        register_student_providers()
        self.assertTrue({Algorithm.content, Algorithm.itemcf, Algorithm.popular,
                         Algorithm.cold_start}.issubset(PROVIDERS))

    def test_positive_history_ranks_neighbors_and_excludes_seen_movies(self):
        user = history([("1", 5), ("2", 3)], ["3"])
        neighbors = {"1": (("2", .9), ("4", .8)), "3": (("4", .5), ("5", .4))}
        with patch.object(itemcf, "_neighbors", side_effect=lambda movie: neighbors.get(movie, ())):
            result = itemcf.rank_itemcf(user, 10)
        self.assertEqual([movie for movie, _, _ in result], ["4", "5"])
        self.assertEqual([source for _, _, source in result], ["itemcf", "itemcf"])


class ColdStartTests(unittest.TestCase):
    def setUp(self):
        self.catalog = {"1": ("Action",), "2": ("Drama",), "3": ("Action", "Drama"), "4": ("Comedy",)}

    def test_selected_genre_changes_new_user_results_and_excludes_seen(self):
        user = history([("1", 2)])
        popularity = [("1", 100, 3.5), ("2", 80, 4.1), ("3", 60, 4.0), ("4", 50, 4.2)]
        with patch.object(cold_start, "_genre_catalog", return_value=self.catalog), \
             patch.object(cold_start, "read_popularity", return_value=popularity):
            action = cold_start.rank_cold_start(user, 3, ("Action",))
            drama = cold_start.rank_cold_start(user, 3, ("Drama",))
        self.assertNotEqual([movie for movie, _, _ in action], [movie for movie, _, _ in drama])
        self.assertNotIn("1", [movie for movie, _, _ in action + drama])
        self.assertTrue(all(source == "genre_preference" for _, _, source in action + drama))

    def test_no_behavior_or_preferences_is_explicit_popular_fallback(self):
        popularity = [("1", 100, 3.5), ("2", 80, 4.1)]
        with patch.object(cold_start, "read_popularity", return_value=popularity):
            result = cold_start.rank_cold_start(history(), 2, ())
        self.assertEqual([source for _, _, source in result], ["popular_non_personalized"] * 2)


class RequestValidationTests(unittest.TestCase):
    def test_rejects_more_than_five_genre_preferences(self):
        request = RecommendationRequest("ml", 14, 10, "business", DATASET, SPLIT,
                                        ("Action", "Drama", "Comedy", "Thriller", "War", "Western"))
        with self.assertRaises(ContractError):
            check_request(request)


if __name__ == "__main__":
    unittest.main()
