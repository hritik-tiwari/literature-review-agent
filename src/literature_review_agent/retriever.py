from __future__ import annotations

import json
import math
import os
import re
import urllib.parse
import urllib.request
from dataclasses import asdict

from src.literature_review_agent.schemas import RankedPaper


SEMANTIC_SCHOLAR_API_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
SEMANTIC_SCHOLAR_FIELDS = ",".join(
    [
        "paperId",
        "title",
        "abstract",
        "year",
        "citationCount",
        "url",
        "venue",
        "publicationDate",
        "authors",
    ]
)
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "how",
    "in",
    "is",
    "it",
    "most",
    "of",
    "on",
    "or",
    "recent",
    "that",
    "the",
    "their",
    "to",
    "using",
    "what",
    "with",
}


class SemanticScholarRetriever:
    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "").strip()

    def search_and_rank(
        self,
        question: str,
        candidate_limit: int = 20,
        keep_top_n: int = 8,
    ) -> list[RankedPaper]:
        papers = self.search_papers(question=question, limit=candidate_limit)
        ranked = [self._rank_paper(question, paper) for paper in papers]
        ranked.sort(key=lambda paper: paper.rank_score, reverse=True)

        selected = ranked[:keep_top_n]
        for index, paper in enumerate(selected, start=1):
            paper.rank = index
        return selected

    def search_papers(self, question: str, limit: int = 20) -> list[dict]:
        params = urllib.parse.urlencode(
            {
                "query": question,
                "limit": str(limit),
                "fields": SEMANTIC_SCHOLAR_FIELDS,
            }
        )
        request = urllib.request.Request(f"{SEMANTIC_SCHOLAR_API_URL}?{params}")
        if self.api_key:
            request.add_header("x-api-key", self.api_key)

        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))

        return payload.get("data", [])

    def _rank_paper(self, question: str, paper: dict) -> RankedPaper:
        title = (paper.get("title") or "").strip()
        abstract = (paper.get("abstract") or "").strip()
        combined_text = f"{title} {abstract}".lower()
        question_terms = self._important_terms(question)

        overlap_terms = sorted(term for term in question_terms if term in combined_text)
        overlap_score = min(len(overlap_terms) / max(len(question_terms), 1), 1.0)

        citation_count = int(paper.get("citationCount") or 0)
        citation_score = min(math.log1p(citation_count) / math.log1p(1000), 1.0)

        year = int(paper.get("year") or 0)
        recency_score = 0.0
        if year:
            recency_score = max(min((year - 2015) / 12, 1.0), 0.0)

        abstract_score = 1.0 if abstract else 0.0
        venue_score = 1.0 if (paper.get("venue") or "").strip() else 0.0

        rank_score = round(
            (overlap_score * 0.5)
            + (citation_score * 0.2)
            + (recency_score * 0.15)
            + (abstract_score * 0.1)
            + (venue_score * 0.05),
            4,
        )

        ranking_reason = self._build_ranking_reason(
            overlap_terms=overlap_terms,
            citation_count=citation_count,
            year=year,
            has_abstract=bool(abstract),
            venue=(paper.get("venue") or "").strip(),
        )

        authors = [author.get("name", "").strip() for author in paper.get("authors", []) if author.get("name")]

        return RankedPaper(
            paper_id=(paper.get("paperId") or "").strip(),
            title=title or "Untitled paper",
            abstract=abstract,
            year=year or None,
            citation_count=citation_count,
            venue=(paper.get("venue") or "").strip(),
            url=(paper.get("url") or "").strip(),
            authors=authors,
            rank=0,
            rank_score=rank_score,
            ranking_reason=ranking_reason,
            matched_terms=overlap_terms,
        )

    @staticmethod
    def _important_terms(text: str) -> set[str]:
        tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9\-]+", text.lower())
        return {token for token in tokens if token not in STOPWORDS and len(token) > 2}

    @staticmethod
    def _build_ranking_reason(
        overlap_terms: list[str],
        citation_count: int,
        year: int,
        has_abstract: bool,
        venue: str,
    ) -> str:
        reasons: list[str] = []
        if overlap_terms:
            reasons.append(f"matches query terms: {', '.join(overlap_terms[:5])}")
        if citation_count:
            reasons.append(f"{citation_count} citations")
        if year:
            reasons.append(f"published in {year}")
        if venue:
            reasons.append(f"venue: {venue}")
        if has_abstract:
            reasons.append("abstract available for extraction")
        return "; ".join(reasons) if reasons else "selected from Semantic Scholar search results"

    @staticmethod
    def ranked_papers_as_dicts(papers: list[RankedPaper]) -> list[dict]:
        return [asdict(paper) for paper in papers]
