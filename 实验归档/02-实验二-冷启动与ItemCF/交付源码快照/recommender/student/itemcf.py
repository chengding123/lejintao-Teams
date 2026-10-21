"""Item-based collaborative filtering from real positive user/movie interactions."""
from collections import defaultdict
from datetime import datetime, timezone
from functools import lru_cache
from math import sqrt

from ..business import read_history, read_positive_interactions
from ..contracts import Algorithm, RecommendationItem, RecommendationResult
from ..data import DATASET, SPLIT
from .model_binding import create_model_binding
from .popular import MODEL_VERSION as POPULAR_MODEL_VERSION, rank_popular

MODEL_VERSION = "itemcf-cosine-v1"
MIN_COMMON_USERS = 2
MAX_NEIGHBORS_PER_ITEM = 200
MODEL_MANIFEST = create_model_binding("itemcf", MODEL_VERSION, {
    "similarity": "positive-interaction-cosine",
    "positive_threshold": 4.0,
    "minimum_common_users": MIN_COMMON_USERS,
    "maximum_neighbors_per_item": MAX_NEIGHBORS_PER_ITEM,
    "source": "business/history_ratings.csv",
    "favorites": "binary-positive-signal",
    "exclude_seen": True,
})


@lru_cache(maxsize=1024)
def _neighbors(movie_id):
    index = read_positive_interactions()
    raters = index.users_by_movie.get(movie_id, ())
    support = len(raters)
    if support < MIN_COMMON_USERS:
        return ()
    cooccurrence = defaultdict(int)
    for user_id in raters:
        for neighbor_id in index.movies_by_user.get(user_id, ()):
            if neighbor_id != movie_id:
                cooccurrence[neighbor_id] += 1
    scored = [(neighbor_id, count / sqrt(support * len(index.users_by_movie[neighbor_id])))
              for neighbor_id, count in cooccurrence.items() if count >= MIN_COMMON_USERS]
    return tuple(sorted(scored, key=lambda item: (-item[1], int(item[0])))[:MAX_NEIGHBORS_PER_ITEM])


def rank_itemcf(history, limit):
    seed_weights = {}
    for feedback in history.ratings:
        rating = float(feedback.rating)
        if rating >= 4.0:
            seed_weights[feedback.movie_id] = max(seed_weights.get(feedback.movie_id, 0.0), rating - 3.0)
    for movie_id in history.favorite_movie_ids:
        seed_weights.setdefault(movie_id, 1.0)
    if not seed_weights:
        return []
    seen = {feedback.movie_id for feedback in history.ratings} | set(history.favorite_movie_ids)
    scores = defaultdict(float)
    for seed_id, weight in seed_weights.items():
        for candidate_id, similarity in _neighbors(seed_id):
            if candidate_id not in seen:
                scores[candidate_id] += weight * similarity
    ranked = sorted(scores.items(), key=lambda item: (-item[1], int(item[0])))[:limit]
    return [(movie_id, score, "itemcf") for movie_id, score in ranked]


def rank_itemcf_with_fallback(history, limit):
    ranked = rank_itemcf(history, limit)
    if len(ranked) >= limit:
        return ranked
    seen = {feedback.movie_id for feedback in history.ratings} | set(history.favorite_movie_ids)
    present = {movie_id for movie_id, _, _ in ranked}
    fallback = [(movie_id, score, "popular_fallback") for movie_id, score in rank_popular(history, limit)
                if movie_id not in present and movie_id not in seen]
    return ranked + fallback[:limit - len(ranked)]


class ItemCFProvider:
    model_manifest_path = MODEL_MANIFEST

    def recommend(self, request):
        history = read_history(request)
        ranked = rank_itemcf_with_fallback(history, request.limit)
        items = [RecommendationItem(movie_id=movie_id, rank=rank, algorithm=Algorithm.itemcf,
            model_version=MODEL_VERSION, score=round(score, 6), recall_sources=[source])
            for rank, (movie_id, score, source) in enumerate(ranked, 1)]
        return RecommendationResult(algorithm=Algorithm.itemcf, model_version=MODEL_VERSION,
            dataset_version=DATASET, split_version=SPLIT, runtime_mode=request.runtime_mode,
            generated_at=datetime.now(timezone.utc), items=items)


provider = ItemCFProvider()
