"""Bayesian popularity ranking for the business recommendation API."""
from datetime import datetime, timezone
from math import isfinite

from ..business import read_history, read_popularity
from ..contracts import Algorithm, RecommendationItem, RecommendationResult
from ..data import DATASET, SPLIT
from .model_binding import create_model_binding

MODEL_VERSION = "popular-bayes-v1"
PRIOR_COUNT = 25
MODEL_MANIFEST = create_model_binding("popular", MODEL_VERSION, {
    "ranking": "bayesian-average",
    "prior_count": PRIOR_COUNT,
    "source": "business/history_ratings.csv",
    "exclude_seen": True,
})


def rank_popular(history, limit):
    rows = read_popularity()
    total_count = sum(count for _, count, _ in rows)
    global_mean = sum(count * average for _, count, average in rows) / total_count
    seen = {feedback.movie_id for feedback in history.ratings} | set(history.favorite_movie_ids)
    scored = []
    for movie_id, count, average in rows:
        if movie_id in seen:
            continue
        score = (count * average + PRIOR_COUNT * global_mean) / (count + PRIOR_COUNT)
        if isfinite(score):
            scored.append((movie_id, score))
    return sorted(scored, key=lambda item: (-item[1], int(item[0])))[:limit]


class PopularProvider:
    model_manifest_path = MODEL_MANIFEST

    def recommend(self, request):
        history = read_history(request)
        ranked = rank_popular(history, request.limit)
        items = [RecommendationItem(movie_id=movie_id, rank=rank, algorithm=Algorithm.popular,
            model_version=MODEL_VERSION, score=round(score, 6), recall_sources=["popular"])
            for rank, (movie_id, score) in enumerate(ranked, 1)]
        return RecommendationResult(algorithm=Algorithm.popular, model_version=MODEL_VERSION,
            dataset_version=DATASET, split_version=SPLIT, runtime_mode=request.runtime_mode,
            generated_at=datetime.now(timezone.utc), items=items)


provider = PopularProvider()
