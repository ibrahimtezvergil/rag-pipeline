from __future__ import annotations

import base64
import re
from html import unescape
from pathlib import Path

import httpx
import fitz
from app.config import get_settings
from app.services.document_ai import extract_small_pdf_document
from app.services.media import detect_image_mime_type, load_binary_source
from app.services.summary_formatter import (
    format_structured_data,
    format_structured_data_semantically,
)


async def load_source(
    source_type: str,
    source_ref: str | None = None,
    *,
    source_bytes: bytes | None = None,
    source_filename: str | None = None,
    source_sql: str | None = None,
    records: list[dict] | None = None,
    title: str | None = None,
    scope_type: str | None = None,
    scope_id: str | None = None,
    entity_type: str | None = None,
    origin: str | None = None,
    entity_id: str | None = None,
    record_ids: list[str] | None = None,
    snapshot_date: str | None = None,
    tags: list[str] | None = None,
) -> dict[str, object]:
    if source_type == "web":
        if source_ref is None:
            raise ValueError("web sources require source_ref")
        return await load_web_source(source_ref)
    if source_type == "pdf":
        return await load_pdf_source(
            source_ref=source_ref,
            source_bytes=source_bytes,
            source_filename=source_filename,
        )
    if source_type == "image":
        return await load_image_source(
            source_ref=source_ref,
            source_bytes=source_bytes,
            source_filename=source_filename,
        )
    if source_type == "db":
        if source_sql is None:
            raise ValueError("db sources require source_sql")
        return await load_db_source(source_sql)
    if source_type == "structured":
        if records is None:
            raise ValueError("structured sources require records")
        return await load_structured_source(
            title=title or "Structured Records",
            records=records,
            scope_type=scope_type,
            scope_id=scope_id,
            entity_type=entity_type,
            origin=origin,
            entity_id=entity_id,
            record_ids=record_ids,
            snapshot_date=snapshot_date,
            tags=tags,
        )
    raise ValueError(f"Unsupported source type: {source_type}")


async def load_web_source(source_ref: str) -> dict[str, object]:
    crawl_error: Exception | None = None
    try:
        rendered = await _render_web_with_crawl4ai(source_ref)
    except Exception as exc:
        crawl_error = exc
    else:
        return _build_web_result(
            html=rendered["html"],
            source_ref=str(rendered.get("final_url") or source_ref),
            loader_strategy="crawl4ai_rendered",
        )

    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        response = await client.get(source_ref)
        response.raise_for_status()

    response_headers = getattr(response, "headers", {})
    content_type = response_headers.get("content-type", "").lower()
    if "application/json" in content_type:
        payload = response.json()
        title = "Structured web content"
        text = format_structured_data(payload, title=title)
        return {
            "content": text,
            "metadata": {
                "title": title,
                "content_length": len(text),
                "url": source_ref,
                "content_type": "application/json",
                "loader_strategy": "static_json_fallback",
                **({"crawl4ai_error": str(crawl_error)} if crawl_error else {}),
            },
            "chunk_count": 1,
        }

    return _build_web_result(
        html=response.text,
        source_ref=source_ref,
        loader_strategy="static_html_fallback",
        crawl_error=crawl_error,
    )


async def load_pdf_source(
    source_ref: str | None = None,
    *,
    source_bytes: bytes | None = None,
    source_filename: str | None = None,
) -> dict[str, object]:
    if source_bytes is None:
        assert source_ref is not None
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            response = await client.get(source_ref)
            response.raise_for_status()
        pdf_bytes = response.content
    else:
        pdf_bytes = source_bytes

    document = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages: list[dict[str, int]] = []
    extracted_pages: list[str] = []
    page_blocks: list[list[tuple[float, float, float, float]]] = []
    for page in document:
        extracted_pages.append(page.get_text("text").strip())
        pages.append({"page_number": page.number + 1})
        blocks = []
        try:
            raw_blocks = page.get_text("blocks")
        except Exception:
            raw_blocks = []
        for block in raw_blocks:
            x0, y0, x1, y1, *_ = block
            blocks.append((float(x0), float(y0), float(x1), float(y1)))
        page_blocks.append(blocks)

    text = "\n".join(filter(None, extracted_pages)).strip()
    title = source_filename or Path(source_ref or "document.pdf").name
    page_count = len(document)
    document.close()
    if page_count <= 6:
        if get_settings().gemini_api_key.strip():
            direct_result = await extract_small_pdf_document(
                pdf_bytes=pdf_bytes,
                title=title,
                source_ref=source_ref or title,
            )
            direct_result["metadata"]["page_count"] = page_count
            direct_result["metadata"]["binary_size_bytes"] = len(pdf_bytes)
            direct_result["metadata"]["pages"] = pages
            return direct_result

        metadata = {
            "title": title,
            "page_count": page_count,
            "loader_strategy": "direct_small_pdf",
            "direct_embed_ready": True,
            "binary_size_bytes": len(pdf_bytes),
            "modality": "pdf",
            "pages": pages,
            "url": source_ref or title,
        }
        chunk_count = 1
    else:
        chunks = []
        for index, start in enumerate(range(0, page_count, 6)):
            end = min(start + 6, page_count)
            bbox = _merge_bboxes(page_blocks[start:end])
            chunks.append(
                {
                    "chunk_index": index,
                    "page_start": start + 1,
                    "page_end": end,
                    "page_number": start + 1,
                    "bbox": bbox,
                }
            )
        metadata = {
            "title": title,
            "page_count": page_count,
            "loader_strategy": "pymupdf_layout_chunked",
            "pages": pages,
            "chunks": chunks,
            "url": source_ref or title,
        }
        chunk_count = len(chunks)
    return {
        "content": text,
        "metadata": metadata,
        "chunk_count": chunk_count,
    }


