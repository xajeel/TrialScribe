"""Turn stored file bytes into plain text with optional page spans."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import json

from pypdf import PdfReader

from trialscribe_worker.utils.constant import EVIDENCE_SOURCE_TRIAL_DATA
from trialscribe_worker.utils.exceptions import DocumentExtractionError

PAGE_JOINER = "\n\n"
TRIAL_DATA_CONTENT_TYPE = "application/json"
PDF_CONTENT_TYPE = "application/pdf"
PLAIN_TEXT_CONTENT_TYPE = "text/plain"
MARKDOWN_CONTENT_TYPE = "text/markdown"


@dataclass(frozen=True, slots=True)
class ExtractedDocument:
    """Plain text plus optional 1-based page spans in that text."""

    text: str
    pages: list[tuple[int, int, int]]


def extract_source(kind: str, content_type: str, content: bytes) -> ExtractedDocument:
    """Return extractable text for one stored file, or refuse it."""

    if content_type in {PLAIN_TEXT_CONTENT_TYPE, MARKDOWN_CONTENT_TYPE}:
        return _extract_text(content)
    if content_type == PDF_CONTENT_TYPE:
        return _extract_pdf(content)
    if content_type == TRIAL_DATA_CONTENT_TYPE or kind == EVIDENCE_SOURCE_TRIAL_DATA:
        return _extract_trial_json(content)
    raise DocumentExtractionError


def _extract_text(content: bytes) -> ExtractedDocument:
    try:
        text = content.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    except UnicodeDecodeError:
        raise DocumentExtractionError from None
    return ExtractedDocument(text=text, pages=[])


def _extract_pdf(content: bytes) -> ExtractedDocument:
    try:
        reader = PdfReader(BytesIO(content))
    except Exception:
        raise DocumentExtractionError from None
    if reader.is_encrypted:
        raise DocumentExtractionError
    parts: list[str] = []
    pages: list[tuple[int, int, int]] = []
    cursor = 0
    for number, page in enumerate(reader.pages, start=1):
        try:
            piece = page.extract_text() or ""
        except Exception:
            raise DocumentExtractionError from None
        if parts:
            parts.append(PAGE_JOINER)
            cursor += len(PAGE_JOINER)
        start = cursor
        parts.append(piece)
        cursor += len(piece)
        pages.append((number, start, cursor))
    return ExtractedDocument(text="".join(parts), pages=pages)


def _extract_trial_json(content: bytes) -> ExtractedDocument:
    try:
        parsed = json.loads(content)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise DocumentExtractionError from None
    if not isinstance(parsed, dict):
        raise DocumentExtractionError
    flattened = _flatten_trial(parsed)
    if flattened.strip():
        return ExtractedDocument(text=flattened, pages=[])
    dumped = json.dumps(parsed, sort_keys=True, ensure_ascii=True)
    return ExtractedDocument(text=dumped, pages=[])


def _flatten_trial(data: dict[str, object]) -> str:
    lines = [
        _labelled("Title", data.get("titleLong")),
        _labelled("Phase", _nested_name(data.get("phase"))),
        _labelled("Disease area", _nested_name(data.get("diseaseArea"))),
        _labelled("Therapeutic area", _nested_name(data.get("therapeuticArea"))),
        _labelled("Ingredients", _ingredient_names(data.get("interventions"))),
        _labelled("Route", data.get("routeOfAdministration")),
        _labelled("Intervention groups", data.get("interventionGroups")),
        _labelled("Objectives", data.get("objectivesAndEndpoints")),
        _labelled("Epochs", _nested_get(data.get("studyDesign"), "epochs")),
        _labelled("Inclusion", data.get("inclusion")),
        _labelled("Exclusion", data.get("exclusion")),
    ]
    return "".join(line for line in lines if line)


def _nested_name(value: object) -> object:
    if isinstance(value, dict):
        return value.get("name")
    return None


def _nested_get(value: object, key: str) -> object:
    if isinstance(value, dict):
        return value.get(key)
    return None


def _ingredient_names(value: object) -> list[str]:
    names: list[str] = []
    if not isinstance(value, list):
        return names
    for intervention in value:
        if not isinstance(intervention, dict):
            continue
        ingredients = intervention.get("ingredients")
        if not isinstance(ingredients, list):
            continue
        for item in ingredients:
            if not isinstance(item, dict):
                continue
            ingredient = item.get("ingredient")
            name: object = None
            if isinstance(ingredient, dict):
                name = ingredient.get("name")
            elif isinstance(ingredient, str):
                name = ingredient
            if isinstance(name, str) and name:
                names.append(name)
    return names


def _labelled(label: str, value: object) -> str:
    if value is None or value == "" or value == []:
        return ""
    if isinstance(value, list):
        rendered = ", ".join(str(item) for item in value if item not in (None, ""))
        if not rendered:
            return ""
        return f"{label}: {rendered}\n"
    if isinstance(value, (dict, list)):
        return f"{label}: {json.dumps(value, ensure_ascii=True)}\n"
    return f"{label}: {value}\n"
