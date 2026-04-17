from __future__ import annotations

import hashlib
import html
import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict
from pathlib import Path

from src.literature_review_agent.query_planner import QueryPlanner
from src.literature_review_agent.schemas import RankedPaper


ARTIFACTS_DIR = Path(__file__).resolve().parents[2] / "artifacts"
CACHE_DIR = ARTIFACTS_DIR / "retrieval_cache"
CACHE_TTL_SECONDS = 60 * 60 * 24
SEMANTIC_SCHOLAR_SOURCE = "Semantic Scholar"
ARXIV_SOURCE = "arXiv"
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
ARXIV_API_URL = "http://export.arxiv.org/api/query"
SOURCE_QUALITY = {
    SEMANTIC_SCHOLAR_SOURCE: 1.0,
    ARXIV_SOURCE: 0.92,
    CROSSREF_SOURCE: 0.78,
}
SOURCE_PRIORITY = {
    SEMANTIC_SCHOLAR_SOURCE: 3,
    ARXIV_SOURCE: 2,
    CROSSREF_SOURCE: 1,
}


class RetrievalError(RuntimeError):
    pass


class SemanticScholarRetriever:
    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or ""
        self.query_planner = QueryPlanner()

    def search_and_rank(
        self,
        question: str,
        candidate_limit: int = 20,
        keep_top_n: int = 8,
    ) -> list[RankedPaper]:
        plan = self.query_planner.plan(question)
        papers = self.search_papers(question=question, plan=plan, limit=candidate_limit)
        ranked = [self._rank_paper(question, paper) for paper in papers]
        ranked.sort(key=lambda paper: paper.rank_score, reverse=True)

        ranked_with_abstract = [paper for paper in ranked if paper.abstract]
        ranked_without_abstract = [paper for paper in ranked if not paper.abstract]
        selected = (ranked_with_abstract + ranked_without_abstract)[:keep_top_n]
        for index, paper in enumerate(selected, start=1):
            paper.rank = index
        return selected

    def search_papers(self, question: str, plan: dict, limit: int = 20) -> list[dict]:
        cache_key = self._cache_key(question=question, plan=plan, limit=limit)
        cached_payload = self._load_cache(cache_key)
        if cached_payload is not None:
            return cached_payload.get("papers", [])

        stale_cache = self._load_cache(cache_key, allow_stale=True)
        source_methods = (
            (SEMANTIC_SCHOLAR_SOURCE, self._search_semantic_scholar, plan.get("semantic_scholar_query", question)),
            (ARXIV_SOURCE, self._search_arxiv, plan.get("arxiv_query", question)),
            (CROSSREF_SOURCE, self._search_crossref, plan.get("crossref_query", question)),
        )

        errors: list[str] = []
        aggregated_papers: list[dict] = []
        for source_name, source_method, source_query in source_methods:
            try:
                papers = source_method(query=source_query, limit=limit)
                if papers:
                    aggregated_papers.extend(papers)
                else:
                    errors.append(f"{source_name}: returned no papers")
            except RetrievalError as exc:
                errors.append(f"{source_name}: {exc}")

        deduped_papers = self._dedupe_papers(aggregated_papers)
        if deduped_papers:
            self._write_cache(cache_key, {"plan": plan, "papers": deduped_papers})
            return deduped_papers

        if stale_cache is not None:
            return stale_cache.get("papers", [])

        raise RetrievalError(" | ".join(errors) or "No retrieval source returned papers")

    def _search_semantic_scholar(self, query: str, limit: int) -> list[dict]:
        params = urllib.parse.urlencode(
            {
                "query": query,
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

    def _search_arxiv(self, query: str, limit: int) -> list[dict]:
        params = urllib.parse.urlencode(
            {
                "search_query": query,
                "start": "0",
                "max_results": str(limit),
                "sortBy": "relevance",
                "sortOrder": "descending",
            }
        )
        request = urllib.request.Request(f"{ARXIV_API_URL}?{params}")
        xml_text = self._fetch_text(request=request, source_name=ARXIV_SOURCE, retries=2)
        return self._parse_arxiv_feed(xml_text)

    def _search_crossref(self, query: str, limit: int) -> list[dict]:
        params = {
            "query.bibliographic": query,
            "rows": str(limit * 2),
            "filter": "type:journal-article",
            "select": "DOI,title,abstract,URL,container-title,published-print,published-online,issued,is-referenced-by-count,author",
        }
        request = urllib.request.Request(f"{CROSSREF_API_URL}?{urllib.parse.urlencode(params)}")
        request.add_header("User-Agent", "literature-review-agent/0.2")
        payload = self._fetch_json(request=request, source_name=CROSSREF_SOURCE, retries=2)
        items = payload.get("message", {}).get("items", [])
        return [self._normalize_crossref_paper(item) for item in items]

    def _fetch_json(self, request: urllib.request.Request, source_name: str, retries: int) -> dict:
        text = self._fetch_text(request=request, source_name=source_name, retries=retries)
        return json.loads(text)

    def _fetch_text(self, request: urllib.request.Request, source_name: str, retries: int) -> str:
        last_error: str | None = None
        for attempt in range(retries):
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    return response.read().decode("utf-8")
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
        question_terms = set(self.query_planner.plan(question).get("keywords", []))
        overlap_terms = sorted(term for term in question_terms if term in combined_text)
        overlap_score = min(len(overlap_terms) / max(len(question_terms), 1), 1.0)

        citation_count = int(paper.get("citationCount") or 0)
        citation_score = min(math.log1p(citation_count) / math.log1p(1000), 1.0)
        year = int(paper.get("year") or 0)
        recency_score = max(min((year - 2016) / 10, 1.0), 0.0) if year else 0.0
        abstract_score = min(len(abstract.split()) / 180, 1.0) if abstract else 0.0
        venue_score = 1.0 if (paper.get("venue") or "").strip() else 0.0
        source = (paper.get("source") or "").strip()
        source_quality = SOURCE_QUALITY.get(source, 0.65)
        multi_source_bonus = 0.05 if len(paper.get("sources_seen") or []) > 1 else 0.0

        rank_score = round(
            (overlap_score * 0.4)
            + (citation_score * 0.15)
            + (recency_score * 0.12)
            + (abstract_score * 0.12)
            + (venue_score * 0.04)
            + (source_quality * 0.12)
            + multi_source_bonus,
            4,
        )

        authors = [author.get("name", "").strip() for author in paper.get("authors", []) if author.get("name")]
        return RankedPaper(
            paper_id=(paper.get("paperId") or "").strip(),
            source=source,
            source_quality=source_quality,
            source_priority=SOURCE_PRIORITY.get(source, 0),
            title=title or "Untitled paper",
            abstract=abstract,
            year=year or None,
            citation_count=citation_count,
            venue=(paper.get("venue") or "").strip(),
            url=(paper.get("url") or "").strip(),
            authors=authors,
            rank=0,
            rank_score=rank_score,
            ranking_reason=self._build_ranking_reason(
                source=source,
                overlap_terms=overlap_terms,
                citation_count=citation_count,
                year=year,
                has_abstract=bool(abstract),
                venue=(paper.get("venue") or "").strip(),
                sources_seen=list(paper.get("sources_seen") or [source]),
            ),
            matched_terms=overlap_terms,
            dedup_key=(paper.get("dedup_key") or "").strip(),
            sources_seen=list(paper.get("sources_seen") or [source]),
        )

    @staticmethod
    def _build_ranking_reason(
        source: str,
        overlap_terms: list[str],
        citation_count: int,
        year: int,
        has_abstract: bool,
        venue: str,
        sources_seen: list[str],
    ) -> str:
        reasons: list[str] = []
        if source:
            reasons.append(f"primary source: {source}")
        if len(sources_seen) > 1:
            reasons.append(f"confirmed across {len(sources_seen)} sources")
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
        return "; ".join(reasons) if reasons else "selected from scholarly search results"

    @staticmethod
    def ranked_papers_as_dicts(papers: list[RankedPaper]) -> list[dict]:
        return [asdict(paper) for paper in papers]

    @staticmethod
    def _normalize_semantic_scholar_paper(paper: dict) -> dict:
        title = (paper.get("title") or "").strip()
        paper_id = (paper.get("paperId") or "").strip()
        return {
            "paperId": paper_id,
            "source": SEMANTIC_SCHOLAR_SOURCE,
            "title": title,
            "abstract": (paper.get("abstract") or "").strip(),
            "year": paper.get("year"),
            "citationCount": paper.get("citationCount") or 0,
            "url": (paper.get("url") or "").strip(),
            "venue": (paper.get("venue") or "").strip(),
            "authors": paper.get("authors") or [],
            "dedup_key": SemanticScholarRetriever._make_dedup_key(title, paper_id),
            "sources_seen": [SEMANTIC_SCHOLAR_SOURCE],
        }

    def _normalize_crossref_paper(self, item: dict) -> dict:
        title = self._first_text(item.get("title"))
        venue = self._first_text(item.get("container-title"))
        abstract = self._clean_crossref_abstract(item.get("abstract") or "")
        year = self._extract_crossref_year(item)
        doi = (item.get("DOI") or "").strip()
        return {
            "paperId": doi,
            "source": CROSSREF_SOURCE,
            "title": title,
            "abstract": abstract,
            "year": year,
            "citationCount": item.get("is-referenced-by-count") or 0,
            "url": (item.get("URL") or "").strip(),
            "venue": venue,
            "authors": self._normalize_crossref_authors(item.get("author", [])),
            "dedup_key": self._make_dedup_key(title, doi),
            "sources_seen": [CROSSREF_SOURCE],
        }

    def _parse_arxiv_feed(self, xml_text: str) -> list[dict]:
        namespace = {"atom": "http://www.w3.org/2005/Atom"}
        root = ET.fromstring(xml_text)
        papers: list[dict] = []
        for entry in root.findall("atom:entry", namespace):
            entry_id = self._xml_text(entry, "atom:id", namespace)
            title = self._normalize_whitespace(self._xml_text(entry, "atom:title", namespace))
            abstract = self._normalize_whitespace(self._xml_text(entry, "atom:summary", namespace))
            published = self._xml_text(entry, "atom:published", namespace)
            year = int(published[:4]) if published[:4].isdigit() else None
            authors = []
            for author in entry.findall("atom:author", namespace):
                name = self._xml_text(author, "atom:name", namespace)
                if name:
                    authors.append({"name": name})
            papers.append(
                {
                    "paperId": entry_id,
                    "source": ARXIV_SOURCE,
                    "title": title,
                    "abstract": abstract,
                    "year": year,
                    "citationCount": 0,
                    "url": entry_id,
                    "venue": "arXiv",
                    "authors": authors,
                    "dedup_key": self._make_dedup_key(title, entry_id),
                    "sources_seen": [ARXIV_SOURCE],
                }
            )
        return papers

    @staticmethod
    def _dedupe_papers(papers: list[dict]) -> list[dict]:
        deduped: dict[str, dict] = {}
        for paper in papers:
            dedup_key = paper.get("dedup_key") or SemanticScholarRetriever._make_dedup_key(
                (paper.get("title") or "").strip(),
                (paper.get("paperId") or "").strip(),
            )
            paper["dedup_key"] = dedup_key
            if not dedup_key:
                continue
            if dedup_key not in deduped:
                deduped[dedup_key] = paper
            else:
                deduped[dedup_key] = SemanticScholarRetriever._merge_papers(deduped[dedup_key], paper)
        return list(deduped.values())

    @staticmethod
    def _merge_papers(left: dict, right: dict) -> dict:
        left_priority = SOURCE_PRIORITY.get(left.get("source", ""), 0)
        right_priority = SOURCE_PRIORITY.get(right.get("source", ""), 0)
        preferred = left if left_priority >= right_priority else right
        secondary = right if preferred is left else left
        return {
            "paperId": preferred.get("paperId") or secondary.get("paperId") or "",
            "source": preferred.get("source") or secondary.get("source") or "",
            "title": preferred.get("title") or secondary.get("title") or "",
            "abstract": preferred.get("abstract") or secondary.get("abstract") or "",
            "year": preferred.get("year") or secondary.get("year"),
            "citationCount": max(int(preferred.get("citationCount") or 0), int(secondary.get("citationCount") or 0)),
            "url": preferred.get("url") or secondary.get("url") or "",
            "venue": preferred.get("venue") or secondary.get("venue") or "",
            "authors": SemanticScholarRetriever._merge_authors(preferred.get("authors", []), secondary.get("authors", [])),
            "dedup_key": preferred.get("dedup_key") or secondary.get("dedup_key") or "",
            "sources_seen": sorted(set((preferred.get("sources_seen") or [preferred.get("source")]) + (secondary.get("sources_seen") or [secondary.get("source")]))),
        }

    @staticmethod
    def _merge_authors(left: list[dict], right: list[dict]) -> list[dict]:
        seen: set[str] = set()
        merged: list[dict] = []
        for author in left + right:
            name = (author.get("name") or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            merged.append({"name": name})
        return merged

    @staticmethod
    def _normalize_crossref_authors(authors: list[dict]) -> list[dict]:
        normalized: list[dict] = []
        for author in authors:
            name_parts = [author.get("given", "").strip(), author.get("family", "").strip()]
            full_name = " ".join(part for part in name_parts if part).strip()
            if full_name:
                normalized.append({"name": full_name})
        return normalized

    @staticmethod
    def _make_dedup_key(title: str, paper_id: str) -> str:
        lowered = paper_id.lower()
        if lowered.startswith("10."):
            return lowered
        if "doi.org/" in lowered:
            return lowered.split("doi.org/", 1)[1]
        normalized_title = "".join(ch for ch in title.lower() if ch.isalnum())
        return normalized_title[:160]

    @staticmethod
    def _xml_text(element: ET.Element, path: str, namespace: dict[str, str]) -> str:
        child = element.find(path, namespace)
        return child.text.strip() if child is not None and child.text else ""

    @staticmethod
    def _normalize_whitespace(text: str) -> str:
        return " ".join(text.split())

    @staticmethod
    def _first_text(value: object) -> str:
        if isinstance(value, list) and value:
            return str(value[0]).strip()
        if isinstance(value, str):
            return value.strip()
        return ""

    @staticmethod
    def _extract_crossref_year(item: dict) -> int | None:
        for field in ("published-print", "published-online", "issued"):
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
        text = html.unescape(raw_abstract)
        cleaned = []
        in_tag = False
        for char in text:
            if char == "<":
                in_tag = True
            elif char == ">":
                in_tag = False
            elif not in_tag:
                cleaned.append(char)
        return " ".join("".join(cleaned).split())

    @staticmethod
    def _cache_key(question: str, plan: dict, limit: int) -> str:
        payload = json.dumps({"question": question, "plan": plan, "limit": limit}, sort_keys=True)
        return hashlib.sha256(f"v3|{payload}".encode("utf-8")).hexdigest()

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
        with cache_path.open("w", encoding="utf-8") as handle:
            json.dump({"cached_at": time.time(), **payload}, handle, ensure_ascii=True, indent=2)
