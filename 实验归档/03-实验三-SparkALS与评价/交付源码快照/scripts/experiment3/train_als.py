"""Train real Spark MLlib ALS on a frozen split; never read held-out labels."""
import argparse
import hashlib
import json
from pathlib import Path
import platform

from pyspark.ml.recommendation import ALS
from pyspark.sql import SparkSession

DATASET = "rec-course-v3-train5-1.0.0"
SPLIT = "temporal-v1-cold500-train5-v3"
SCHEMA = "student-eight-v3"
MANIFEST_SHA = "fcfb9a195a56709773696aab02f769c691778af0eb433a1e0778a71c4b289b9e"
VERSION = "spark-als-explicit-v1"


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("/workspace"))
    parser.add_argument("--mode", choices=["evaluation", "business"], required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    package = root / "data/packages" / DATASET
    source_name = "evaluation/train.csv" if args.mode == "evaluation" else "business/history_ratings.csv"
    source = package / source_name
    manifest_file = package / "manifest.json"
    if digest(manifest_file) != MANIFEST_SHA:
        raise ValueError("Frozen dataset manifest changed")
    frozen = json.loads(manifest_file.read_text(encoding="utf-8"))
    if digest(source) != frozen["files"][source_name]["sha256"]:
        raise ValueError("Frozen training CSV changed")
    output = root / "models" / args.mode / "als"
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite previous ALS run: {output}")
    output.mkdir(parents=True)
    spark = (SparkSession.builder.master("local[2]").appName("CineLab-Experiment3-ALS")
             .config("spark.driver.memory", "4g")
             .config("spark.sql.shuffle.partitions", "8").getOrCreate())
    try:
        ratings = (spark.read.option("header", True).option("inferSchema", False).csv(str(source))
                   .selectExpr("cast(userId as int) userId", "cast(movieId as int) movieId",
                               "cast(rating as double) rating").cache())
        count = ratings.count()
        if count != frozen["files"][source_name]["records"]:
            raise ValueError("Training row count differs from frozen manifest")
        parameters = {"rank": 16, "maxIter": 8, "regParam": 0.1, "seed": 42,
                      "implicitPrefs": False, "nonnegative": False,
                      "coldStartStrategy": "drop", "training_rows": count}
        model = ALS(userCol="userId", itemCol="movieId", ratingCol="rating",
                    rank=16, maxIter=8, regParam=0.1, seed=42,
                    implicitPrefs=False, nonnegative=False, coldStartStrategy="drop").fit(ratings)
        model.write().save(str(output / "spark_model"))
        for frame, name in ((model.userFactors, "user_factors.jsonl"),
                            (model.itemFactors, "item_factors.jsonl")):
            with (output / name).open("w", encoding="utf-8", newline="\n") as stream:
                for row in frame.orderBy("id").toLocalIterator():
                    stream.write(json.dumps({"id": row.id, "features": row.features},
                                            separators=(",", ":")) + "\n")
        artifacts = {str(path.relative_to(output)).replace("\\", "/"): digest(path)
                     for path in sorted((output / "spark_model").rglob("*")) if path.is_file()}
        artifacts.update({name: digest(output / name) for name in
                          ("user_factors.jsonl", "item_factors.jsonl")})
        model_manifest = {
            "algorithm": "als", "model_version": VERSION, "runtime_mode": args.mode,
            "dataset_version": DATASET, "split_version": SPLIT,
            "schema_version": SCHEMA, "manifest_sha256": MANIFEST_SHA,
            "training_files": {source_name: frozen["files"][source_name]["sha256"]},
            "feature_files": {}, "artifacts": artifacts, "parameters": parameters,
            "tool_versions": {"spark": spark.version, "python": platform.python_version(),
                              "pyspark": spark.version}}
        (output / "model.json").write_text(json.dumps(model_manifest, ensure_ascii=False,
                                            indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"mode": args.mode, "rows": count, "users": model.userFactors.count(),
                          "items": model.itemFactors.count(), "output": str(output)}))
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
