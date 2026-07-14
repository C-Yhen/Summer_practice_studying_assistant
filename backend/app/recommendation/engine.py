from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RecommendationFeatures:
    knowledge_match: float
    weakness: float
    difficulty_match: float
    preference_match: float
    resource_quality: float
    time_match: float


WEIGHTS = {
    "knowledge_match": 0.30,
    "weakness": 0.25,
    "difficulty_match": 0.20,
    "preference_match": 0.10,
    "resource_quality": 0.10,
    "time_match": 0.05,
}


def score_recommendation(features: RecommendationFeatures) -> tuple[float, dict[str, float]]:
    raw = features.__dict__
    normalized = {name: min(1.0, max(0.0, float(value))) for name, value in raw.items()}
    weighted_score = sum(normalized[name] * weight for name, weight in WEIGHTS.items())
    breakdown = {name: round(normalized[name], 4) for name in WEIGHTS}
    return round(weighted_score * 100, 2), breakdown


def explain_recommendation(
    *, knowledge_name: str, mastery: float, difficulty: str, item_type: str
) -> str:
    return (
        f"推荐该{item_type}，因为你在“{knowledge_name}”上的掌握度为"
        f"{mastery * 100:.0f}%，当前仍需要巩固；内容难度为{difficulty}，"
        "与当前基础和可用学习时间匹配。"
    )
