"""Create ephemeral, hash-bound manifests for student-built business providers."""
import hashlib
import json
from pathlib import Path

from ..data import DATASET, SPLIT, SCHEMA, MANIFEST_SHA, FrozenData


def create_model_binding(algorithm: str, model_version: str, specification: dict,
                        feature_files: tuple[str, ...] = ()) -> Path:
    data = FrozenData()
    model_dir = Path("/tmp/cinelab-models") / algorithm
    model_dir.mkdir(parents=True, exist_ok=True)
    artifact_name = f"{algorithm}.artifact.json"
    artifact_text = json.dumps(specification, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    (model_dir / artifact_name).write_text(artifact_text, encoding="utf-8")
    training_hash = data.manifest["files"]["business/history_ratings.csv"]["sha256"]
    manifest = {
        "algorithm": algorithm,
        "model_version": model_version,
        "runtime_mode": "business",
        "dataset_version": DATASET,
        "split_version": SPLIT,
        "schema_version": SCHEMA,
        "manifest_sha256": MANIFEST_SHA,
        "training_files": {"business/history_ratings.csv": training_hash},
        "feature_files": {name: data.manifest["files"][name]["sha256"] for name in feature_files},
        "artifacts": {artifact_name: hashlib.sha256(artifact_text.encode()).hexdigest()},
        "parameters": specification,
        "tool_versions": {"python": "3.12", "algorithm": model_version},
    }
    manifest_path = model_dir / "model.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest_path
