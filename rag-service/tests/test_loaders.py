import io

import pytest

from app.services import loaders as loaders_module


@pytest.mark.asyncio
async def test_load_web_source_extracts_clean_title_and_body(monkeypatch):
    html = """
    <html>
      <head><title>Example Article</title></head>
      <body>
        <nav>Navigation</nav>
        <main><h1>Heading</h1><p>Hello world.</p></main>
        <footer>Footer links</footer>
      </body>
    </html>
    """

    class FakeResponse:
        text = html

        def raise_for_status(self):
            return None

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, source_ref):
            return FakeResponse()

    monkeypatch.setattr(loaders_module.httpx, "AsyncClient", lambda **kwargs: FakeClient())

    result = await loaders_module.load_web_source("https://example.com/article")

    assert result["metadata"]["title"] == "Example Article"
    assert result["metadata"]["loader_strategy"] == "static_html_fallback"
    assert "Hello world." in result["content"]
    assert "Navigation" not in result["content"]
    assert "Footer links" not in result["content"]


@pytest.mark.asyncio
async def test_load_web_source_prefers_crawl4ai_rendered_html(monkeypatch):
    html = """
    <html>
      <head><title>Rendered Article</title></head>
      <body>
        <nav>Navigation</nav>
        <main><h1>Heading</h1><p>Rendered body.</p></main>
        <footer>Footer links</footer>
      </body>
    </html>
    """

    async def fake_render(source_ref):
        assert source_ref == "https://example.com/article"
        return {
            "html": html,
            "final_url": "https://example.com/rendered",
        }

    class FakeResponse:
        text = ""
        headers = {"content-type": "text/html"}

        def raise_for_status(self):
            return None

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, source_ref):
            raise AssertionError(f"httpx fallback should not run for {source_ref}")

    monkeypatch.setattr(loaders_module, "_render_web_with_crawl4ai", fake_render, raising=False)
    monkeypatch.setattr(loaders_module.httpx, "AsyncClient", lambda **kwargs: FakeClient())

    result = await loaders_module.load_web_source("https://example.com/article")

    assert result["metadata"]["title"] == "Rendered Article"
    assert result["metadata"]["loader_strategy"] == "crawl4ai_rendered"
    assert result["metadata"]["url"] == "https://example.com/rendered"
    assert "Rendered body." in result["content"]
    assert "Navigation" not in result["content"]
    assert "Footer links" not in result["content"]


@pytest.mark.asyncio
async def test_load_web_source_falls_back_to_static_html_when_crawl4ai_fails(monkeypatch):
    html = """
    <html>
      <head><title>Fallback Article</title></head>
      <body>
        <nav>Navigation</nav>
        <main><p>Static body.</p></main>
        <footer>Footer links</footer>
      </body>
    </html>
    """

    async def fake_render(source_ref):
        raise RuntimeError(f"crawl failed for {source_ref}")

    class FakeResponse:
        text = html
        headers = {"content-type": "text/html"}

        def raise_for_status(self):
            return None

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, source_ref):
            return FakeResponse()

    monkeypatch.setattr(loaders_module, "_render_web_with_crawl4ai", fake_render, raising=False)
    monkeypatch.setattr(loaders_module.httpx, "AsyncClient", lambda **kwargs: FakeClient())

    result = await loaders_module.load_web_source("https://example.com/article")

    assert result["metadata"]["title"] == "Fallback Article"
    assert result["metadata"]["loader_strategy"] == "static_html_fallback"
    assert result["metadata"]["url"] == "https://example.com/article"
    assert "Static body." in result["content"]
    assert "Navigation" not in result["content"]
    assert "Footer links" not in result["content"]


@pytest.mark.asyncio
async def test_load_web_source_formats_json_payload_into_natural_language(monkeypatch):
    payload = {
        "customer": "Acme",
        "plan": "growth",
        "active": True,
    }

    class FakeResponse:
        headers = {"content-type": "application/json"}

        def json(self):
            return payload

        def raise_for_status(self):
            return None

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, source_ref):
            return FakeResponse()

    monkeypatch.setattr(loaders_module.httpx, "AsyncClient", lambda **kwargs: FakeClient())

    result = await loaders_module.load_web_source("https://example.com/api/customer")

    assert result["metadata"]["title"] == "Structured web content"
    assert "customer is Acme" in result["content"]
    assert "plan is growth" in result["content"]
    assert "active is true" in result["content"]


@pytest.mark.asyncio
async def test_load_db_source_formats_sql_rows_into_natural_language(monkeypatch):
    class FakeResult:
        def mappings(self):
            return self

        def all(self):
            return [
                {"customer": "Acme", "plan": "growth"},
                {"customer": "Beta", "plan": "starter"},
            ]

    class FakeConnection:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def execute(self, statement):
            assert "SELECT customer, plan FROM accounts" in str(statement)
            return FakeResult()

    class FakeEngine:
        def connect(self):
            return FakeConnection()

    monkeypatch.setattr(loaders_module, "engine", FakeEngine())

    result = await loaders_module.load_db_source("SELECT customer, plan FROM accounts")

    assert result["metadata"]["title"] == "SQL Query Result"
    assert result["metadata"]["row_count"] == 2
    assert result["metadata"]["query"] == "SELECT customer, plan FROM accounts"
    assert "Row 1" in result["content"]
    assert "customer is Acme" in result["content"]
    assert "plan is starter" in result["content"]


