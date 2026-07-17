from __future__ import annotations

from dataclasses import dataclass

ALGORITHM_VERSION = "rule-v2"
BASE_SCORES = {
    "study_task": 35.0,
    "mastery_review": 30.0,
    "course_chat": 45.0,
    "create_plan": 55.0,
    "upload_document": 50.0,
    "weekly_report": 40.0,
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
