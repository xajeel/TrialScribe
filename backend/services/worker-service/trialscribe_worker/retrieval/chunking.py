"""Split extracted text into overlapping chunks with original character spans."""

from bisect import bisect_right

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


class PageLocator:
    """Answer "which page is this offset on?" without rescanning the document.

    A 500-page file split into a few thousand chunks asks this question once per
    chunk. Walking the page list each time is quadratic in the size of the file;
    building the offset index once makes each answer a binary search.

    Page spans produced by extraction are ordered and never overlap, so the
    index is exact. Anything else falls back to the original scan rather than
    guessing.
    """

    __slots__ = ("_pages", "_starts", "_ordered")

    def __init__(self, pages: list[tuple[int, int, int]]) -> None:
        self._pages = pages
        self._starts = [start for _number, start, _end in pages]
        self._ordered = _is_ordered(pages)

    def page_for(self, start_char: int) -> int | None:
        """Return the 1-based page holding `start_char`, if any."""

        if not self._ordered:
            return _scan_pages(self._pages, start_char)
        index = bisect_right(self._starts, start_char) - 1
        if index < 0:
            return None
        page_number, start, end = self._pages[index]
        if start <= start_char < end or (start == end == start_char):
            return page_number
        return None


def page_for_span(
    pages: list[tuple[int, int, int]],
    start_char: int,
    end_char: int,
) -> int | None:
    """Return the 1-based page that contains `start_char`, if any.

    Kept for single lookups. Use `PageLocator` when locating many spans in the
    same document.
    """

    del end_char
    return _scan_pages(pages, start_char)


def _scan_pages(pages: list[tuple[int, int, int]], start_char: int) -> int | None:
    for page_number, start, end in pages:
        if start <= start_char < end or (start == end == start_char):
            return page_number
    return None


def _is_ordered(pages: list[tuple[int, int, int]]) -> bool:
    """Report whether spans rise strictly and never reach into one another."""

    previous_end = None
    previous_start = None
    for _number, start, end in pages:
        if end < start:
            return False
        if previous_start is not None and start <= previous_start:
            return False
        if previous_end is not None and start < previous_end:
            return False
        previous_start, previous_end = start, end
    return True


def _split_before(text: str, start: int, end: int) -> int:
    window = text[start:end]
    for separator in SEPARATORS:
        if separator == "":
            return end
        index = window.rfind(separator)
        if index > 0:
            return start + index + len(separator)
    return end
