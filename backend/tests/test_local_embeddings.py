from app.retrieval.embed import VECTOR_SIZE, embed_single_query, embed_texts


def test_local_embeddings_are_deterministic_and_fixed_width():
    first = embed_texts(["cash transaction monitoring"])[0]
    second = embed_texts(["cash transaction monitoring"])[0]

    assert len(first) == VECTOR_SIZE
    assert first == second
    assert any(value != 0 for value in first)


def test_empty_query_has_a_safe_zero_vector():
    vector = embed_single_query("   ")

    assert len(vector) == VECTOR_SIZE
    assert set(vector) == {0.0}
