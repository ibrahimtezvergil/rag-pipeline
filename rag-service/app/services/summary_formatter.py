from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence

import httpx

from app.config import get_settings


def format_structured_data(data: object, *, title: str | None = None) -> str:
    sections: list[str] = []
    if title:
        sections.append(title)

    body = _format_value(data)
    if body:
        sections.append(body)

    return "\n\n".join(sections).strip()


async def format_structured_data_semantically(
    data: object,
    *,
    title: str | None = None,
) -> dict[str, str]:
    settings = get_settings()
    if not settings.gemini_api_key.strip():
        return {
            "text": format_structured_data(data, title=title),
            "model": "rule-based",
            "mode": "rule_based_fallback",
        }

    try:
        result = await _generate_semantic_summary(data=data, title=title)
        result["text"] = _truncate_text(
            result["text"],
            max_chars=getattr(settings, "formatter_output_char_limit", 2000),
        )
        return result
    except Exception:
        return {
            "text": format_structured_data(data, title=title),
            "model": "rule-based",
            "mode": "rule_based_fallback",
        }


def _format_value(value: object) -> str:
    if isinstance(value, Mapping):
        parts = [f"{key} is {_stringify(item)}." for key, item in value.items()]
        return " ".join(parts)

    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        rows: list[str] = []
        for index, item in enumerate(value, start=1):
            row_text = _format_row(item)
            if row_text:
                rows.append(f"Row {index}: {row_text}")
        return "\n".join(rows)

    return _stringify(value)


def _format_row(value: object) -> str:
    if isinstance(value, Mapping):
        return " ".join(f"{key} is {_stringify(item)}." for key, item in value.items())
    return _stringify(value)


def _stringify(value: object) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    if value is None:
        return "null"
    if isinstance(value, Mapping | list):
        return json.dumps(value, ensure_ascii=True, separators=(", ", ": "))
    return str(value)


async def _generate_semantic_summary(data: object, *, title: str | None = None) -> dict[str, str]:
    settings = get_settings()
    url = (
        "https://generativelanguage.googleapis.com/v1beta/"
        f"models/{settings.formatter_model}:generateContent"
    )
    sanitized_data = _sanitize_structured_data(
        data,
        max_chars=getattr(settings, "formatter_input_char_limit", 12000),
    )
    prompt = (
        "Convert the following structured JSON data into a concise, semantic, retrieval-friendly text. "
        "Do not invent facts. Omit null or empty fields. Prefer natural language over raw key repetition. "
        "Keep important entities, states, dates, quantities, and relationships. "
        "Mask emails and phone numbers. Keep output concise and semantically useful for retrieval.\n\n"
        f"Title: {title or 'Structured Record'}\n"
        f"JSON:\n{json.dumps(sanitized_data, ensure_ascii=True, separators=(', ', ': '))}"
    )
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    headers = {
        "x-goog-api-key": settings.gemini_api_key,
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()

    body = response.json()
    text = body["candidates"][0]["content"]["parts"][0]["text"].strip()
    return {
        "text": text,
        "model": settings.formatter_model,
        "mode": "llm_semantic",
    }


def _sanitize_structured_data(value: object, *, max_chars: int) -> object:
    sanitized = _sanitize_value(value)
    serialized = json.dumps(sanitized, ensure_ascii=True, separators=(", ", ": "))
    if len(serialized) <= max_chars:
        return sanitized
    return {
        "_truncated": True,
        "preview": _truncate_text(serialized, max_chars=max_chars),
    }


def _sanitize_value(value: object) -> object:
    if isinstance(value, Mapping):
        cleaned: dict[str, object] = {}
        for key, item in value.items():
            sanitized_item = _sanitize_value(item)
            if sanitized_item in (None, "", [], {}):
                continue
            cleaned[str(key)] = sanitized_item
        return cleaned

    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        cleaned_items = [
            sanitized_item
            for item in value
            if (sanitized_item := _sanitize_value(item)) not in (None, "", [], {})
        ]
        return cleaned_items

    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return ""
        stripped = re.sub(
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
            "[redacted-email]",
            stripped,
        )
        stripped = re.sub(
            r"(?<!\w)(?:\+?\d[\d\s().-]{8,}\d)",
            "[redacted-phone]",
            stripped,
        )
        return stripped

    return value


def _truncate_text(text: str, *, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    if max_chars <= 3:
        return text[:max_chars]
    return text[: max_chars - 3].rstrip() + "..."
