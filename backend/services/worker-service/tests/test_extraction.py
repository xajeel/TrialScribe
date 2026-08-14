from io import BytesIO
import json

import pytest
from pypdf import PdfReader, PdfWriter

from trialscribe_worker.retrieval.extraction import extract_source
from trialscribe_worker.utils.exceptions import DocumentExtractionError

PDF_MARKER = "FAROHEALTH_PDF_MARKER"

_MINIMAL_PDF = b"""%PDF-1.4
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj
3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200]
/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj
4 0 obj << /Length 55 >> stream
BT /F1 12 Tf 10 100 Td (FAROHEALTH_PDF_MARKER) Tj ET
endstream
endobj
5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj
xref
0 6
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000266 00000 n 
0000000371 00000 n 
trailer << /Size 6 /Root 1 0 R >>
startxref
454
%%EOF
"""


def _pdf_with_marker() -> bytes:
    reader = PdfReader(BytesIO(_MINIMAL_PDF))
    writer = PdfWriter()
    writer.add_page(reader.pages[0])
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def test_utf8_plain_text_normalizes_newlines() -> None:
    extracted = extract_source("research_document", "text/plain", b"hello\r\nworld")

    assert extracted.text == "hello\nworld"
    assert extracted.pages == []


def test_markdown_is_decoded_as_utf8() -> None:
    extracted = extract_source(
        "research_document",
        "text/markdown",
        b"# Heading\n\nbody",
    )

    assert "Heading" in extracted.text
    assert "body" in extracted.text


def test_trial_json_flattens_title_and_inclusion() -> None:
    payload = {
        "titleLong": "A Phase 2 Study",
        "inclusion": "Age 18 years or older",
        "other": "ignored unless no known fields",
    }
    extracted = extract_source(
        "trial_data",
        "application/json",
        json.dumps(payload).encode("utf-8"),
    )

    assert "Title: A Phase 2 Study" in extracted.text
    assert "Inclusion: Age 18 years or older" in extracted.text


def test_unknown_json_object_is_dumped_with_sorted_keys() -> None:
    payload = {"zeta": 1, "alpha": 2}
    extracted = extract_source(
        "trial_data",
        "application/json",
        json.dumps(payload).encode("utf-8"),
    )

    assert extracted.text == json.dumps(payload, sort_keys=True, ensure_ascii=True)


def test_non_object_json_is_an_extraction_error() -> None:
    with pytest.raises(DocumentExtractionError):
        extract_source("trial_data", "application/json", b"[1, 2]")


def test_pdf_writer_page_contains_the_marker() -> None:
    extracted = extract_source("research_document", "application/pdf", _pdf_with_marker())

    assert PDF_MARKER in extracted.text
    assert extracted.pages
    assert extracted.pages[0][0] == 1
