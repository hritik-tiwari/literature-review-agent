from __future__ import annotations

from src.literature_review_agent.gemini_client import GeminiJSONClient
from src.literature_review_agent.prompts import (
    COMPARISON_PROMPT,
    FINAL_SYNTHESIS_PROMPT,
    PAPER_EXTRACTION_PROMPT,
    PLAN_PROMPT,
)
from src.literature_review_agent.schemas import ReviewResult
from src.literature_review_agent.utils import split_papers


class LiteratureReviewAgent:
    def __init__(self, api_key: str) -> None:
        self.client = GeminiJSONClient(api_key=api_key)

    def run(self, question: str, raw_papers_text: str) -> ReviewResult:
        trace: list[dict] = []
        papers = split_papers(raw_papers_text)

        plan = self.client.generate_json(PLAN_PROMPT, {"question": question})
        trace.append({"stage": "plan", "title": "Generated sub-questions", "payload": plan})

        extracted_papers = []
        for index, paper_text in enumerate(papers, start=1):
            paper_record = self.client.generate_json(
                PAPER_EXTRACTION_PROMPT,
                {
                    "question": question,
                    "paper_index": index,
                    "paper_text": paper_text,
                    "sub_questions": plan.get("sub_questions", []),
                },
            )
            extracted_papers.append(paper_record)
            trace.append(
                {
                    "stage": "extract",
                    "title": f"Extracted paper {index}",
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
            final_review=final_review,
            gaps=comparison.get("gaps", []),
            conflicts=comparison.get("conflicts", []),
            trace=trace,
        )
