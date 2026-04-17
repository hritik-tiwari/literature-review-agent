from __future__ import annotations

import hashlib
import html
import json
import math
import os
import re
import time
import urllib.parse
import urllib.error
import urllib.request
from dataclasses import asdict
from pathlib import Path

from src.literature_review_agent.schemas import RankedPaper


ARTIFACTS_DIR = Path(__file__).resolve().parents[2] / "artifacts"
CACHE_DIR = ARTIFACTS_DIR / "retrieval_cache"
CACHE_TTL_SECONDS = 60 * 60 * 24
SEMANTIC_SCHOLAR_SOURCE = "Semantic Scholar"
CROSSREF_SOURCE = "Crossref"
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
CROSSREF_API_URL = "https://api.crossref.org/works"
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "across",
    "appear",
    "as",
    "at",
    "be",
    "by",
    "can",
    "common",
    "do",
    "for",
    "from",
    "how",
    "in",
    "is",
    "it",
    "many",
    "most",
    "often",
    "of",
    "on",
    "or",
    "paper",
    "papers",
    "recent",
    "several",
    "that",
    "the",
    "their",
    "to",
    "using",
    "what",
    "with",
}


class RetrievalError(RuntimeError):
    pass


class SemanticScholarRetriever:
    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "").strip()
        self.crossref_mailto = os.environ.get("CROSSREF_MAILTO", "").strip()

    def search_and_rank(
        self,
        question: str,
        candidate_limit: int = 20,
        keep_top_n: int = 8,
    ) -> list[RankedPaper]:
        papers = self.search_papers(question=question, limit=candidate_limit)
        ranked = [self._rank_paper(question, paper) for paper in papers]
        ranked.sort(key=lambda paper: paper.rank_score, reverse=True)

        ranked_with_abstract = [paper for paper in ranked if paper.abstract]
        ranked_without_abstract = [paper for paper in ranked if not paper.abstract]
        selected = (ranked_with_abstract + ranked_without_abstract)[:keep_top_n]
        for index, paper in enumerate(selected, start=1):
            paper.rank = index
        return selected

    def search_papers(self, question: str, limit: int = 20) -> list[dict]:
        cache_key = self._cache_key(question=question, limit=limit)
        cached_payload = self._load_cache(cache_key)
        if cached_payload is not None:
            return cached_payload.get("papers", [])

        stale_cache = self._load_cache(cache_key, allow_stale=True)
        source_methods = (
            (SEMANTIC_SCHOLAR_SOURCE, self._search_semantic_scholar),
            (CROSSREF_SOURCE, self._search_crossref),
        )
        errors: list[str] = []

        for source_name, source_method in source_methods:
            try:
                papers = source_method(question=question, limit=limit)
                if papers:
                    self._write_cache(cache_key, {"source": source_name, "papers": papers})
                    return papers
                errors.append(f"{source_name}: returned no papers")
            except RetrievalError as exc:
                errors.append(f"{source_name}: {exc}")

        if stale_cache is not None:
            return stale_cache.get("papers", [])

        raise RetrievalError(" | ".join(errors) or "No retrieval source returned papers")

    def _search_semantic_scholar(self, question: str, limit: int) -> list[dict]:
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

        payload = self._fetch_json(request=request, source_name=SEMANTIC_SCHOLAR_SOURCE, retries=3)
        data = payload.get("data", [])
        return [self._normalize_semantic_scholar_paper(paper) for paper in data]

    def _search_crossref(self, question: str, limit: int) -> list[dict]:
        query_text = self._build_crossref_query(question)
        params: dict[str, str] = {
            "query.bibliographic": query_text,
            "rows": str(limit * 2),
            "filter": "type:journal-article",
            "select": "DOI,title,abstract,URL,container-title,published-print,published-online,issued,is-referenced-by-count,author",
        }
        if self.crossref_mailto:
            params["mailto"] = self.crossref_mailto

        request = urllib.request.Request(f"{CROSSREF_API_URL}?{urllib.parse.urlencode(params)}")
        request.add_header("User-Agent", "literature-review-agent/0.1 (mailto optional)")
        payload = self._fetch_json(request=request, source_name=CROSSREF_SOURCE, retries=2)
        items = payload.get("message", {}).get("items", [])
        return [self._normalize_crossref_paper(item) for item in items]

    def _fetch_json(self, request: urllib.request.Request, source_name: str, retries: int) -> dict:
        last_error: str | None = None
        for attempt in range(retries):
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                if exc.code == 429 and attempt < retries - 1:
                    time.sleep(2**attempt)
                    last_error = f"rate limited ({exc.code})"
                    continue
                last_error = f"HTTP {exc.code}"
                break
            except urllib.error.URLError as exc:
                last_error = str(exc.reason)
                break

        raise RetrievalError(f"{source_name} request failed: {last_error or 'unknown error'}")

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
            source=(paper.get("source") or "").strip(),
            overlap_terms=overlap_terms,
            citation_count=citation_count,
            year=year,
            has_abstract=bool(abstract),
            venue=(paper.get("venue") or "").strip(),
        )

        authors = [author.get("name", "").strip() for author in paper.get("authors", []) if author.get("name")]

        return RankedPaper(
            paper_id=(paper.get("paperId") or "").strip(),
            source=(paper.get("source") or "").strip(),
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
    def _build_crossref_query(question: str) -> str:
        ordered_terms: list[str] = []
        seen: set[str] = set()
        tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9\-]+", question.lower())
        for token in tokens:
            normalized = token.rstrip("s") if token.endswith("s") and len(token) > 4 else token
            if normalized in STOPWORDS or len(normalized) <= 2 or normalized in seen:
                continue
            ordered_terms.append(normalized)
            seen.add(normalized)
        return " ".join(ordered_terms[:8]) or question

    @staticmethod
    def _build_ranking_reason(
        source: str,
        overlap_terms: list[str],
        citation_count: int,
        year: int,
        has_abstract: bool,
        venue: str,
    ) -> str:
        reasons: list[str] = []
        if source:
            reasons.append(f"source: {source}")
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

    @staticmethod
    def _normalize_semantic_scholar_paper(paper: dict) -> dict:
        return {
            "paperId": (paper.get("paperId") or "").strip(),
            "source": SEMANTIC_SCHOLAR_SOURCE,
            "title": (paper.get("title") or "").strip(),
            "abstract": (paper.get("abstract") or "").strip(),
            "year": paper.get("year"),
            "citationCount": paper.get("citationCount") or 0,
            "url": (paper.get("url") or "").strip(),
            "venue": (paper.get("venue") or "").strip(),
            "authors": paper.get("authors") or [],
        }

    def _normalize_crossref_paper(self, item: dict) -> dict:
        title = self._first_text(item.get("title"))
        venue = self._first_text(item.get("container-title"))
        abstract = self._clean_crossref_abstract(item.get("abstract") or "")
        year = self._extract_crossref_year(item)
        authors = []
        for author in item.get("author", []):
            name_parts = [author.get("given", "").strip(), author.get("family", "").strip()]
            full_name = " ".join(part for part in name_parts if part).strip()
            if full_name:
                authors.append({"name": full_name})

        return {
            "paperId": (item.get("DOI") or "").strip(),
            "source": CROSSREF_SOURCE,
            "title": title,
            "abstract": abstract,
            "year": year,
            "citationCount": item.get("is-referenced-by-count") or 0,
            "url": (item.get("URL") or "").strip(),
            "venue": venue,
            "authors": authors,
        }

    @staticmethod
    def _first_text(value: object) -> str:
        if isinstance(value, list) and value:
            return str(value[0]).strip()
        if isinstance(value, str):
            return value.strip()
        return ""

    @staticmethod
    def _extract_crossref_year(item: dict) -> int | None:
        date_sources = ("published-print", "published-online", "issued")
        for field in date_sources:
            date_parts = item.get(field, {}).get("date-parts", [])
            if date_parts and date_parts[0]:
                try:
                    return int(date_parts[0][0])
                except (TypeError, ValueError, IndexError):
                    continue
        return None

    @staticmethod
    def _clean_crossref_abstract(raw_abstract: str) -> str:
        if not raw_abstract:
            return ""
        text = re.sub(r"<[^>]+>", " ", raw_abstract)
        text = html.unescape(text)
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _cache_key(question: str, limit: int) -> str:
        digest = hashlib.sha256(f"v2|{question}|{limit}".encode("utf-8")).hexdigest()
        return digest

    def _load_cache(self, cache_key: str, allow_stale: bool = False) -> dict | None:
        cache_path = CACHE_DIR / f"{cache_key}.json"
        if not cache_path.exists():
            return None

        with cache_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)

        cached_at = float(payload.get("cached_at", 0))
        is_fresh = (time.time() - cached_at) <= CACHE_TTL_SECONDS
        if is_fresh or allow_stale:
            return payload
        return None

    def _write_cache(self, cache_key: str, payload: dict) -> None:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_path = CACHE_DIR / f"{cache_key}.json"
        enriched_payload = {
            "cached_at": time.time(),
            **payload,
        }
        with cache_path.open("w", encoding="utf-8") as handle:
            json.dump(enriched_payload, handle, ensure_ascii=True, indent=2)
