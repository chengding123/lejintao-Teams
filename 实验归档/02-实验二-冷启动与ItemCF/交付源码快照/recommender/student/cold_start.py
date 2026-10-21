"""Actionable genre-preference cold start with explicit popularity fallback."""
from datetime import datetime, timezone
from functools import lru_cache

from ..business import read_history, read_popularity
from ..contracts import Algorithm, RecommendationItem, RecommendationResult
from ..data import DATASET, SPLIT, FrozenData
from .itemcf import rank_itemcf_with_fallback
from .model_binding import create_model_binding
from .popular import PRIOR_COUNT

MODEL_VERSION = "cold-start-genres-v1"
MODEL_MANIFEST = create_model_binding("cold_start", MODEL_VERSION, {
    "new_user": "genre-preference-then-bayesian-popularity",
    "known_user": "itemcf-when-positive-history-exists",
    "fallback": "popular-non-personalized",
    "maximum_preferences": 5,
    "exclude_seen": True,
    "source": "business/history_ratings.csv",
})


@lru_cache(maxsize=1)
def _genre_catalog():
    return {row["movie_id"]: tuple(genre for genre in row["genres"].split("|")
                                   if genre and genre != "(no genres listed)")
            for row in FrozenData().rows("movies.csv")}


def _popularity_scores(rows):
    total_count = sum(count for _, count, _ in rows)
    mean = sum(count * average for _, count, average in rows) / total_count
    return {movie_id: (count * average + PRIOR_COUNT * mean) / (count + PRIOR_COUNT)
            for movie_id, count, average in rows}


def rank_cold_start(history, limit, preferred_genres=()):
    seeds = any(float(feedback.rating) >= 4.0 for feedback in history.ratings) or bool(history.favorite_movie_ids)
    if seeds:
        return rank_itemcf_with_fallback(history, limit)

    seen = {feedback.movie_id for feedback in history.ratings} | set(history.favorite_movie_ids)
    popularity = _popularity_scores(read_popularity())
    if preferred_genres:
        requested = set(preferred_genres)
        catalog = _genre_catalog()
        candidates = []
        for movie_id, genres in catalog.items():
            matches = len(requested.intersection(genres))
            if matches and movie_id not in seen and movie_id in popularity:
                candidates.append((movie_id, matches, popularity[movie_id]))
        candidates.sort(key=lambda item: (-item[1], -item[2], int(item[0])))
        return [(movie_id, popularity_score, "genre_preference")
                for movie_id, _, popularity_score in candidates[:limit]]

    ranked = sorted(((movie_id, score) for movie_id, score in popularity.items() if movie_id not in seen),
                    key=lambda item: (-item[1], int(item[0])))[:limit]
    return [(movie_id, score, "popular_non_personalized") for movie_id, score in ranked]


class ColdStartProvider:
    model_manifest_path = MODEL_MANIFEST

    def recommend(self, request):
        history = read_history(request)
        ranked = rank_cold_start(history, request.limit, request.preferred_genres)
        items = [RecommendationItem(movie_id=movie_id, rank=rank, algorithm=Algorithm.cold_start,
            model_version=MODEL_VERSION, score=round(score, 6), recall_sources=[source])
            for rank, (movie_id, score, source) in enumerate(ranked, 1)]
        return RecommendationResult(algorithm=Algorithm.cold_start, model_version=MODEL_VERSION,
            dataset_version=DATASET, split_version=SPLIT, runtime_mode=request.runtime_mode,
            generated_at=datetime.now(timezone.utc), items=items)


provider = ColdStartProvider()
