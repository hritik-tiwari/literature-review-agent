from __future__ import annotations

from dataclasses import asdict

from src.literature_review_agent.gemini_client import GeminiJSONClient
from src.literature_review_agent.prompts import (
    COMPARISON_PROMPT,
    FINAL_SYNTHESIS_PROMPT,
    PAPER_EXTRACTION_PROMPT,
    PLAN_PROMPT,
)
from src.literature_review_agent.schemas import ReviewResult
from src.literature_review_agent.retriever import SemanticScholarRetriever


class LiteratureReviewAgent:
    def __init__(self, api_key: str) -> None:
        self.client = GeminiJSONClient(api_key=api_key)
        self.retriever = SemanticScholarRetriever()

    def run(
        self,
        question: str,
        candidate_limit: int = 20,
        keep_top_n: int = 8,
    ) -> ReviewResult:
        trace: list[dict] = []

        selected_papers = self.retriever.search_and_rank(
            question=question,
            candidate_limit=candidate_limit,
            keep_top_n=keep_top_n,
        )
        trace.append(
            {
                "stage": "retrieve",
                "title": "Retrieved and ranked candidate papers",
                "payload": {
                    "candidate_limit": candidate_limit,
                    "selected_count": len(selected_papers),
                    "papers": [asdict(paper) for paper in selected_papers],
                },
            }
        )

        plan = self.client.generate_json(PLAN_PROMPT, {"question": question})
        trace.append({"stage": "plan", "title": "Generated sub-questions", "payload": plan})

        extracted_papers = []
        for paper in selected_papers:
            paper_record = self.client.generate_json(
                PAPER_EXTRACTION_PROMPT,
                {
                    "question": question,
                    "paper": {
                        "title": paper.title,
                        "abstract": paper.abstract,
                        "year": paper.year,
                        "citation_count": paper.citation_count,
                        "venue": paper.venue,
                        "authors": paper.authors,
                        "rank_score": paper.rank_score,
                        "ranking_reason": paper.ranking_reason,
                    },
                    "sub_questions": plan.get("sub_questions", []),
                },
            )
            extracted_papers.append(paper_record)
            trace.append(
                {
                    "stage": "extract",
                    "title": f"Extracted evidence for rank {paper.rank}",
                    "payload": paper_record,
                }
            )

        comparison = self.client.generate_json(
            COMPARISON_PROMPT,
            {"question": question, "papers": extracted_papers},
        )
        trace.append({"stage": "compare", "title": "Compared evidence", "payload": comparison})

        final_review = self.client.generate_text(
            FINAL_SYNTHESIS_PROMPT,
            {
                "question": question,
                "sub_questions": plan.get("sub_questions", []),
                "papers": extracted_papers,
                "comparison": comparison,
            },
        )
        trace.append(
            {
                "stage": "synthesize",
                "title": "Generated final review",
                "payload": {"preview": final_review[:1200]},
            }
        )

        return ReviewResult(
            selected_papers=selected_papers,
            extracted_evidence=extracted_papers,
            final_review=final_review,
            gaps=comparison.get("gaps", []),
            conflicts=comparison.get("conflicts", []),
            trace=trace,
        )
