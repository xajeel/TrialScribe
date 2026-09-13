"""Safe HTTP header helpers for worker downloads."""

from urllib.parse import quote


def attachment_content_disposition(filename: str) -> str:
    """Return a Content-Disposition that stays valid for hostile filenames."""

    sanitized = "".join(
        character
        for character in filename
        if ord(character) >= 32 and ord(character) != 127
    )
    if not sanitized:
        sanitized = "download"
    fallback = "".join(
        character
        if character.isascii()
        and (character.isalnum() or character in "._- ()")
        else "_"
        for character in sanitized
    ).strip()
    if not fallback.strip("._"):
        fallback = "download"
    encoded = quote(sanitized, safe="")
    return f'attachment; filename="{fallback}"; filename*=UTF-8\'\'{encoded}'