@pytest.mark.asyncio
async def test_load_structured_source_formats_records_and_scope_metadata(monkeypatch):
    async def fake_semantic_formatter(records, *, title):
        assert title == "CRM Customer Snapshot"
        assert records == [
            {
                "customer_id": 42,
                "company_name": "Acme Mobilya",
                "stage": "negotiation",
            }
        ]
        return {
            "text": "Acme Mobilya musterisinin asamasi negotiation durumunda.",
            "model": "gemini-test",
            "mode": "llm_semantic",
        }

    monkeypatch.setattr(
        loaders_module,
        "format_structured_data_semantically",
        fake_semantic_formatter,
        raising=False,
    )

    result = await loaders_module.load_structured_source(
        title="CRM Customer Snapshot",
        records=[
            {
                "customer_id": 42,
                "company_name": "Acme Mobilya",
                "stage": "negotiation",
            }
        ],
        scope_type="customer",
        scope_id="cust_42",
        entity_type="customer",
        origin="crm",
        entity_id="cust_42",
        record_ids=["opp_91", "note_18"],
        snapshot_date="2026-03-15",
        tags=["crm", "daily-sync"],
    )

    assert result["metadata"] == {
        "title": "CRM Customer Snapshot",
        "record_count": 1,
        "formatter_model": "gemini-test",
        "formatter_mode": "llm_semantic",
        "scope_type": "customer",
        "scope_id": "cust_42",
        "entity_type": "customer",
        "origin": "crm",
        "entity_id": "cust_42",
        "record_ids": ["opp_91", "note_18"],
        "snapshot_date": "2026-03-15",
        "tags": ["crm", "daily-sync"],
    }
    assert result["content"] == "Acme Mobilya musterisinin asamasi negotiation durumunda."
    assert result["chunk_count"] == 1


@pytest.mark.asyncio
async def test_load_image_source_fetches_url_and_detects_png_metadata(monkeypatch):
    png_bytes = b"\x89PNG\r\n\x1a\nfakepng"

    class FakeResponse:
        content = png_bytes

        def raise_for_status(self):
            return None

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, source_ref):
            assert source_ref == "https://example.com/avatar.png"
            return FakeResponse()

    monkeypatch.setattr(loaders_module.httpx, "AsyncClient", lambda **kwargs: FakeClient())

    result = await loaders_module.load_image_source("https://example.com/avatar.png")

    assert result["content"] == "avatar.png"
    assert result["metadata"] == {
        "title": "avatar.png",
        "loader_strategy": "gemini_direct_image",
        "mime_type": "image/png",
        "binary_size_bytes": len(png_bytes),
        "modality": "image",
        "url": "https://example.com/avatar.png",
    }
    assert result["image_bytes"] == png_bytes
    assert result["chunk_count"] == 1


@pytest.mark.asyncio
async def test_load_image_source_decodes_base64_jpeg(monkeypatch):
    jpeg_bytes = b"\xff\xd8\xff\xe0fakejpeg"

    result = await loaders_module.load_image_source(
        None,
        source_bytes=jpeg_bytes,
        source_filename="photo.jpg",
    )

    assert result["content"] == "photo.jpg"
    assert result["metadata"] == {
        "title": "photo.jpg",
        "loader_strategy": "gemini_direct_image",
        "mime_type": "image/jpeg",
        "binary_size_bytes": len(jpeg_bytes),
        "modality": "image",
        "url": "photo.jpg",
    }
    assert result["image_bytes"] == jpeg_bytes
    assert result["chunk_count"] == 1


@pytest.mark.asyncio
async def test_load_audio_source_short_file_returns_single_clip(monkeypatch):
    mp3_bytes = b"ID3short-audio"

    class FakeResponse:
        content = mp3_bytes

        def raise_for_status(self):
            return None

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, source_ref):
            assert source_ref == "https://example.com/audio.mp3"
            return FakeResponse()

    monkeypatch.setattr(loaders_module.httpx, "AsyncClient", lambda **kwargs: FakeClient())
    monkeypatch.setattr(loaders_module, "probe_audio_duration_seconds", lambda *args, **kwargs: 95)

    result = await loaders_module.load_audio_source("https://example.com/audio.mp3")

    assert result["content"] == "audio.mp3"
    assert result["metadata"] == {
        "title": "audio.mp3",
        "loader_strategy": "gemini_audio_clipped",
        "mime_type": "audio/mpeg",
        "binary_size_bytes": len(mp3_bytes),
        "modality": "audio",
        "url": "https://example.com/audio.mp3",
        "duration_seconds": 95,
        "clip_count": 1,
        "clips": [{"clip_index": 0, "start_second": 0, "end_second": 95}],
    }
    assert result["audio_bytes"] == mp3_bytes
    assert result["chunk_count"] == 1


