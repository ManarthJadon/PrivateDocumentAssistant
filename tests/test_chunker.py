from app.chunker import Chunk, chunk_pages, split_text


# --- split_text: cutting one long text into pieces ---

def test_empty_text_gives_no_chunks():
    assert split_text("   ") == []


def test_short_text_is_one_chunk():
    assert split_text("Hello world.") == ["Hello world."]


def test_chunks_respect_size():
    chunks = split_text("word " * 1000)
    assert len(chunks) > 1
    assert all(len(c) <= 1000 for c in chunks)


def test_never_cuts_mid_word():
    # Every word is exactly 5 characters (w0000, w0001, ...), so half a word
    # like "w00" can never be mistaken for a real word.
    words = [f"w{i:04d}" for i in range(2000)]
    chunks = split_text(" ".join(words))
    original = set(words)
    for chunk in chunks:
        for word in chunk.split():
            assert word in original


def test_overlap_repeats_text():
    text = " ".join(f"w{i:04d}" for i in range(2000))
    chunks = split_text(text)
    for first, second in zip(chunks, chunks[1:]):
        assert first[-50:].strip() in second


def test_prefers_paragraph_break():
    text = "a " * 350 + "\n\n" + "b " * 350
    chunks = split_text(text)
    assert "b" not in chunks[0]


def test_long_word_is_hard_cut():
    chunks = split_text("x" * 2500)
    assert len(chunks) >= 3
    assert all(len(c) <= 1000 for c in chunks)


# --- chunk_pages: cutting page by page and remembering the page ---

def test_chunk_pages_never_crosses_pages():
    pages = [(1, "apple " * 300), (2, "banana " * 300)]
    chunks = chunk_pages(pages)
    for chunk in chunks:
        if chunk.page == 1:
            assert "banana" not in chunk.text
        else:
            assert "apple" not in chunk.text
    assert {c.page for c in chunks} == {1, 2}


def test_chunk_pages_keeps_none_page():
    assert chunk_pages([(None, "hi there")]) == [Chunk(None, "hi there")]