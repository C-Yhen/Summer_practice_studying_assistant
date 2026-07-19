from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Literal

ALGORITHM_VERSION = "rule-v2"
BASE_SCORES = {
    "study_task": 35.0,
    "mastery_review": 30.0,
    "course_chat": 45.0,
    "create_plan": 55.0,
    "upload_document": 50.0,
    "weekly_report": 40.0,
}

RecommendationCategory = Literal["task", "mastery", "resource", "plan", "report"]

CATEGORY_BY_ITEM_TYPE: dict[str, RecommendationCategory] = {
    "study_task": "task",
    "mastery_review": "mastery",
    "course_chat": "resource",
    "upload_document": "resource",
    "create_plan": "plan",
    "weekly_report": "report",
}

CATEGORY_LABELS: dict[RecommendationCategory, str] = {
    "task": "学习任务",
    "mastery": "薄弱点复习",
    "resource": "资料与问答",
    "plan": "学习计划",
    "report": "学习复盘",
}

DEFAULT_CATEGORY_LIMITS: dict[RecommendationCategory, int] = {
    "task": 2,
    "mastery": 1,
    "resource": 1,
    "plan": 1,
    "report": 1,
}


@dataclass(frozen=True)
class Signal:
    code: str
    label: str
    value: float
    contribution: float

    def payload(self) -> dict[str, float | str]:
        return {
            "code": self.code,
            "label": self.label,
            "value": round(min(1.0, max(0.0, self.value)), 4),
            "contribution": round(self.contribution, 2),
        }


def score(signals: list[Signal]) -> tuple[float, dict[str, float]]:
    contributions = {signal.code: round(signal.contribution, 2) for signal in signals}
    return round(min(100.0, max(0.0, sum(contributions.values()))), 2), contributions


def base_signal(item_type: str) -> Signal:
    return Signal("rule_base", "规则基础分", 1.0, BASE_SCORES[item_type])


def recommendation_key(course_id: int, item_type: str, item_id: int) -> str:
    return f"{ALGORITHM_VERSION}:{course_id}:{item_type}:{item_id}"


def category_for_item_type(item_type: str) -> RecommendationCategory:
    try:
        return CATEGORY_BY_ITEM_TYPE[item_type]
    except KeyError as error:
        raise ValueError(f"Unsupported recommendation item type: {item_type}") from error


def recommendation_sort_key(item: dict) -> tuple[float, str, int]:
    return (-float(item["score"]), str(item["item_type"]), int(item["item_id"]))


def _is_high_priority_task(item: dict) -> bool:
    return item["category"] == "task" and any(
        signal["code"] in {"overdue", "due_today"} for signal in item["signals"]
    )


def select_diverse_recommendations(candidates: list[dict], limit: int) -> list[dict]:
    """Select deterministic, score-first recommendations without one category monopolizing the default view."""
    ranked = sorted(candidates, key=recommendation_sort_key)
    selected: list[dict] = []
    selected_keys: set[str] = set()
    category_counts: dict[str, int] = {category: 0 for category in DEFAULT_CATEGORY_LIMITS}
    high_priority_tasks = 0
    deferred_high_priority: list[dict] = []

    for candidate in ranked:
        if len(selected) >= limit:
            break
        category = candidate["category"]
        if category_counts[category] >= DEFAULT_CATEGORY_LIMITS[category]:
            continue
        selected.append(candidate)
        selected_keys.add(candidate["recommendation_key"])
        category_counts[category] += 1
        high_priority_tasks += int(_is_high_priority_task(candidate))

    non_task_candidates_exist = any(candidate["category"] != "task" for candidate in ranked)
    task_ceiling = max(2, ceil(limit / 2))
    for candidate in ranked:
        if len(selected) >= limit:
            break
        if candidate["recommendation_key"] in selected_keys:
            continue
        if candidate["category"] == "task":
            if non_task_candidates_exist and category_counts["task"] >= task_ceiling:
                continue
            if _is_high_priority_task(candidate) and high_priority_tasks >= 2:
                deferred_high_priority.append(candidate)
                continue
        selected.append(candidate)
        selected_keys.add(candidate["recommendation_key"])
        category_counts[candidate["category"]] += 1
        high_priority_tasks += int(_is_high_priority_task(candidate))

    for candidate in deferred_high_priority:
        if len(selected) >= limit:
            break
        if non_task_candidates_exist and category_counts["task"] >= task_ceiling:
            continue
        selected.append(candidate)
        selected_keys.add(candidate["recommendation_key"])
        category_counts[candidate["category"]] += 1

    return sorted(selected, key=recommendation_sort_key)
