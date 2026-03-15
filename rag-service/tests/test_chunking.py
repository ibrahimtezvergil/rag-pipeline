import pytest

from app.services.chunking import build_chunks


def test_build_chunks_splits_web_content_and_filters_duplicates():
    content = (
        "one two three four five six seven eight nine ten eleven twelve\n\n"
        "one two three four five six seven eight nine ten eleven twelve\n\n"
        "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu"
    )

    chunks = build_chunks("web", content, {"title": "Article"}, min_tokens=4, max_tokens=8)

    assert [chunk["content"] for chunk in chunks] == [
        "one two three four five six seven eight",
        "nine ten eleven twelve",
        "alpha beta gamma delta epsilon zeta eta theta",
        "iota kappa lambda mu",
    ]


def test_build_chunks_uses_pdf_metadata_and_keeps_bbox_page_number():
    content = "\n".join(f"page {index}" for index in range(1, 9))
    metadata = {
        "chunks": [
            {
                "chunk_index": 0,
                "page_start": 1,
                "page_end": 6,
                "page_number": 1,
                "bbox": {"x0": 0.0, "y0": 0.0, "x1": 100.0, "y1": 15.0},
            },
            {
                "chunk_index": 1,
                "page_start": 7,
                "page_end": 8,
                "page_number": 7,
                "bbox": {"x0": 0.0, "y0": 6.0, "x1": 100.0, "y1": 17.0},
            },
        ]
    }

    chunks = build_chunks("pdf", content, metadata, min_tokens=1, max_tokens=20)

    assert chunks == [
        {
            "content": "page 1\npage 2\npage 3\npage 4\npage 5\npage 6",
            "page_number": 1,
            "bbox": {"x0": 0.0, "y0": 0.0, "x1": 100.0, "y1": 15.0},
        },
        {
            "content": "page 7\npage 8",
            "page_number": 7,
            "bbox": {"x0": 0.0, "y0": 6.0, "x1": 100.0, "y1": 17.0},
        },
    ]


def test_build_chunks_drops_short_and_empty_segments():
    content = "tiny\n\n\nuseful words live here for retrieval quality"

    chunks = build_chunks("web", content, {}, min_tokens=3, max_tokens=20)

    assert chunks == [
        {"content": "useful words live here for retrieval quality", "page_number": None}
    ]
