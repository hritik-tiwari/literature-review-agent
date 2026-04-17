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
        st.write("2. Paste notes, abstracts, or excerpts from multiple papers.")
        st.write("3. Run the agent and inspect the trace.")

    question = st.text_input(
        "Research question",
        placeholder="Example: How are transformers being used for time-series forecasting, and what limitations are most common?",
    )
    papers_blob = st.text_area(
        "Paper texts",
        height=280,
        placeholder="Paste one or more paper abstracts or notes here. Separate papers with a line containing only ---",
    )

    run = st.button("Run agent", type="primary", use_container_width=True)

    if not run:
        return

    if not question.strip() or not papers_blob.strip():
        st.error("Please provide both a research question and at least one paper text.")
        return

    agent = LiteratureReviewAgent(api_key=api_key)

    with st.spinner("Running multi-step literature review agent..."):
        result = agent.run(question=question, raw_papers_text=papers_blob)

    left, right = st.columns([1.2, 1])

    with left:
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

    with right:
        st.subheader("Agent trace")
        for step in result.trace:
            with st.expander(f"{step['stage']}: {step['title']}", expanded=False):
                st.json(step["payload"])


if __name__ == "__main__":
    main()

