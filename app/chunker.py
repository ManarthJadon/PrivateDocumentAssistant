from dataclasses import dataclass

# How big each chunk is, and how much neighbouring chunks share.
# The quality check scored 20/20 with 500, 1000 and 1500; 1000 keeps more
# context per excerpt for questions that need more than one sentence.
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150

# Where we prefer to cut, best first: paragraph, sentence, word.
SEPARATORS = ("\n\n", ". ", " ")


@dataclass
class Chunk:
    page: int | None  # page number for PDFs, None for .docx / .txt / .md
    text: str


def split_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    chunks = []
    start = 0

    while start < len(text):
        # 1. Take at most `size` characters.
        end = min(start + size, len(text))

        # 2. If this isn't the end of the text, move the cut back to a nice
        #    place: the last paragraph break, sentence end or space in the
        #    second half of the piece. No such place (one huge word): hard cut.
        if end < len(text):
            for sep in SEPARATORS:
                cut = text.rfind(sep, start + size // 2, end)
                if cut != -1:
                    end = cut + len(sep)
                    break

        # 3. Keep the piece unless it's only whitespace.
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)

        if end >= len(text):
            break

        # 4. Start the next chunk about `overlap` characters earlier, at the
        #    beginning of a word. Always move forward, so the loop can't get stuck.
        space = text.find(" ", end - overlap, end)
        next_start = space + 1 if space != -1 else end
        start = max(next_start, start + 1)

    return chunks


def chunk_pages(
    pages: list[tuple[int | None, str]], size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP
) -> list[Chunk]:
    # Split every page on its own, so a chunk never mixes two pages.
    return [
        Chunk(page, piece)
        for page, text in pages
        for piece in split_text(text, size, overlap)
    ]