@pytest.mark.asyncio
async def test_load_audio_source_long_file_creates_120_second_windows(monkeypatch):
    mp3_bytes = b"ID3long-audio"

    monkeypatch.setattr(loaders_module, "probe_audio_duration_seconds", lambda *args, **kwargs: 255)

    result = await loaders_module.load_audio_source(
        None,
        source_bytes=mp3_bytes,
        source_filename="voice.mp3",
    )

    assert result["metadata"]["mime_type"] == "audio/mpeg"
    assert result["metadata"]["duration_seconds"] == 255
    assert result["metadata"]["clip_count"] == 3
    assert result["metadata"]["clips"] == [
        {"clip_index": 0, "start_second": 0, "end_second": 120},
        {"clip_index": 1, "start_second": 120, "end_second": 240},
        {"clip_index": 2, "start_second": 240, "end_second": 255},
    ]


@pytest.mark.asyncio
async def test_load_pdf_source_uses_direct_strategy_for_small_pdf(monkeypatch):
    class FakeResponse:
        content = b"%PDF-fake"

        def raise_for_status(self):
            return None

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, source_ref):
            return FakeResponse()

    class FakePage:
        def __init__(self, number, text):
            self.number = number
            self._text = text

        def get_text(self, mode):
            assert mode == "text"
            return self._text

    class FakeDocument:
        def __iter__(self):
            return iter([FakePage(0, "Page one"), FakePage(1, "Page two")])

        def __len__(self):
            return 2

        def close(self):
            return None

    async def fake_extract_small_pdf_document(pdf_bytes, title, source_ref):
        assert pdf_bytes == FakeResponse.content
        assert title == "report.pdf"
        assert source_ref == "https://example.com/files/report.pdf"
        return {
            "content": "Gemini extracted text",
            "metadata": {
                "title": "report.pdf",
                "loader_strategy": "gemini_direct_pdf",
                "direct_embed_ready": True,
                "modality": "pdf",
                "url": source_ref,
            },
            "chunk_count": 1,
        }

    monkeypatch.setattr(loaders_module.httpx, "AsyncClient", lambda **kwargs: FakeClient())
    monkeypatch.setattr(loaders_module, "fitz", type("FakeFitz", (), {"open": staticmethod(lambda **kwargs: FakeDocument())}))
    monkeypatch.setattr(loaders_module, "extract_small_pdf_document", fake_extract_small_pdf_document)
    monkeypatch.setattr(
        loaders_module,
        "get_settings",
        lambda: type("FakeSettings", (), {"gemini_api_key": "secret-key"})(),
    )

    result = await loaders_module.load_pdf_source("https://example.com/files/report.pdf")

    assert result["metadata"]["title"] == "report.pdf"
    assert result["metadata"]["page_count"] == 2
    assert result["metadata"]["loader_strategy"] == "gemini_direct_pdf"
    assert result["metadata"]["direct_embed_ready"] is True
    assert result["metadata"]["binary_size_bytes"] == len(FakeResponse.content)
    assert result["metadata"]["modality"] == "pdf"
    assert result["metadata"]["pages"] == [{"page_number": 1}, {"page_number": 2}]
    assert result["chunk_count"] == 1
    assert result["content"] == "Gemini extracted text"


@pytest.mark.asyncio
async def test_load_pdf_source_uses_chunked_strategy_for_large_pdf(monkeypatch):
    class FakeResponse:
        content = b"%PDF-fake"

        def raise_for_status(self):
            return None

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, source_ref):
            return FakeResponse()

    class FakePage:
        def __init__(self, number):
            self.number = number

        def get_text(self, mode):
            if mode == "text":
                return f"Page {self.number + 1}"
            if mode == "blocks":
                return [
                    (0.0, float(self.number), 100.0, float(self.number + 10), f"Page {self.number + 1}", 0, 0),
                ]
            raise AssertionError(mode)

    class FakeDocument:
        def __iter__(self):
            return iter([FakePage(index) for index in range(8)])

        def __len__(self):
            return 8

        def close(self):
            return None

    monkeypatch.setattr(loaders_module.httpx, "AsyncClient", lambda **kwargs: FakeClient())
    monkeypatch.setattr(loaders_module, "fitz", type("FakeFitz", (), {"open": staticmethod(lambda **kwargs: FakeDocument())}))

    result = await loaders_module.load_pdf_source("https://example.com/files/big-report.pdf")

    assert result["metadata"]["title"] == "big-report.pdf"
    assert result["metadata"]["page_count"] == 8
    assert result["metadata"]["loader_strategy"] == "pymupdf_layout_chunked"
    assert result["metadata"]["chunks"] == [
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
    assert result["chunk_count"] == 2
