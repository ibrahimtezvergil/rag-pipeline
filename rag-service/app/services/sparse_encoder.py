from __future__ import annotations

import hashlib
import re


_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "what",
    "when",
    "where",
    "this",
    "that",
    "rapor",
    "ne",
    "icin",
    "ile",
    "in",
}


def _token_to_index(token: str) -> int:
    digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big")


def encode_sparse_text(text: str) -> dict[str, list[int] | list[float]]:
    counts: dict[int, float] = {}
    for token in re.findall(r"[A-Za-z0-9]+", text.lower()):
        if token in _STOPWORDS:
            continue
        if len(token) < 2 and not any(character.isdigit() for character in token):
            continue
        token_index = _token_to_index(token)
        counts[token_index] = counts.get(token_index, 0.0) + 1.0

    indices = sorted(counts)
    return {
        "indices": indices,
        "values": [counts[index] for index in indices],
    }
