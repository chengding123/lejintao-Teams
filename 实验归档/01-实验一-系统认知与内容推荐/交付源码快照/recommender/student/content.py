"""Content-based recommendation provider for Experiment 1."""
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from math import sqrt
from pathlib import Path

from ..contracts import Algorithm, RecommendationItem, RecommendationResult
from ..data import DATASET, SPLIT, FrozenData

MODEL_VERSION = "content-genres-v1"
MODEL_DIR = Path("/tmp/cinelab-content-model")
MODEL_MANIFEST = MODEL_DIR / "content_model.json"
MODEL_ARTIFACT = MODEL_DIR / "content_model.artifact.json"


def _ensure_model_files():
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    artifact = json.dumps({"algorithm": "content", "feature": "genres-multi-hot",
        "similarity": "cosine", "positive_threshold": 4.0, "exclude_seen": True,
        "model_version": MODEL_VERSION}, indent=2, sort_keys=True) + "\n"
    MODEL_ARTIFACT.write_text(artifact, encoding="utf-8")
    artifact_sha = hashlib.sha256(artifact.encode()).hexdigest()
    manifest = {"algorithm": "content", "model_version": MODEL_VERSION, "runtime_mode": "business",
        "dataset_version": DATASET, "split_version": SPLIT, "schema_version": "student-eight-v3",
        "manifest_sha256": "fcfb9a195a56709773696aab02f769c691778af0eb433a1e0778a71c4b289b9e",
        "training_files": {"business/history_ratings.csv": "b73992a5390d668e80d777bc7425404dd3a850dd5b7eaad5abc7f4cac21ff438"},
        "feature_files": {"movies.csv": "99f7951a528890bc6ca088b65987790e926adc8f595971346b5b606e4c71454e"},
        "artifacts": {MODEL_ARTIFACT.name: artifact_sha},
        "parameters": {"positive_threshold": 4.0, "similarity": "cosine", "feature": "genres-multi-hot"},
        "tool_versions": {"python": "3.12", "algorithm": MODEL_VERSION}}
    MODEL_MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


_ensure_model_files()


def _load_movies():
    data = FrozenData()
    movies = {}
    for row in data.rows("movies.csv"):
        genres = tuple(g for g in row["genres"].split("|") if g and g != "(no genres listed)")
        movies[row["movie_id"]] = genres
    return movies


def _similarity(left, right):
    if not left or not right:
        return 0.0
    left_set, right_set = set(left), set(right)
    return len(left_set & right_set) / sqrt(len(left_set) * len(right_set))


class ContentProvider:
    model_manifest_path = MODEL_MANIFEST

    def recommend(self, request):
        from ..business import read_history
        movies = _load_movies()
        history = read_history(request)
        seen = {feedback.movie_id for feedback in history.ratings}
        liked = {feedback.movie_id for feedback in history.ratings if float(feedback.rating) >= 4.0}
        scores = defaultdict(float)
        for source_id in liked:
            source_genres = movies.get(source_id, ())
            for candidate_id, candidate_genres in movies.items():
                if candidate_id in seen:
                    continue
                similarity = _similarity(source_genres, candidate_genres)
                if similarity:
                    scores[candidate_id] += similarity
        ranked = sorted(scores.items(), key=lambda pair: (-pair[1], int(pair[0])))[:request.limit]
        items = [RecommendationItem(movie_id=movie_id, rank=rank, algorithm=Algorithm.content,
                                    model_version=MODEL_VERSION, score=round(score, 6))
                 for rank, (movie_id, score) in enumerate(ranked, 1)]
        return RecommendationResult(algorithm=Algorithm.content, model_version=MODEL_VERSION,
            dataset_version=DATASET, split_version=SPLIT, runtime_mode=request.runtime_mode,
            generated_at=datetime.now(timezone.utc), items=items)


provider = ContentProvider()
