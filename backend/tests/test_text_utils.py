from app.utils.text import clean_text, chunk_text, make_id, extract_price, extract_emails


def test_clean_text_normalizes_whitespace():
    assert clean_text('  hello\n\n world\t test  ') == 'hello\nworld test'


def test_chunk_text_splits_and_overlaps():
    text = ' '.join([f'word{i}' for i in range(200)])
    chunks = chunk_text(text, chunk_size=120, overlap=20)
    assert len(chunks) > 1
    assert all(chunks)
    assert chunks[0] != chunks[-1]


def test_make_id_stable():
    assert make_id('https://example.com/a') == make_id('https://example.com/a')
    assert make_id('a') != make_id('b')


def test_extract_helpers():
    assert extract_price('Starting from AED 2,500,000 for villas') is not None
    assert 'info@example.com' in extract_emails('Contact info@example.com for details')
