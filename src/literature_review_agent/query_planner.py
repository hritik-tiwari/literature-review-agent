from __future__ import annotations

import re


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
DOMAIN_PHRASES = (
    "time series",
    "time-series",
    "forecasting",
    "transformer",
    "transformers",
    "multivariate",
    "univariate",
    "long horizon",
    "long-range",
    "limitations",
)


class QueryPlanner:
    def plan(self, question: str) -> dict:
        keywords = self._extract_keywords(question)
        phrases = self._extract_phrases(question)
        primary_terms = self._pick_primary_terms(keywords, phrases)
        return {
            "question": question,
            "keywords": keywords,
            "phrases": phrases,
            "primary_terms": primary_terms,
            "semantic_scholar_query": self._build_semantic_query(primary_terms, phrases),
            "crossref_query": self._build_crossref_query(primary_terms, phrases),
            "arxiv_query": self._build_arxiv_query(primary_terms, phrases),
        }

    @staticmethod
    def _extract_keywords(question: str) -> list[str]:
        tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9\-]+", question.lower())
        keywords: list[str] = []
        seen: set[str] = set()
        for token in tokens:
            normalized = token.rstrip("s") if token.endswith("s") and len(token) > 4 else token
            if normalized in STOPWORDS or len(normalized) <= 2 or normalized in seen:
                continue
            keywords.append(normalized)
            seen.add(normalized)
        return keywords

    @staticmethod
    def _extract_phrases(question: str) -> list[str]:
        lowered = question.lower()
        phrases = [phrase for phrase in DOMAIN_PHRASES if phrase in lowered]
        deduped: list[str] = []
        seen: set[str] = set()
        for phrase in phrases:
            normalized = phrase.replace("-", " ")
            if normalized in seen:
                continue
            deduped.append(phrase)
            seen.add(normalized)
        return deduped

    @staticmethod
    def _pick_primary_terms(keywords: list[str], phrases: list[str]) -> list[str]:
        terms = [phrase.replace("-", " ") for phrase in phrases[:3]] + keywords
        deduped: list[str] = []
        seen: set[str] = set()
        for term in terms:
            normalized = term.strip()
            if not normalized or normalized in seen:
                continue
            deduped.append(normalized)
            seen.add(normalized)
        return deduped[:8]

    @staticmethod
    def _build_semantic_query(primary_terms: list[str], phrases: list[str]) -> str:
        return " ".join((phrases[:2] + primary_terms)[:8]).strip()

    @staticmethod
    def _build_crossref_query(primary_terms: list[str], phrases: list[str]) -> str:
        return " ".join((phrases[:2] + primary_terms[:6])[:8]).strip()

    @staticmethod
    def _build_arxiv_query(primary_terms: list[str], phrases: list[str]) -> str:
        grouped = [f'all:\"{phrase}\"' for phrase in phrases[:2]]
        for term in primary_terms[:4]:
            grouped.append(f'all:\"{term}\"' if " " in term else f"all:{term}")
        return " AND ".join(grouped) if grouped else "all:forecasting"
