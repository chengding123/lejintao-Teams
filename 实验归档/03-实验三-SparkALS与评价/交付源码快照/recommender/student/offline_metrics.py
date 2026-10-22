"""Frozen-user Top-10 metrics; never read labels before predictions are sealed."""


def macro_top10(predictions: dict[str, list[str]], relevant: dict[str, set[str]],
                eligible: set[str]) -> dict:
    if set(predictions) != eligible or set(relevant) != eligible or not eligible:
        raise ValueError("Predictions and labels must cover the same fixed eligible users")
    precision = recall = nonempty = 0.0
    unique = set()
    for uid in eligible:
        movies = predictions[uid]
        if len(movies) > 10 or len(movies) != len(set(movies)):
            raise ValueError("Each user must have at most 10 unique movies")
        hits = len(set(movies) & relevant[uid])
        precision += hits / 10  # Short/empty lists still use the fixed denominator.
        recall += hits / len(relevant[uid]) if relevant[uid] else 0.0
        nonempty += bool(movies)
        unique.update(movies)
    count = len(eligible)
    return {"precision_at_10": precision / count, "recall_at_10": recall / count,
            "user_count": count, "users_with_recommendations": int(nonempty),
            "user_coverage": nonempty / count, "unique_recommended_movies": len(unique)}
