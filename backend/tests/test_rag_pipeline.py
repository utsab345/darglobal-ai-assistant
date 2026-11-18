import numpy as np

from app.rag.simple_embed import embed_texts, embed_query
from app.rag.store import VectorStore
from app.utils.text import chunk_text


def test_chunking_produces_chunks():
    text = 'DarGlobal develops luxury projects. ' * 80
    chunks = chunk_text(text, chunk_size=120, overlap=20)
    assert len(chunks) >= 2
    assert all(len(c) > 0 for c in chunks)


def test_simple_embeddings_shape_and_normalization():
    emb = embed_texts(['DarGlobal luxury villas in Dubai', 'Wasalt apartments in Riyadh'], dim=64)
    assert emb.shape == (2, 64)
    norms = np.linalg.norm(emb, axis=1)
    assert np.all(norms > 0)


def test_vector_store_search_and_filter(tmp_path):
    texts = [
        'DarGlobal project in Dubai with branded residences',
        'Wasalt listing platform for properties in Riyadh',
        'DarGlobal development in Saudi Arabia',
    ]
    emb = embed_texts(texts, dim=64)
    metas = [
        {'chunk_id': '1', 'source': 'dar_global', 'url': 'https://darglobal.co.uk/a', 'title': 'DG', 'content': texts[0], 'snippet': texts[0], 'metadata': {}},
        {'chunk_id': '2', 'source': 'wasalt', 'url': 'https://wasalt.sa/en/b', 'title': 'W', 'content': texts[1], 'snippet': texts[1], 'metadata': {}},
        {'chunk_id': '3', 'source': 'dar_global', 'url': 'https://darglobal.co.uk/c', 'title': 'DG2', 'content': texts[2], 'snippet': texts[2], 'metadata': {}},
    ]
    store = VectorStore(tmp_path)
    store.build(emb, metas, provider='hash', model_name='test')
    assert store.load() is True
    q = embed_query('Riyadh properties on Wasalt', dim=64)
    res = store.search(q, top_k=2, source_filter='wasalt')
    assert len(res) >= 1
    assert all(r['source'] == 'wasalt' for r in res)
