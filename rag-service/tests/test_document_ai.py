import base64

import pytest

from app.services import document_ai as document_ai_module


@pytest.mark.asyncio
async def test_extract_small_pdf_document_calls_generate_content(monkeypatch):
    captured: dict[str, object] = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"text": "Extracted PDF text"}
                            ]
                        }
                    }
                ]
            }

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json=None):
            captured["url"] = url
            captured["json"] = json
            return FakeResponse()

    monkeypatch.setattr(document_ai_module.httpx, "AsyncClient", lambda timeout=30.0: FakeClient())
    monkeypatch.setattr(
        document_ai_module,
        "get_settings",
        lambda: type("FakeSettings", (), {"gemini_api_key": "secret-key"})(),
    )

    pdf_bytes = b"%PDF-test"
    result = await document_ai_module.extract_small_pdf_document(
        pdf_bytes=pdf_bytes,
        title="report.pdf",
        source_ref="https://example.com/report.pdf",
    )

    encoded = base64.b64encode(pdf_bytes).decode("utf-8")
    assert captured["url"] == (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-2.5-flash:generateContent?key=secret-key"
    )
    assert captured["json"] == {
        "contents": [
            {
                "parts": [
                    {
                        "inline_data": {
                            "mime_type": "application/pdf",
                            "data": encoded,
                        }
                    },
                    {
                        "text": (
                            "Extract the readable text from this PDF document. "
                            "Return only the plain text content."
                        )
                    },
                ]
            }
        ]
    }
    assert result == {
        "content": "Extracted PDF text",
        "metadata": {
            "title": "report.pdf",
            "loader_strategy": "gemini_direct_pdf",
            "direct_embed_ready": True,
            "modality": "pdf",
            "url": "https://example.com/report.pdf",
        },
        "chunk_count": 1,
    }
