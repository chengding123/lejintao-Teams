"""Reproducible frozen validation: predict first, read relevance labels afterward."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import argparse
import hashlib
import json
from math import sqrt
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from recommender.contracts import Algorithm, RecommendationItem, RecommendationResult
from recommender.data import DATASET, SPLIT, SCHEMA, MANIFEST_SHA, FrozenData, sha256
from recommender.evaluation import EvaluationResult, check_evaluation_result, check_predictions, eligible_users, task
from recommender.student.offline_metrics import macro_top10

VERSIONS = {"popular": "popular-bayes-v1", "content": "content-genres-v1",
            "itemcf": "itemcf-cosine-v1", "als": "spark-als-explicit-v1",
            "cold_start": "cold-start-genres-v1"}
PRIOR = 25


def create_manifest(data, name, parameters):
    directory = ROOT / "models/evaluation" / name
    directory.mkdir(parents=True, exist_ok=True)
    artifact = directory / "parameters.json"
    artifact.write_text(json.dumps(parameters, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    body = {"algorithm": name, "model_version": VERSIONS[name], "runtime_mode": "evaluation",
            "dataset_version": DATASET, "split_version": SPLIT, "schema_version": SCHEMA,
            "manifest_sha256": MANIFEST_SHA,
            "training_files": {"evaluation/train.csv": data.manifest["files"]["evaluation/train.csv"]["sha256"]},
            "feature_files": {"movies.csv": data.manifest["files"]["movies.csv"]["sha256"]} if name in {"content", "cold_start"} else {},
            "artifacts": {artifact.name: sha256(artifact)}, "parameters": parameters,
            "tool_versions": {"python": sys.version.split()[0], "numpy": np.__version__}}
    manifest = directory / "model.json"
    manifest.write_text(json.dumps(body, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return manifest


def history(data):
    result = defaultdict(dict)
    for row in data.training():
        result[row["userId"]][row["movieId"]] = float(row["rating"])
    return result


def popularity(all_history):
    counts, sums = Counter(), defaultdict(float)
    for ratings in all_history.values():
        for movie, rating in ratings.items():
            counts[movie] += 1
            sums[movie] += rating
    global_mean = sum(sums.values()) / sum(counts.values())
    scores = {movie: (sums[movie] + PRIOR * global_mean) / (count + PRIOR)
              for movie, count in counts.items()}
    return sorted(scores, key=lambda movie: (-scores[movie], int(movie))), scores


def content_rank(ratings, genres, catalog, limit=10):
    profile = defaultdict(float)
    for movie, rating in ratings.items():
        source = genres.get(movie, ())
        if rating >= 4 and source:
            for genre in source:
                profile[genre] += 1 / sqrt(len(source))
    scored = []
    for movie in catalog - ratings.keys():
        target = genres.get(movie, ())
        if target:
            score = sum(profile[genre] for genre in target) / sqrt(len(target))
            if score:
                scored.append((movie, score))
    return sorted(scored, key=lambda pair: (-pair[1], int(pair[0])))[:limit]


def itemcf_index(all_history, catalog):
    support = Counter()
    co = defaultdict(Counter)
    for ratings in all_history.values():
        liked = [movie for movie, rating in ratings.items() if rating >= 4 and movie in catalog]
        support.update(liked)
        for seed in liked:
            co[seed].update(movie for movie in liked if movie != seed)
    neighbors = {}
    for seed, counts in co.items():
        scored = [(movie, common / sqrt(support[seed] * support[movie]))
                  for movie, common in counts.items() if common >= 2]
        neighbors[seed] = sorted(scored, key=lambda pair: (-pair[1], int(pair[0])))[:200]
    return neighbors


def itemcf_rank(ratings, index, popular_order, popular_scores, limit=10):
    scores = defaultdict(float)
    for seed, rating in ratings.items():
        if rating < 4:
            continue
        for movie, similarity in index.get(seed, ()):
            if movie not in ratings:
                scores[movie] += (rating - 3) * similarity
    ranked = sorted(scores.items(), key=lambda pair: (-pair[1], int(pair[0])))[:limit]
    if len(ranked) < limit:
        present = {movie for movie, _ in ranked}
        for movie in popular_order:
            if movie not in ratings and movie not in present:
                ranked.append((movie, popular_scores[movie]))
                if len(ranked) == limit:
                    break
    return ranked[:limit]


def als_index():
    directory = ROOT / "models/evaluation/als"
    def read(name):
        with (directory / name).open(encoding="utf-8") as stream:
            return {str(row["id"]): row["features"] for row in map(json.loads, stream)}
    users, items = read("user_factors.jsonl"), read("item_factors.jsonl")
    movies = sorted(items, key=int)
    matrix = np.asarray([items[movie] for movie in movies], dtype=np.float32)
    return users, movies, matrix


def als_rank(uid, ratings, index, popular_order, popular_scores, limit=10):
    users, movies, matrix = index
    vector = users.get(uid)
    ranked = []
    if vector is not None:
        scores = matrix @ np.asarray(vector, dtype=np.float32)
        ranked = sorted(((movie, float(score)) for movie, score in zip(movies, scores)
                         if movie not in ratings and np.isfinite(score)),
                        key=lambda pair: (-pair[1], int(pair[0])))[:limit]
    if len(ranked) < limit:
        present = {movie for movie, _ in ranked}
        for movie in popular_order:
            if movie not in ratings and movie not in present:
                ranked.append((movie, popular_scores[movie]))
                if len(ranked) == limit:
                    break
    return ranked[:limit]


def write_predictions(data, algorithm, partition, users, ranker, model_path):
    directory = ROOT / "results/experiment3"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{algorithm}-{partition}-predictions.jsonl"
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for uid in sorted(users, key=int):
            ranked = ranker(uid)
            items = [RecommendationItem(movie_id=movie, rank=rank, algorithm=Algorithm(algorithm),
                                        model_version=VERSIONS[algorithm], score=score)
                     for rank, (movie, score) in enumerate(ranked, 1)]
            dto = RecommendationResult(algorithm=Algorithm(algorithm),
                model_version=VERSIONS[algorithm], dataset_version=DATASET,
                split_version=SPLIT, runtime_mode="evaluation",
                generated_at=datetime.now(timezone.utc), items=items)
            stream.write(json.dumps({"ml_user_id": uid, "result": dto.model_dump(mode="json")},
                                    ensure_ascii=False, separators=(",", ":")) + "\n")
    check_predictions(path, model_path, partition, data)
    return path


def evaluate_predictions(data, algorithm, partition, path, model_path, relevant):
    predictions = {}
    with path.open(encoding="utf-8") as stream:
        for row in map(json.loads, stream):
            predictions[row["ml_user_id"]] = [item["movie_id"] for item in row["result"]["items"]]
    metrics = macro_top10(predictions, relevant, eligible_users(data, partition))
    summary = EvaluationResult(status="completed", runtime_mode="evaluation", algorithm=algorithm,
        model_version=VERSIONS[algorithm], task_sha256=task(data, partition)["task_sha256"],
        model_manifest_sha256=sha256(model_path), dataset_version=DATASET,
        split_version=SPLIT, schema_version=SCHEMA, partition=partition,
        user_count=metrics["user_count"], precision_at_10=metrics["precision_at_10"],
        recall_at_10=metrics["recall_at_10"])
    result_path = path.with_name(path.name.replace("-predictions.jsonl", "-metrics.json"))
    result_path.write_text(summary.model_dump_json(indent=2) + "\n", encoding="utf-8")
    check_evaluation_result(result_path, model_path, data)
    return {**summary.model_dump(), **{key: metrics[key] for key in
            ("users_with_recommendations", "user_coverage", "unique_recommended_movies")},
            "predictions_sha256": sha256(path)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-als", action="store_true", help="Calculate classical baselines while Spark is unavailable; do not publish")
    args = parser.parse_args()
    data = FrozenData()
    catalog = data.catalog()
    all_history = history(data)
    genres = {row["movie_id"]: tuple(g for g in row["genres"].split("|")
               if g and g != "(no genres listed)") for row in data.rows("movies.csv")}
    pop_order, pop_scores = popularity(all_history)
    item_index = itemcf_index(all_history, catalog)
    als = None if args.skip_als else als_index()
    specs = {"popular": {"prior_count": PRIOR, "ranking": "bayesian-average"},
             "content": {"positive_threshold": 4, "similarity": "genre-cosine"},
             "itemcf": {"positive_threshold": 4, "similarity": "positive-cosine",
                        "min_common_users": 2, "max_neighbors_per_item": 200,
                        "fallback": "popular"},
             "cold_start": {"fallback": "popular", "positive_threshold": 4,
                            "support_strategy": "itemcf"}}
    manifests = {name: create_manifest(data, name, spec) for name, spec in specs.items()}
    if not args.skip_als:
        manifests["als"] = ROOT / "models/evaluation/als/model.json"
    warm = eligible_users(data, "validation")
    work = []
    for name in (("popular", "content", "itemcf") if args.skip_als else
                 ("popular", "content", "itemcf", "als")):
        def rank(uid, algorithm=name):
            ratings = all_history.get(uid, {})
            if algorithm == "popular":
                return [(movie, pop_scores[movie]) for movie in pop_order if movie not in ratings][:10]
            if algorithm == "content":
                return content_rank(ratings, genres, catalog)
            if algorithm == "itemcf":
                return itemcf_rank(ratings, item_index, pop_order, pop_scores)
            return als_rank(uid, ratings, als, pop_order, pop_scores)
        path = write_predictions(data, name, "validation", warm, rank, manifests[name])
        work.append((name, "validation", path))
        print(f"Predicted and validated {name} validation: {len(warm)} users", flush=True)
    for partition in ("cold-k0", "cold-k5"):
        cold = eligible_users(data, partition)
        support = defaultdict(dict)
        for row in data.rows(f"evaluation/{partition}-support.csv", evaluation=True):
            support[row["userId"]][row["movieId"]] = float(row["rating"])
        def rank_cold(uid):
            ratings = support[uid]
            return (itemcf_rank(ratings, item_index, pop_order, pop_scores) if
                    any(score >= 4 for score in ratings.values()) else
                    [(movie, pop_scores[movie]) for movie in pop_order if movie not in ratings][:10])
        path = write_predictions(data, "cold_start", partition, cold, rank_cold,
                                 manifests["cold_start"])
        work.append(("cold_start", partition, path))
        print(f"Predicted and validated cold_start {partition}: {len(cold)} users", flush=True)
    # Relevance labels enter only after *all* prediction files have passed validation.
    summaries = []
    for name, partition, path in work:
        label_file = "evaluation/validation.csv" if partition == "validation" else f"evaluation/{partition}-query.csv"
        users = eligible_users(data, partition)
        relevant = {uid: set() for uid in users}
        for row in data.rows(label_file, evaluation=True):
            if row["userId"] in relevant and float(row["rating"]) >= 4:
                relevant[row["userId"]].add(row["movieId"])
        result = evaluate_predictions(data, name, partition, path, manifests[name], relevant)
        summaries.append(result)
        print(f"{name} {partition}: P@10={result['precision_at_10']:.6f} "
              f"R@10={result['recall_at_10']:.6f}", flush=True)
    published = {"status": "completed", "dataset_version": DATASET, "split_version": SPLIT,
                 "positive_threshold": 4.0, "top_k": 10, "source": "frozen evaluation files",
                 "generated_at": datetime.now(timezone.utc).isoformat(), "items": summaries}
    output = (ROOT / "results/experiment3/partial-summary.json" if args.skip_als else
              ROOT / "models/business/experiment3-validation-summary.json")
    output.write_text(json.dumps(published, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Published read-only summary: {output}")


if __name__ == "__main__":
    main()
