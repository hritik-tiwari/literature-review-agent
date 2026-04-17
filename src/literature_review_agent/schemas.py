from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PaperRecord:
    title: str
    summary: str
    methods: list[str]
    findings: list[str]
    limitations: list[str]
    relevance_score: int


@dataclass
class ReviewResult:
    final_review: str
    gaps: list[str]
    conflicts: list[str]
    trace: list[dict]

