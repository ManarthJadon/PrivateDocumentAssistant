import io
from pathlib import Path

import docx
import pypdf

SUPPORTED_TYPES = {".pdf", ".docx", ".txt", ".md"}


class ReadError(Exception):
    """A problem with the file. Its text is shown to the user as it is."""


def read_document(filename: str, data: bytes) -> list[tuple[int | None, str]]:
    # 1. Decide the file type from the name's ending: "Notes.PDF" -> ".pdf".
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_TYPES:
        raise ReadError("Only .pdf, .docx, .txt and .md files are supported.")

    # 2. Pull the text out. Each result is (page number, text);
    #    only PDFs have pages, everything else gets None.
    try:
        if suffix == ".pdf":
            reader = pypdf.PdfReader(io.BytesIO(data))
            if reader.is_encrypted:
                raise ValueError("locked PDF")
            pages = [
                (number, page.extract_text() or "")
                for number, page in enumerate(reader.pages, start=1)
            ]
        elif suffix == ".docx":
            document = docx.Document(io.BytesIO(data))
            pages = [(None, "\n\n".join(p.text for p in document.paragraphs))]
        else:
            # .txt / .md: "utf-8-sig" also removes the invisible mark Notepad
            # sometimes adds; "replace" turns unreadable bytes into � instead of crashing.
            pages = [(None, data.decode("utf-8-sig", errors="replace"))]
    except Exception as error:
        raise ReadError("Couldn't read this file. It may be damaged or locked.") from error

    # 3. A file with no words at all (e.g. a scanned PDF, which is only pictures).
    if not any(text.strip() for _, text in pages):
        raise ReadError("No text found. Scanned PDFs aren't supported yet.")

    return pages