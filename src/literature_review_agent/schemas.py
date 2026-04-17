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
class RankedPaper:
    paper_id: str
    source: str
    title: str
    abstract: str
    year: int | None
    citation_count: int
    venue: str
    url: str
    authors: list[str]
    rank: int
    rank_score: float
    ranking_reason: str
    matched_terms: list[str]


@dataclass
class ReviewResult:
    selected_papers: list[RankedPaper]
    extracted_evidence: list[dict]
    final_review: str
    gaps: list[str]
    conflicts: list[str]
    trace: list[dict]
