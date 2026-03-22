from app.services.sparse_encoder import encode_sparse_text


def test_encode_sparse_text_returns_deterministic_sorted_sparse_vector():
    result = encode_sparse_text("Revenue revenue growth in Q1")

    assert result == encode_sparse_text("Revenue revenue growth in Q1")
    assert result["indices"] == sorted(result["indices"])
    assert len(result["indices"]) == len(result["values"]) == 3
    assert max(result["values"]) == 2.0


def test_encode_sparse_text_skips_stopwords_and_empty_tokens():
    assert encode_sparse_text("the and with") == {"indices": [], "values": []}
    assert encode_sparse_text("") == {"indices": [], "values": []}
