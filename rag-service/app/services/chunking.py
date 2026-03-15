from __future__ import annotations


def build_chunks(
    source_type: str,
    content: str,
    metadata: dict[str, object],
    *,
    min_tokens: int = 4,
    max_tokens: int = 600,
) -> list[dict[str, object]]:
    if source_type == "pdf" and metadata.get("chunks"):
        raw_chunks = _pdf_chunks(content, metadata)
    else:
        raw_chunks = _text_chunks(content, page_number=1 if source_type == "pdf" else None)

    return _filter_and_split(raw_chunks, min_tokens=min_tokens, max_tokens=max_tokens)


def _pdf_chunks(content: str, metadata: dict[str, object]) -> list[dict[str, object]]:
    pages = [segment.strip() for segment in content.split("\n") if segment.strip()]
    chunk_rows: list[dict[str, object]] = []
    for chunk in metadata["chunks"]:
        page_start = int(chunk["page_start"])
        page_end = int(chunk["page_end"])
        segment = "\n".join(pages[page_start - 1:page_end]).strip() or content
        chunk_rows.append(
            {
                "content": segment,
                "page_number": chunk.get("page_number", page_start),
                "bbox": chunk.get("bbox"),
            }
        )
    return chunk_rows


def _text_chunks(content: str, *, page_number: int | None) -> list[dict[str, object]]:
    paragraphs = [segment.strip() for segment in content.split("\n\n") if segment.strip()]
    if not paragraphs and content.strip():
        paragraphs = [content.strip()]
    return [{"content": paragraph, "page_number": page_number} for paragraph in paragraphs]


def _filter_and_split(
    raw_chunks: list[dict[str, object]],
    *,
    min_tokens: int,
    max_tokens: int,
) -> list[dict[str, object]]:
    chunks: list[dict[str, object]] = []
    seen_contents: set[str] = set()
    fallback_chunk: dict[str, object] | None = None

    for raw_chunk in raw_chunks:
        original = str(raw_chunk["content"]).strip()
        normalized = " ".join(original.split()).strip()
        if not normalized:
            continue
        if normalized in seen_contents:
            continue
        seen_contents.add(normalized)
        if fallback_chunk is None:
            fallback_chunk = {
                "content": original,
                "page_number": raw_chunk.get("page_number"),
            }
            if raw_chunk.get("bbox") is not None:
                fallback_chunk["bbox"] = raw_chunk["bbox"]

        tokens = normalized.split()
        if len(tokens) <= max_tokens and len(tokens) >= min_tokens:
            chunk = {
                "content": original,
                "page_number": raw_chunk.get("page_number"),
            }
            if raw_chunk.get("bbox") is not None:
                chunk["bbox"] = raw_chunk["bbox"]
            chunks.append(chunk)
            continue

        for start in range(0, len(tokens), max_tokens):
            part_tokens = tokens[start : start + max_tokens]
            if len(part_tokens) < min_tokens:
                continue
            chunk = {
                "content": " ".join(part_tokens),
                "page_number": raw_chunk.get("page_number"),
            }
            if raw_chunk.get("bbox") is not None:
                chunk["bbox"] = raw_chunk["bbox"]
            chunks.append(chunk)

    if not chunks and fallback_chunk is not None:
        return [fallback_chunk]

    return chunks
