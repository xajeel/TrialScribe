"""Split extracted text into overlapping chunks with original character spans."""

SEPARATORS = ("\n\n", "\n", ". ", " ", "")


def chunk_text(text: str, size: int, overlap: int) -> list[tuple[int, int, str]]:
    """Return `(start_char, end_char, chunk)` spans inside `text`."""

    if size < 1 or overlap >= size:
        raise ValueError
    if not text:
        return []
    chunks: list[tuple[int, int, str]] = []
    start = 0
    length = len(text)
    while start < length:
        end = min(start + size, length)
        if end < length:
            cut = _split_before(text, start, end)
            if cut > start:
                end = cut
        chunk = text[start:end]
        if chunk:
            chunks.append((start, end, chunk))
        if end >= length:
            break
        next_start = end - overlap
        if next_start <= start:
            next_start = end
        start = next_start
    return chunks


def page_for_span(
    pages: list[tuple[int, int, int]],
    start_char: int,
    end_char: int,
) -> int | None:
    """Return the 1-based page that contains `start_char`, if any."""

    del end_char
    for page_number, start, end in pages:
        if start <= start_char < end or (start == end == start_char):
            return page_number
    return None


def _split_before(text: str, start: int, end: int) -> int:
    window = text[start:end]
    for separator in SEPARATORS:
        if separator == "":
            return end
        index = window.rfind(separator)
        if index > 0:
            return start + index + len(separator)
    return end
