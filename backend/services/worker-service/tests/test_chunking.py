from trialscribe_worker.retrieval.chunking import chunk_text, page_for_span


def test_a_long_run_of_characters_overlaps_and_covers_the_source() -> None:
    text = "a" * 3000
    chunks = chunk_text(text, 1200, 200)

    assert len(chunks) > 1
    starts = [start for start, _end, _chunk in chunks]
    ends = [end for _start, end, _chunk in chunks]
    for index, (start, end, chunk) in enumerate(chunks):
        assert end == start + len(chunk)
        assert 0 <= start < end <= len(text)
        assert chunk == text[start:end]
        if index > 0:
            previous_end = chunks[index - 1][1]
            assert start < previous_end
            assert previous_end - start == 200 or start == chunks[index - 1][0]
    covered = [False] * len(text)
    for start, end, _chunk in chunks:
        for offset in range(start, end):
            covered[offset] = True
    assert all(covered)
    assert starts[0] == 0
    assert ends[-1] == len(text)


def test_page_for_span_returns_the_page_that_contains_the_start() -> None:
    pages = [(1, 0, 10), (2, 12, 20)]

    assert page_for_span(pages, 0, 4) == 1
    assert page_for_span(pages, 12, 15) == 2
    assert page_for_span(pages, 10, 11) is None
