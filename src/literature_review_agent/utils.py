from __future__ import annotations


def split_papers(raw_text: str) -> list[str]:
    chunks = [chunk.strip() for chunk in raw_text.split("\n---\n")]
    return [chunk for chunk in chunks if chunk]

