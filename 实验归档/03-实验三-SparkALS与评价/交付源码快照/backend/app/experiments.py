from functools import lru_cache
import json
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Query, Request
from pydantic import Field
from sqlalchemy import text

from recommender.contracts import Algorithm, AlgorithmNotImplemented, RecommendationRequest, RecommendationResult, PROVIDERS, recommend, register_student_providers
from recommender.data import ContractError, FrozenData, require
from .config import DATASET, SPLIT
from .errors import APIError
from .schemas import IdPath, Input, identifier
from .security import ActorDependency

router = APIRouter(tags=["学生算法预留边界"])


class RecommendationQuery(Input):
    limit: int = Field(default=10, ge=1, le=50)
    genres: str = Field(default="", max_length=200)


@lru_cache(maxsize=1)
def allowed_genres():
    values = set()
    for row in FrozenData().rows("movies.csv"):
        values.update(genre for genre in row["genres"].split("|") if genre and genre != "(no genres listed)")
    return values


def invoke(algorithm: Algorithm, kind: str, uid: int, limit: int, genres: str = ""):
    try:
        preferred_genres = tuple(dict.fromkeys(part.strip() for part in genres.split(",") if part.strip()))
        require(algorithm == Algorithm.cold_start or not preferred_genres,
                "只有冷启动策略接受类型偏好", "REQUEST_CONTEXT_INVALID")
        require(len(preferred_genres) <= 5 and all(genre in allowed_genres() for genre in preferred_genres),
                "类型偏好最多5项且必须来自电影目录", "REQUEST_CONTEXT_INVALID")
        request = RecommendationRequest(kind, uid, limit, "business", DATASET, SPLIT, preferred_genres)
        return recommend(algorithm, request)
    except AlgorithmNotImplemented:
        raise APIError(501, "ALGORITHM_NOT_IMPLEMENTED", "此推荐算法留给学生实现", {
            "status": "not_implemented", "algorithm": algorithm.value, "subject_key": kind + ":" + str(uid),
            "dataset_version": DATASET, "split_version": SPLIT, "runtime_mode": "business",
            "model_version": None, "batch_id": None, "items": []}) from None
    except ContractError as exc:
        status = 503 if exc.code in {"MODEL_BINDING_INVALID", "DATA_IDENTITY_INVALID", "DATA_MODE_INVALID"} else 422 if exc.code == "REQUEST_CONTEXT_INVALID" else 500
        raise APIError(status,
            exc.code, str(exc)) from None


@router.get("/experiments/algorithms")
def algorithms():
    register_student_providers()
    return {"items": [{"algorithm": algorithm.value, "status": "registered" if algorithm in PROVIDERS else "not_implemented"} for algorithm in Algorithm]}


@router.get("/experiments/evaluations")
def evaluations():
    # Only an offline-produced aggregate is mounted here. Business API cannot read
    # validation/test labels, evaluation/train.csv, or the evaluation database.
    summary = Path(__file__).resolve().parents[2] / "models/business/experiment3-validation-summary.json"
    if not summary.is_file():
        raise APIError(501, "EVALUATION_NOT_IMPLEMENTED", "离线评价尚未生成", {
            "status": "not_implemented", "metrics": None,
            "dataset_version": DATASET, "split_version": SPLIT})
    try:
        value = json.loads(summary.read_text(encoding="utf-8"))
        if (value["status"] != "completed" or value["dataset_version"] != DATASET or
                value["split_version"] != SPLIT or len(value["items"]) < 5):
            raise ValueError("Evaluation summary identity is invalid")
        return value
    except (OSError, ValueError, KeyError, TypeError):
        raise APIError(503, "EVALUATION_SUMMARY_INVALID", "离线评价摘要不可用或数据版本不匹配") from None


@router.get("/me/recommendations/{algorithm}", response_model=RecommendationResult)
def my_recommendations(algorithm: Algorithm, actor: ActorDependency, query: Annotated[RecommendationQuery, Query()]):
    return invoke(algorithm, "app", actor.account_id, query.limit, query.genres)


@router.get("/demo/history-users/{ml_user_id}/recommendations/{algorithm}", response_model=RecommendationResult)
def history_recommendations(ml_user_id: IdPath, algorithm: Algorithm, request: Request,
                            query: Annotated[RecommendationQuery, Query()]):
    uid = identifier(ml_user_id)
    with request.app.state.db.connection() as conn:
        if conn.execute(text("SELECT ml_user_id FROM history_users WHERE ml_user_id=:id"), {"id": uid}).first() is None:
            raise APIError(404, "HISTORY_USER_NOT_FOUND", "历史匿名用户不存在")
    return invoke(algorithm, "ml", uid, query.limit, query.genres)