async def load_image_source(
    source_ref: str | None = None,
    *,
    source_bytes: bytes | None = None,
    source_filename: str | None = None,
) -> dict[str, object]:
    image_bytes = await load_binary_source(source_ref, source_bytes=source_bytes)
    title = source_filename or Path(source_ref or "image").name
    mime_type = detect_image_mime_type(image_bytes, title)
    metadata = {
        "title": title,
        "loader_strategy": "gemini_direct_image",
        "mime_type": mime_type,
        "binary_size_bytes": len(image_bytes),
        "modality": "image",
        "url": source_ref or title,
    }
    return {
        "content": title,
        "metadata": metadata,
        "image_bytes": image_bytes,
        "chunk_count": 1,
    }


async def load_db_source(source_sql: str) -> dict[str, object]:
    # Disabled: this function previously used the internal RAG engine without tenant
    # isolation, allowing cross-tenant data access. Re-implement with an explicit
    # external DB connection string and per-project scoping before re-enabling.
    raise NotImplementedError(
        "DB loader is disabled. Use an external connection string with explicit tenant scoping."
    )


async def load_structured_source(
    *,
    title: str,
    records: list[dict],
    scope_type: str | None = None,
    scope_id: str | None = None,
    entity_type: str | None = None,
    origin: str | None = None,
    entity_id: str | None = None,
    record_ids: list[str] | None = None,
    snapshot_date: str | None = None,
    tags: list[str] | None = None,
) -> dict[str, object]:
    formatted = await format_structured_data_semantically(records, title=title)
    content = formatted["text"]
    metadata = {
        "title": title,
        "record_count": len(records),
        "formatter_model": formatted["model"],
        "formatter_mode": formatted["mode"],
        **({"scope_type": scope_type} if scope_type else {}),
        **({"scope_id": scope_id} if scope_id else {}),
        **({"entity_type": entity_type} if entity_type else {}),
        **({"origin": origin} if origin else {}),
        **({"entity_id": entity_id} if entity_id else {}),
        **({"record_ids": record_ids} if record_ids else {}),
        **({"snapshot_date": snapshot_date} if snapshot_date else {}),
        **({"tags": tags} if tags else {}),
    }
    return {
        "content": content,
        "metadata": metadata,
        "chunk_count": max(1, len(records)),
    }


def decode_base64_source(source_base64: str) -> bytes:
    return base64.b64decode(source_base64.encode("utf-8"), validate=True)


async def _render_web_with_crawl4ai(source_ref: str) -> dict[str, str]:
    try:
        from crawl4ai import AsyncWebCrawler
    except ImportError as exc:
        raise RuntimeError("crawl4ai is not installed") from exc

    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(url=source_ref)

    if getattr(result, "success", True) is False:
        error_message = getattr(result, "error_message", "crawl4ai render failed")
        raise RuntimeError(str(error_message))

    html = (
        getattr(result, "cleaned_html", None)
        or getattr(result, "html", None)
        or getattr(result, "markdown", None)
    )
    if not html:
        raise RuntimeError("crawl4ai returned no content")

    return {
        "html": str(html),
        "final_url": str(getattr(result, "url", source_ref)),
    }


def _build_web_result(
    *,
    html: str,
    source_ref: str,
    loader_strategy: str,
    crawl_error: Exception | None = None,
) -> dict[str, object]:
    title_match = re.search(r"<title>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
    title = unescape(title_match.group(1).strip()) if title_match else source_ref
    text = _strip_html(html)
    return {
        "content": text,
        "metadata": {
            "title": title,
            "content_length": len(text),
            "url": source_ref,
            "loader_strategy": loader_strategy,
            **({"crawl4ai_error": str(crawl_error)} if crawl_error else {}),
        },
        "chunk_count": 1,
    }


def _strip_html(html: str) -> str:
    text = re.sub(r"<script.*?>.*?</script>", " ", html, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<style.*?>.*?</style>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<nav.*?>.*?</nav>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<footer.*?>.*?</footer>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _merge_bboxes(page_blocks: list[list[tuple[float, float, float, float]]]) -> dict[str, float] | None:
    flattened = [block for page in page_blocks for block in page]
    if not flattened:
        return None
    return {
        "x0": min(block[0] for block in flattened),
        "y0": min(block[1] for block in flattened),
        "x1": max(block[2] for block in flattened),
        "y1": max(block[3] for block in flattened),
    }
