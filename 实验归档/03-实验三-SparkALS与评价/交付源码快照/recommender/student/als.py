"""Serve a genuine Spark ALS factor model trained from frozen business history."""
from datetime import datetime, timezone
from functools import lru_cache
import json
from math import isfinite
from pathlib import Path

from ..contracts import Algorithm, RecommendationItem, RecommendationResult
from ..data import DATASET, SPLIT

MODEL_VERSION = "spark-als-explicit-v1"
MODEL_DIR = Path(__file__).resolve().parents[2] / "models/business/als"
MODEL_MANIFEST = MODEL_DIR / "model.json"


def rank_als_factors(user_vector: list[float], item_vectors: dict[str, list[float]],
                     seen: set[str], limit: int) -> list[tuple[str, float]]:
    ranked = []
    for movie_id, vector in item_vectors.items():
        if movie_id in seen or len(vector) != len(user_vector):
            continue
        score = sum(a * b for a, b in zip(user_vector, vector))
        if isfinite(score):
            ranked.append((movie_id, score))
    return sorted(ranked, key=lambda pair: (-pair[1], int(pair[0])))[:limit]


@lru_cache(maxsize=1)
def _factors():
    def load(name):
        with (MODEL_DIR / name).open(encoding="utf-8") as stream:
            return {str(row["id"]): row["features"] for row in map(json.loads, stream)}
    return load("user_factors.jsonl"), load("item_factors.jsonl")


class ALSProvider:
    model_manifest_path = MODEL_MANIFEST

    def recommend(self, request):
        from ..business import read_history
        from .popular import rank_popular
        history = read_history(request)
        seen = {row.movie_id for row in history.ratings} | set(history.favorite_movie_ids)
        users, items = _factors()
        vector = users.get(str(request.subject_id)) if request.subject_kind == "ml" else None
        ranked = [(movie, score, "als") for movie, score in rank_als_factors(vector, items, seen, request.limit)] if vector else []
        if len(ranked) < request.limit:
            existing = {movie for movie, _, _ in ranked}
            ranked.extend((movie, score, "popular_fallback") for movie, score in
                          rank_popular(history, request.limit) if movie not in existing)
        recommendations = [RecommendationItem(movie_id=movie, rank=rank, algorithm=Algorithm.als,
            model_version=MODEL_VERSION, score=round(score, 6), recall_sources=[source])
            for rank, (movie, score, source) in enumerate(ranked[:request.limit], 1)]
        return RecommendationResult(algorithm=Algorithm.als, model_version=MODEL_VERSION,
            dataset_version=DATASET, split_version=SPLIT, runtime_mode=request.runtime_mode,
            generated_at=datetime.now(timezone.utc), items=recommendations)


provider = ALSProvider()
