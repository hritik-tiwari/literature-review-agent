from __future__ import annotations

import os

import streamlit as st

from src.literature_review_agent.agent import LiteratureReviewAgent


st.set_page_config(page_title="Literature Review Agent", page_icon="📚", layout="wide")


def main() -> None:
    st.title("Literature Review Agent")
    st.caption("A multi-step research agent built with Gemini function-style orchestration.")

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        st.warning("Set GEMINI_API_KEY in your environment before running the agent.")
        st.stop()

    with st.sidebar:
        st.header("How to use")
        st.write("1. Enter a research question.")
        st.write("2. The app retrieves papers from Semantic Scholar.")
        st.write("3. Python ranks candidates before Gemini analyzes them.")
        st.write("4. Review selected papers, evidence, and the final synthesis.")
        candidate_limit = st.slider("Candidate papers to retrieve", min_value=10, max_value=30, value=20, step=5)
        keep_top_n = st.slider("Top papers to keep", min_value=5, max_value=10, value=8, step=1)

    question = st.text_input(
        "Research question",
        placeholder="Example: How are transformers being used for time-series forecasting, and what limitations are most common?",
    )

    run = st.button("Run agent", type="primary", use_container_width=True)

    if not run:
        return

    if not question.strip():
        st.error("Please provide a research question.")
        return

    agent = LiteratureReviewAgent(api_key=api_key)

    try:
        with st.spinner("Retrieving papers and running the literature review agent..."):
            result = agent.run(question=question, candidate_limit=candidate_limit, keep_top_n=keep_top_n)
    except Exception as exc:
        st.error(f"Run failed: {exc}")
        return

    selected_tab, evidence_tab, review_tab, trace_tab = st.tabs(
        ["Selected papers", "Extracted evidence", "Final review", "Trace"]
    )

    with selected_tab:
        st.subheader("Selected papers")
        for paper in result.selected_papers:
            authors = ", ".join(paper.authors[:4]) if paper.authors else "Unknown authors"
            with st.container(border=True):
                st.markdown(f"**#{paper.rank} {paper.title}**")
                st.caption(
                    f"{paper.source} | {authors} | {paper.venue or 'Unknown venue'} | "
                    f"{paper.year or 'Year unavailable'} | {paper.citation_count} citations"
                )
                if paper.url:
                    st.markdown(f"[Semantic Scholar page]({paper.url})")
                st.write(f"Ranking reason: {paper.ranking_reason}")
                if paper.abstract:
                    st.write(paper.abstract)

    with evidence_tab:
        st.subheader("Extracted evidence")
        for index, paper_record in enumerate(result.extracted_evidence, start=1):
            with st.expander(f"Paper {index}: {paper_record.get('title', 'Untitled')}", expanded=False):
                st.json(paper_record)

    with review_tab:
        st.subheader("Final review")
        st.markdown(result.final_review)

        st.subheader("Key gaps")
        for gap in result.gaps:
            st.write(f"- {gap}")

        st.subheader("Conflicts")
        if result.conflicts:
            for conflict in result.conflicts:
                st.write(f"- {conflict}")
        else:
            st.write("No major conflicts detected.")

    with trace_tab:
        st.subheader("Run trace")
        for step in result.trace:
            with st.expander(f"{step['stage']}: {step['title']}", expanded=False):
                st.json(step["payload"])


if __name__ == "__main__":
    main()
